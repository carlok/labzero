use std::io::{self, BufRead, Write};

use rand::seq::SliceRandom;

use crate::board::Board;
use crate::fen::STARTPOS_FEN;
use crate::mov::Move;
use crate::movegen::generate_legal_moves;
use crate::search::{search, SearchResult};
use crate::time::{TimeBudget, TimeControl};

static STOP_FLAG: std::sync::Mutex<bool> = std::sync::Mutex::new(false);

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
            let _ = writeln!(out, "uciok");
            let _ = out.flush();
        } else if trimmed == "isready" {
            let _ = writeln!(out, "readyok");
            let _ = out.flush();
        } else if trimmed == "ucinewgame" {
            board = Board::from_fen(STARTPOS_FEN).expect("startpos");
            board.rep_keys.clear();
        } else if trimmed == "stop" {
            if let Ok(mut g) = STOP_FLAG.lock() {
                *g = true;
            }
        } else if trimmed == "quit" {
            break;
        } else if let Some(rest) = trimmed.strip_prefix("position ") {
            apply_position(&mut board, rest);
        } else if let Some(rest) = trimmed.strip_prefix("go ") {
            let tc = parse_go(rest);
            let result = run_go(&board, &tc);
            if let Some(mv) = result.best_move {
                let _ = writeln!(out, "bestmove {}", mv.to_uci());
            } else {
                let _ = writeln!(out, "bestmove 0000");
            }
            let _ = out.flush();
        } else if trimmed == "go" {
            let tc = TimeControl::default();
            let result = run_go(&board, &tc);
            if let Some(mv) = result.best_move {
                let _ = writeln!(out, "bestmove {}", mv.to_uci());
            }
            let _ = out.flush();
        }
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

fn run_go(board: &Board, tc: &TimeControl) -> SearchResult {
    if let Ok(mut g) = STOP_FLAG.lock() {
        *g = false;
    }

    let moves = generate_legal_moves(board);
    if moves.is_empty() {
        return SearchResult {
            best_move: None,
            score: 0,
            nodes: 0,
        };
    }

    let max_depth = tc.depth.unwrap_or(6);
    let stm_white = board.stm == crate::color::Color::White;
    let mut budget = TimeBudget::new(tc, stm_white);
    let result = search(board, max_depth, &mut budget);
    if result.best_move.is_some() {
        return result;
    }

    let mut rng = rand::thread_rng();
    let choice = moves.choose(&mut rng).copied();
    SearchResult {
        best_move: choice,
        score: 0,
        nodes: 0,
    }
}
