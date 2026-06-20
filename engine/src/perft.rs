use crate::board::Board;
use crate::mov::Move;

pub fn perft(board: &Board, depth: u32) -> u64 {
    if depth == 0 {
        return 1;
    }
    let moves = crate::movegen::generate_legal_moves(board);
    if depth == 1 {
        return moves.len() as u64;
    }
    let mut nodes = 0u64;
    for mv in moves {
        let mut b = board.clone();
        let undo = b.make_move(mv);
        nodes += perft(&b, depth - 1);
        b.unmake_move(undo);
    }
    nodes
}

pub fn divide(board: &Board, depth: u32) -> Vec<(Move, u64)> {
    let moves = crate::movegen::generate_legal_moves(board);
    moves
        .into_iter()
        .map(|mv| {
            let mut b = board.clone();
            let undo = b.make_move(mv);
            let n = perft(&b, depth - 1);
            b.unmake_move(undo);
            (mv, n)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fen::STARTPOS_FEN;

    #[test]
    fn perft_depth_1() {
        let b = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_eq!(perft(&b, 1), 20);
    }

    #[test]
    fn perft_depth_2() {
        let b = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_eq!(perft(&b, 2), 400);
    }

    #[test]
    fn perft_depth_3() {
        let b = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_eq!(perft(&b, 3), 8902);
    }
}
