use std::cmp::max;

use std::sync::Arc;

use crate::board::Board;
use crate::eval::search_eval as evaluate;
use crate::mov::{Move, MoveKind};
use crate::movegen::generate_legal_moves;
use crate::policy;
use crate::see::see_capture_value;
use crate::time::TimeBudget;
use crate::tt::{TranspositionTable, TtFlag};

pub const MATE_SCORE: i32 = 30_000;
pub const MAX_DEPTH: u32 = 64;
pub const MAX_PLY: usize = 128;
const QSEARCH_MAX: u32 = 6;
const NULL_MOVE_R: u32 = 2;
const LMR_FULL: usize = 4;
const ASPIRATION_DELTA: i32 = 50;
const ASPIRATION_MIN_DEPTH: u32 = 5;
const HISTORY_MAX: i32 = 16_384;

fn history_bonus(depth: u32) -> i32 {
    ((depth * depth) as i32 * 16).min(2_048)
}

fn update_history(entry: &mut i32, bonus: i32) {
    let delta = bonus - *entry * bonus.abs() / HISTORY_MAX;
    *entry = (*entry + delta).clamp(-HISTORY_MAX, HISTORY_MAX);
}

struct SearchCtx<'a> {
    budget: &'a mut TimeBudget,
    state: &'a mut SearchState,
    nodes: &'a mut u64,
}

#[derive(Clone, Debug)]
pub struct SearchInfo {
    pub depth: u32,
    pub score: i32,
    pub nodes: u64,
    pub time_ms: u64,
}

#[derive(Copy, Clone)]
struct Frame {
    ply: usize,
    prev_move: Move,
}

impl Frame {
    fn child(self, mv: Move) -> Self {
        Self {
            ply: self.ply + 1,
            prev_move: mv,
        }
    }
}

pub struct SearchResult {
    pub best_move: Option<Move>,
    pub score: i32,
    pub nodes: u64,
    pub depth: u32,
}

pub struct SearchState {
    pub tt: Arc<TranspositionTable>,
    killers: [[Option<Move>; 2]; MAX_PLY],
    history: [[[i32; 64]; 64]; 2],
}

impl SearchState {
    pub fn new() -> Self {
        Self::with_tt(Arc::new(TranspositionTable::new(1 << 20)))
    }

    pub fn with_tt(tt: Arc<TranspositionTable>) -> Self {
        Self {
            tt,
            killers: [[None; 2]; MAX_PLY],
            history: [[[0; 64]; 64]; 2],
        }
    }

    pub fn set_hash_mb(&mut self, mb: usize) {
        let entries = mb * 1024 * 1024 / 24;
        self.tt = Arc::new(TranspositionTable::new(entries.max(1024)));
    }

    pub fn clear(&mut self) {
        self.tt.clear();
        self.killers = [[None; 2]; MAX_PLY];
        self.history = [[[0; 64]; 64]; 2];
    }
}

impl Default for SearchState {
    fn default() -> Self {
        Self::new()
    }
}

pub fn search(
    board: &Board,
    max_depth: u32,
    budget: &mut TimeBudget,
    state: &mut SearchState,
) -> SearchResult {
    search_with_info(board, max_depth, budget, state, None)
}

pub fn search_with_info(
    board: &Board,
    max_depth: u32,
    budget: &mut TimeBudget,
    state: &mut SearchState,
    info_cb: Option<&mut dyn FnMut(SearchInfo)>,
) -> SearchResult {
    search_with_info_from_depth(board, max_depth, 1, budget, state, info_cb)
}

