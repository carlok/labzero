use crate::board::Board;
use crate::color::Color;
use crate::mov::{Move, MoveKind};
use crate::piece::PieceKind;
use crate::square::{bb, knight_attack_bb, sliding_attacks, Square, BISHOP_DIRS, ROOK_DIRS};

const VALUES: [i32; 6] = [100, 320, 330, 500, 900, 0];

/// Static exchange evaluation for capture ordering (approximate swap-off on `mv.to`).
pub fn see_capture_value(board: &Board, mv: Move) -> i32 {
    let target = mv.to;
    let Some(aggressor) = board.piece_at(mv.from) else {
        return 0;
    };

    let gain = if mv.kind == MoveKind::EnPassant {
        VALUES[PieceKind::Pawn.index()]
    } else if let Some(victim) = board.piece_at(target) {
        VALUES[victim.kind.index()]
    } else if mv.promotion.is_some() {
        100
    } else {
        return 0;
    };

    let side = aggressor.color;
    let mut balance = gain - VALUES[aggressor.kind.index()];
    let mut occupied = board.occupied() & !bb(mv.from) & !bb(target);
    if mv.kind != MoveKind::EnPassant {
        occupied |= bb(target);
    }

    let mut attackers = attackers_to(board, target, occupied);
    let mut stm = side.opposite();

    if attackers == 0 {
        return balance;
    }

    while attackers != 0 {
        let piece = least_valuable_attacker(board, target, attackers, stm, occupied);
        let Some((sq, _kind, value)) = piece else {
            break;
        };
        balance = value - balance;
        if balance >= 0 {
            return -balance;
        }
        occupied &= !bb(sq);
        attackers = attackers_to(board, target, occupied);
        stm = stm.opposite();
    }

    -balance
}

fn attackers_to(board: &Board, sq: Square, occupied: u64) -> u64 {
    let mut a = 0u64;
    for color in [Color::White, Color::Black] {
        let idx = |k: PieceKind| crate::square::piece_index(color, k);
        a |= board.pieces[idx(PieceKind::Pawn)] & pawn_attackers(board, sq, color);
        a |= board.pieces[idx(PieceKind::Knight)] & knight_attack_bb(sq);
        a |= board.pieces[idx(PieceKind::King)] & crate::square::king_attack_bb(sq);
        let diag = sliding_attacks(sq, occupied, &BISHOP_DIRS);
        a |= (board.pieces[idx(PieceKind::Bishop)] | board.pieces[idx(PieceKind::Queen)]) & diag;
        let ortho = sliding_attacks(sq, occupied, &ROOK_DIRS);
        a |= (board.pieces[idx(PieceKind::Rook)] | board.pieces[idx(PieceKind::Queen)]) & ortho;
    }
    a & occupied
}

fn pawn_attackers(board: &Board, sq: Square, by: Color) -> u64 {
    let mut m = 0u64;
    let (dr, pawns) = if by == Color::White {
        (
            -1i8,
            board.pieces[crate::square::piece_index(Color::White, PieceKind::Pawn)],
        )
    } else {
        (
            1,
            board.pieces[crate::square::piece_index(Color::Black, PieceKind::Pawn)],
        )
    };
    for df in [-1i8, 1] {
        let f = sq.file() as i8 + df;
        let r = sq.rank() as i8 + dr;
        if (0..8).contains(&f) && (0..8).contains(&r) {
            let from = Square::new(f as u8, r as u8);
            if pawns & bb(from) != 0 {
                m |= bb(from);
            }
        }
    }
    m
}

fn least_valuable_attacker(
    board: &Board,
    _target: Square,
    attackers: u64,
    side: Color,
    occupied: u64,
) -> Option<(Square, PieceKind, i32)> {
    let side_bb = board.color_bb(side) & attackers & occupied;
    if side_bb == 0 {
        return None;
    }
    for kind in [
        PieceKind::Pawn,
        PieceKind::Knight,
        PieceKind::Bishop,
        PieceKind::Rook,
        PieceKind::Queen,
        PieceKind::King,
    ] {
        let b = board.pieces[crate::square::piece_index(side, kind)] & side_bb;
        if b != 0 {
            let sq = Square(b.trailing_zeros() as u8);
            return Some((sq, kind, VALUES[kind.index()]));
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::movegen::generate_legal_moves;
    use crate::square::Square;

    fn capture_to(board: &Board, to: Square) -> Move {
        generate_legal_moves(board)
            .into_iter()
            .find(|m| m.kind == MoveKind::Capture && m.to == to)
            .unwrap_or_else(|| panic!("no capture to {:?}", to))
    }

    #[test]
    fn see_pawn_takes_undefended_queen_positive() {
        let board = Board::from_fen("8/8/8/3q4/4P3/8/8/8 w - - 0 1").unwrap();
        let mv = capture_to(&board, Square::new(3, 4));
        let see = see_capture_value(&board, mv);
        assert!(see > 500, "see={see}");
    }

    #[test]
    fn see_queen_sac_on_defended_pawn_negative() {
        let board = Board::from_fen("r3k3/p7/8/8/Q7/8/8/4K3 w - - 0 1").unwrap();
        let mv = capture_to(&board, Square::new(0, 6));
        let see = see_capture_value(&board, mv);
        assert!(see < -100, "see={see}");
    }

    #[test]
    fn see_equal_pawn_capture_near_neutral() {
        let board = Board::from_fen("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1").unwrap();
        let mv = generate_legal_moves(&board)
            .into_iter()
            .find(|m| m.kind == MoveKind::Capture)
            .expect("pawn capture");
        let see = see_capture_value(&board, mv);
        assert!(see.abs() <= 50, "see={see}");
    }
}
