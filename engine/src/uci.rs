use std::io::{self, BufRead, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use rand::seq::SliceRandom;

use crate::board::Board;
use crate::book::Book;
use crate::fen::STARTPOS_FEN;
use crate::mov::Move;
use crate::movegen::generate_legal_moves;
use crate::search::{SearchInfo, SearchResult, SearchState};
use crate::smp::{ensure_hash_size, run_search, EngineOptions};
use crate::time::TimeControl;

static SEARCH_STATE: Mutex<Option<SearchState>> = Mutex::new(None);
static ENGINE_OPTS: OnceLock<Mutex<EngineOptions>> = OnceLock::new();
static STOP: OnceLock<Arc<AtomicBool>> = OnceLock::new();
static BOOK: OnceLock<Mutex<Book>> = OnceLock::new();

fn engine_opts() -> &'static Mutex<EngineOptions> {
    ENGINE_OPTS.get_or_init(|| Mutex::new(EngineOptions::default()))
}

fn stop_flag() -> Arc<AtomicBool> {
    STOP.get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

fn book() -> &'static Mutex<Book> {
    BOOK.get_or_init(|| Mutex::new(Book::new()))
}

fn search_state() -> SearchState {
    let mut guard = SEARCH_STATE.lock().expect("search state lock");
    if guard.is_none() {
        *guard = Some(SearchState::new());
    }
    guard.take().expect("search state")
}

fn restore_search_state(state: SearchState) {
    *SEARCH_STATE.lock().expect("search state lock") = Some(state);
}

pub fn run_uci_loop() {
    let mut board = Board::from_fen(STARTPOS_FEN).expect("startpos");
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    for line in stdin.lock().lines().map_while(Result::ok) {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if trimmed == "uci" {
            let _ = writeln!(out, "id name labzero");
            let _ = writeln!(out, "id author labzero");
            let _ = writeln!(out, "id version {}", env!("CARGO_PKG_VERSION"));
            let _ = writeln!(out, "option name Hash type spin default 64 min 1 max 1024");
            let _ = writeln!(out, "option name Threads type spin default 1 min 1 max 8");
            let _ = writeln!(out, "option name OwnBook type check default false");
            let _ = writeln!(out, "uciok");
            let _ = out.flush();
        } else if trimmed == "isready" {
            let _ = writeln!(out, "readyok");
            let _ = out.flush();
        } else if trimmed == "ucinewgame" {
            stop_flag().store(false, Ordering::Relaxed);
            board = Board::from_fen(STARTPOS_FEN).expect("startpos");
            board.rep_keys.clear();
            let mut state = search_state();
            state.clear();
            restore_search_state(state);
        } else if trimmed == "stop" {
            stop_flag().store(true, Ordering::Relaxed);
        } else if trimmed == "quit" {
            break;
        } else if let Some(rest) = trimmed.strip_prefix("setoption ") {
            apply_setoption(rest);
        } else if let Some(rest) = trimmed.strip_prefix("position ") {
            apply_position(&mut board, rest);
        } else if let Some(rest) = trimmed.strip_prefix("go ") {
            let tc = parse_go(rest);
            run_go_and_reply(&board, &tc, &mut out);
        } else if trimmed == "go" {
            let tc = TimeControl::default();
            run_go_and_reply(&board, &tc, &mut out);
        }
    }
}

fn apply_setoption(rest: &str) {
    let tokens: Vec<&str> = rest.split_whitespace().collect();
    let mut i = 0;
    while i < tokens.len() {
        if tokens[i] == "name" {
            i += 1;
            let mut name = String::new();
            while i < tokens.len() && tokens[i] != "value" {
                if !name.is_empty() {
                    name.push(' ');
                }
                name.push_str(tokens[i]);
                i += 1;
            }
            let value = if i < tokens.len() && tokens[i] == "value" {
                i += 1;
                tokens.get(i).copied()
            } else {
                None
            };
            if let Some(v) = value {
                match name.as_str() {
                    "Hash" => {
                        if let Ok(mb) = v.parse::<usize>() {
                            let mut state = search_state();
                            ensure_hash_size(&mut state, mb.clamp(1, 1024));
                            restore_search_state(state);
                            if let Ok(mut opts) = engine_opts().lock() {
                                opts.hash_mb = mb.clamp(1, 1024);
                            }
                        }
                    }
                    "Threads" => {
                        if let Ok(n) = v.parse::<usize>() {
                            if let Ok(mut opts) = engine_opts().lock() {
                                opts.threads = n.clamp(1, 8);
                            }
                        }
                    }
                    "OwnBook" => {
                        let on = matches!(v, "true" | "True" | "1");
                        if let Ok(mut book) = book().lock() {
                            book.set_enabled(on);
                        }
                    }
                    "BookFile" => {
                        if let Ok(mut book) = book().lock() {
                            let _ = book.load_file(std::path::Path::new(v));
                        }
                    }
                    _ => {}
                }
                i += 1;
            }
        }
        i += 1;
    }
}

