use crate::color::Color;
use crate::piece::PieceKind;

#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub struct Square(pub u8);

impl Square {
    pub const fn new(file: u8, rank: u8) -> Self {
        debug_assert!(file < 8 && rank < 8);
        Self(rank * 8 + file)
    }

    pub fn file(self) -> u8 {
        self.0 % 8
    }

    pub fn rank(self) -> u8 {
        self.0 / 8
    }

    pub fn from_index(i: u8) -> Self {
        debug_assert!(i < 64);
        Self(i)
    }

    pub fn index(self) -> u8 {
        self.0
    }

    pub fn shift(self, df: i8, dr: i8) -> Option<Square> {
        let f = self.file() as i8 + df;
        let r = self.rank() as i8 + dr;
        if (0..8).contains(&f) && (0..8).contains(&r) {
            Some(Square::new(f as u8, r as u8))
        } else {
            None
        }
    }
}

pub type Bitboard = u64;

pub const fn bb(sq: Square) -> Bitboard {
    1u64 << sq.0
}

pub fn pop_lsb(bb: &mut Bitboard) -> Option<Square> {
    if *bb == 0 {
        return None;
    }
    let idx = bb.trailing_zeros() as u8;
    *bb &= *bb - 1;
    Some(Square(idx))
}

pub fn bit_count(b: Bitboard) -> u32 {
    b.count_ones()
}

pub const FILES: [Bitboard; 8] = [
    0x0101_0101_0101_0101,
    0x0202_0202_0202_0202,
    0x0404_0404_0404_0404,
    0x0808_0808_0808_0808,
    0x1010_1010_1010_1010,
    0x2020_2020_2020_2020,
    0x4040_4040_4040_4040,
    0x8080_8080_8080_8080,
];

pub const RANKS: [Bitboard; 8] = [
    0x0000_0000_0000_00FF,
    0x0000_0000_0000_FF00,
    0x0000_0000_00FF_0000,
    0x0000_0000_FF00_0000,
    0x0000_00FF_0000_0000,
    0x0000_FF00_0000_0000,
    0x00FF_0000_0000_0000,
    0xFF00_0000_0000_0000,
];

pub fn pawn_attack_bb(sq: Square, color: Color) -> Bitboard {
    let mut attacks = 0u64;
    let f = sq.file() as i8;
    let r = sq.rank() as i8;
    let dr = if color == Color::White { 1 } else { -1 };
    for df in [-1i8, 1] {
        if (0..8).contains(&(f + df)) && (0..8).contains(&(r + dr)) {
            attacks |= bb(Square::new((f + df) as u8, (r + dr) as u8));
        }
    }
    attacks
}

pub fn knight_attack_bb(sq: Square) -> Bitboard {
    const OFFSETS: [(i8, i8); 8] = [
        (1, 2),
        (2, 1),
        (2, -1),
        (1, -2),
        (-1, -2),
        (-2, -1),
        (-2, 1),
        (-1, 2),
    ];
    let mut attacks = 0u64;
    for (df, dr) in OFFSETS {
        if let Some(to) = sq.shift(df, dr) {
            attacks |= bb(to);
        }
    }
    attacks
}

pub fn king_attack_bb(sq: Square) -> Bitboard {
    let mut attacks = 0u64;
    for df in -1i8..=1 {
        for dr in -1i8..=1 {
            if df == 0 && dr == 0 {
                continue;
            }
            if let Some(to) = sq.shift(df, dr) {
                attacks |= bb(to);
            }
        }
    }
    attacks
}

pub fn ray_between(from: Square, to: Square) -> Bitboard {
    let ff = from.file() as i8;
    let fr = from.rank() as i8;
    let tf = to.file() as i8;
    let tr = to.rank() as i8;
    let df = (tf - ff).signum();
    let dr = (tr - fr).signum();
    if df == 0 && dr == 0 {
        return 0;
    }
    if df != 0 && dr != 0 && (tf - ff).abs() != (tr - fr).abs() {
        return 0;
    }
    if df == 0 && dr == 0 {
        return 0;
    }

    let mut mask = 0u64;
    let mut f = ff + df;
    let mut r = fr + dr;
    while f != tf || r != tr {
        mask |= bb(Square::new(f as u8, r as u8));
        f += df;
        r += dr;
    }
    mask
}

pub fn sliding_attacks(from: Square, occupied: Bitboard, directions: &[(i8, i8)]) -> Bitboard {
    let mut attacks = 0u64;
    for &(df, dr) in directions {
        let mut sq = from;
        while let Some(next) = sq.shift(df, dr) {
            attacks |= bb(next);
            if occupied & bb(next) != 0 {
                break;
            }
            sq = next;
        }
    }
    attacks
}

pub const BISHOP_DIRS: [(i8, i8); 4] = [(1, 1), (1, -1), (-1, 1), (-1, -1)];
pub const ROOK_DIRS: [(i8, i8); 4] = [(1, 0), (-1, 0), (0, 1), (0, -1)];

pub fn piece_index(color: Color, kind: PieceKind) -> usize {
    color.index() * 6 + kind.index()
}
