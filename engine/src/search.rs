use std::cmp::max;

use std::sync::Arc;

use crate::board::Board;
use crate::eval::evaluate;
use crate::mov::{Move, MoveKind};
use crate::movegen::generate_legal_moves;
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
const ASPIRATION_MIN_DEPTH: u32 = 4;

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
    mut info_cb: Option<&mut dyn FnMut(SearchInfo)>,
) -> SearchResult {
    let max_depth = max_depth.min(MAX_DEPTH);
    let mut board = board.clone();
    let mut best = None;
    let mut best_score = 0;
    let mut nodes = 0u64;
    let mut depth = 1u32;
    let mut prev_score = 0i32;
    let mut pv_move = None;
    let mut last_iter_ms = budget.elapsed_ms();

    while depth <= max_depth {
        if depth > 1 && !budget.should_start_depth(last_iter_ms) {
            break;
        }
        if budget.should_stop() && depth > 1 {
            break;
        }

        let (alpha, beta) = if depth >= ASPIRATION_MIN_DEPTH {
            (
                prev_score.saturating_sub(ASPIRATION_DELTA),
                prev_score.saturating_add(ASPIRATION_DELTA),
            )
        } else {
            (i32::MIN + 1, i32::MAX - 1)
        };

        let mut result = search_root(
            &mut board, depth, alpha, beta, budget, state, &mut nodes, pv_move,
        );

        if depth >= ASPIRATION_MIN_DEPTH && (result.1 <= alpha || result.1 >= beta) {
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

        last_iter_ms = budget.elapsed_ms();
        if budget.should_stop() && depth > 1 {
            break;
        }
        if let Some(m) = result.0 {
            best = Some(m);
            best_score = result.1;
            prev_score = result.1;
            pv_move = Some(m);
        }
        depth += 1;
    }

    SearchResult {
        best_move: best,
        score: best_score,
        nodes,
        depth: depth.saturating_sub(1).max(1),
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

#[allow(dead_code)]
fn tt_cutoff(
    tt_score: i32,
    tt_depth: u8,
    flag: TtFlag,
    depth: u32,
    alpha: i32,
    beta: i32,
) -> Option<i32> {
    if (tt_depth as u32) < depth {
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
    if let Some((_tt_score, _tt_depth, _flag, bm)) = ctx.state.tt.probe(key, frame.ply) {
        // TT cutoffs disabled for timed search — bad Exact entries caused blunders
        // (see beta 0-8 vs SF@1320). Use TT for move ordering only.
        tt_move = bm;
    }

    if depth >= 4
        && !in_check
        && board.non_pawn_material(board.stm) >= 2
        && frame.prev_move.from.index() != frame.prev_move.to.index()
    {
        board.null_move();
        let null_depth = depth.saturating_sub(1 + NULL_MOVE_R);
        let null_score = -negamax(
            board,
            null_depth,
            -beta,
            -beta + 1,
            ctx,
            frame.child(Move::quiet(frame.prev_move.from, frame.prev_move.from)),
        );
        board.unnull_move();
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
    );

    let mut best = i32::MIN + 1;
    let mut best_move = None;
    let mut flag = TtFlag::Upper;

    let move_count = sorted.len();
    let mut searched = 0usize;

    for (move_idx, mv) in sorted.into_iter().enumerate() {
        if ctx.budget.should_stop() {
            break;
        }
        searched += 1;
        let undo = board.make_move(mv);
        let gives_check = board.in_check(board.stm);
        let mut score;
        let reduction: u32 =
            if move_idx >= LMR_FULL && depth >= 3 && !in_check && !gives_check && !is_noisy(mv) {
                (1 + move_idx / 8) as u32
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
                ctx.state.history[side][fi][ti] += (depth * depth) as i32;
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
        .store(key, depth as u8, flag, best, best_move, frame.ply);
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

    let in_check = board.in_check(board.stm);
    let moves = generate_legal_moves(board);
    if moves.is_empty() {
        if in_check {
            return -MATE_SCORE + frame.ply as i32;
        }
        return 0;
    }

    let ply = frame.ply;
    let mut sorted: Vec<Move> = moves
        .into_iter()
        .filter(|&m| is_noisy(m) || (in_check && qs_depth == 0))
        .collect();
    order_moves(
        board,
        &mut sorted,
        None,
        ctx.state.killers[ply],
        &ctx.state.history,
        board.stm,
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

fn order_moves(
    board: &Board,
    moves: &mut [Move],
    tt_move: Option<Move>,
    killers: [Option<Move>; 2],
    history: &[[[i32; 64]; 64]; 2],
    stm: crate::color::Color,
) {
    let side = stm.index();
    moves.sort_by(|a, b| {
        move_order_key(board, *a, tt_move, killers, history, side)
            .cmp(&move_order_key(board, *b, tt_move, killers, history, side))
            .reverse()
    });
}

fn move_order_key(
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
    use crate::fen::STARTPOS_FEN;
    use crate::time::TimeControl;

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
}
