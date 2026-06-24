use crate::board::{Board, BLACK_OO, BLACK_OOO, WHITE_OO, WHITE_OOO};
use crate::color::Color;
use crate::mov::{Move, MoveKind};
use crate::piece::{Piece, PieceKind};
use crate::square::{bb, piece_index, Square};
use crate::zobrist;

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

fn castle_rook_squares(mv: Move) -> (Square, Square) {
    if mv.to.file() == 6 {
        (
            Square::new(7, mv.from.rank()),
            Square::new(5, mv.from.rank()),
        )
    } else {
        (
            Square::new(0, mv.from.rank()),
            Square::new(3, mv.from.rank()),
        )
    }
}

fn update_hash_after_move(
    board: &mut Board,
    undo: &Undo,
    stm: Color,
    moving: Piece,
    placed_kind: PieceKind,
    mv: Move,
) {
    let mover_idx = piece_index(moving.color, moving.kind);
    board.hash ^= zobrist::piece_key(mover_idx, mv.from);

    if let Some((cap, sq)) = undo.captured {
        board.hash ^= zobrist::piece_key(piece_index(cap.color, cap.kind), sq);
    }

    let placed_idx = piece_index(stm, placed_kind);
    board.hash ^= zobrist::piece_key(placed_idx, mv.to);

    if mv.kind == MoveKind::Castle {
        let (rook_from, rook_to) = castle_rook_squares(mv);
        let rook_idx = piece_index(stm, PieceKind::Rook);
        board.hash ^= zobrist::piece_key(rook_idx, rook_from);
        board.hash ^= zobrist::piece_key(rook_idx, rook_to);
    }

    board.hash ^= zobrist::castling_key(undo.castling);
    board.hash ^= zobrist::castling_key(board.castling);

    if let Some(ep) = undo.ep_square {
        board.hash ^= zobrist::ep_file_key(ep.file());
    }
    if let Some(ep) = board.ep_square {
        board.hash ^= zobrist::ep_file_key(ep.file());
    }

    board.hash ^= zobrist::side_key();
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
    board.mailbox[mv.from.index() as usize] = None;

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
        board.mailbox[capture_sq.index() as usize] = None;
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
    board.mailbox[mv.to.index() as usize] = Some(Piece::new(moving.color, placed_kind));

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
            let (rook_from, rook_to) = castle_rook_squares(mv);
            let rook_idx = piece_index(moving.color, PieceKind::Rook);
            board.pieces[rook_idx] &= !bb(rook_from);
            board.pieces[rook_idx] |= bb(rook_to);
            board.mailbox[rook_from.index() as usize] = None;
            board.mailbox[rook_to.index() as usize] =
                Some(Piece::new(moving.color, PieceKind::Rook));
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
    update_hash_after_move(board, &undo, stm, moving, placed_kind, mv);
    board.stm = stm.opposite();
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
    board.mailbox[undo.mv.to.index() as usize] = None;
    let from_idx = piece_index(stm, kind);
    board.pieces[from_idx] |= from_bb;
    board.mailbox[undo.mv.from.index() as usize] = Some(Piece::new(stm, kind));

    if let Some((cap, sq)) = undo.captured {
        let cap_idx = piece_index(cap.color, cap.kind);
        board.pieces[cap_idx] |= bb(sq);
        board.mailbox[sq.index() as usize] = Some(cap);
    }

    if undo.mv.kind == MoveKind::Castle {
        let (rook_from, rook_to) = castle_rook_squares(undo.mv);
        let rook_idx = piece_index(stm, PieceKind::Rook);
        board.pieces[rook_idx] &= !bb(rook_to);
        board.pieces[rook_idx] |= bb(rook_from);
        board.mailbox[rook_to.index() as usize] = None;
        board.mailbox[rook_from.index() as usize] = Some(Piece::new(stm, PieceKind::Rook));
    }

    if stm == Color::Black {
        board.fullmove -= 1;
    }
}
