use crate::board::{Board, BLACK_OO, BLACK_OOO, WHITE_OO, WHITE_OOO};
use crate::color::Color;
use crate::mov::{Move, MoveKind};
use crate::piece::{Piece, PieceKind};
use crate::square::{bb, piece_index, Square};

#[derive(Clone, Debug)]
pub struct Undo {
    pub mv: Move,
    pub captured: Option<(Piece, Square)>,
    pub castling: u8,
    pub ep_square: Option<Square>,
    pub halfmove: u16,
    pub hash: u64,
    pub rep_len: usize,
}

pub fn make_move(board: &mut Board, mv: Move) -> Undo {
    let mut undo = Undo {
        mv,
        captured: None,
        castling: board.castling,
        ep_square: board.ep_square,
        halfmove: board.halfmove,
        hash: board.hash,
        rep_len: board.rep_keys.len(),
    };

    board.push_rep();

    let stm = board.stm;
    let moving = board.piece_at(mv.from).expect("moving piece");
    assert_eq!(moving.color, stm);

    let from_bb = bb(mv.from);
    let to_bb = bb(mv.to);
    let from_idx = piece_index(moving.color, moving.kind);
    board.pieces[from_idx] &= !from_bb;

    let capture_sq = if mv.kind == MoveKind::EnPassant {
        let cap_rank = if stm == Color::White {
            mv.to.rank() - 1
        } else {
            mv.to.rank() + 1
        };
        Square::new(mv.to.file(), cap_rank)
    } else {
        mv.to
    };

    if let Some(cap) = board.piece_at(capture_sq) {
        let cap_idx = piece_index(cap.color, cap.kind);
        board.pieces[cap_idx] &= !bb(capture_sq);
        undo.captured = Some((cap, capture_sq));
        board.halfmove = 0;
    } else if moving.kind == PieceKind::Pawn {
        board.halfmove = 0;
    } else {
        board.halfmove += 1;
    }

    let placed_kind = mv.promotion.unwrap_or(moving.kind);
    let placed_idx = piece_index(moving.color, placed_kind);
    board.pieces[placed_idx] |= to_bb;

    board.ep_square = None;
    match mv.kind {
        MoveKind::DoublePush => {
            let ep_rank = if stm == Color::White {
                mv.from.rank() + 1
            } else {
                mv.from.rank() - 1
            };
            board.ep_square = Some(Square::new(mv.from.file(), ep_rank));
        }
        MoveKind::Castle => {
            let (rook_from, rook_to) = if mv.to.file() == 6 {
                (
                    Square::new(7, mv.from.rank()),
                    Square::new(5, mv.from.rank()),
                )
            } else {
                (
                    Square::new(0, mv.from.rank()),
                    Square::new(3, mv.from.rank()),
                )
            };
            let rook_idx = piece_index(moving.color, PieceKind::Rook);
            board.pieces[rook_idx] &= !bb(rook_from);
            board.pieces[rook_idx] |= bb(rook_to);
        }
        _ => {}
    }

    if moving.kind == PieceKind::King {
        board.castling &= match moving.color {
            Color::White => !(WHITE_OO | WHITE_OOO),
            Color::Black => !(BLACK_OO | BLACK_OOO),
        };
    }
    if moving.kind == PieceKind::Rook {
        board.castling &= match (moving.color, mv.from) {
            (Color::White, sq) if sq == Square::new(0, 0) => !WHITE_OOO,
            (Color::White, sq) if sq == Square::new(7, 0) => !WHITE_OO,
            (Color::Black, sq) if sq == Square::new(0, 7) => !BLACK_OOO,
            (Color::Black, sq) if sq == Square::new(7, 7) => !BLACK_OO,
            _ => 0xFF,
        };
    }
    if let Some((cap, sq)) = undo.captured {
        if cap.kind == PieceKind::Rook {
            board.castling &= match (cap.color, sq) {
                (Color::White, sq) if sq == Square::new(0, 0) => !WHITE_OOO,
                (Color::White, sq) if sq == Square::new(7, 0) => !WHITE_OO,
                (Color::Black, sq) if sq == Square::new(0, 7) => !BLACK_OOO,
                (Color::Black, sq) if sq == Square::new(7, 7) => !BLACK_OO,
                _ => 0xFF,
            };
        }
    }

    if stm == Color::Black {
        board.fullmove += 1;
    }
    board.stm = stm.opposite();
    board.hash = board.compute_hash();
    undo
}

pub fn unmake_move(board: &mut Board, undo: Undo) {
    board.stm = board.stm.opposite();
    board.castling = undo.castling;
    board.ep_square = undo.ep_square;
    board.halfmove = undo.halfmove;
    board.hash = undo.hash;
    board.rep_keys.truncate(undo.rep_len);

    let stm = board.stm;
    let moving = board.piece_at(undo.mv.to).expect("piece on to");
    let kind = if undo.mv.promotion.is_some() {
        PieceKind::Pawn
    } else {
        moving.kind
    };

    let to_bb = bb(undo.mv.to);
    let from_bb = bb(undo.mv.from);
    let placed_idx = piece_index(stm, moving.kind);
    board.pieces[placed_idx] &= !to_bb;
    let from_idx = piece_index(stm, kind);
    board.pieces[from_idx] |= from_bb;

    if let Some((cap, sq)) = undo.captured {
        let cap_idx = piece_index(cap.color, cap.kind);
        board.pieces[cap_idx] |= bb(sq);
    }

    if undo.mv.kind == MoveKind::Castle {
        let (rook_from, rook_to) = if undo.mv.to.file() == 6 {
            (
                Square::new(7, undo.mv.from.rank()),
                Square::new(5, undo.mv.from.rank()),
            )
        } else {
            (
                Square::new(0, undo.mv.from.rank()),
                Square::new(3, undo.mv.from.rank()),
            )
        };
        let rook_idx = piece_index(stm, PieceKind::Rook);
        board.pieces[rook_idx] &= !bb(rook_to);
        board.pieces[rook_idx] |= bb(rook_from);
    }

    if stm == Color::Black {
        board.fullmove -= 1;
    }
}
