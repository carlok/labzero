use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;

use crate::board::Board;
use crate::search::{
    search_with_info, search_with_info_from_depth, SearchInfo, SearchResult, SearchState,
    MAX_DEPTH,
};
use crate::time::{TimeBudget, TimeControl};

pub type InfoCallback = Arc<Mutex<dyn FnMut(SearchInfo) + Send>>;

const HELPER_START_DEPTHS: [u32; 3] = [3, 4, 5];

pub(crate) fn helper_start_depth(helper_index: usize) -> u32 {
    HELPER_START_DEPTHS[helper_index % 3]
}

#[derive(Clone, Debug)]
pub struct EngineOptions {
    pub hash_mb: usize,
    pub threads: usize,
}

impl Default for EngineOptions {
    fn default() -> Self {
        Self {
            hash_mb: 64,
            threads: 1,
        }
    }
}

pub fn run_search(
    board: &Board,
    tc: &TimeControl,
    stm_white: bool,
    state: &mut SearchState,
    options: &EngineOptions,
    stop_flag: Arc<AtomicBool>,
    info_cb: Option<InfoCallback>,
) -> SearchResult {
    let max_depth = tc.depth.unwrap_or(MAX_DEPTH);
    let mut budget = TimeBudget::new(tc, stm_white).with_external_stop(stop_flag.clone());

    if options.threads <= 1 {
        return run_main_search(board, max_depth, &mut budget, state, info_cb);
    }

    let shared_tt = Arc::clone(&state.tt);
    let board_clone = board.clone();
    let tc_clone = tc.clone();
    let stop_helpers = Arc::clone(&stop_flag);
    let mut handles = Vec::new();

    for (helper_index, _) in (1..options.threads).enumerate() {
        let b = board_clone.clone();
        let tc = tc_clone.clone();
        let stop = Arc::clone(&stop_helpers);
        let tt = Arc::clone(&shared_tt);
        let start_depth = helper_start_depth(helper_index);
        handles.push(thread::spawn(move || {
            let mut helper_state = SearchState::with_tt(tt);
            let mut helper_budget = TimeBudget::new(&tc, stm_white).with_external_stop(stop);
            let _ = search_with_info_from_depth(
                &b,
                max_depth,
                start_depth,
                &mut helper_budget,
                &mut helper_state,
                None,
            );
        }));
    }

    let result = run_main_search(board, max_depth, &mut budget, state, info_cb);

    stop_flag.store(true, Ordering::Relaxed);
    for h in handles {
        let _ = h.join();
    }
    stop_flag.store(false, Ordering::Relaxed);

    result
}

fn run_main_search(
    board: &Board,
    max_depth: u32,
    budget: &mut TimeBudget,
    state: &mut SearchState,
    info_cb: Option<InfoCallback>,
) -> SearchResult {
    let mut local_cb = info_cb.map(|cb| {
        move |info: SearchInfo| {
            if let Ok(mut f) = cb.lock() {
                f(info);
            }
        }
    });
    search_with_info(
        board,
        max_depth,
        budget,
        state,
        local_cb.as_mut().map(|f| f as &mut dyn FnMut(SearchInfo)),
    )
}

pub fn ensure_hash_size(state: &mut SearchState, hash_mb: usize) {
    let want = (hash_mb * 1024 * 1024 / 24).next_power_of_two().max(1024);
    if state.tt.entry_count() != want {
        state.set_hash_mb(hash_mb);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn helper_start_depth_cycles() {
        assert_eq!(helper_start_depth(0), 3);
        assert_eq!(helper_start_depth(1), 4);
        assert_eq!(helper_start_depth(2), 5);
        assert_eq!(helper_start_depth(3), 3);
    }

    #[test]
    fn threads_four_yields_three_staggered_starts() {
        let starts: Vec<u32> = (0..3).map(helper_start_depth).collect();
        assert_eq!(starts, vec![3, 4, 5]);
    }
}
