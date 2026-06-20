use crate::color::Color;

#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub enum PieceKind {
    Pawn,
    Knight,
    Bishop,
    Rook,
    Queen,
    King,
}

impl PieceKind {
    pub fn index(self) -> usize {
        match self {
            PieceKind::Pawn => 0,
            PieceKind::Knight => 1,
            PieceKind::Bishop => 2,
            PieceKind::Rook => 3,
            PieceKind::Queen => 4,
            PieceKind::King => 5,
        }
    }

    pub fn from_char(c: char) -> Option<(PieceKind, Color)> {
        match c {
            'P' => Some((PieceKind::Pawn, Color::White)),
            'N' => Some((PieceKind::Knight, Color::White)),
            'B' => Some((PieceKind::Bishop, Color::White)),
            'R' => Some((PieceKind::Rook, Color::White)),
            'Q' => Some((PieceKind::Queen, Color::White)),
            'K' => Some((PieceKind::King, Color::White)),
            'p' => Some((PieceKind::Pawn, Color::Black)),
            'n' => Some((PieceKind::Knight, Color::Black)),
            'b' => Some((PieceKind::Bishop, Color::Black)),
            'r' => Some((PieceKind::Rook, Color::Black)),
            'q' => Some((PieceKind::Queen, Color::Black)),
            'k' => Some((PieceKind::King, Color::Black)),
            _ => None,
        }
    }

    pub fn to_char(self, color: Color) -> char {
        let base = match self {
            PieceKind::Pawn => 'P',
            PieceKind::Knight => 'N',
            PieceKind::Bishop => 'B',
            PieceKind::Rook => 'R',
            PieceKind::Queen => 'Q',
            PieceKind::King => 'K',
        };
        if color == Color::White {
            base
        } else {
            base.to_ascii_lowercase()
        }
    }
}

#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub struct Piece {
    pub color: Color,
    pub kind: PieceKind,
}

impl Piece {
    pub fn new(color: Color, kind: PieceKind) -> Self {
        Self { color, kind }
    }
}
