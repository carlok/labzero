use std::env;
use std::process::Command;

use cozy_chess::Board;

fn cozy_perft(board: &Board, depth: u32) -> u64 {
    if depth == 0 {
        return 1;
    }
    let mut nodes = 0u64;
    board.generate_moves(|moves| {
        for mv in moves {
            let mut next = board.clone();
            next.try_play(mv).expect("legal cozy move");
            nodes += cozy_perft(&next, depth - 1);
        }
        false
    });
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
        eprintln!("usage: cozy_crosscheck <engine> <depth> <fen>");
        std::process::exit(1);
    }
    let engine = &args[1];
    let depth: u32 = args[2].parse().expect("depth");
    let fen = args[3..].join(" ");

    let board = Board::from_fen(&fen, false).expect("cozy fen");
    let cozy = cozy_perft(&board, depth);
    let engine_nodes = engine_perft(engine, depth, &fen);

    if cozy != engine_nodes {
        eprintln!("cozy_crosscheck FAIL cozy={cozy} engine={engine_nodes} fen={fen}");
        std::process::exit(1);
    }
    println!("cozy_crosscheck: PASS depth={depth} nodes={cozy}");
}
