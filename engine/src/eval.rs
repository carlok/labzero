use crate::board::Board;
use crate::color::Color;
use crate::mov::Move;
use crate::piece::PieceKind;
use crate::square::Square;

const MATERIAL: [i32; 6] = [100, 320, 330, 500, 900, 0];

// Original piece-square tables for labzero (not copied from existing engines).
const PST_PAWN: [i32; 64] = [
    0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, -20, -20, 10, 10, 5, 5, -5, -10, 0, 0, -10, -5, 5, 0, 0, 0,
    20, 20, 0, 0, 0, 5, 5, 10, 25, 25, 10, 5, 5, 10, 10, 20, 30, 30, 20, 10, 10, 50, 50, 50, 50,
    50, 50, 50, 50, 0, 0, 0, 0, 0, 0, 0, 0,
];

const PST_KNIGHT: [i32; 64] = [
    -50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 5, 5, 0, -20, -40, -30, 5, 10, 15, 15, 10,
    5, -30, -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30, -30, 0, 10, 15, 15, 10,
    0, -30, -40, -20, 0, 0, 0, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50,
];

const PST_BISHOP: [i32; 64] = [
    -20, -10, -10, -10, -10, -10, -10, -20, -10, 5, 0, 0, 0, 0, 5, -10, -10, 10, 10, 10, 10, 10,
    10, -10, -10, 0, 10, 10, 10, 10, 0, -10, -10, 5, 10, 10, 10, 10, 5, -10, -10, 0, 5, 10, 10, 5,
    0, -10, -10, 0, 0, 0, 0, 0, 0, -10, -20, -10, -10, -10, -10, -10, -10, -20,
];

const PST_ROOK: [i32; 64] = [
    0, 0, 0, 5, 5, 0, 0, 0, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0,
    0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 5, 10, 10, 10, 10, 10, 5, 0, 0, 0,
    0, 0, 0, 0, 0, 0,
];

const PST_QUEEN: [i32; 64] = [
    -20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 5, 0, 0, 0, 0, -10, -10, 5, 5, 5, 5, 5, 0, -10,
    0, 0, 5, 5, 5, 5, 0, -5, -5, 0, 5, 5, 5, 5, 0, -5, -10, 0, 5, 5, 5, 5, 0, -10, -10, 0, 0, 0, 0,
    0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20,
];

const PST_KING_MG: [i32; 64] = [
    20, 30, 10, 0, 0, 10, 30, 20, 20, 20, 0, 0, 0, 0, 20, 20, -10, -20, -20, -20, -20, -20, -20,
    -10, -20, -30, -30, -40, -40, -30, -30, -20, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40,
    -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50,
    -40, -40, -30,
];

fn pst_for(kind: PieceKind) -> &'static [i32; 64] {
    match kind {
        PieceKind::Pawn => &PST_PAWN,
        PieceKind::Knight => &PST_KNIGHT,
        PieceKind::Bishop => &PST_BISHOP,
        PieceKind::Rook => &PST_ROOK,
        PieceKind::Queen => &PST_QUEEN,
        PieceKind::King => &PST_KING_MG,
    }
}

fn mirror_sq(sq: Square) -> Square {
    Square::new(sq.file(), 7 - sq.rank())
}

pub fn evaluate(board: &Board) -> i32 {
    let mut score = 0i32;
    for sq in 0..64u8 {
        let s = Square(sq);
        if let Some(p) = board.piece_at(s) {
            let sign = if p.color == Color::White { 1 } else { -1 };
            let pst_sq = if p.color == Color::White {
                s
            } else {
                mirror_sq(s)
            };
            score += sign * (MATERIAL[p.kind.index()] + pst_for(p.kind)[pst_sq.index() as usize]);
        }
    }
    if board.stm == Color::White {
        score
    } else {
        -score
    }
}

pub fn score_move(mv: Move) -> i32 {
    let mut s = 0;
    if mv.kind == crate::mov::MoveKind::Capture
        || mv.kind == crate::mov::MoveKind::EnPassant
        || mv.promotion.is_some()
    {
        s += 1000;
    }
    if mv.promotion.is_some() {
        s += 500;
    }
    s
}
