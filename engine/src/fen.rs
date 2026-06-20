use crate::board::Board;
use crate::color::Color;
use crate::piece::PieceKind;
use crate::square::{bb, piece_index, Square};

pub const STARTPOS_FEN: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

impl Board {
    pub fn from_fen(fen: &str) -> Result<Self, String> {
        let parts: Vec<&str> = fen.split_whitespace().collect();
        if parts.len() < 4 {
            return Err("fen needs at least 4 fields".into());
        }

        let mut board = Board {
            pieces: [0; 12],
            stm: if parts[1] == "w" {
                Color::White
            } else if parts[1] == "b" {
                Color::Black
            } else {
                return Err("invalid side".into());
            },
            castling: 0,
            ep_square: None,
            halfmove: parts.get(4).and_then(|s| s.parse().ok()).unwrap_or(0),
            fullmove: parts.get(5).and_then(|s| s.parse().ok()).unwrap_or(1),
            hash: 0,
            history: Vec::new(),
            rep_keys: Vec::new(),
        };

        let mut rank = 7i8;
        let mut file = 0i8;
        for ch in parts[0].chars() {
            match ch {
                '/' => {
                    rank -= 1;
                    file = 0;
                }
                '1'..='8' => file += ch as i8 - '0' as i8,
                _ => {
                    if !(0..8).contains(&rank) || !(0..8).contains(&file) {
                        return Err("fen overflow".into());
                    }
                    let sq = Square::new(file as u8, rank as u8);
                    let (kind, color) = PieceKind::from_char(ch).ok_or("bad piece")?;
                    let idx = piece_index(color, kind);
                    board.pieces[idx] |= bb(sq);
                    file += 1;
                }
            }
        }

        for c in parts[2].chars() {
            match c {
                'K' => board.castling |= crate::board::WHITE_OO,
                'Q' => board.castling |= crate::board::WHITE_OOO,
                'k' => board.castling |= crate::board::BLACK_OO,
                'q' => board.castling |= crate::board::BLACK_OOO,
                '-' => {}
                _ => {}
            }
        }

        if parts[3] != "-" {
            let bytes = parts[3].as_bytes();
            if bytes.len() == 2 {
                let f = bytes[0].wrapping_sub(b'a');
                let r = bytes[1].wrapping_sub(b'1');
                if f < 8 && r < 8 {
                    board.ep_square = Some(Square::new(f, r));
                }
            }
        }

        board.hash = board.compute_hash();
        Ok(board)
    }

    pub fn to_fen(&self) -> String {
        let mut fen = String::new();
        for rank in (0..8).rev() {
            let mut empty = 0;
            for file in 0..8 {
                let sq = Square::new(file, rank);
                if let Some(p) = self.piece_at(sq) {
                    if empty > 0 {
                        fen.push_str(&empty.to_string());
                        empty = 0;
                    }
                    fen.push(p.kind.to_char(p.color));
                } else {
                    empty += 1;
                }
            }
            if empty > 0 {
                fen.push_str(&empty.to_string());
            }
            if rank > 0 {
                fen.push('/');
            }
        }
        fen.push(' ');
        fen.push(if self.stm == Color::White { 'w' } else { 'b' });
        fen.push(' ');
        let mut castled = false;
        let mut cstr = String::new();
        if self.castling & crate::board::WHITE_OO != 0 {
            cstr.push('K');
            castled = true;
        }
        if self.castling & crate::board::WHITE_OOO != 0 {
            cstr.push('Q');
            castled = true;
        }
        if self.castling & crate::board::BLACK_OO != 0 {
            cstr.push('k');
            castled = true;
        }
        if self.castling & crate::board::BLACK_OOO != 0 {
            cstr.push('q');
            castled = true;
        }
        if !castled {
            cstr.push('-');
        }
        fen.push_str(&cstr);
        fen.push(' ');
        if let Some(ep) = self.ep_square {
            fen.push((b'a' + ep.file()) as char);
            fen.push((b'1' + ep.rank()) as char);
        } else {
            fen.push('-');
        }
        fen.push(' ');
        fen.push_str(&self.halfmove.to_string());
        fen.push(' ');
        fen.push_str(&self.fullmove.to_string());
        fen
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn startpos_roundtrip() {
        let b = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_eq!(b.to_fen(), STARTPOS_FEN);
    }
}