pub fn search_with_info_from_depth(
    board: &Board,
    max_depth: u32,
    start_depth: u32,
    budget: &mut TimeBudget,
    state: &mut SearchState,
    mut info_cb: Option<&mut dyn FnMut(SearchInfo)>,
) -> SearchResult {
    let cap = max_depth.min(MAX_DEPTH);
    let start = start_depth.clamp(1, MAX_DEPTH);
    if start > cap {
        return SearchResult {
            best_move: None,
            score: 0,
            nodes: 0,
            depth: 0,
        };
    }
    let mut board = board.clone();
    let mut best = None;
    let mut best_score = 0;
    let mut nodes = 0u64;
    let mut depth = start;
    let mut prev_score = 0i32;
    let mut pv_move = None;
    let mut last_iter_ms = budget.elapsed_ms();
    let mut completed_depth = 0u32;
    let mut have_prior_score = false;

    while depth <= cap {
        if depth > start && !budget.should_start_depth(last_iter_ms) {
            break;
        }
        if budget.should_stop() && depth > start {
            break;
        }

        let (alpha, beta) = if depth >= ASPIRATION_MIN_DEPTH && have_prior_score {
            (
                prev_score.saturating_sub(ASPIRATION_DELTA),
                prev_score.saturating_add(ASPIRATION_DELTA),
            )
        } else {
            (i32::MIN + 1, i32::MAX - 1)
        };

        let iter_start_ms = budget.elapsed_ms();

        let mut result = search_root(
            &mut board, depth, alpha, beta, budget, state, &mut nodes, pv_move,
        );

        if have_prior_score
            && depth >= ASPIRATION_MIN_DEPTH
            && (result.1 <= alpha || result.1 >= beta)
        {
            result = search_root(
                &mut board,
                depth,
                i32::MIN + 1,
                i32::MAX - 1,
                budget,
                state,
                &mut nodes,
                pv_move,
            );
        }

        if let Some(ref mut cb) = info_cb {
            cb(SearchInfo {
                depth,
                score: result.1,
                nodes,
                time_ms: budget.elapsed_ms(),
            });
        }

        last_iter_ms = budget.elapsed_ms().saturating_sub(iter_start_ms).max(1);
        if budget.should_stop() && depth > start {
            break;
        }
        if let Some(m) = result.0 {
            best = Some(m);
            best_score = result.1;
            prev_score = result.1;
            pv_move = Some(m);
            completed_depth = depth;
            have_prior_score = true;
        }
        depth += 1;
    }

    let reported_depth = if completed_depth > 0 {
        completed_depth
    } else if best.is_some() {
        1
    } else {
        0
    };

    SearchResult {
        best_move: best,
        score: best_score,
        nodes,
        depth: reported_depth,
    }
}

#[allow(clippy::too_many_arguments)]
fn search_root(
    board: &mut Board,
    depth: u32,
    mut alpha: i32,
    beta: i32,
    budget: &mut TimeBudget,
    state: &mut SearchState,
    nodes: &mut u64,
    pv_move: Option<Move>,
) -> (Option<Move>, i32) {
    let mut moves = generate_legal_moves(board);
    order_moves(
        board,
        &mut moves,
        pv_move,
        state.killers[1],
        &state.history,
        board.stm,
        depth,
    );

    let mut best = None;
    let mut best_score = i32::MIN + 1;

    for mv in moves {
        if budget.should_stop() {
            break;
        }
        let undo = board.make_move(mv);
        let score = -negamax(
            board,
            depth - 1,
            -beta,
            -alpha,
            &mut SearchCtx {
                budget,
                state,
                nodes,
            },
            Frame {
                ply: 2,
                prev_move: mv,
            },
        );
        board.unmake_move(undo);
        if score > best_score {
            best_score = score;
            best = Some(mv);
        }
        alpha = max(alpha, score);
    }

    (best, best_score)
}

fn tt_cutoff(
    tt_score: i32,
    tt_depth: u8,
    flag: TtFlag,
    depth: u32,
    alpha: i32,
    beta: i32,
    complete: bool,
) -> Option<i32> {
    if !complete || (tt_depth as u32) < depth {
        return None;
    }
    if tt_score.abs() > MATE_SCORE - 1000 {
        return None;
    }
    match flag {
        TtFlag::Exact => Some(tt_score),
        TtFlag::Lower if tt_score >= beta => Some(tt_score),
        TtFlag::Upper if tt_score <= alpha => Some(tt_score),
        _ => None,
    }
}

