//! Original NNUE-style evaluation feeding the existing alpha-beta search.
//!
//! This is the S3/S4 "disruptive bet" from the roadmap. The network and its
//! weights are entirely original to this project: weights are produced only by
//! the host trainer (`scripts/host-nnue-train.py`) from labzero's own self-play
//! data and own search labels — no external engine games or weights — per
//! `docs/originality_policy.md`.
//!
//! Architecture (deliberately simple so a first net is trainable on local
//! compute and verifiable end-to-end):
//!   * Inputs: two perspectives (side-to-move, then the opponent). Each
//!     perspective is a 768-dim sparse vector indexed by
//!     `rel_color*384 + piece_type*64 + rel_square`, where the board is
//!     vertically flipped for the black perspective so "our" pieces always sit
//!     on the low ranks. This is a HalfKP-free, king-bucket-free feature set —
//!     simple and original.
//!   * `acc[p] = b_in + sum_active W_in[:, idx]`  (per perspective, dim `H`)
//!   * `h = clamp(acc, 0, 127)`  (clipped ReLU, quantized activation range)
//!   * `out = b_out + W_out · concat(h_stm, h_opp)`  (dim `2H` -> scalar)
//!   * `cp = out * 100 / out_div`  (centipawns, side-to-move relative)
//!
//! The accumulator is computed from scratch on each call here. That is correct
//! but not yet "efficiently updatable" inside search; incremental add/subtract
//! on make/unmake is a pure-speed follow-up that does not change outputs (the
//! "EU" in NNUE). It is intentionally deferred until a net actually passes the
//! gauntlet keep-gate, so we never optimize a net we are about to discard.
//!
//! Disabled by default: with no net configured the engine uses the classical
//! `eval::evaluate`, so this module is inert until the operator points
//! `LABZERO_NNUE` (or the `NnueFile` UCI option, wired in `uci.rs`) at a net.

use std::env;
use std::fs;
use std::sync::{LazyLock, RwLock};

use crate::board::Board;
use crate::color::Color;

const MAGIC: &[u8; 4] = b"LZN1";
const NUM_FEATURES: usize = 768;

/// A loaded, quantized network. All weights are integers exported by the host
/// trainer; inference is pure integer arithmetic for determinism across CPUs.
#[derive(Clone)]
pub struct Network {
    hidden: usize,
    /// Feature-major input weights, length `NUM_FEATURES * hidden`
    /// (`w_in[idx * hidden + h]`), so an active feature adds one contiguous row.
    w_in: Vec<i16>,
    /// Input biases, length `hidden`.
    b_in: Vec<i32>,
    /// Output weights over `concat(h_stm, h_opp)`, length `2 * hidden`.
    w_out: Vec<i16>,
    /// Output bias (scalar).
    b_out: i32,
    /// Final divisor mapping the integer output to centipawns.
    out_div: i32,
}

fn read_u32(buf: &[u8], off: &mut usize) -> Option<u32> {
    let end = off.checked_add(4)?;
    let bytes = buf.get(*off..end)?;
    *off = end;
    Some(u32::from_le_bytes(bytes.try_into().ok()?))
}

