use std::time::{Duration, Instant};

#[derive(Clone, Debug, Default)]
pub struct TimeControl {
    pub movetime_ms: Option<u64>,
    pub wtime_ms: Option<u64>,
    pub btime_ms: Option<u64>,
    pub winc_ms: Option<u64>,
    pub binc_ms: Option<u64>,
    pub movestogo: Option<u32>,
    pub depth: Option<u32>,
    pub infinite: bool,
}

pub struct TimeBudget {
    pub start: Instant,
    pub limit: Option<Duration>,
    pub stop: bool,
}

impl TimeBudget {
    pub fn new(tc: &TimeControl, stm_white: bool) -> Self {
        let limit = if let Some(ms) = tc.movetime_ms {
            Some(Duration::from_millis(ms))
        } else if tc.infinite || tc.depth.is_some() {
            None
        } else {
            let (time, inc) = if stm_white {
                (tc.wtime_ms, tc.winc_ms)
            } else {
                (tc.btime_ms, tc.binc_ms)
            };
            time.map(|t| {
                let moves_left = tc.movestogo.unwrap_or(30) as u64;
                let bonus = inc.unwrap_or(0);
                Duration::from_millis(t / moves_left + bonus)
            })
        };
        Self {
            start: Instant::now(),
            limit,
            stop: false,
        }
    }

    pub fn should_stop(&self) -> bool {
        self.stop
            || self.limit.is_some_and(|l| {
                self.start.elapsed() >= l.saturating_sub(Duration::from_millis(10))
            })
    }

    pub fn request_stop(&mut self) {
        self.stop = true;
    }
}