fn negamax(
    board: &mut Board,
    depth: u32,
    mut alpha: i32,
    beta: i32,
    ctx: &mut SearchCtx<'_>,
    frame: Frame,
) -> i32 {
    if ctx.budget.should_stop() {
        return evaluate(board);
    }
    *ctx.nodes += 1;

    if frame.ply >= MAX_PLY - 1 {
        return evaluate(board);
    }

    let in_check = board.in_check(board.stm);
    let mut depth = depth;
    if in_check {
        depth += 1;
    }

    let key = board.hash;
    let mut tt_move = None;
    if let Some((tt_score, tt_depth, flag, bm, complete)) = ctx.state.tt.probe(key, frame.ply) {
        // Re-enabled for timed search post-Zobrist (prior 1+0 regression was pre-real-hash).
        // Safeguards: complete node, sufficient depth, mate exclusion; partial nodes skip store.
        if let Some(score) = tt_cutoff(tt_score, tt_depth, flag, depth, alpha, beta, complete) {
            return score;
        }
        tt_move = bm;
    }

    if depth >= 4
        && !in_check
        && board.non_pawn_material(board.stm) >= 2
        && frame.prev_move.from.index() != frame.prev_move.to.index()
    {
        let null_undo = board.null_move();
        let null_depth = depth.saturating_sub(1 + NULL_MOVE_R);
        let null_score = -negamax(
            board,
            null_depth,
            -beta,
            -beta + 1,
            ctx,
            frame.child(Move::quiet(frame.prev_move.from, frame.prev_move.from)),
        );
        board.unnull_move(null_undo);
        if null_score >= beta {
            return beta;
        }
    }

    if depth == 0 {
        return qsearch(board, alpha, beta, ctx, frame, 0);
    }

    let moves = generate_legal_moves(board);
    if moves.is_empty() {
        if in_check {
            return -MATE_SCORE + frame.ply as i32;
        }
        return 0;
    }

    let ply = frame.ply;
    let mut sorted = moves;
    order_moves(
        board,
        &mut sorted,
        tt_move,
        ctx.state.killers[ply],
        &ctx.state.history,
        board.stm,
        depth,
    );

    let mut best = i32::MIN + 1;
    let mut best_move = None;
    let mut flag = TtFlag::Upper;

    let move_count = sorted.len();
    let mut searched = 0usize;

    for (move_idx, &mv) in sorted.iter().enumerate() {
        if ctx.budget.should_stop() {
            break;
        }
        searched += 1;
        let undo = board.make_move(mv);
        let gives_check = board.in_check(board.stm);
        let mut score;
        let reduction: u32 =
            if move_idx >= LMR_FULL && depth >= 3 && !in_check && !gives_check && !is_noisy(mv) {
                (1 + move_idx / 10) as u32
            } else {
                0
            };
        let search_depth = depth.saturating_sub(1).saturating_sub(reduction);
        let child = frame.child(mv);

        if reduction > 0 {
            score = -negamax(board, search_depth, -alpha - 1, -alpha, ctx, child);
            if score > alpha {
                score = -negamax(board, depth - 1, -beta, -alpha, ctx, child);
            }
        } else {
            score = -negamax(board, depth - 1, -beta, -alpha, ctx, child);
        }
        board.unmake_move(undo);

        if score > best {
            best = score;
            best_move = Some(mv);
        }
        if score > alpha {
            alpha = score;
            flag = TtFlag::Exact;
        }
        if alpha >= beta {
            if !is_noisy(mv) {
                ctx.state.killers[ply][1] = ctx.state.killers[ply][0];
                ctx.state.killers[ply][0] = Some(mv);
                let side = board.stm.index();
                let fi = mv.from.index() as usize;
                let ti = mv.to.index() as usize;
                let bonus = history_bonus(depth);
                update_history(&mut ctx.state.history[side][fi][ti], bonus);
                for &prior in sorted.iter().take(move_idx) {
                    if !is_noisy(prior) {
                        let pfi = prior.from.index() as usize;
                        let pti = prior.to.index() as usize;
                        update_history(&mut ctx.state.history[side][pfi][pti], -bonus);
                    }
                }
            }
            flag = TtFlag::Lower;
            break;
        }
    }

    if best_move.is_none() || best <= i32::MIN + 100 {
        return best;
    }

    // Do not store Exact from a time-cut node; poisons TT ordering and future cutoffs.
    if searched < move_count && flag == TtFlag::Exact {
        flag = TtFlag::Upper;
    }
    if searched < move_count {
        return best;
    }

    ctx.state
        .tt
        .store(key, depth as u8, flag, best, best_move, frame.ply, true);
    best
}

