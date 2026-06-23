use crate::board::Board;
use crate::color::Color;
use crate::mov::Move;
use crate::piece::PieceKind;
use crate::square::{
    bb, bit_count, knight_attack_bb, pawn_attack_bb, piece_index, pop_lsb, sliding_attacks, Square,
    BISHOP_DIRS, FILES, RANKS, ROOK_DIRS,
};

const MATERIAL: [i32; 6] = [100, 320, 330, 500, 900, 0];

// Original piece-square tables (mg); eg derived with king/endgame adjustments.
const PST_PAWN_MG: [i32; 64] = [
    0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, -20, -20, 10, 10, 5, 5, -5, -10, 0, 0, -10, -5, 5, 0, 0, 0,
    20, 20, 0, 0, 0, 5, 5, 10, 25, 25, 10, 5, 5, 10, 10, 20, 30, 30, 20, 10, 10, 50, 50, 50, 50,
    50, 50, 50, 50, 0, 0, 0, 0, 0, 0, 0, 0,
];

const PST_PAWN_EG: [i32; 64] = [
    0, 0, 0, 0, 0, 0, 0, 0, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 20, 20, 20, 20, 10, 10, 20, 20,
    20, 30, 30, 20, 20, 20, 30, 30, 40, 50, 50, 40, 30, 30, 50, 50, 50, 50, 50, 50, 50, 50, 80, 80,
    80, 80, 80, 80, 80, 80, 0, 0, 0, 0, 0, 0, 0, 0,
];

const PST_KNIGHT_MG: [i32; 64] = [
    -50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 5, 5, 0, -20, -40, -30, 5, 10, 15, 15, 10,
    5, -30, -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30, -30, 0, 10, 15, 15, 10,
    0, -30, -40, -20, 0, 0, 0, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50,
];

const PST_KNIGHT_EG: [i32; 64] = [
    -30, -20, -10, -10, -10, -10, -20, -30, -20, -10, 0, 5, 5, 0, -10, -20, -10, 0, 5, 10, 10, 5,
    0, -10, -10, 5, 10, 15, 15, 10, 5, -10, -10, 0, 10, 15, 15, 10, 0, -10, -10, 0, 5, 10, 10, 5,
    0, -10, -20, -10, 0, 0, 0, 0, -10, -20, -30, -20, -10, -10, -10, -10, -20, -30,
];

const PST_BISHOP_MG: [i32; 64] = [
    -20, -10, -10, -10, -10, -10, -10, -20, -10, 5, 0, 0, 0, 0, 5, -10, -10, 10, 10, 10, 10, 10,
    10, -10, -10, 0, 10, 10, 10, 10, 0, -10, -10, 5, 10, 10, 10, 10, 5, -10, -10, 0, 5, 10, 10, 5,
    0, -10, -10, 0, 0, 0, 0, 0, 0, -10, -20, -10, -10, -10, -10, -10, -10, -20,
];

const PST_BISHOP_EG: [i32; 64] = [
    -10, -5, -5, -5, -5, -5, -5, -10, -5, 5, 5, 5, 5, 5, 5, -5, -5, 5, 10, 10, 10, 10, 5, -5, -5,
    5, 10, 10, 10, 10, 5, -5, -5, 5, 10, 10, 10, 10, 5, -5, -5, 5, 10, 10, 10, 10, 5, -5, -5, 5, 5,
    5, 5, 5, 5, -5, -10, -5, -5, -5, -5, -5, -5, -10,
];

const PST_ROOK_MG: [i32; 64] = [
    0, 0, 0, 5, 5, 0, 0, 0, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0,
    0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 5, 10, 10, 10, 10, 10, 5, 0, 0, 0,
    0, 0, 0, 0, 0, 0,
];

