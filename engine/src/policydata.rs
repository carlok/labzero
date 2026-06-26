//! Policy training data: quiet positions labeled by a deeper LabZero search.
//!
//! Output line format (one position per line):
//!   <fen>;<best_uci>;<score>;<depth>
//! where score is centipawns from side-to-move and depth is the label search depth.

use std::fs::{File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

use crate::board::Board;
use crate::fen::STARTPOS_FEN;
use crate::mov::MoveKind;
use crate::movegen::generate_legal_moves;
use crate::search::{search, SearchState, MATE_SCORE};
use crate::time::{TimeBudget, TimeControl};

pub struct PolicyDataConfig {
    pub out_path: PathBuf,
    pub target_games: u64,
    pub play_depth: u32,
    pub label_depth: u32,
    pub random_plies: u32,
    pub max_plies: u32,
    pub seed: u64,
}

impl PolicyDataConfig {
    pub fn from_args(out: &str, games: u64, play_depth: u32, label_depth: u32, seed: u64) -> Self {
        Self {
            out_path: PathBuf::from(out),
            target_games: games,
            play_depth: play_depth.max(1),
            label_depth: label_depth.max(play_depth),
            random_plies: 8,
            max_plies: 200,
            seed,
        }
    }
}

struct SplitMix64(u64);

impl SplitMix64 {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    fn below(&mut self, n: usize) -> usize {
        (self.next() % n as u64) as usize
    }
}

fn games_done(meta_path: &Path) -> u64 {
    std::fs::read_to_string(meta_path)
        .ok()
        .and_then(|s| s.trim().parse().ok())
        .unwrap_or(0)
}

struct Recorded {
    fen: String,
    best_uci: String,
    score: i32,
    depth: u32,
}

pub fn run(cfg: &PolicyDataConfig) -> std::io::Result<()> {
    let meta_path = cfg.out_path.with_extension("games");
    let start_game = games_done(&meta_path);
    if start_game >= cfg.target_games {
        eprintln!(
            "policydata already has {start_game}/{} games; nothing to do",
            cfg.target_games
        );
        return Ok(());
    }

    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&cfg.out_path)?;
    let mut writer = BufWriter::new(file);

    eprintln!(
        "policydata: resuming from game {} -> {} (play d{} label d{})",
        start_game + 1,
        cfg.target_games,
        cfg.play_depth,
        cfg.label_depth
    );

    let mut state = SearchState::new();
    let mut positions_total = 0u64;

    for game_idx in start_game..cfg.target_games {
        state.clear();
        let mut rng = SplitMix64(cfg.seed ^ game_idx.wrapping_mul(0x2545_F491_4F6C_DD1D));
        let records = play_game(cfg, &mut state, &mut rng);

        for r in &records {
            writeln!(writer, "{};{};{};{}", r.fen, r.best_uci, r.score, r.depth)?;
        }
        positions_total += records.len() as u64;
        writer.flush()?;
        std::fs::write(&meta_path, (game_idx + 1).to_string())?;

        if (game_idx + 1) % 10 == 0 {
            eprintln!(
                "  game {}/{}  (+{} positions, {} total this run)",
                game_idx + 1,
                cfg.target_games,
                records.len(),
                positions_total
            );
        }
    }

    eprintln!(
        "policydata done: {} games, {} positions written to {}",
        cfg.target_games,
        positions_total,
        cfg.out_path.display()
    );
    Ok(())
}

fn play_game(
    cfg: &PolicyDataConfig,
    state: &mut SearchState,
    rng: &mut SplitMix64,
) -> Vec<Recorded> {
    let mut board = Board::from_fen(STARTPOS_FEN).expect("startpos");
    let mut records = Vec::new();

    for _ in 0..cfg.random_plies {
        let legal = generate_legal_moves(&board);
        if legal.is_empty() {
            return records;
        }
        board.make_move(legal[rng.below(legal.len())]);
    }

    let mut ply = 0u32;
    loop {
        let legal = generate_legal_moves(&board);
        if legal.is_empty() || board.is_draw() || ply >= cfg.max_plies {
            return records;
        }

        let tc_play = TimeControl {
            depth: Some(cfg.play_depth),
            ..Default::default()
        };
        let mut budget = TimeBudget::new(&tc_play, board.stm == crate::color::Color::White);
        let play = search(&board, cfg.play_depth, &mut budget, state);
        let mv = play.best_move.unwrap_or(legal[0]);

        let quiet = !board.in_check(board.stm)
            && mv.kind != MoveKind::Capture
            && mv.kind != MoveKind::EnPassant
            && mv.promotion.is_none()
            && play.score.abs() < MATE_SCORE - 1000;
        if quiet {
            let tc_label = TimeControl {
                depth: Some(cfg.label_depth),
                ..Default::default()
            };
            let mut label_budget =
                TimeBudget::new(&tc_label, board.stm == crate::color::Color::White);
            let label = search(&board, cfg.label_depth, &mut label_budget, state);
            if let Some(best) = label.best_move {
                records.push(Recorded {
                    fen: board.to_fen(),
                    best_uci: best.to_uci(),
                    score: label.score,
                    depth: cfg.label_depth,
                });
            }
        }

        board.make_move(mv);
        ply += 1;
    }
}

pub fn preflight(out: &str) -> std::io::Result<()> {
    let p = Path::new(out);
    if let Some(parent) = p.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)?;
        }
    }
    let _ = File::options().create(true).append(true).open(p)?;
    Ok(())
}