fn qsearch(
    board: &mut Board,
    mut alpha: i32,
    beta: i32,
    ctx: &mut SearchCtx<'_>,
    frame: Frame,
    qs_depth: u32,
) -> i32 {
    if ctx.budget.should_stop() || frame.ply >= MAX_PLY - 1 {
        return evaluate(board);
    }
    *ctx.nodes += 1;

    let in_check = board.in_check(board.stm);

    if !in_check {
        let stand_pat = evaluate(board);
        if stand_pat >= beta {
            return beta;
        }
        if stand_pat > alpha {
            alpha = stand_pat;
        }
        if qs_depth >= QSEARCH_MAX {
            return alpha;
        }
    } else if qs_depth >= QSEARCH_MAX {
        return evaluate(board);
    }

    let moves = generate_legal_moves(board);
    if moves.is_empty() {
        if in_check {
            return -MATE_SCORE + frame.ply as i32;
        }
        return 0;
    }

    let ply = frame.ply;
    let mut sorted: Vec<Move> = if in_check {
        moves
    } else {
        moves.into_iter().filter(|&m| is_noisy(m)).collect()
    };
    order_moves(
        board,
        &mut sorted,
        None,
        ctx.state.killers[ply],
        &ctx.state.history,
        board.stm,
        0,
    );

    for mv in sorted {
        if ctx.budget.should_stop() {
            break;
        }
        let undo = board.make_move(mv);
        let score = -qsearch(board, -beta, -alpha, ctx, frame.child(mv), qs_depth + 1);
        board.unmake_move(undo);
        if score >= beta {
            return beta;
        }
        if score > alpha {
            alpha = score;
        }
    }
    alpha
}

fn is_noisy(mv: Move) -> bool {
    matches!(
        mv.kind,
        MoveKind::Capture | MoveKind::EnPassant | MoveKind::Promotion
    )
}

fn is_policy_eligible(mv: Move, tt_move: Option<Move>, killers: [Option<Move>; 2]) -> bool {
    !is_noisy(mv) && tt_move != Some(mv) && killers[0] != Some(mv) && killers[1] != Some(mv)
}

fn order_moves(
    board: &Board,
    moves: &mut [Move],
    tt_move: Option<Move>,
    killers: [Option<Move>; 2],
    history: &[[[i32; 64]; 64]; 2],
    stm: crate::color::Color,
    depth: u32,
) {
    let side = stm.index();
    let policy_logits = if depth >= 4 {
        policy::quiet_scores(board, moves)
    } else {
        None
    };
    let policy_bonus = policy_logits
        .as_ref()
        .map(|logits| rank_normalize_policy_bonuses(moves, logits, tt_move, killers));

    let mut decorated: Vec<(i64, Move)> = moves
        .iter()
        .enumerate()
        .map(|(i, &mv)| {
            let bonus = policy_bonus
                .as_ref()
                .and_then(|bonuses| bonuses[i])
                .filter(|_| is_policy_eligible(mv, tt_move, killers));
            let key = move_order_key(board, mv, tt_move, killers, history, side, bonus);
            (key, mv)
        })
        .collect();
    decorated.sort_by_key(|item| std::cmp::Reverse(item.0));
    for (i, (_, mv)) in decorated.into_iter().enumerate() {
        moves[i] = mv;
    }
}