const PST_ROOK_EG: [i32; 64] = [
    5, 10, 10, 10, 10, 10, 10, 5, 5, 10, 10, 10, 10, 10, 10, 5, 5, 10, 10, 10, 10, 10, 10, 5, 5,
    10, 10, 10, 10, 10, 10, 5, 5, 10, 10, 10, 10, 10, 10, 5, 5, 10, 10, 10, 10, 10, 10, 5, 5, 10,
    10, 10, 10, 10, 10, 5, 5, 10, 10, 10, 10, 10, 10, 5,
];

const PST_QUEEN_MG: [i32; 64] = [
    -20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 5, 0, 0, 0, 0, -10, -10, 5, 5, 5, 5, 5, 0, -10,
    0, 0, 5, 5, 5, 5, 0, -5, -5, 0, 5, 5, 5, 5, 0, -5, -10, 0, 5, 5, 5, 5, 0, -10, -10, 0, 0, 0, 0,
    0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20,
];

const PST_QUEEN_EG: [i32; 64] = [
    -10, -5, -5, 0, 0, -5, -5, -10, -5, 0, 5, 5, 5, 5, 0, -5, -5, 5, 5, 5, 5, 5, 5, -5, 0, 5, 5, 5,
    5, 5, 5, 0, 0, 5, 5, 5, 5, 5, 5, 0, -5, 0, 5, 5, 5, 5, 5, 0, -5, -5, 0, 0, 0, 0, 0, -5, -10,
    -5, -5, 0, 0, -5, -5, -10,
];

const PST_KING_MG: [i32; 64] = [
    20, 30, 10, 0, 0, 10, 30, 20, 20, 20, 0, 0, 0, 0, 20, 20, -10, -20, -20, -20, -20, -20, -20,
    -10, -20, -30, -30, -40, -40, -30, -30, -20, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40,
    -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50,
    -40, -40, -30,
];

const PST_KING_EG: [i32; 64] = [
    -30, -20, -10, -10, -10, -10, -20, -30, -20, -10, 0, 5, 5, 0, -10, -20, -10, 0, 10, 15, 15, 10,
    0, -10, -10, 0, 15, 20, 20, 15, 0, -10, -10, 0, 15, 20, 20, 15, 0, -10, -10, 0, 10, 15, 15, 10,
    0, -10, -20, -10, 0, 0, 0, 0, -10, -20, -40, -30, -20, -10, -10, -10, -20, -40,
];

fn pst_mg(kind: PieceKind) -> &'static [i32; 64] {
    match kind {
        PieceKind::Pawn => &PST_PAWN_MG,
        PieceKind::Knight => &PST_KNIGHT_MG,
        PieceKind::Bishop => &PST_BISHOP_MG,
        PieceKind::Rook => &PST_ROOK_MG,
        PieceKind::Queen => &PST_QUEEN_MG,
        PieceKind::King => &PST_KING_MG,
    }
}

fn pst_eg(kind: PieceKind) -> &'static [i32; 64] {
    match kind {
        PieceKind::Pawn => &PST_PAWN_EG,
        PieceKind::Knight => &PST_KNIGHT_EG,
        PieceKind::Bishop => &PST_BISHOP_EG,
        PieceKind::Rook => &PST_ROOK_EG,
        PieceKind::Queen => &PST_QUEEN_EG,
        PieceKind::King => &PST_KING_EG,
    }
}

fn mirror_sq(sq: Square) -> Square {
    Square::new(sq.file(), 7 - sq.rank())
}

fn game_phase(board: &Board) -> i32 {
    let mut phase = 0u32;
    for color in [Color::White, Color::Black] {
        let base = color.index() * 6;
        phase += bit_count(board.pieces[base + PieceKind::Knight.index()]);
        phase += bit_count(board.pieces[base + PieceKind::Bishop.index()]);
        phase += bit_count(board.pieces[base + PieceKind::Rook.index()]) * 2;
        phase += bit_count(board.pieces[base + PieceKind::Queen.index()]) * 4;
    }
    (phase.min(24) * 256 / 24) as i32
}

fn piece_pst(kind: PieceKind, sq: Square, phase: i32) -> i32 {
    let mg = pst_mg(kind)[sq.index() as usize];
    let eg = pst_eg(kind)[sq.index() as usize];
    (phase * mg + (256 - phase) * eg) / 256
}

