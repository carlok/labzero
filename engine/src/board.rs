use crate::color::Color;
use crate::make_unmake::Undo;
use crate::mov::Move;
use crate::piece::{Piece, PieceKind};
use crate::square::{
    bb, king_attack_bb, knight_attack_bb, pawn_attack_bb, sliding_attacks, Bitboard, Square,
    BISHOP_DIRS, ROOK_DIRS,
};

#[derive(Clone, Debug)]
pub struct Board {
    pub pieces: [Bitboard; 12],
    pub stm: Color,
    pub castling: u8,
    pub ep_square: Option<Square>,
    pub halfmove: u16,
    pub fullmove: u16,
    pub hash: u64,
    pub history: Vec<Undo>,
    pub rep_keys: Vec<u64>,
}

pub const WHITE_OO: u8 = 1;
pub const WHITE_OOO: u8 = 2;
pub const BLACK_OO: u8 = 4;
pub const BLACK_OOO: u8 = 8;

impl Default for Board {
    fn default() -> Self {
        Self::from_fen(crate::fen::STARTPOS_FEN).expect("startpos")
    }
}

impl Board {
    pub fn occupied(&self) -> Bitboard {
        let mut o = 0u64;
        for b in &self.pieces {
            o |= b;
        }
        o
    }

    pub fn color_bb(&self, color: Color) -> Bitboard {
        let base = color.index() * 6;
        self.pieces[base..base + 6].iter().fold(0u64, |a, &b| a | b)
    }

    pub fn piece_at(&self, sq: Square) -> Option<Piece> {
        for kind in [
            PieceKind::Pawn,
            PieceKind::Knight,
            PieceKind::Bishop,
            PieceKind::Rook,
            PieceKind::Queen,
            PieceKind::King,
        ] {
            for color in [Color::White, Color::Black] {
                let idx = crate::square::piece_index(color, kind);
                if self.pieces[idx] & bb(sq) != 0 {
                    return Some(Piece::new(color, kind));
                }
            }
        }
        None
    }

    pub fn king_square(&self, color: Color) -> Square {
        let idx = crate::square::piece_index(color, PieceKind::King);
        let b = self.pieces[idx];
        Square(b.trailing_zeros() as u8)
    }

    pub fn is_square_attacked(&self, sq: Square, by: Color) -> bool {
        let occ = self.occupied();
        let their_pawns = self.pieces[crate::square::piece_index(by, PieceKind::Pawn)];
        if pawn_attack_bb(sq, by.opposite()) & their_pawns != 0 {
            return true;
        }
        let their_knights = self.pieces[crate::square::piece_index(by, PieceKind::Knight)];
        if knight_attack_bb(sq) & their_knights != 0 {
            return true;
        }
        let their_kings = self.pieces[crate::square::piece_index(by, PieceKind::King)];
        if king_attack_bb(sq) & their_kings != 0 {
            return true;
        }
        let their_bishops = self.pieces[crate::square::piece_index(by, PieceKind::Bishop)];
        let their_queens = self.pieces[crate::square::piece_index(by, PieceKind::Queen)];
        let diag = sliding_attacks(sq, occ, &BISHOP_DIRS);
        if diag & (their_bishops | their_queens) != 0 {
            return true;
        }
        let their_rooks = self.pieces[crate::square::piece_index(by, PieceKind::Rook)];
        let ortho = sliding_attacks(sq, occ, &ROOK_DIRS);
        if ortho & (their_rooks | their_queens) != 0 {
            return true;
        }
        false
    }

    pub fn in_check(&self, color: Color) -> bool {
        let king = self.king_square(color);
        self.is_square_attacked(king, color.opposite())
    }

    pub fn make_move(&mut self, mv: Move) -> Undo {
        crate::make_unmake::make_move(self, mv)
    }

    pub fn unmake_move(&mut self, undo: Undo) {
        crate::make_unmake::unmake_move(self, undo);
    }

    pub fn is_repetition(&self) -> bool {
        let key = self.hash;
        self.rep_keys.iter().filter(|&&k| k == key).count() >= 2
    }

    pub fn is_draw(&self) -> bool {
        self.halfmove >= 100 || self.is_repetition()
    }

    pub fn is_checkmate(&self) -> bool {
        if !self.in_check(self.stm) {
            return false;
        }
        crate::movegen::generate_legal_moves(self).is_empty()
    }

    pub fn is_stalemate(&self) -> bool {
        !self.in_check(self.stm) && crate::movegen::generate_legal_moves(self).is_empty()
    }

    pub fn game_over(&self) -> bool {
        self.is_checkmate() || self.is_stalemate() || self.is_draw()
    }

    pub fn compute_hash(&self) -> u64 {
        let mut h = 0u64;
        for sq in 0..64u8 {
            let s = Square(sq);
            if let Some(p) = self.piece_at(s) {
                h ^= hash_piece(s, p);
            }
        }
        if self.stm == Color::Black {
            h ^= 0xAA55_AA55_AA55_AA55;
        }
        h ^= (self.castling as u64).wrapping_mul(0x1234);
        if let Some(ep) = self.ep_square {
            h ^= (ep.index() as u64 + 1).wrapping_mul(0x5678);
        }
        h
    }

    pub fn push_rep(&mut self) {
        self.rep_keys.push(self.hash);
    }
}

fn hash_piece(sq: Square, piece: Piece) -> u64 {
    let idx = crate::square::piece_index(piece.color, piece.kind) as u64;
    idx.wrapping_mul(7919).wrapping_add(sq.index() as u64 + 1)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fen::STARTPOS_FEN;
    use crate::square::bit_count;

    #[test]
    fn startpos_has_pieces() {
        let b = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_eq!(bit_count(b.occupied()), 32);
    }
}
