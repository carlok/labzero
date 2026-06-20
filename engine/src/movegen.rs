use crate::board::{Board, BLACK_OO, BLACK_OOO, WHITE_OO, WHITE_OOO};
use crate::color::Color;
use crate::mov::{Move, MoveKind};
use crate::piece::PieceKind;
use crate::square::{
    bb, bit_count, king_attack_bb, knight_attack_bb, pawn_attack_bb, pop_lsb, sliding_attacks,
    Square, BISHOP_DIRS, ROOK_DIRS,
};

pub fn generate_legal_moves(board: &Board) -> Vec<Move> {
    let mut pseudo = generate_pseudo_legal(board);
    pseudo.retain(|&mv| {
        let mut b = board.clone();
        let undo = b.make_move(mv);
        let legal = !b.in_check(board.stm);
        b.unmake_move(undo);
        legal
    });
    pseudo
}

fn generate_pseudo_legal(board: &Board) -> Vec<Move> {
    let mut moves = Vec::with_capacity(64);
    let stm = board.stm;
    let occ = board.occupied();
    let own = board.color_bb(stm);
    let enemy = board.color_bb(stm.opposite());

    generate_pawn_moves(board, stm, occ, own, enemy, &mut moves);
    generate_piece_moves(board, stm, occ, own, enemy, &mut moves);
    generate_castling(board, stm, &mut moves);
    moves
}

fn generate_pawn_moves(
    board: &Board,
    stm: Color,
    occ: u64,
    _own: u64,
    enemy: u64,
    moves: &mut Vec<Move>,
) {
    let pawns = board.pieces[crate::square::piece_index(stm, PieceKind::Pawn)];
    let mut pawns_bb = pawns;
    let promo_rank = if stm == Color::White { 7 } else { 0 };
    let start_rank = if stm == Color::White { 1 } else { 6 };
    let dir: i8 = if stm == Color::White { 1 } else { -1 };

    while let Some(from) = pop_lsb(&mut pawns_bb) {
        let to = from.shift(0, dir);
        if let Some(one) = to {
            if occ & bb(one) == 0 {
                if one.rank() == promo_rank {
                    for pk in [
                        PieceKind::Queen,
                        PieceKind::Rook,
                        PieceKind::Bishop,
                        PieceKind::Knight,
                    ] {
                        moves.push(Move::promotion(from, one, pk));
                    }
                } else {
                    moves.push(Move::quiet(from, one));
                    if from.rank() == start_rank {
                        if let Some(two) = from.shift(0, dir * 2) {
                            if occ & bb(two) == 0 {
                                moves.push(Move {
                                    from,
                                    to: two,
                                    promotion: None,
                                    kind: MoveKind::DoublePush,
                                });
                            }
                        }
                    }
                }
            }
        }

        for df in [-1i8, 1] {
            if let Some(cap_sq) = from.shift(df, dir) {
                if enemy & bb(cap_sq) != 0 {
                    if cap_sq.rank() == promo_rank {
                        for pk in [
                            PieceKind::Queen,
                            PieceKind::Rook,
                            PieceKind::Bishop,
                            PieceKind::Knight,
                        ] {
                            moves.push(Move::promotion(from, cap_sq, pk));
                        }
                    } else {
                        moves.push(Move::capture(from, cap_sq));
                    }
                }
            }
        }

        if let Some(ep) = board.ep_square {
            if (pawn_attack_bb(ep, stm.opposite()) & bb(from)) != 0 {
                moves.push(Move {
                    from,
                    to: ep,
                    promotion: None,
                    kind: MoveKind::EnPassant,
                });
            }
        }
    }
}

