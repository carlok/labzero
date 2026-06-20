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

    uci::run_uci_loop();
}