fn taper_mg_eg(mg: i32, eg: i32, phase: i32) -> i32 {
    (phase * mg + (256 - phase) * eg) / 256
}

fn is_passed_pawn(board: &Board, color: Color, sq: Square) -> bool {
    let enemy = color.opposite();
    let enemy_pawns = board.pieces[piece_index(enemy, PieceKind::Pawn)];
    let file = sq.file();
    let rank = sq.rank();

    let mut file_mask = 0u64;
    for df in -1i8..=1 {
        let f = file as i8 + df;
        if (0..8).contains(&f) {
            file_mask |= FILES[f as usize];
        }
    }

    let enemy_on_files = enemy_pawns & file_mask;
    let ahead = if color == Color::White {
        let mut mask = 0u64;
        for r in (rank + 1)..8 {
            mask |= RANKS[r as usize];
        }
        mask
    } else {
        let mut mask = 0u64;
        for r in 0..rank {
            mask |= RANKS[r as usize];
        }
        mask
    };
    enemy_on_files & ahead == 0
}

fn is_protected_passer(board: &Board, color: Color, sq: Square) -> bool {
    let pawns = board.pieces[piece_index(color, PieceKind::Pawn)];
    let mut p = pawns;
    while let Some(def_sq) = pop_lsb(&mut p) {
        if def_sq == sq {
            continue;
        }
        if pawn_attack_bb(def_sq, color) & bb(sq) != 0 {
            return true;
        }
    }
    false
}

fn passed_pawns(board: &Board, phase: i32) -> i32 {
    const MG_RANK: [i32; 8] = [0, 0, 8, 16, 28, 45, 75, 0];
    const EG_RANK: [i32; 8] = [0, 0, 12, 28, 50, 85, 140, 0];
    const MG_PROTECTED: i32 = 10;
    const EG_PROTECTED: i32 = 18;

    let mut s = 0;
    for color in [Color::White, Color::Black] {
        let sign = if color == Color::White { 1 } else { -1 };
        let pawns = board.pieces[piece_index(color, PieceKind::Pawn)];
        let mut p = pawns;
        while let Some(sq) = pop_lsb(&mut p) {
            if !is_passed_pawn(board, color, sq) {
                continue;
            }
            let rel_rank = if color == Color::White {
                sq.rank() as usize
            } else {
                (7 - sq.rank()) as usize
            };
            let bonus = taper_mg_eg(MG_RANK[rel_rank], EG_RANK[rel_rank], phase);
            s += sign * bonus;
            if is_protected_passer(board, color, sq) {
                s += sign * taper_mg_eg(MG_PROTECTED, EG_PROTECTED, phase);
            }
        }
    }
    s
}

fn mobility(board: &Board, phase: i32) -> i32 {
    const KNIGHT_MG: i32 = 4;
    const KNIGHT_EG: i32 = 3;
    const BISHOP_MG: i32 = 4;
    const BISHOP_EG: i32 = 4;
    const ROOK_MG: i32 = 2;
    const ROOK_EG: i32 = 3;
    const QUEEN_MG: i32 = 1;
    const QUEEN_EG: i32 = 1;

    let occ = board.occupied();
    let mut s = 0;
    for color in [Color::White, Color::Black] {
        let sign = if color == Color::White { 1 } else { -1 };
        let own = board.color_bb(color);

        let mut knights = board.pieces[piece_index(color, PieceKind::Knight)];
        while let Some(sq) = pop_lsb(&mut knights) {
            let attacks = bit_count(knight_attack_bb(sq) & !own);
            let w = taper_mg_eg(KNIGHT_MG, KNIGHT_EG, phase);
            s += sign * attacks as i32 * w;
        }

        let mut bishops = board.pieces[piece_index(color, PieceKind::Bishop)];
        while let Some(sq) = pop_lsb(&mut bishops) {
            let attacks = bit_count(sliding_attacks(sq, occ, &BISHOP_DIRS) & !own);
            let w = taper_mg_eg(BISHOP_MG, BISHOP_EG, phase);
            s += sign * attacks as i32 * w;
        }

        let mut rooks = board.pieces[piece_index(color, PieceKind::Rook)];
        while let Some(sq) = pop_lsb(&mut rooks) {
            let attacks = bit_count(sliding_attacks(sq, occ, &ROOK_DIRS) & !own);
            let w = taper_mg_eg(ROOK_MG, ROOK_EG, phase);
            s += sign * attacks as i32 * w;
        }

        let mut queens = board.pieces[piece_index(color, PieceKind::Queen)];
        while let Some(sq) = pop_lsb(&mut queens) {
            let attacks = bit_count(
                (sliding_attacks(sq, occ, &BISHOP_DIRS) | sliding_attacks(sq, occ, &ROOK_DIRS))
                    & !own,
            );
            let w = taper_mg_eg(QUEEN_MG, QUEEN_EG, phase);
            s += sign * attacks as i32 * w;
        }
    }
    s
}

