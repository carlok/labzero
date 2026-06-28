use std::sync::Mutex;

use crate::mov::Move;

const MATE_SCORE: i32 = 30_000;
const NUM_SHARDS: usize = 64;
const SHARD_MASK: usize = NUM_SHARDS - 1;
const SHARD_SHIFT: u32 = 6;

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
    complete: bool,
}

impl TtEntry {
    const fn empty() -> Self {
        Self {
            key: 0,
            score: 0,
            depth: 0,
            flag: TtFlag::Exact,
            best_move: None,
            complete: false,
        }
    }
}

struct TtShard {
    entries: Mutex<Vec<TtEntry>>,
    mask: usize,
}

impl TtShard {
    fn new(capacity: usize) -> Self {
        let n = capacity.next_power_of_two().max(16);
        Self {
            entries: Mutex::new(vec![TtEntry::empty(); n]),
            mask: n - 1,
        }
    }

    fn len(&self) -> usize {
        self.entries.lock().map(|e| e.len()).unwrap_or(0)
    }

    fn clear(&self) {
        if let Ok(mut entries) = self.entries.lock() {
            for e in entries.iter_mut() {
                *e = TtEntry::empty();
            }
        }
    }

    fn probe(
        &self,
        key: u64,
        slot: usize,
        ply: usize,
    ) -> Option<(i32, u8, TtFlag, Option<Move>, bool)> {
        let entries = self.entries.lock().ok()?;
        let e = &entries[slot & self.mask];
        if e.key == key {
            Some((
                from_tt_score(e.score, ply),
                e.depth,
                e.flag,
                e.best_move,
                e.complete,
            ))
        } else {
            None
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn store(
        &self,
        key: u64,
        slot: usize,
        depth: u8,
        flag: TtFlag,
        score: i32,
        best_move: Option<Move>,
        ply: usize,
        complete: bool,
    ) {
        let Ok(mut entries) = self.entries.lock() else {
            return;
        };
        let idx = slot & self.mask;
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
            complete,
        };
    }
}

pub struct TranspositionTable {
    shards: Vec<TtShard>,
}

impl TranspositionTable {
    pub fn new(size: usize) -> Self {
        let total = size.next_power_of_two().max(1024);
        let per_shard = (total / NUM_SHARDS).next_power_of_two().max(16);
        let shards = (0..NUM_SHARDS).map(|_| TtShard::new(per_shard)).collect();
        Self { shards }
    }

    fn locate(key: u64) -> (usize, usize) {
        let k = key as usize;
        let shard_id = k & SHARD_MASK;
        let slot = k >> SHARD_SHIFT;
        (shard_id, slot)
    }

    pub fn clear(&self) {
        for shard in &self.shards {
            shard.clear();
        }
    }

    pub fn entry_count(&self) -> usize {
        self.shards.iter().map(TtShard::len).sum()
    }

    pub fn probe(&self, key: u64, ply: usize) -> Option<(i32, u8, TtFlag, Option<Move>, bool)> {
        let (shard_id, slot) = Self::locate(key);
        self.shards[shard_id].probe(key, slot, ply)
    }

    #[allow(clippy::too_many_arguments)]
    pub fn store(
        &self,
        key: u64,
        depth: u8,
        flag: TtFlag,
        score: i32,
        best_move: Option<Move>,
        ply: usize,
        complete: bool,
    ) {
        let (shard_id, slot) = Self::locate(key);
        self.shards[shard_id].store(key, slot, depth, flag, score, best_move, ply, complete);
    }
}

fn to_tt_score(score: i32, ply: usize) -> i32 {
    if score > MATE_SCORE - 1000 {
        score.saturating_add(ply as i32).min(MATE_SCORE - 1)
    } else if score < -MATE_SCORE + 1000 {
        score.saturating_sub(ply as i32).max(-MATE_SCORE + 1)
    } else {
        score
    }
}

fn from_tt_score(score: i32, ply: usize) -> i32 {
    if score > MATE_SCORE - 1000 {
        score.saturating_sub(ply as i32).max(MATE_SCORE - 128)
    } else if score < -MATE_SCORE + 1000 {
        score.saturating_add(ply as i32).min(-MATE_SCORE + 128)
    } else {
        score
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::thread;

    #[test]
    fn mate_score_roundtrip() {
        let ply = 5;
        let mate = -MATE_SCORE + 3;
        assert_eq!(from_tt_score(to_tt_score(mate, ply), ply), mate);
    }

    #[test]
    fn total_capacity_matches_request() {
        let tt = TranspositionTable::new(1 << 20);
        assert_eq!(tt.entry_count(), 1 << 20);
    }

    #[test]
    fn cross_shard_store_probe() {
        let tt = TranspositionTable::new(4096);
        let key_a = 0x1000_u64;
        let key_b = 0x2001_u64;
        assert_ne!(
            TranspositionTable::locate(key_a).0,
            TranspositionTable::locate(key_b).0
        );

        tt.store(key_a, 4, TtFlag::Exact, 42, None, 0, true);
        tt.store(key_b, 5, TtFlag::Lower, -17, None, 1, true);

        let a = tt.probe(key_a, 0).expect("key_a");
        assert_eq!(a.0, 42);
        assert_eq!(a.1, 4);
        assert_eq!(a.2, TtFlag::Exact);

        let b = tt.probe(key_b, 1).expect("key_b");
        assert_eq!(b.0, -17);
        assert_eq!(b.1, 5);
        assert_eq!(b.2, TtFlag::Lower);
    }

    #[test]
    fn clear_empties_all_shards() {
        let tt = TranspositionTable::new(1024);
        tt.store(0xABCD, 3, TtFlag::Exact, 10, None, 0, true);
        assert!(tt.probe(0xABCD, 0).is_some());
        tt.clear();
        assert!(tt.probe(0xABCD, 0).is_none());
    }

    #[test]
    fn concurrent_probe_store_smoke() {
        let tt = Arc::new(TranspositionTable::new(1 << 16));
        let mut handles = Vec::new();
        for t in 0..8 {
            let tt = Arc::clone(&tt);
            handles.push(thread::spawn(move || {
                for i in 0..500 {
                    let key = (t as u64) << 32 | i;
                    tt.store(key, 3, TtFlag::Exact, i as i32, None, 0, true);
                    let _ = tt.probe(key, 0);
                }
            }));
        }
        for h in handles {
            h.join().expect("thread panicked");
        }
        let mate = -MATE_SCORE + 3;
        assert_eq!(from_tt_score(to_tt_score(mate, 2), 2), mate);
    }
}
