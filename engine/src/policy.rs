//! Policy network for quiet-move ordering (disabled by default).
//!
//! Architecture: sparse 768-dim features (same layout as `nnue.rs`, STM perspective
//! only) -> 64 clipped ReLU -> 4096 from-to logits. Weights are produced only by
//! `scripts/host-policy-train.py` from labzero policy-data labels.

use std::env;
use std::fs;
use std::sync::{LazyLock, RwLock};

use crate::board::Board;
use crate::color::Color;
use crate::mov::Move;

const MAGIC: &[u8; 4] = b"LZP1";
const NUM_FEATURES: usize = 768;
const NUM_MOVES: usize = 4096;
const QA: i32 = 127;

#[derive(Clone)]
pub struct Network {
    hidden: usize,
    w_in: Vec<i16>,
    b_in: Vec<i32>,
    w_out: Vec<i16>,
    b_out: Vec<i32>,
}

fn read_u32(buf: &[u8], off: &mut usize) -> Option<u32> {
    let end = off.checked_add(4)?;
    let bytes = buf.get(*off..end)?;
    *off = end;
    Some(u32::from_le_bytes(bytes.try_into().ok()?))
}

fn read_i16_vec(buf: &[u8], off: &mut usize, n: usize) -> Option<Vec<i16>> {
    let bytes_len = n.checked_mul(2)?;
    let end = off.checked_add(bytes_len)?;
    let slice = buf.get(*off..end)?;
    *off = end;
    Some(
        slice
            .chunks_exact(2)
            .map(|c| i16::from_le_bytes([c[0], c[1]]))
            .collect(),
    )
}

fn read_i32_vec(buf: &[u8], off: &mut usize, n: usize) -> Option<Vec<i32>> {
    let bytes_len = n.checked_mul(4)?;
    let end = off.checked_add(bytes_len)?;
    let slice = buf.get(*off..end)?;
    *off = end;
    Some(
        slice
            .chunks_exact(4)
            .map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]))
            .collect(),
    )
}

impl Network {
    pub fn from_bytes(buf: &[u8]) -> Result<Network, String> {
        let mut off = 0usize;
        let magic = buf.get(0..4).ok_or("policy: file too short for magic")?;
        if magic != MAGIC {
            return Err(format!("policy: bad magic {magic:?}, expected {MAGIC:?}"));
        }
        off += 4;
        let hidden = read_u32(buf, &mut off).ok_or("policy: truncated header (hidden)")? as usize;
        let num_features =
            read_u32(buf, &mut off).ok_or("policy: truncated header (features)")? as usize;
        if num_features != NUM_FEATURES {
            return Err(format!(
                "policy: feature count {num_features} != expected {NUM_FEATURES}"
            ));
        }
        if hidden == 0 || hidden > 512 {
            return Err(format!("policy: implausible hidden size {hidden}"));
        }
        let w_in =
            read_i16_vec(buf, &mut off, num_features * hidden).ok_or("policy: truncated w_in")?;
        let b_in = read_i32_vec(buf, &mut off, hidden).ok_or("policy: truncated b_in")?;
        let w_out =
            read_i16_vec(buf, &mut off, hidden * NUM_MOVES).ok_or("policy: truncated w_out")?;
        let b_out = read_i32_vec(buf, &mut off, NUM_MOVES).ok_or("policy: truncated b_out")?;
        Ok(Network {
            hidden,
            w_in,
            b_in,
            w_out,
            b_out,
        })
    }

    pub fn from_file(path: &str) -> Result<Network, String> {
        let bytes = fs::read(path).map_err(|e| format!("policy: cannot read {path}: {e}"))?;
        Network::from_bytes(&bytes)
    }

    fn accumulate_stm(&self, board: &Board, acc: &mut [i32]) {
        acc.copy_from_slice(&self.b_in);
        let perspective = board.stm;
        for sq in 0..64u8 {
            if let Some(p) = board.piece_at(crate::square::Square(sq)) {
                let rel_color = if p.color == perspective { 0 } else { 1 };
                let rel_sq = if perspective == Color::White {
                    sq as usize
                } else {
                    (sq ^ 56) as usize
                };
                let idx = rel_color * 384 + p.kind.index() * 64 + rel_sq;
                let base = idx * self.hidden;
                let row = &self.w_in[base..base + self.hidden];
                for (a, &w) in acc.iter_mut().zip(row) {
                    *a += w as i32;
                }
            }
        }
    }

