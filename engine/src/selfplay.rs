//! Self-play data generator (Rust producer).
//!
//! Plays the engine against itself at a fixed search depth, with a few random
//! opening plies for diversity, and writes labeled quiet positions to disk. The
//! output feeds both Texel-style eval tuning and NNUE training; every position
//! carries the game result and the engine's search score, both from the side to
//! move. Games are appended incrementally and a sidecar counter makes a run
//! resumable across shutdowns.
//!
//! Output line format (one position per line):
//!   <fen>;<result>;<cp>
//! where result is 1.0 / 0.5 / 0.0 (side-to-move perspective) and cp is the
//! engine's search score in centipawns (side-to-move perspective).

use std::fs::{File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

use crate::board::Board;
use crate::color::Color;
use crate::fen::STARTPOS_FEN;
use crate::mov::MoveKind;
use crate::movegen::generate_legal_moves;
use crate::search::{search, SearchState, MATE_SCORE};
use crate::time::{TimeBudget, TimeControl};

pub struct SelfPlayConfig {
    pub out_path: PathBuf,
    pub target_games: u64,
    pub depth: u32,
    pub random_plies: u32,
    pub max_plies: u32,
    pub seed: u64,
}

impl SelfPlayConfig {
    pub fn from_args(out: &str, games: u64, depth: u32, seed: u64) -> Self {
        Self {
            out_path: PathBuf::from(out),
            target_games: games,
            depth,
            random_plies: 8,
            max_plies: 200,
            seed,
        }
    }
}

/// Small deterministic PRNG (SplitMix64) so resumed runs reproduce the same
/// games and no external rng crate state needs persisting.
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

/// White-perspective result in {1.0, 0.5, 0.0}.
struct Recorded {
    fen: String,
    stm: Color,
    cp: i32,
}

pub fn run(cfg: &SelfPlayConfig) -> std::io::Result<()> {
    let meta_path = cfg.out_path.with_extension("games");
    let start_game = games_done(&meta_path);
    if start_game >= cfg.target_games {
        eprintln!(
            "self-play already has {start_game}/{} games; nothing to do",
            cfg.target_games
        );
        return Ok(());
    }

    // Append to existing data; create if missing.
    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&cfg.out_path)?;
    let mut writer = BufWriter::new(file);

    eprintln!(
        "self-play: resuming from game {} -> {} (depth {})",
        start_game + 1,
        cfg.target_games,
        cfg.depth
    );

    let mut state = SearchState::new();
    let mut positions_total = 0u64;

    for game_idx in start_game..cfg.target_games {
        state.clear();
        let mut rng = SplitMix64(cfg.seed ^ game_idx.wrapping_mul(0x2545_F491_4F6C_DD1D));
        let (records, white_result) = play_game(&cfg_clone(cfg), &mut state, &mut rng);

        for r in &records {
            let stm_result = if r.stm == Color::White {
                white_result
            } else {
                1.0 - white_result
            };
            writeln!(writer, "{};{:.1};{}", r.fen, stm_result, r.cp)?;
        }
        positions_total += records.len() as u64;
        writer.flush()?;
        // Persist progress only after the game's positions are durably written.
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
        "self-play done: {} games, {} positions written to {}",
        cfg.target_games,
        positions_total,
        cfg.out_path.display()
    );
    Ok(())
}

fn cfg_clone(cfg: &SelfPlayConfig) -> SelfPlayConfig {
    SelfPlayConfig {
        out_path: cfg.out_path.clone(),
        target_games: cfg.target_games,
        depth: cfg.depth,
        random_plies: cfg.random_plies,
        max_plies: cfg.max_plies,
        seed: cfg.seed,
    }
}

/// Play one game; return recorded quiet positions and white's result.
fn play_game(
    cfg: &SelfPlayConfig,
    state: &mut SearchState,
    rng: &mut SplitMix64,
) -> (Vec<Recorded>, f64) {
    let mut board = Board::from_fen(STARTPOS_FEN).expect("startpos");
    let mut records: Vec<Recorded> = Vec::new();

    // Random opening for diversity.
    for _ in 0..cfg.random_plies {
        let legal = generate_legal_moves(&board);
        if legal.is_empty() {
            return (records, 0.5);
        }
        let mv = legal[rng.below(legal.len())];
        board.make_move(mv);
    }

    let mut last_white_cp = 0i32;
    let mut ply = 0u32;
    loop {
        let legal = generate_legal_moves(&board);
        if legal.is_empty() {
            // Checkmate -> side to move lost; stalemate -> draw.
            let result = if board.in_check(board.stm) {
                if board.stm == Color::White {
                    0.0
                } else {
                    1.0
                }
            } else {
                0.5
            };
            return (records, result);
        }
        if board.is_draw() {
            return (records, 0.5);
        }
        if ply >= cfg.max_plies {
            // Adjudicate long games by the last evaluation.
            let result = if last_white_cp > 800 {
                1.0
            } else if last_white_cp < -800 {
                0.0
            } else {
                0.5
            };
            return (records, result);
        }

        let tc = TimeControl {
            depth: Some(cfg.depth),
            ..Default::default()
        };
        let mut budget = TimeBudget::new(&tc, board.stm == Color::White);
        let res = search(&board, cfg.depth, &mut budget, state);
        let mv = res.best_move.unwrap_or(legal[0]);

        // Record quiet, non-mate positions only (better for static-eval labels).
        let quiet = !board.in_check(board.stm)
            && mv.kind != MoveKind::Capture
            && mv.kind != MoveKind::EnPassant
            && mv.promotion.is_none()
            && res.score.abs() < MATE_SCORE - 1000;
        if quiet {
            let cp = res.score;
            last_white_cp = if board.stm == Color::White { cp } else { -cp };
            records.push(Recorded {
                fen: board.to_fen(),
                stm: board.stm,
                cp,
            });
        } else {
            // Still track score sign for adjudication.
            last_white_cp = if board.stm == Color::White {
                res.score
            } else {
                -res.score
            };
        }

        // best_move (or the legal fallback) is always legal.
        board.make_move(mv);
        ply += 1;
    }
}

/// Touch the output so a writer error surfaces early (used by the CLI).
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
