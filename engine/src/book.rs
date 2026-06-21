use std::fs;
use std::path::Path;

use crate::board::Board;
use crate::fen::STARTPOS_FEN;
use crate::mov::Move;
use crate::movegen::generate_legal_moves;

pub struct Book {
    lines: Vec<Vec<Move>>,
    enabled: bool,
}

impl Book {
    pub fn new() -> Self {
        Self {
            lines: Vec::new(),
            enabled: false,
        }
    }

    pub fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
    }

    pub fn load_file(&mut self, path: &Path) -> std::io::Result<()> {
        let text = fs::read_to_string(path)?;
        self.lines.clear();
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let mut board = Board::from_fen(STARTPOS_FEN).expect("startpos");
            let mut seq = Vec::new();
            for token in line.split_whitespace() {
                if let Some(mv) = resolve_move(&board, token) {
                    board.make_move(mv);
                    seq.push(mv);
                }
            }
            if !seq.is_empty() {
                self.lines.push(seq);
            }
        }
        Ok(())
    }

    pub fn probe(&self, board: &Board, ply: usize) -> Option<Move> {
        if !self.enabled || self.lines.is_empty() {
            return None;
        }
        let idx = ply % self.lines.len();
        let line = &self.lines[idx];
        let mut b = board.clone();
        for &mv in line {
            let legal = generate_legal_moves(&b);
            if !legal.contains(&mv) {
                return legal.first().copied();
            }
            if b.history.len() == ply {
                return Some(mv);
            }
            let undo = b.make_move(mv);
            b.history.push(undo);
        }
        None
    }
}

fn resolve_move(board: &Board, uci: &str) -> Option<Move> {
    let partial = Move::from_uci(uci)?;
    generate_legal_moves(board)
        .into_iter()
        .find(|m| m.from == partial.from && m.to == partial.to && m.promotion == partial.promotion)
}

impl Default for Book {
    fn default() -> Self {
        Self::new()
    }
}
