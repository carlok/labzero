use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
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
    start: Instant,
    limit: Option<Duration>,
    reserve: Duration,
    stop: bool,
    external_stop: Option<Arc<AtomicBool>>,
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
                let moves_left = tc.movestogo.unwrap_or(30).max(1) as u64;
                let bonus = inc.unwrap_or(0);
                let base = t / moves_left;
                Duration::from_millis(base.saturating_add(bonus * 7 / 10))
            })
        };
        let reserve = limit.map_or(Duration::from_millis(10), |l| {
            Duration::from_millis((l.as_millis() as u64 * 12 / 100).max(10))
        });
        Self {
            start: Instant::now(),
            limit,
            reserve,
            stop: false,
            external_stop: None,
        }
    }

    pub fn with_external_stop(mut self, flag: Arc<AtomicBool>) -> Self {
        self.external_stop = Some(flag);
        self
    }

    pub fn elapsed_ms(&self) -> u64 {
        self.start.elapsed().as_millis() as u64
    }

    pub fn should_stop(&self) -> bool {
        if self.stop {
            return true;
        }
        if self
            .external_stop
            .as_ref()
            .is_some_and(|f| f.load(Ordering::Relaxed))
        {
            return true;
        }
        self.limit
            .is_some_and(|l| self.start.elapsed() >= l.saturating_sub(Duration::from_millis(10)))
    }

    pub fn should_start_depth(&self, prev_iter_ms: u64) -> bool {
        if self.should_stop() {
            return false;
        }
        let Some(limit) = self.limit else {
            return true;
        };
        let elapsed = self.start.elapsed();
        let remaining = limit.saturating_sub(elapsed);
        let needed =
            self.reserve + Duration::from_millis(prev_iter_ms.max(5)) + Duration::from_millis(10);
        remaining > needed
    }

    pub fn request_stop(&mut self) {
        self.stop = true;
    }

    pub fn is_timed(&self) -> bool {
        self.limit.is_some()
    }
}
