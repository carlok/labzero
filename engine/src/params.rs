//! Runtime-loadable evaluation parameters for offline tuning (SPSA/Texel).
//!
//! By default the engine plays with the hardcoded weights baked into `eval.rs`
//! (the [`EvalParams::default`] values here mirror them exactly), so an
//! un-configured engine is bit-for-bit identical to the previous build. When
//! the environment variable `LABZERO_EVAL_PARAMS` points at a parameter file,
//! the listed keys override the defaults. This lets an external tuner perturb a
//! small, high-ROI subset of weights and measure the strength delta against the
//! gauntlet baseline without recompiling.
//!
//! File format: one `key value` pair per line; `#` starts a comment; blank
//! lines are ignored. Unknown keys are reported on stderr and ignored so a
//! tuner can stay forward-compatible.

use std::env;
use std::fs;
use std::sync::LazyLock;

/// The curated, tunable slice of the hand-crafted evaluation. Kept deliberately
/// small (material + mobility + a few positional terms) so SPSA converges in a
/// tractable number of games on local compute.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EvalParams {
    /// Material values indexed by `PieceKind` (pawn, knight, bishop, rook, queen, king).
    pub material: [i32; 6],
    /// Mobility weight per minor/major piece as `(middlegame, endgame)`.
    pub mob_knight: (i32, i32),
    pub mob_bishop: (i32, i32),
    pub mob_rook: (i32, i32),
    pub mob_queen: (i32, i32),
    /// Bonus for holding the bishop pair.
    pub bishop_pair: i32,
    /// Rook on a fully open file.
    pub rook_open: i32,
    /// Rook on a half-open file (no friendly pawn).
    pub rook_semi: i32,
}

impl Default for EvalParams {
    fn default() -> Self {
        // These are the historical hand-tuned weights; eval.rs now reads them
        // from here, so this struct is the single source of truth.
        EvalParams {
            material: [100, 320, 330, 500, 900, 0],
            mob_knight: (4, 3),
            mob_bishop: (4, 4),
            mob_rook: (2, 3),
            mob_queen: (1, 1),
            bishop_pair: 25,
            rook_open: 15,
            rook_semi: 8,
        }
    }
}

impl EvalParams {
    /// Apply a single `key value` assignment, returning `false` for unknown keys.
    fn apply(&mut self, key: &str, value: i32) -> bool {
        match key {
            "material.pawn" => self.material[0] = value,
            "material.knight" => self.material[1] = value,
            "material.bishop" => self.material[2] = value,
            "material.rook" => self.material[3] = value,
            "material.queen" => self.material[4] = value,
            "mob.knight.mg" => self.mob_knight.0 = value,
            "mob.knight.eg" => self.mob_knight.1 = value,
            "mob.bishop.mg" => self.mob_bishop.0 = value,
            "mob.bishop.eg" => self.mob_bishop.1 = value,
            "mob.rook.mg" => self.mob_rook.0 = value,
            "mob.rook.eg" => self.mob_rook.1 = value,
            "mob.queen.mg" => self.mob_queen.0 = value,
            "mob.queen.eg" => self.mob_queen.1 = value,
            "bishop_pair" => self.bishop_pair = value,
            "rook_open" => self.rook_open = value,
            "rook_semi" => self.rook_semi = value,
            _ => return false,
        }
        true
    }

    /// Parse a parameter file body (the `key value` format described above).
    pub fn parse_text(body: &str) -> EvalParams {
        let mut params = EvalParams::default();
        for (lineno, raw) in body.lines().enumerate() {
            let line = raw.split('#').next().unwrap_or("").trim();
            if line.is_empty() {
                continue;
            }
            let mut it = line.split_whitespace();
            let key = it.next().unwrap_or("");
            match it.next().and_then(|v| v.parse::<i32>().ok()) {
                Some(value) => {
                    if !params.apply(key, value) {
                        eprintln!("params: unknown key '{key}' (line {})", lineno + 1);
                    }
                }
                None => eprintln!("params: malformed line {}: '{}'", lineno + 1, raw),
            }
        }
        params
    }
}

static PARAMS: LazyLock<EvalParams> = LazyLock::new(|| match env::var("LABZERO_EVAL_PARAMS") {
    Ok(path) if !path.is_empty() => match fs::read_to_string(&path) {
        Ok(body) => {
            let p = EvalParams::parse_text(&body);
            eprintln!("params: loaded eval params from {path}");
            p
        }
        Err(e) => {
            eprintln!("params: cannot read {path}: {e}; using defaults");
            EvalParams::default()
        }
    },
    _ => EvalParams::default(),
});

/// The active evaluation parameters, loaded once on first access.
#[inline]
pub fn eval_params() -> &'static EvalParams {
    &PARAMS
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_round_trips() {
        let body = "\
material.knight 330\n\
mob.rook.mg 3\n\
# a comment\n\
bishop_pair 30\n";
        let p = EvalParams::parse_text(body);
        assert_eq!(p.material[1], 330);
        assert_eq!(p.mob_rook.0, 3);
        assert_eq!(p.bishop_pair, 30);
        // Untouched keys keep defaults.
        assert_eq!(p.material[4], 900);
    }

    #[test]
    fn unknown_and_malformed_keys_are_ignored() {
        let p = EvalParams::parse_text("nonsense.key 5\nmaterial.queen\nmaterial.rook 480\n");
        assert_eq!(p.material[3], 480);
        assert_eq!(p, {
            let mut d = EvalParams::default();
            d.material[3] = 480;
            d
        });
    }
}
