use std::env;
use std::panic;

use labzero::fen::STARTPOS_FEN;
use labzero::perft;
use labzero::uci;

fn main() {
    panic::set_hook(Box::new(|info| {
        eprintln!("labzero panic: {info}");
    }));

    let args: Vec<String> = env::args().collect();
    if args.len() >= 2 && args[1] == "perft" {
        let depth: u32 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or_else(|| {
            eprintln!("usage: labzero perft <depth> [fen]");
            std::process::exit(1);
        });
        let fen = args.get(3).map(String::as_str).unwrap_or(STARTPOS_FEN);
        let board = labzero::Board::from_fen(fen).expect("invalid fen");
        let nodes = perft::perft(&board, depth);
        println!("perft {} {}", depth, nodes);
        return;
    }

    if args.len() >= 2 && args[1] == "selfplay" {
        // labzero selfplay <out_file> [games] [depth] [seed]
        let out = args.get(2).cloned().unwrap_or_else(|| {
            eprintln!("usage: labzero selfplay <out_file> [games] [depth] [seed]");
            std::process::exit(1);
        });
        let games: u64 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(1000);
        let depth: u32 = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(4);
        let seed: u64 = args
            .get(5)
            .and_then(|s| s.parse().ok())
            .unwrap_or(0x9E37_79B9_7F4A_7C15);
        if let Err(e) = labzero::selfplay::preflight(&out) {
            eprintln!("selfplay: cannot open {out}: {e}");
            std::process::exit(1);
        }
        let cfg = labzero::selfplay::SelfPlayConfig::from_args(&out, games, depth, seed);
        if let Err(e) = labzero::selfplay::run(&cfg) {
            eprintln!("selfplay error: {e}");
            std::process::exit(1);
        }
        return;
    }

    if args.len() >= 2 && args[1] == "policydata" {
        let out = args.get(2).cloned().unwrap_or_else(|| {
            eprintln!("usage: labzero policydata <out_file> [games] [depth] [label_depth] [seed]");
            std::process::exit(1);
        });
        let games: u64 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(100);
        let depth: u32 = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(6);
        let label_depth: u32 = args.get(5).and_then(|s| s.parse().ok()).unwrap_or(depth + 2);
        let seed: u64 = args
            .get(6)
            .and_then(|s| s.parse().ok())
            .unwrap_or(0x9E37_79B9_7F4A_7C15);
        if let Err(e) = labzero::policydata::preflight(&out) {
            eprintln!("policydata: cannot open {out}: {e}");
            std::process::exit(1);
        }
        let cfg = labzero::policydata::PolicyDataConfig::from_args(
            &out, games, depth, label_depth, seed,
        );
        if let Err(e) = labzero::policydata::run(&cfg) {
            eprintln!("policydata error: {e}");
            std::process::exit(1);
        }
        return;
    }

    if args.len() >= 2 && args[1] == "eval" {
        // labzero eval <fen>   -> prints the static eval (cp, side-to-move
        // relative) used by search. Honours LABZERO_NNUE / NnueFile, so it
        // doubles as the Python<->Rust NNUE parity probe.
        let fen = args.get(2).map(String::as_str).unwrap_or(STARTPOS_FEN);
        let board = labzero::Board::from_fen(fen).expect("invalid fen");
        println!("{}", labzero::eval::search_eval(&board));
        return;
    }

    uci::run_uci_loop();
}