pub fn evaluate(board: &Board) -> i32 {
    let phase = game_phase(board);
    let mut score = 0i32;

    for sq in 0..64u8 {
        let s = Square(sq);
        if let Some(p) = board.piece_at(s) {
            let sign = if p.color == Color::White { 1 } else { -1 };
            let pst_sq = if p.color == Color::White {
                s
            } else {
                mirror_sq(s)
            };
            score += sign * (MATERIAL[p.kind.index()] + piece_pst(p.kind, pst_sq, phase));
        }
    }

    score += bishop_pair(board);
    score += rook_files(board);
    score += pawn_structure(board);
    score += passed_pawns(board, phase);
    score += mobility(board, phase);
    score += king_safety(board);

    if board.stm == Color::White {
        score
    } else {
        -score
    }
}

fn bishop_pair(board: &Board) -> i32 {
    let mut s = 0;
    for color in [Color::White, Color::Black] {
        let base = color.index() * 6;
        if bit_count(board.pieces[base + PieceKind::Bishop.index()]) >= 2 {
            s += if color == Color::White { 25 } else { -25 };
        }
    }
    s
}

fn rook_files(board: &Board) -> i32 {
    let mut s = 0;
    for color in [Color::White, Color::Black] {
        let sign = if color == Color::White { 1 } else { -1 };
        let rooks = board.pieces[crate::square::piece_index(color, PieceKind::Rook)];
        let mut r = rooks;
        while r != 0 {
            let sq = Square(r.trailing_zeros() as u8);
            let file_bb = 0x0101_0101_0101_0101u64 << sq.file();
            let pawns_on_file = (board.pieces[crate::square::piece_index(color, PieceKind::Pawn)]
                | board.pieces[crate::square::piece_index(color.opposite(), PieceKind::Pawn)])
                & file_bb;
            if pawns_on_file == 0 {
                s += sign * 15;
            } else if pawns_on_file
                & board.pieces[crate::square::piece_index(color, PieceKind::Pawn)]
                == 0
            {
                s += sign * 8;
            }
            r &= r - 1;
        }
    }
    s
}

fn pawn_structure(board: &Board) -> i32 {
    let mut s = 0;
    for color in [Color::White, Color::Black] {
        let sign = if color == Color::White { 1 } else { -1 };
        let pawns = board.pieces[crate::square::piece_index(color, PieceKind::Pawn)];
        for file in 0..8u8 {
            let file_bb = 0x0101_0101_0101_0101u64 << file;
            let file_pawns = pawns & file_bb;
            if bit_count(file_pawns) > 1 {
                s -= sign * 8;
            }
            let mut p = file_pawns;
            while p != 0 {
                let sq = Square(p.trailing_zeros() as u8);
                let adjacent_file = |f: i8| -> u64 {
                    if (0..8).contains(&f) {
                        0x0101_0101_0101_0101u64 << (f as u8)
                    } else {
                        0
                    }
                };
                let support_files =
                    adjacent_file(sq.file() as i8 - 1) | adjacent_file(sq.file() as i8 + 1);
                let friendly_adj = pawns
                    & support_files
                    & if color == Color::White {
                        !0u64 << sq.index()
                    } else {
                        (1u64 << sq.index()) - 1
                    };
                if friendly_adj == 0 {
                    s -= sign * 6;
                }
                p &= p - 1;
            }
        }
    }
    s
}

