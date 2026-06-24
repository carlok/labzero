//! Original attack tables for LabZero.
//!
//! Leaper attacks (knight, king, pawn) are precomputed lookup tables. Slider
//! attacks (bishop, rook, queen) use plain-magic multiply-shift bitboards whose
//! multipliers are searched at startup with a seeded xorshift PRNG, so no
//! engine-derived magic constants are embedded in the repo. Everything here is
//! generated deterministically from the rules of chess.

use std::sync::LazyLock;

use crate::color::Color;
use crate::square::{Bitboard, Square};

const BISHOP_DIRS: [(i8, i8); 4] = [(1, 1), (1, -1), (-1, 1), (-1, -1)];
const ROOK_DIRS: [(i8, i8); 4] = [(1, 0), (-1, 0), (0, 1), (0, -1)];

/// Slider attacks for `sq` given `occ`, by walking rays until a blocker. Used
/// only to build the magic tables (cold path).
fn ray_attacks(sq: usize, occ: u64, dirs: &[(i8, i8)]) -> u64 {
    let mut attacks = 0u64;
    let f0 = (sq % 8) as i8;
    let r0 = (sq / 8) as i8;
    for &(df, dr) in dirs {
        let mut f = f0 + df;
        let mut r = r0 + dr;
        while (0..8).contains(&f) && (0..8).contains(&r) {
            let s = (r * 8 + f) as u64;
            attacks |= 1u64 << s;
            if occ & (1u64 << s) != 0 {
                break;
            }
            f += df;
            r += dr;
        }
    }
    attacks
}

/// Relevant-occupancy mask: ray squares excluding the far edge square of each
/// direction (a blocker on the edge cannot change what lies beyond it).
fn slider_mask(sq: usize, dirs: &[(i8, i8)]) -> u64 {
    let mut mask = 0u64;
    let f0 = (sq % 8) as i8;
    let r0 = (sq / 8) as i8;
    for &(df, dr) in dirs {
        let mut f = f0 + df;
        let mut r = r0 + dr;
        while (0..8).contains(&f) && (0..8).contains(&r) {
            let nf = f + df;
            let nr = r + dr;
            if !(0..8).contains(&nf) || !(0..8).contains(&nr) {
                break;
            }
            mask |= 1u64 << (r * 8 + f) as u64;
            f += df;
            r += dr;
        }
    }
    mask
}

/// Deterministic xorshift64 PRNG used only for magic search.
struct XorShift(u64);

impl XorShift {
    fn next(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }

    /// Sparse candidate: ANDing three draws yields few set bits, which makes
    /// good magic multipliers far more often than dense values.
    fn sparse(&mut self) -> u64 {
        self.next() & self.next() & self.next()
    }
}

struct SquareMagic {
    mask: u64,
    magic: u64,
    shift: u32,
    attacks: Vec<u64>,
}

impl SquareMagic {
    #[inline(always)]
    fn lookup(&self, occ: u64) -> u64 {
        let idx = ((occ & self.mask).wrapping_mul(self.magic) >> self.shift) as usize;
        self.attacks[idx]
    }
}

/// Enumerate every subset of `mask` via the carry-rippler trick.
fn occupancy_subsets(mask: u64) -> Vec<u64> {
    let mut subsets = Vec::with_capacity(1 << mask.count_ones());
    let mut sub = 0u64;
    loop {
        subsets.push(sub);
        sub = sub.wrapping_sub(mask) & mask;
        if sub == 0 {
            break;
        }
    }
    subsets
}

fn build_square_magic(sq: usize, dirs: &[(i8, i8)], rng: &mut XorShift) -> SquareMagic {
    let mask = slider_mask(sq, dirs);
    let bits = mask.count_ones();
    let size = 1usize << bits;
    let shift = 64 - bits;

    let subsets = occupancy_subsets(mask);
    let refs: Vec<u64> = subsets.iter().map(|&o| ray_attacks(sq, o, dirs)).collect();

    loop {
        let magic = rng.sparse();
        // Reject candidates that scatter the top bits poorly.
        if mask.wrapping_mul(magic) & 0xFF00_0000_0000_0000 == 0 {
            continue;
        }
        let mut table = vec![u64::MAX; size];
        let mut ok = true;
        for (i, &occ) in subsets.iter().enumerate() {
            let idx = ((occ.wrapping_mul(magic)) >> shift) as usize;
            if table[idx] == u64::MAX {
                table[idx] = refs[i];
            } else if table[idx] != refs[i] {
                ok = false;
                break;
            }
        }
        if ok {
            // Unused slots stay u64::MAX; harmless since they are never indexed.
            return SquareMagic {
                mask,
                magic,
                shift,
                attacks: table,
            };
        }
    }
}

