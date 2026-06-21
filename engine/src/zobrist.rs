//! Deterministic Zobrist keys (labzero-original constants, not copied from other engines).

use crate::square::Square;

const fn splitmix64(mut x: u64) -> u64 {
    x = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = x;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

const fn key(table: u64, index: u64) -> u64 {
    splitmix64(table.wrapping_mul(0x1000_0000_01B3).wrapping_add(index))
}

const fn init_piece_keys() -> [[u64; 64]; 12] {
    let mut table = [[0u64; 64]; 12];
    let mut pc = 0usize;
    while pc < 12 {
        let mut sq = 0usize;
        while sq < 64 {
            table[pc][sq] = key(0, (pc * 64 + sq) as u64);
            sq += 1;
        }
        pc += 1;
    }
    table
}

const fn init_castling_keys() -> [u64; 16] {
    let mut table = [0u64; 16];
    let mut i = 0usize;
    while i < 16 {
        table[i] = key(2, i as u64);
        i += 1;
    }
    table
}

const fn init_ep_file_keys() -> [u64; 8] {
    let mut table = [0u64; 8];
    let mut i = 0usize;
    while i < 8 {
        table[i] = key(3, i as u64);
        i += 1;
    }
    table
}

const PIECE: [[u64; 64]; 12] = init_piece_keys();
const SIDE: u64 = key(1, 0);
const CASTLING: [u64; 16] = init_castling_keys();
const EP_FILE: [u64; 8] = init_ep_file_keys();

#[inline]
pub fn piece_key(piece_idx: usize, sq: Square) -> u64 {
    PIECE[piece_idx][sq.index() as usize]
}

#[inline]
pub fn side_key() -> u64 {
    SIDE
}

#[inline]
pub fn castling_key(rights: u8) -> u64 {
    CASTLING[(rights & 0x0F) as usize]
}

#[inline]
pub fn ep_file_key(file: u8) -> u64 {
    EP_FILE[file as usize]
}
