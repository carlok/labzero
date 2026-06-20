use std::env;
use std::process::Command;

use shakmaty::fen::Fen;
use shakmaty::{CastlingMode, Chess, Position};

fn shak_perft(pos: Chess, depth: u32) -> u64 {
    if depth == 0 {
        return 1;
    }
    let mut nodes = 0u64;
    for m in pos.legal_moves() {
        let mut next = pos.clone();
        next.play_unchecked(&m);
        nodes += shak_perft(next, depth - 1);
    }
    nodes
}

fn engine_perft(engine: &str, depth: u32, fen: &str) -> u64 {
    let out = Command::new(engine)
        .args(["perft", &depth.to_string(), fen])
        .output()
        .expect("spawn engine");
    if !out.status.success() {
        panic!("engine failed: {}", String::from_utf8_lossy(&out.stderr));
    }
    String::from_utf8_lossy(&out.stdout)
        .split_whitespace()
        .last()
        .expect("perft output")
        .parse()
        .expect("parse nodes")
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 4 {
        eprintln!("usage: shakmaty_crosscheck <engine> <depth> <fen>");
        std::process::exit(1);
    }
    let engine = &args[1];
    let depth: u32 = args[2].parse().expect("depth");
    let fen = args[3..].join(" ");

    let setup: Fen = fen.parse().expect("fen parse");
    let pos: Chess = setup
        .into_position(CastlingMode::Standard)
        .expect("position");

    let shak = shak_perft(pos, depth);
    let engine_nodes = engine_perft(engine, depth, &fen);

    if shak != engine_nodes {
        eprintln!("shakmaty_crosscheck FAIL shak={shak} engine={engine_nodes}");
        std::process::exit(1);
    }
    println!("shakmaty_crosscheck: PASS depth={depth} nodes={shak}");
}
