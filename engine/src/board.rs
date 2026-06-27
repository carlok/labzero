use crate::color::Color;
use crate::make_unmake::Undo;
use crate::mov::Move;
use crate::piece::{Piece, PieceKind};
use crate::square::{
    king_attack_bb, knight_attack_bb, pawn_attack_bb, piece_index, Bitboard, Square,
};
use crate::zobrist;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct NullUndo {
    pub ep_square: Option<Square>,
}

#[derive(Clone, Debug)]
pub struct Board {
    pub pieces: [Bitboard; 12],
    /// Square -> piece redundant index, kept in sync with `pieces` for O(1)
    /// `piece_at`. Maintained incrementally by make/unmake.
    pub mailbox: [Option<Piece>; 64],
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

    #[inline(always)]
    pub fn piece_at(&self, sq: Square) -> Option<Piece> {
        self.mailbox[sq.index() as usize]
    }

    /// Rebuild the mailbox from the piece bitboards (used at construction).
    pub fn sync_mailbox(&mut self) {
        self.mailbox = [None; 64];
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
                let mut b = self.pieces[idx];
                while b != 0 {
                    let s = b.trailing_zeros() as usize;
                    self.mailbox[s] = Some(Piece::new(color, kind));
                    b &= b - 1;
                }
            }
        }
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
        let diag = crate::magic::bishop_attacks(sq, occ);
        if diag & (their_bishops | their_queens) != 0 {
            return true;
        }
        let their_rooks = self.pieces[crate::square::piece_index(by, PieceKind::Rook)];
        let ortho = crate::magic::rook_attacks(sq, occ);
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
        self.repetition_count_current() >= 2
    }

    pub fn repetition_count_current(&self) -> usize {
        let key = self.hash;
        self.rep_keys.iter().filter(|&&k| k == key).count()
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
                h ^= zobrist::piece_key(piece_index(p.color, p.kind), s);
            }
        }
        if self.stm == Color::Black {
            h ^= zobrist::side_key();
        }
        h ^= zobrist::castling_key(self.castling);
        if let Some(ep) = self.ep_square {
            h ^= zobrist::ep_file_key(ep.file());
        }
        h
    }

    pub fn push_rep(&mut self) {
        self.rep_keys.push(self.hash);
    }

    pub fn null_move(&mut self) -> NullUndo {
        let undo = NullUndo {
            ep_square: self.ep_square,
        };
        if let Some(ep) = self.ep_square {
            self.hash ^= zobrist::ep_file_key(ep.file());
            self.ep_square = None;
        }
        self.stm = self.stm.opposite();
        self.hash ^= zobrist::side_key();
        undo
    }

    pub fn unnull_move(&mut self, undo: NullUndo) {
        self.stm = self.stm.opposite();
        self.hash ^= zobrist::side_key();
        if let Some(ep) = undo.ep_square {
            self.ep_square = Some(ep);
            self.hash ^= zobrist::ep_file_key(ep.file());
        }
    }

    pub fn non_pawn_material(&self, color: Color) -> u32 {
        use crate::square::bit_count;
        let base = color.index() * 6;
        bit_count(self.pieces[base + PieceKind::Knight.index()])
            + bit_count(self.pieces[base + PieceKind::Bishop.index()])
            + bit_count(self.pieces[base + PieceKind::Rook.index()])
            + bit_count(self.pieces[base + PieceKind::Queen.index()])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fen::STARTPOS_FEN;
    use crate::mov::MoveKind;
    use crate::movegen::generate_legal_moves;
    use crate::square::bit_count;

    fn assert_hash_oracle(board: &Board) {
        assert_eq!(
            board.hash,
            board.compute_hash(),
            "hash oracle mismatch stm={:?} castling={} ep={:?}",
            board.stm,
            board.castling,
            board.ep_square
        );
    }

    #[test]
    fn startpos_has_pieces() {
        let b = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_eq!(bit_count(b.occupied()), 32);
    }

    #[test]
    fn startpos_hash_matches_oracle() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_hash_oracle(&board);
    }

    #[test]
    fn make_unmake_restores_hash() {
        let mut board = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_hash_oracle(&board);
        for _ in 0..12 {
            let moves = generate_legal_moves(&board);
            let Some(mv) = moves.first().copied() else {
                break;
            };
            let before = board.hash;
            let undo = board.make_move(mv);
            assert_hash_oracle(&board);
            board.unmake_move(undo);
            assert_hash_oracle(&board);
            assert_eq!(board.hash, before);
        }
    }

    #[test]
    fn castling_hash_consistent() {
        let mut board =
            Board::from_fen("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
                .unwrap();
        assert_hash_oracle(&board);
        let e1g1 = generate_legal_moves(&board)
            .into_iter()
            .find(|m| m.kind == MoveKind::Castle && m.to == Square::new(6, 0))
            .expect("white O-O");
        let undo = board.make_move(e1g1);
        assert_hash_oracle(&board);
        board.unmake_move(undo);
        assert_hash_oracle(&board);
    }

    #[test]
    fn en_passant_hash_consistent() {
        let ep_setup =
            Board::from_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1").unwrap();
        assert_hash_oracle(&ep_setup);
        let mut board = ep_setup;
        let black_push = generate_legal_moves(&board)
            .into_iter()
            .find(|m| m.kind == MoveKind::DoublePush)
            .expect("black double push");
        let undo = board.make_move(black_push);
        assert_hash_oracle(&board);
        board.unmake_move(undo);
        assert_hash_oracle(&board);
    }

    #[test]
    fn promotion_hash_consistent() {
        let mut board = Board::from_fen("8/4P3/8/8/8/8/8/4K2k w - - 0 1").unwrap();
        assert_hash_oracle(&board);
        let promo = generate_legal_moves(&board)
            .into_iter()
            .find(|m| m.promotion == Some(PieceKind::Queen))
            .expect("queen promotion");
        let undo = board.make_move(promo);
        assert_hash_oracle(&board);
        board.unmake_move(undo);
        assert_hash_oracle(&board);
    }

    #[test]
    fn null_move_clears_ep_square() {
        let board =
            Board::from_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1").unwrap();
        assert!(board.ep_square.is_some());
        let mut board = board;
        let _ = board.null_move();
        assert!(board.ep_square.is_none());
        assert_hash_oracle(&board);
    }

    #[test]
    fn null_unnull_restores_ep_and_hash() {
        let board =
            Board::from_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1").unwrap();
        assert_hash_oracle(&board);
        let stm_before = board.stm;
        let ep_before = board.ep_square;
        let hash_before = board.hash;
        let mut board = board;
        let undo = board.null_move();
        assert_hash_oracle(&board);
        board.unnull_move(undo);
        assert_eq!(board.stm, stm_before);
        assert_eq!(board.ep_square, ep_before);
        assert_eq!(board.hash, hash_before);
        assert_hash_oracle(&board);
    }

    #[test]
    fn null_unnull_without_ep_restores_hash() {
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_hash_oracle(&board);
        assert!(board.ep_square.is_none());
        let stm_before = board.stm;
        let hash_before = board.hash;
        let mut board = board;
        let undo = board.null_move();
        assert_hash_oracle(&board);
        board.unnull_move(undo);
        assert_eq!(board.stm, stm_before);
        assert_eq!(board.hash, hash_before);
        assert_hash_oracle(&board);
    }

    #[test]
    fn random_legal_sequence_oracle() {
        let mut board = Board::from_fen(STARTPOS_FEN).unwrap();
        let mut seed: u64 = 42;
        for _ in 0..200 {
            assert_hash_oracle(&board);
            let moves = generate_legal_moves(&board);
            if moves.is_empty() {
                break;
            }
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            let idx = (seed as usize) % moves.len();
            board.make_move(moves[idx]);
        }
        assert_hash_oracle(&board);
    }
}