    fn hidden_layer(&self, board: &Board) -> Vec<i32> {
        let mut acc = vec![0i32; self.hidden];
        self.accumulate_stm(board, &mut acc);
        acc.into_iter().map(|v| v.clamp(0, QA)).collect()
    }

    pub fn move_logit_from_hidden(&self, hidden: &[i32], mv: Move) -> i32 {
        let idx = mv.from.index() as usize * 64 + mv.to.index() as usize;
        let mut out: i64 = self.b_out[idx] as i64;
        for (h, &a) in hidden.iter().enumerate() {
            out += a as i64 * self.w_out[h * NUM_MOVES + idx] as i64;
        }
        out.clamp(i32::MIN as i64, i32::MAX as i64) as i32
    }

    pub fn move_logit(&self, board: &Board, mv: Move) -> i32 {
        let hidden = self.hidden_layer(board);
        self.move_logit_from_hidden(&hidden, mv)
    }

    fn quiet_logits(&self, board: &Board, moves: &[Move]) -> Vec<i32> {
        let hidden = self.hidden_layer(board);
        moves
            .iter()
            .map(|&mv| self.move_logit_from_hidden(&hidden, mv))
            .collect()
    }
}

static NET: LazyLock<RwLock<Option<Network>>> = LazyLock::new(|| {
    let net = match env::var("LABZERO_POLICY") {
        Ok(path) if !path.is_empty() => match Network::from_file(&path) {
            Ok(n) => {
                eprintln!("policy: loaded network from {path}");
                Some(n)
            }
            Err(e) => {
                eprintln!("{e}; policy ordering disabled");
                None
            }
        },
        _ => None,
    };
    RwLock::new(net)
});

pub fn load_from_file(path: &str) -> Result<(), String> {
    let net = Network::from_file(path)?;
    *NET.write().unwrap() = Some(net);
    Ok(())
}

pub fn is_enabled() -> bool {
    NET.read().unwrap().is_some()
}

/// Raw logits aligned with `moves`; `None` when policy is off.
pub fn quiet_scores(board: &Board, moves: &[Move]) -> Option<Vec<i32>> {
    NET.read()
        .unwrap()
        .as_ref()
        .map(|n| n.quiet_logits(board, moves))
}

/// Single-move logit for CLI parity probes.
pub fn move_logit(board: &Board, mv: Move) -> Option<i32> {
    NET.read()
        .unwrap()
        .as_ref()
        .map(|n| n.move_logit(board, mv))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fen::STARTPOS_FEN;
    use crate::square::Square;

    fn pack(hidden: usize, w_in: &[i16], b_in: &[i32], w_out: &[i16], b_out: &[i32]) -> Vec<u8> {
        let mut v = Vec::new();
        v.extend_from_slice(MAGIC);
        v.extend_from_slice(&(hidden as u32).to_le_bytes());
        v.extend_from_slice(&(NUM_FEATURES as u32).to_le_bytes());
        for &w in w_in {
            v.extend_from_slice(&w.to_le_bytes());
        }
        for &b in b_in {
            v.extend_from_slice(&b.to_le_bytes());
        }
        for &w in w_out {
            v.extend_from_slice(&w.to_le_bytes());
        }
        for &b in b_out {
            v.extend_from_slice(&b.to_le_bytes());
        }
        v
    }

    #[test]
    fn roundtrip_minimal_net() {
        let hidden = 2usize;
        let w_in = vec![1i16; NUM_FEATURES * hidden];
        let b_in = vec![0i32; hidden];
        let w_out = vec![0i16; hidden * NUM_MOVES];
        let mut b_out = vec![0i32; NUM_MOVES];
        b_out[8 * 64 + 16] = 42;
        let buf = pack(hidden, &w_in, &b_in, &w_out, &b_out);
        let net = Network::from_bytes(&buf).expect("parse");
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        let mv = Move::quiet(Square::new(0, 1), Square::new(0, 2));
        assert_eq!(net.move_logit(&board, mv), 42);
    }
}