fn generate_piece_moves(
    board: &Board,
    stm: Color,
    occ: u64,
    own: u64,
    enemy: u64,
    moves: &mut Vec<Move>,
) {
    let knights = board.pieces[crate::square::piece_index(stm, PieceKind::Knight)];
    let mut nbb = knights;
    while let Some(from) = pop_lsb(&mut nbb) {
        let mut attacks = knight_attack_bb(from) & !own;
        while let Some(to) = pop_lsb(&mut attacks) {
            let m = if enemy & bb(to) != 0 {
                Move::capture(from, to)
            } else {
                Move::quiet(from, to)
            };
            moves.push(m);
        }
    }

    for (kind, dirs) in [
        (PieceKind::Bishop, &BISHOP_DIRS[..]),
        (PieceKind::Rook, &ROOK_DIRS[..]),
        (PieceKind::Queen, &BISHOP_DIRS[..]),
    ] {
        let mut pbb = board.pieces[crate::square::piece_index(stm, kind)];
        while let Some(from) = pop_lsb(&mut pbb) {
            let mut attacks = sliding_attacks(from, occ, dirs) & !own;
            while let Some(to) = pop_lsb(&mut attacks) {
                let m = if enemy & bb(to) != 0 {
                    Move::capture(from, to)
                } else {
                    Move::quiet(from, to)
                };
                moves.push(m);
            }
        }
    }

    // queen rook dirs already partially covered; add queen bishop+rook combined
    let mut qbb = board.pieces[crate::square::piece_index(stm, PieceKind::Queen)];
    while let Some(from) = pop_lsb(&mut qbb) {
        let mut attacks = sliding_attacks(from, occ, &ROOK_DIRS) & !own;
        while let Some(to) = pop_lsb(&mut attacks) {
            let m = if enemy & bb(to) != 0 {
                Move::capture(from, to)
            } else {
                Move::quiet(from, to)
            };
            moves.push(m);
        }
    }

    let mut kbb = board.pieces[crate::square::piece_index(stm, PieceKind::King)];
    while let Some(from) = pop_lsb(&mut kbb) {
        let mut attacks = king_attack_bb(from) & !own;
        while let Some(to) = pop_lsb(&mut attacks) {
            let m = if enemy & bb(to) != 0 {
                Move::capture(from, to)
            } else {
                Move::quiet(from, to)
            };
            moves.push(m);
        }
    }
}

fn generate_castling(board: &Board, stm: Color, moves: &mut Vec<Move>) {
    if board.in_check(stm) {
        return;
    }
    let rank = if stm == Color::White { 0 } else { 7 };
    let king = Square::new(4, rank);
    let occ = board.occupied();

    let rights = board.castling;
    let (oo, ooo, rook_k, rook_q) = match stm {
        Color::White => (WHITE_OO, WHITE_OOO, Square::new(7, 0), Square::new(0, 0)),
        Color::Black => (BLACK_OO, BLACK_OOO, Square::new(7, 7), Square::new(0, 7)),
    };

    if rights & oo != 0
        && occ & (bb(Square::new(5, rank)) | bb(Square::new(6, rank))) == 0
        && board.piece_at(rook_k).map(|p| p.kind) == Some(PieceKind::Rook)
        && !board.is_square_attacked(king, stm.opposite())
        && !board.is_square_attacked(Square::new(5, rank), stm.opposite())
        && !board.is_square_attacked(Square::new(6, rank), stm.opposite())
    {
        moves.push(Move {
            from: king,
            to: Square::new(6, rank),
            promotion: None,
            kind: MoveKind::Castle,
        });
    }

    if rights & ooo != 0
        && occ & (bb(Square::new(1, rank)) | bb(Square::new(2, rank)) | bb(Square::new(3, rank)))
            == 0
        && board.piece_at(rook_q).map(|p| p.kind) == Some(PieceKind::Rook)
        && !board.is_square_attacked(king, stm.opposite())
        && !board.is_square_attacked(Square::new(3, rank), stm.opposite())
        && !board.is_square_attacked(Square::new(2, rank), stm.opposite())
    {
        moves.push(Move {
            from: king,
            to: Square::new(2, rank),
            promotion: None,
            kind: MoveKind::Castle,
        });
    }
}

#[allow(dead_code)]
fn _bit_count(b: u64) -> u32 {
    bit_count(b)
}