fn read_i32(buf: &[u8], off: &mut usize) -> Option<i32> {
    read_u32(buf, off).map(|v| v as i32)
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
    /// Parse the `LZN1` binary format. Returns an error string on any
    /// truncation or magic/size mismatch so a bad file fails loudly.
    pub fn from_bytes(buf: &[u8]) -> Result<Network, String> {
        let mut off = 0usize;
        let magic = buf.get(0..4).ok_or("nnue: file too short for magic")?;
        if magic != MAGIC {
            return Err(format!("nnue: bad magic {magic:?}, expected {MAGIC:?}"));
        }
        off += 4;
        let hidden = read_u32(buf, &mut off).ok_or("nnue: truncated header (hidden)")? as usize;
        let num_features =
            read_u32(buf, &mut off).ok_or("nnue: truncated header (features)")? as usize;
        if num_features != NUM_FEATURES {
            return Err(format!(
                "nnue: feature count {num_features} != expected {NUM_FEATURES}"
            ));
        }
        if hidden == 0 || hidden > 4096 {
            return Err(format!("nnue: implausible hidden size {hidden}"));
        }
        let w_in =
            read_i16_vec(buf, &mut off, num_features * hidden).ok_or("nnue: truncated w_in")?;
        let b_in = read_i32_vec(buf, &mut off, hidden).ok_or("nnue: truncated b_in")?;
        let w_out = read_i16_vec(buf, &mut off, 2 * hidden).ok_or("nnue: truncated w_out")?;
        let b_out = read_i32(buf, &mut off).ok_or("nnue: truncated b_out")?;
        let out_div = read_i32(buf, &mut off).ok_or("nnue: truncated out_div")?;
        if out_div == 0 {
            return Err("nnue: out_div must be non-zero".into());
        }
        Ok(Network {
            hidden,
            w_in,
            b_in,
            w_out,
            b_out,
            out_div,
        })
    }

    pub fn from_file(path: &str) -> Result<Network, String> {
        let bytes = fs::read(path).map_err(|e| format!("nnue: cannot read {path}: {e}"))?;
        Network::from_bytes(&bytes)
    }

    /// Accumulate the active-feature rows for one perspective into `acc`.
    fn accumulate(&self, board: &Board, perspective: Color, acc: &mut [i32]) {
        acc.copy_from_slice(&self.b_in);
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

    /// Static evaluation in centipawns, positive favouring the side to move.
    pub fn evaluate(&self, board: &Board) -> i32 {
        let stm = board.stm;
        let opp = stm.opposite();
        let mut acc_stm = vec![0i32; self.hidden];
        let mut acc_opp = vec![0i32; self.hidden];
        self.accumulate(board, stm, &mut acc_stm);
        self.accumulate(board, opp, &mut acc_opp);

        let mut out: i64 = self.b_out as i64;
        for (&a, &w) in acc_stm.iter().zip(&self.w_out[..self.hidden]) {
            out += a.clamp(0, 127) as i64 * w as i64;
        }
        for (&a, &w) in acc_opp.iter().zip(&self.w_out[self.hidden..]) {
            out += a.clamp(0, 127) as i64 * w as i64;
        }
        (out * 100 / self.out_div as i64) as i32
    }
}

static NET: LazyLock<RwLock<Option<Network>>> = LazyLock::new(|| {
    let net = match env::var("LABZERO_NNUE") {
        Ok(path) if !path.is_empty() => match Network::from_file(&path) {
            Ok(n) => {
                eprintln!("nnue: loaded network from {path}");
                Some(n)
            }
            Err(e) => {
                eprintln!("{e}; falling back to classical eval");
                None
            }
        },
        _ => None,
    };
    RwLock::new(net)
});

/// Load (or replace) the active network at runtime, e.g. from the `NnueFile`
/// UCI option. Returns an error string on failure, leaving any prior net intact.
pub fn load_from_file(path: &str) -> Result<(), String> {
    let net = Network::from_file(path)?;
    *NET.write().unwrap() = Some(net);
    Ok(())
}

/// Whether an NNUE network is active.
pub fn is_enabled() -> bool {
    NET.read().unwrap().is_some()
}

/// NNUE evaluation if a network is loaded, else `None` (caller uses classical).
pub fn evaluate(board: &Board) -> Option<i32> {
    NET.read().unwrap().as_ref().map(|n| n.evaluate(board))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fen::STARTPOS_FEN;

    /// Build a minimal valid LZN1 buffer with the given weights for testing.
    fn pack(
        hidden: usize,
        w_in: &[i16],
        b_in: &[i32],
        w_out: &[i16],
        b_out: i32,
        out_div: i32,
    ) -> Vec<u8> {
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
        v.extend_from_slice(&b_out.to_le_bytes());
        v.extend_from_slice(&out_div.to_le_bytes());
        v
    }

    #[test]
    fn rejects_bad_magic() {
        let mut buf = pack(1, &[0; NUM_FEATURES], &[0], &[0, 0], 0, 1);
        buf[0] = b'X';
        assert!(Network::from_bytes(&buf).is_err());
    }

    #[test]
    fn rejects_truncation() {
        let buf = pack(2, &vec![0; NUM_FEATURES * 2], &[0, 0], &[0, 0, 0, 0], 0, 1);
        assert!(Network::from_bytes(&buf[..buf.len() - 3]).is_err());
    }

    #[test]
    fn zero_net_is_zero_plus_bias() {
        // hidden=1, all weights zero, b_out=500, out_div=100 -> 500*100/100 = 500.
        let buf = pack(1, &[0; NUM_FEATURES], &[0], &[0, 0], 500, 100);
        let net = Network::from_bytes(&buf).unwrap();
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        assert_eq!(net.evaluate(&board), 500);
    }

    #[test]
    fn known_feature_contributes_expected_value() {
        // hidden=1. Set the input weight for the stm-perspective feature of a
        // white pawn on a2 to 10, all biases zero, w_out[0]=2 (stm half),
        // out_div=1. On the startpos with white to move, white pawn a2:
        //   rel_color=0 (own), type=pawn=0, rel_sq=a2=8 -> idx=8.
        // acc_stm[0] gets +10 from that pawn (and 0 from all else since only
        // idx 8 is non-zero). clamp(10,0,127)=10. opp half weight is 0.
        //   out = 0 + 10*2 = 20 ; cp = 20*100/1 ... out_div=100 -> 20.
        let mut w_in = vec![0i16; NUM_FEATURES];
        w_in[8] = 10; // idx 8 row, hidden=1 so position 8*1+0
        let buf = pack(1, &w_in, &[0], &[2, 0], 0, 100);
        let net = Network::from_bytes(&buf).unwrap();
        let board = Board::from_fen(STARTPOS_FEN).unwrap();
        // Only the a2 pawn lands on idx 8 for the white (stm) perspective.
        assert_eq!(net.evaluate(&board), 20);
    }
}
