use std::sync::Mutex;

use crate::mov::Move;

const MATE_SCORE: i32 = 30_000;

#[derive(Copy, Clone, Eq, PartialEq, Debug)]
pub enum TtFlag {
    Exact,
    Lower,
    Upper,
}

#[derive(Copy, Clone)]
struct TtEntry {
    key: u64,
    score: i32,
    depth: u8,
    flag: TtFlag,
    best_move: Option<Move>,
}

impl TtEntry {
    const fn empty() -> Self {
        Self {
            key: 0,
            score: 0,
            depth: 0,
            flag: TtFlag::Exact,
            best_move: None,
        }
    }
}

pub struct TranspositionTable {
    entries: Mutex<Vec<TtEntry>>,
    mask: usize,
}

impl TranspositionTable {
    pub fn new(size: usize) -> Self {
        let n = size.next_power_of_two().max(1024);
        Self {
            entries: Mutex::new(vec![TtEntry::empty(); n]),
            mask: n - 1,
        }
    }

    pub fn clear(&self) {
        if let Ok(mut entries) = self.entries.lock() {
            for e in entries.iter_mut() {
                *e = TtEntry::empty();
            }
        }
    }

    pub fn entry_count(&self) -> usize {
        self.entries.lock().map(|e| e.len()).unwrap_or(0)
    }

    pub fn probe(&self, key: u64, ply: usize) -> Option<(i32, u8, TtFlag, Option<Move>)> {
        let entries = self.entries.lock().ok()?;
        let e = &entries[(key as usize) & self.mask];
        if e.key == key {
            Some((from_tt_score(e.score, ply), e.depth, e.flag, e.best_move))
        } else {
            None
        }
    }

    pub fn store(
        &self,
        key: u64,
        depth: u8,
        flag: TtFlag,
        score: i32,
        best_move: Option<Move>,
        ply: usize,
    ) {
        let Ok(mut entries) = self.entries.lock() else {
            return;
        };
        let idx = (key as usize) & self.mask;
        let e = &mut entries[idx];
        if e.key == key && e.depth > depth {
            return;
        }
        if e.key != 0 && e.key != key && e.depth > depth {
            return;
        }
        *e = TtEntry {
            key,
            score: to_tt_score(score, ply),
            depth,
            flag,
            best_move,
        };
    }
}

fn to_tt_score(score: i32, ply: usize) -> i32 {
    if score > MATE_SCORE - 1000 {
        score + ply as i32
    } else if score < -MATE_SCORE + 1000 {
        score - ply as i32
    } else {
        score
    }
}

fn from_tt_score(score: i32, ply: usize) -> i32 {
    if score > MATE_SCORE - 1000 {
        score - ply as i32
    } else if score < -MATE_SCORE + 1000 {
        score + ply as i32
    } else {
        score
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mate_score_roundtrip() {
        let ply = 5;
        let mate = -MATE_SCORE + 3;
        assert_eq!(from_tt_score(to_tt_score(mate, ply), ply), mate);
    }
}
