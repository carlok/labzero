# LabZero Agent Notes

Use these repo-local notes in addition to the user's global agent guidance.

- Prefer `rtk` for shell commands when it is available.
- Inspect the current dirty worktree before editing. Do not revert user or other-agent artifacts.
- Keep strength claims tied to artifacts. Stockfish limited-Elo rows are project-relative only.
- Default production root policy is `LABZERO_ROOT_POLICY=raw`.
- The default release build uses the workspace `[profile.release]` in `Cargo.toml`: thin LTO, one codegen unit, and panic abort. Do not move this profile into `engine/Cargo.toml`; Cargo ignores package-local profiles in this workspace.
- Use `scripts/host-nps-bench.sh` before changing release/profile/performance settings. Treat NPS results as speed evidence, not strength evidence.
- `Threads=8` is diagnostic only unless a benchmark proves it beats `Threads=4`.
- Lichess notifications are optional and best-effort. Keep secrets in `lichess_bot/.env`, not tracked config.
