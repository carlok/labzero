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
    entries: Vec<TtEntry>,
    mask: usize,
}

impl TranspositionTable {
    pub fn new(size: usize) -> Self {
        let n = size.next_power_of_two().max(1024);
        Self {
            entries: vec![TtEntry::empty(); n],
            mask: n - 1,
        }
    }

    pub fn clear(&mut self) {
        for e in &mut self.entries {
            *e = TtEntry::empty();
        }
    }

    pub fn probe(&self, key: u64, ply: usize) -> Option<(i32, u8, TtFlag, Option<Move>)> {
        let e = &self.entries[(key as usize) & self.mask];
        if e.key == key {
            Some((from_tt_score(e.score, ply), e.depth, e.flag, e.best_move))
        } else {
            None
        }
    }

    pub fn store(
        &mut self,
        key: u64,
        depth: u8,
        flag: TtFlag,
        score: i32,
        best_move: Option<Move>,
        ply: usize,
    ) {
        let idx = (key as usize) & self.mask;
        let e = &mut self.entries[idx];
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