fn rank_normalize_policy_bonuses(
    moves: &[Move],
    logits: &[i32],
    tt_move: Option<Move>,
    killers: [Option<Move>; 2],
) -> Vec<Option<i64>> {
    let mut quiet: Vec<(usize, i32)> = moves
        .iter()
        .enumerate()
        .filter(|(_, mv)| is_policy_eligible(**mv, tt_move, killers))
        .map(|(i, _)| (i, logits[i]))
        .collect();
    quiet.sort_by_key(|item| std::cmp::Reverse(item.1));

    let mut out = vec![None; moves.len()];
    let n = quiet.len();
    if n == 0 {
        return out;
    }
    if n == 1 {
        out[quiet[0].0] = Some(99_999);
        return out;
    }
    for (rank, (idx, _)) in quiet.iter().enumerate() {
        let bonus = ((n - 1 - rank) as i64 * 99_999) / (n - 1) as i64;
        out[*idx] = Some(bonus);
    }
    out
}

fn move_order_key(
    board: &Board,
    mv: Move,
    tt_move: Option<Move>,
    killers: [Option<Move>; 2],
    history: &[[[i32; 64]; 64]; 2],
    side: usize,
    policy_bonus: Option<i64>,
) -> i64 {
    let key = base_move_order_key(board, mv, tt_move, killers, history, side);
    if let Some(bonus) = policy_bonus.filter(|_| is_policy_eligible(mv, tt_move, killers)) {
        700_000 + bonus
    } else {
        key
    }
}

