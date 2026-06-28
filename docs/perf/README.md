# LabZero Performance Notes

This folder is for host-side speed probes. These measurements are useful for
engineering decisions, but they are not strength claims.

## Default Release Profile

The workspace root `Cargo.toml` enables the default production release profile:

- `lto = "thin"`
- `codegen-units = 1`
- `panic = "abort"`

Keep the profile at the workspace root. Cargo ignores `[profile.release]` inside
`engine/Cargo.toml` because LabZero is a workspace.

`scripts/build-host-engine.sh` also supports an opt-in host-native build:

```bash
LABZERO_NATIVE=1 ./scripts/build-host-engine.sh
```

That sets `RUSTFLAGS=-C target-cpu=native` for local binaries only.

## NPS Probe

Use:

```bash
./scripts/host-nps-bench.sh
```

The script clears experimental NNUE/policy env vars, sets
`LABZERO_ROOT_POLICY=raw`, and records per-position `nodes`, `nps`, `time_ms`,
`bestmove`, thread count, hash size, engine path, and git commit.

Useful overrides:

```bash
LABZERO_ENGINE=/path/to/labzero THREADS_LIST="1 4" DEPTH=9 ./scripts/host-nps-bench.sh
```

## 2026-06-28 A/B Result

Generic release was compared against the default optimized profile using the
same source commit and fixed FEN suite.

| Run | Threads | Depth | Result |
| --- | ---: | ---: | --- |
| `nps_20260628T174048Z` vs `nps_20260628T174058Z` | 1 | 8 | optimized median NPS about **+30%** |
| `nps_20260628T174330Z` vs `nps_20260628T174338Z` | 4 | 9 | optimized median NPS about **+3.4%** |

The `Threads=4 depth=8` spot was noisy and briefly looked worse, but the deeper
`Threads=4 depth=9` rerun was modestly positive with stable bestmoves.

Decision: keep the optimized release profile as default production polish, but
do not claim a major Elo gain from it. The bigger durable gain is having a
repeatable NPS probe.