fn knight_table() -> [u64; 64] {
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
    let mut table = [0u64; 64];
    for (sq, slot) in table.iter_mut().enumerate() {
        let f0 = (sq % 8) as i8;
        let r0 = (sq / 8) as i8;
        for (df, dr) in OFFSETS {
            let f = f0 + df;
            let r = r0 + dr;
            if (0..8).contains(&f) && (0..8).contains(&r) {
                *slot |= 1u64 << (r * 8 + f) as u64;
            }
        }
    }
    table
}

fn king_table() -> [u64; 64] {
    let mut table = [0u64; 64];
    for (sq, slot) in table.iter_mut().enumerate() {
        let f0 = (sq % 8) as i8;
        let r0 = (sq / 8) as i8;
        for df in -1i8..=1 {
            for dr in -1i8..=1 {
                if df == 0 && dr == 0 {
                    continue;
                }
                let f = f0 + df;
                let r = r0 + dr;
                if (0..8).contains(&f) && (0..8).contains(&r) {
                    *slot |= 1u64 << (r * 8 + f) as u64;
                }
            }
        }
    }
    table
}

fn pawn_table() -> [[u64; 64]; 2] {
    let mut table = [[0u64; 64]; 2];
    for (color, side) in table.iter_mut().enumerate() {
        let dr: i8 = if color == 0 { 1 } else { -1 };
        for (sq, slot) in side.iter_mut().enumerate() {
            let f0 = (sq % 8) as i8;
            let r0 = (sq / 8) as i8;
            for df in [-1i8, 1] {
                let f = f0 + df;
                let r = r0 + dr;
                if (0..8).contains(&f) && (0..8).contains(&r) {
                    *slot |= 1u64 << (r * 8 + f) as u64;
                }
            }
        }
    }
    table
}

struct Tables {
    knight: [u64; 64],
    king: [u64; 64],
    pawn: [[u64; 64]; 2],
    bishop: Vec<SquareMagic>,
    rook: Vec<SquareMagic>,
}

static TABLES: LazyLock<Tables> = LazyLock::new(|| {
    // Fixed seed: deterministic, reproducible magic search across runs.
    let mut rng = XorShift(0x1234_5678_9abc_def1);
    let bishop = (0..64)
        .map(|sq| build_square_magic(sq, &BISHOP_DIRS, &mut rng))
        .collect();
    let rook = (0..64)
        .map(|sq| build_square_magic(sq, &ROOK_DIRS, &mut rng))
        .collect();
    Tables {
        knight: knight_table(),
        king: king_table(),
        pawn: pawn_table(),
        bishop,
        rook,
    }
});

// `king_square` yields index 64 for a kingless board (used by some unit-test
// positions). Treat any off-board square as having no attacks, matching the
// previous loop-based generators which simply produced nothing off the edge.
#[inline(always)]
pub fn knight_attacks(sq: Square) -> Bitboard {
    let i = sq.index() as usize;
    if i >= 64 {
        return 0;
    }
    TABLES.knight[i]
}

#[inline(always)]
pub fn king_attacks(sq: Square) -> Bitboard {
    let i = sq.index() as usize;
    if i >= 64 {
        return 0;
    }
    TABLES.king[i]
}

#[inline(always)]
pub fn pawn_attacks(sq: Square, color: Color) -> Bitboard {
    let i = sq.index() as usize;
    if i >= 64 {
        return 0;
    }
    TABLES.pawn[color.index()][i]
}

#[inline(always)]
pub fn bishop_attacks(sq: Square, occ: Bitboard) -> Bitboard {
    let i = sq.index() as usize;
    if i >= 64 {
        return 0;
    }
    TABLES.bishop[i].lookup(occ)
}

#[inline(always)]
pub fn rook_attacks(sq: Square, occ: Bitboard) -> Bitboard {
    let i = sq.index() as usize;
    if i >= 64 {
        return 0;
    }
    TABLES.rook[i].lookup(occ)
}

#[inline(always)]
pub fn queen_attacks(sq: Square, occ: Bitboard) -> Bitboard {
    bishop_attacks(sq, occ) | rook_attacks(sq, occ)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::square::{sliding_attacks, BISHOP_DIRS as SQ_BISHOP, ROOK_DIRS as SQ_ROOK};

    #[test]
    fn magic_matches_ray_walk_all_squares() {
        // Exhaustive over a pseudo-random sample of occupancies per square.
        let mut rng = XorShift(0xdead_beef_cafe_1234);
        for sq in 0..64usize {
            let s = Square::from_index(sq as u8);
            for _ in 0..256 {
                let occ = rng.next() & rng.next();
                assert_eq!(
                    bishop_attacks(s, occ),
                    sliding_attacks(s, occ, &SQ_BISHOP),
                    "bishop mismatch sq={sq} occ={occ:#x}"
                );
                assert_eq!(
                    rook_attacks(s, occ),
                    sliding_attacks(s, occ, &SQ_ROOK),
                    "rook mismatch sq={sq} occ={occ:#x}"
                );
            }
        }
    }
}
