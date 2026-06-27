use crate::piece::PieceKind;
use crate::square::Square;

#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub enum MoveKind {
    Quiet,
    DoublePush,
    Capture,
    Promotion,
    Castle,
    EnPassant,
}

#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub struct Move {
    pub from: Square,
    pub to: Square,
    pub promotion: Option<PieceKind>,
    pub kind: MoveKind,
}

impl Move {
    pub fn quiet(from: Square, to: Square) -> Self {
        Self {
            from,
            to,
            promotion: None,
            kind: MoveKind::Quiet,
        }
    }

    pub fn capture(from: Square, to: Square) -> Self {
        Self {
            from,
            to,
            promotion: None,
            kind: MoveKind::Capture,
        }
    }

    pub fn promotion(from: Square, to: Square, piece: PieceKind) -> Self {
        Self {
            from,
            to,
            promotion: Some(piece),
            kind: MoveKind::Promotion,
        }
    }

    pub fn to_uci(self) -> String {
        let mut s = format!("{}{}", square_name(self.from), square_name(self.to));
        if let Some(p) = self.promotion {
            let c = match p {
                PieceKind::Queen => 'q',
                PieceKind::Rook => 'r',
                PieceKind::Bishop => 'b',
                PieceKind::Knight => 'n',
                PieceKind::Pawn | PieceKind::King => 'q',
            };
            s.push(c);
        }
        s
    }

    pub fn from_uci(s: &str) -> Option<Self> {
        if s.len() < 4 {
            return None;
        }
        let from = parse_square(&s[0..2])?;
        let to = parse_square(&s[2..4])?;
        let promotion = if s.len() >= 5 {
            Some(match s.as_bytes()[4] {
                b'q' => PieceKind::Queen,
                b'r' => PieceKind::Rook,
                b'b' => PieceKind::Bishop,
                b'n' => PieceKind::Knight,
                _ => return None,
            })
        } else {
            None
        };
        Some(Self {
            from,
            to,
            promotion,
            kind: if promotion.is_some() {
                MoveKind::Promotion
            } else {
                MoveKind::Quiet
            },
        })
    }
}

fn square_name(sq: Square) -> String {
    format!("{}{}", (b'a' + sq.file()) as char, sq.rank() + 1)
}

fn parse_square(s: &str) -> Option<Square> {
    let bytes = s.as_bytes();
    if bytes.len() != 2 {
        return None;
    }
    let file = bytes[0].wrapping_sub(b'a');
    let rank = bytes[1].wrapping_sub(b'1');
    if file >= 8 || rank >= 8 {
        return None;
    }
    Some(Square::new(file, rank))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn uci_roundtrip() {
        let m = Move::promotion(Square::new(0, 6), Square::new(0, 7), PieceKind::Queen);
        assert_eq!(m.to_uci(), "a7a8q");
    }
}