fn king_safety(board: &Board) -> i32 {
    let mut s = 0;
    for color in [Color::White, Color::Black] {
        let sign = if color == Color::White { 1 } else { -1 };
        let king_sq = board.king_square(color);
        let rank = king_sq.rank() as i8;
        let expected_rank = if color == Color::White { 0..2 } else { 6..8 };
        if expected_rank.contains(&rank) {
            let shield_rank = if color == Color::White {
                rank + 1
            } else {
                rank - 1
            };
            if (0..8).contains(&shield_rank) {
                for f in king_sq.file().saturating_sub(1)..=king_sq.file().saturating_add(1).min(7)
                {
                    let sq = Square::new(f, shield_rank as u8);
                    if let Some(p) = board.piece_at(sq) {
                        if p.color == color && p.kind == PieceKind::Pawn {
                            s += sign * 8;
                        }
                    }
                }
            }
        }
        let file_bb = 0x0101_0101_0101_0101u64 << king_sq.file();
        let enemy_rooks =
            board.pieces[crate::square::piece_index(color.opposite(), PieceKind::Rook)];
        if enemy_rooks & file_bb != 0 {
            s -= sign * 10;
        }
    }
    s
}

pub fn score_move(mv: Move) -> i32 {
    let mut s = 0;
    if mv.kind == crate::mov::MoveKind::Capture
        || mv.kind == crate::mov::MoveKind::EnPassant
        || mv.promotion.is_some()
    {
        s += 1000;
    }
    if mv.promotion.is_some() {
        s += 500;
    }
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn endgame_king_pst_differs_from_startpos_balance() {
        let kpk = Board::from_fen("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1").unwrap();
        let kpk_score = evaluate(&kpk);
        assert!(kpk_score > 80, "kpk score was {kpk_score}");
    }

    #[test]
    fn advanced_passed_pawn_beats_second_rank() {
        let advanced = Board::from_fen("7k/8/4P3/8/8/8/8/4K3 w - - 0 1").unwrap();
        let second_rank = Board::from_fen("7k/8/8/8/8/4P3/8/4K3 w - - 0 1").unwrap();
        assert!(
            evaluate(&advanced) > evaluate(&second_rank),
            "e6 passer should outscore e3 passer"
        );
    }

    #[test]
    fn blocked_pawn_not_passed() {
        let blocked = Board::from_fen("4k3/8/3p4/4P3/8/8/8/4K3 w - - 0 1").unwrap();
        let clear = Board::from_fen("4k3/8/8/4P3/8/8/8/4K3 w - - 0 1").unwrap();
        assert!(
            evaluate(&clear) > evaluate(&blocked),
            "unblocked passer should score higher than blocked e5"
        );
    }

    #[test]
    fn protected_passer_beats_unprotected() {
        let protected = Board::from_fen("7k/8/8/4P3/3P4/8/8/4K3 w - - 0 1").unwrap();
        let unprotected = Board::from_fen("7k/8/8/4P3/8/8/8/4K3 w - - 0 1").unwrap();
        assert!(
            evaluate(&protected) > evaluate(&unprotected),
            "protected e5 should outscore lone e5"
        );
    }

    #[test]
    fn open_bishop_mobility_beats_blocked() {
        let open = Board::from_fen("4k3/8/8/8/8/8/6B1/4K3 w - - 0 1").unwrap();
        let blocked = Board::from_fen("4k3/ppp5/8/8/8/8/8/2B1K3 w - - 0 1").unwrap();
        assert!(
            evaluate(&open) > evaluate(&blocked),
            "open g2 bishop should outscore blocked c1 bishop"
        );
    }
}