fn apply_position(board: &mut Board, rest: &str) {
    let tokens: Vec<&str> = rest.split_whitespace().collect();
    if tokens.is_empty() {
        return;
    }
    let mut idx = 0;
    if tokens[idx] == "startpos" {
        *board = Board::from_fen(STARTPOS_FEN).expect("startpos");
        idx += 1;
    } else if tokens[idx] == "fen" {
        idx += 1;
        let mut fen_parts = Vec::new();
        while idx < tokens.len() && tokens[idx] != "moves" {
            fen_parts.push(tokens[idx]);
            idx += 1;
        }
        let fen = fen_parts.join(" ");
        *board = Board::from_fen(&fen).expect("fen");
    }
    board.rep_keys.clear();
    if idx < tokens.len() && tokens[idx] == "moves" {
        idx += 1;
        while idx < tokens.len() {
            if let Some(mv) = resolve_uci_move(board, tokens[idx]) {
                let undo = board.make_move(mv);
                board.history.push(undo);
            }
            idx += 1;
        }
    }
}

fn resolve_uci_move(board: &Board, uci: &str) -> Option<Move> {
    let partial = Move::from_uci(uci)?;
    generate_legal_moves(board)
        .into_iter()
        .find(|m| m.from == partial.from && m.to == partial.to && m.promotion == partial.promotion)
}

fn parse_go(rest: &str) -> TimeControl {
    let mut tc = TimeControl::default();
    let mut it = rest.split_whitespace();
    while let Some(k) = it.next() {
        match k {
            "depth" => tc.depth = it.next().and_then(|v| v.parse().ok()),
            "movetime" => tc.movetime_ms = it.next().and_then(|v| v.parse().ok()),
            "wtime" => tc.wtime_ms = it.next().and_then(|v| v.parse().ok()),
            "btime" => tc.btime_ms = it.next().and_then(|v| v.parse().ok()),
            "winc" => tc.winc_ms = it.next().and_then(|v| v.parse().ok()),
            "binc" => tc.binc_ms = it.next().and_then(|v| v.parse().ok()),
            "movestogo" => tc.movestogo = it.next().and_then(|v| v.parse().ok()),
            "infinite" => tc.infinite = true,
            _ => {}
        }
    }
    tc
}

fn run_go_and_reply(board: &Board, tc: &TimeControl, out: &mut impl Write) {
    stop_flag().store(false, Ordering::Relaxed);

    let moves = generate_legal_moves(board);
    if moves.is_empty() {
        let _ = writeln!(out, "bestmove 0000");
        let _ = out.flush();
        return;
    }

    let ply = board.history.len();
    if let Ok(book) = book().lock() {
        if let Some(mv) = book.probe(board, ply) {
            let _ = writeln!(out, "bestmove {}", mv.to_uci());
            let _ = out.flush();
            return;
        }
    }

    let stm_white = board.stm == crate::color::Color::White;
    let opts = engine_opts().lock().expect("engine opts").clone();
    let stop = stop_flag();
    let info_out = Arc::new(Mutex::new(InfoWriter { out: Vec::new() }));

    let info_cb: Arc<Mutex<dyn FnMut(SearchInfo) + Send>> = {
        let info_out = Arc::clone(&info_out);
        Arc::new(Mutex::new(move |info: SearchInfo| {
            if let Ok(mut w) = info_out.lock() {
                w.emit(&info);
            }
        }))
    };

    let mut state = search_state();
    ensure_hash_size(&mut state, opts.hash_mb);
    let result = run_search(board, tc, stm_white, &mut state, &opts, stop, Some(info_cb));
    restore_search_state(state);

    if let Ok(w) = info_out.lock() {
        for line in &w.out {
            let _ = writeln!(out, "{line}");
        }
    }

    if let Some(mv) = result.best_move {
        let _ = writeln!(out, "bestmove {}", mv.to_uci());
    } else {
        let mut rng = rand::thread_rng();
        let choice = moves.choose(&mut rng).copied();
        if let Some(mv) = choice {
            let _ = writeln!(out, "bestmove {}", mv.to_uci());
        } else {
            let _ = writeln!(out, "bestmove 0000");
        }
    }
    let _ = out.flush();
}

struct InfoWriter {
    out: Vec<String>,
}

impl InfoWriter {
    fn emit(&mut self, info: &SearchInfo) {
        let nps = info
            .nodes
            .saturating_mul(1000)
            .checked_div(info.time_ms.max(1))
            .unwrap_or(0);
        self.out.push(format!(
            "info depth {} score cp {} nodes {} nps {} time {}",
            info.depth, info.score, info.nodes, nps, info.time_ms
        ));
    }
}

#[allow(dead_code)]
fn run_go(board: &Board, tc: &TimeControl) -> SearchResult {
    let mut buf = Vec::new();
    run_go_and_reply(board, tc, &mut buf);
    SearchResult {
        best_move: None,
        score: 0,
        nodes: 0,
        depth: 0,
    }
}
