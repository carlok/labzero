use std::cmp::max;

use crate::board::Board;
use crate::eval::{evaluate, score_move};
use crate::mov::Move;
use crate::movegen::generate_legal_moves;
use crate::time::TimeBudget;

pub const MATE_SCORE: i32 = 30_000;

pub struct SearchResult {
    pub best_move: Option<Move>,
    pub score: i32,
    pub nodes: u64,
}

pub fn search(board: &Board, max_depth: u32, budget: &mut TimeBudget) -> SearchResult {
    let mut best = None;
    let mut best_score = i32::MIN;
    let mut nodes = 0u64;
    let mut depth = 1u32;

    while depth <= max_depth && !budget.should_stop() {
        let (mv, sc, n) = search_root(board, depth, budget);
        nodes += n;
        if budget.should_stop() && depth > 1 {
            break;
        }
        if let Some(m) = mv {
            best = Some(m);
            best_score = sc;
        }
        depth += 1;
    }

    SearchResult {
        best_move: best,
        score: best_score,
        nodes,
    }
}

fn search_root(board: &Board, depth: u32, budget: &mut TimeBudget) -> (Option<Move>, i32, u64) {
    let mut moves = generate_legal_moves(board);
    moves.sort_by_key(|&m| std::cmp::Reverse(score_move(m)));

    let mut best = None;
    let mut best_score = i32::MIN;
    let mut nodes = 0u64;
    let mut alpha = i32::MIN + 1;
    let beta = i32::MAX - 1;

    for mv in moves {
        if budget.should_stop() {
            break;
        }
        let mut b = board.clone();
        let undo = b.make_move(mv);
        nodes += 1;
        let score = -negamax(&mut b, depth - 1, -beta, -alpha, budget, &mut nodes);
        b.unmake_move(undo);
        if score > best_score {
            best_score = score;
            best = Some(mv);
        }
        alpha = max(alpha, score);
    }
    (best, best_score, nodes)
}

fn negamax(
    board: &mut Board,
    depth: u32,
    mut alpha: i32,
    beta: i32,
    budget: &mut TimeBudget,
    nodes: &mut u64,
) -> i32 {
    if budget.should_stop() {
        return evaluate(board);
    }
    *nodes += 1;

    if depth == 0 {
        return evaluate(board);
    }

    let moves = generate_legal_moves(board);
    if moves.is_empty() {
        if board.in_check(board.stm) {
            return -MATE_SCORE + (30 - depth as i32);
        }
        return 0;
    }

    let mut sorted: Vec<Move> = moves;
    sorted.sort_by_key(|&m| std::cmp::Reverse(score_move(m)));

    let mut best = i32::MIN + 1;
    for mv in sorted {
        if budget.should_stop() {
            break;
        }
        let undo = board.make_move(mv);
        let score = -negamax(board, depth - 1, -beta, -alpha, budget, nodes);
        board.unmake_move(undo);
        best = max(best, score);
        alpha = max(alpha, score);
        if alpha >= beta {
            break;
        }
    }
    best
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
        let res = search(&board, 2, &mut budget);
        assert!(res.best_move.is_some());
    }
}