fn base_move_order_key(
    board: &Board,
    mv: Move,
    tt_move: Option<Move>,
    killers: [Option<Move>; 2],
    history: &[[[i32; 64]; 64]; 2],
    side: usize,
) -> i64 {
    if tt_move == Some(mv) {
        return i64::MAX;
    }
    if is_noisy(mv) {
        let mut key = 1_000_000 + see_capture_value(board, mv) as i64;
        if mv.promotion.is_some() {
            key += 50_000;
        }
        return key;
    }
    if killers[0] == Some(mv) {
        return 900_000;
    }
    if killers[1] == Some(mv) {
        return 800_000;
    }
    history[side][mv.from.index() as usize][mv.to.index() as usize] as i64
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::color::Color;
    use crate::fen::STARTPOS_FEN;
    use crate::square::Square;
    use crate::time::TimeControl;

    #[test]
    fn history_positive_gravity_saturates() {
        let mut entry = 0;
        for _ in 0..50 {
            update_history(&mut entry, 2_048);
        }
        assert!(entry <= HISTORY_MAX);
        assert!(entry > 0);
        let before = entry;
        update_history(&mut entry, 2_048);
        assert!(entry - before < 2_048);
    }

    #[test]
    fn history_negative_gravity_saturates() {
        let mut entry = 0;
        for _ in 0..50 {
            update_history(&mut entry, -2_048);
        }
        assert!(entry >= -HISTORY_MAX);
        assert!(entry < 0);
        let before = entry;
        update_history(&mut entry, -2_048);
        assert!(before - entry < 2_048);
    }

    #[test]
    fn history_ordering_prefers_positive_over_negative() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        let good = Move::quiet(Square::new(4, 1), Square::new(4, 3));
        let bad = Move::quiet(Square::new(3, 1), Square::new(3, 3));
        let side = Color::White.index();
        let mut history = [[[0; 64]; 64]; 2];
        update_history(
            &mut history[side][good.from.index() as usize][good.to.index() as usize],
            2_048,
        );
        update_history(
            &mut history[side][bad.from.index() as usize][bad.to.index() as usize],
            -2_048,
        );
        let mut moves = [bad, good];
        order_moves(
            &board,
            &mut moves,
            None,
            [None; 2],
            &history,
            Color::White,
            0,
        );
        assert_eq!(moves[0], good);
        assert_eq!(moves[1], bad);
    }

    #[test]
    fn policy_bonus_skips_tt_and_killer_quiets() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        let tt_mv = Move::quiet(Square::new(4, 1), Square::new(4, 3));
        let killer0 = Move::quiet(Square::new(3, 1), Square::new(3, 3));
        let policy_mv = Move::quiet(Square::new(6, 0), Square::new(5, 2));
        let killers = [Some(killer0), None];
        let history = [[[0; 64]; 64]; 2];
        let side = Color::White.index();

        let moves = [tt_mv, killer0, policy_mv];
        let logits = [-10_000, -10_000, 10_000];
        let bonuses = rank_normalize_policy_bonuses(&moves, &logits, Some(tt_mv), killers);

        assert_eq!(bonuses[0], None, "TT quiet must not get policy bonus");
        assert_eq!(bonuses[1], None, "killer quiet must not get policy bonus");
        assert_eq!(bonuses[2], Some(99_999));

        let tt_key = move_order_key(
            &board,
            tt_mv,
            Some(tt_mv),
            killers,
            &history,
            side,
            bonuses[0],
        );
        let killer_key = move_order_key(
            &board,
            killer0,
            Some(tt_mv),
            killers,
            &history,
            side,
            bonuses[1],
        );
        let policy_key = move_order_key(
            &board,
            policy_mv,
            Some(tt_mv),
            killers,
            &history,
            side,
            bonuses[2],
        );

        assert_eq!(tt_key, i64::MAX);
        assert_eq!(killer_key, 900_000);
        assert_eq!(policy_key, 700_000 + 99_999);

        let mut ordered = moves;
        let mut decorated: Vec<(i64, Move)> = ordered
            .iter()
            .enumerate()
            .map(|(i, &mv)| {
                (
                    move_order_key(&board, mv, Some(tt_mv), killers, &history, side, bonuses[i]),
                    mv,
                )
            })
            .collect();
        decorated.sort_by_key(|item| std::cmp::Reverse(item.0));
        for (i, (_, mv)) in decorated.into_iter().enumerate() {
            ordered[i] = mv;
        }
        assert_eq!(ordered[0], tt_mv);
        assert_eq!(ordered[1], killer0);
        assert_eq!(ordered[2], policy_mv);
    }

    #[test]
    fn finds_a_legal_move() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        let mut budget = TimeBudget::new(
            &TimeControl {
                depth: Some(2),
                ..Default::default()
            },
            true,
        );
        let mut state = SearchState::new();
        let res = search(&board, 2, &mut budget, &mut state);
        assert!(res.best_move.is_some());
    }

    #[test]
    fn qsearch_in_check_searches_quiet_evasions() {
        let mut board = Board::from_fen("4r3/8/8/8/8/8/8/4K3 w - - 0 1").unwrap();
        let mut budget = TimeBudget::new(&TimeControl::default(), true);
        let mut state = SearchState::new();
        let mut nodes = 0u64;
        let mut ctx = SearchCtx {
            budget: &mut budget,
            state: &mut state,
            nodes: &mut nodes,
        };
        let frame = Frame {
            ply: 0,
            prev_move: Move::quiet(Square::new(4, 0), Square::new(4, 0)),
        };
        let _ = qsearch(&mut board, i32::MIN + 1, i32::MAX - 1, &mut ctx, frame, 1);
        assert!(
            nodes > 1,
            "expected quiet king evasions to be searched, nodes={nodes}"
        );
    }

    #[test]
    fn qsearch_finds_winning_capture() {
        let board = Board::from_fen("4k3/8/8/3n4/8/8/4R3/4K3 w K - 0 1").unwrap();
        let mut budget = TimeBudget::new(
            &TimeControl {
                depth: Some(4),
                ..Default::default()
            },
            true,
        );
        let mut state = SearchState::new();
        let res = search(&board, 4, &mut budget, &mut state);
        assert!(res.score >= 150, "score was {}", res.score);
    }

    #[test]
    fn tt_repeat_search_same_score() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        let tc = TimeControl {
            depth: Some(3),
            ..Default::default()
        };
        let mut budget = TimeBudget::new(&tc, true);
        let mut state = SearchState::new();
        let r1 = search(&board, 3, &mut budget, &mut state);
        let mut budget2 = TimeBudget::new(&tc, true);
        let r2 = search(&board, 3, &mut budget2, &mut state);
        assert_eq!(r1.score, r2.score);
    }

    #[test]
    fn tt_exact_cutoff_matches_full_search() {
        let board = Board::from_fen("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1").unwrap();
        let tc = TimeControl {
            depth: Some(6),
            ..Default::default()
        };
        let mut state = SearchState::new();
        let mut budget = TimeBudget::new(&tc, true);
        let with_tt = search(&board, 6, &mut budget, &mut state);
        state.clear();
        let mut budget2 = TimeBudget::new(&tc, true);
        let fresh = search(&board, 6, &mut budget2, &mut state);
        assert!(
            (with_tt.score - fresh.score).abs() <= 50,
            "tt cutoff drift: {} vs {}",
            with_tt.score,
            fresh.score
        );
    }

    #[test]
    fn aspiration_search_finds_move() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        let mut budget = TimeBudget::new(
            &TimeControl {
                depth: Some(8),
                ..Default::default()
            },
            true,
        );
        let mut state = SearchState::new();
        let res = search(&board, 8, &mut budget, &mut state);
        assert!(res.best_move.is_some());
        assert!(res.depth >= 4);
    }

    #[test]
    fn tactical_avoids_back_rank_blunder() {
        let board = Board::from_fen("6k1/7q/8/8/8/8/5PPP/4K2R w K - 0 1").unwrap();
        let mut budget = TimeBudget::new(
            &TimeControl {
                depth: Some(6),
                ..Default::default()
            },
            true,
        );
        let mut state = SearchState::new();
        let res = search(&board, 6, &mut budget, &mut state);
        assert!(res.score > -200, "score was {}", res.score);
        let mv = res.best_move.expect("move");
        assert_ne!(mv.to_uci(), "h1h2", "should not hang rook to queen");
    }

    #[test]
    fn tactical_mate_in_one() {
        let board = Board::from_fen("7k/5Q2/6K1/8/8/8/8/8 w - - 0 1").unwrap();
        let mut budget = TimeBudget::new(
            &TimeControl {
                depth: Some(4),
                ..Default::default()
            },
            true,
        );
        let mut state = SearchState::new();
        let res = search(&board, 4, &mut budget, &mut state);
        assert!(res.score > MATE_SCORE - 500, "score was {}", res.score);
    }

    #[test]
    fn tactical_king_activity() {
        let board = Board::from_fen("8/8/2K5/8/8/8/8/k7 w - - 0 1").unwrap();
        let mut budget = TimeBudget::new(
            &TimeControl {
                depth: Some(8),
                ..Default::default()
            },
            true,
        );
        let mut state = SearchState::new();
        let res = search(&board, 8, &mut budget, &mut state);
        assert!(res.best_move.is_some());
        assert!(res.score >= 0, "king should not lose in drawn KvK endgame");
    }

    #[test]
    fn from_depth_three_finds_legal_move() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        let mut budget = TimeBudget::new(
            &TimeControl {
                depth: Some(8),
                ..Default::default()
            },
            true,
        );
        let mut state = SearchState::new();
        let res = search_with_info_from_depth(&board, 8, 3, &mut budget, &mut state, None);
        assert!(res.best_move.is_some());
        assert!(res.depth >= 3);
    }

    #[test]
    fn from_depth_clamps_above_max() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        let mut budget = TimeBudget::new(
            &TimeControl {
                depth: Some(2),
                ..Default::default()
            },
            true,
        );
        let mut state = SearchState::new();
        let res = search_with_info_from_depth(&board, 2, 5, &mut budget, &mut state, None);
        assert!(res.best_move.is_none());
        assert_eq!(res.depth, 0);
        assert_eq!(res.nodes, 0);
    }

    #[test]
    fn from_depth_one_matches_wrapper() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        let tc = TimeControl {
            depth: Some(4),
            ..Default::default()
        };
        let mut budget1 = TimeBudget::new(&tc, true);
        let mut state1 = SearchState::new();
        let via_wrapper = search_with_info(&board, 4, &mut budget1, &mut state1, None);

        let mut budget2 = TimeBudget::new(&tc, true);
        let mut state2 = SearchState::new();
        let via_from_depth =
            search_with_info_from_depth(&board, 4, 1, &mut budget2, &mut state2, None);

        assert_eq!(via_wrapper.best_move, via_from_depth.best_move);
        assert_eq!(via_wrapper.score, via_from_depth.score);
        assert_eq!(via_wrapper.depth, via_from_depth.depth);
    }
}
