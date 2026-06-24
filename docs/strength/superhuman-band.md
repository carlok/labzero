# Superhuman-band ladder (3+2 gauntlet)

Engine-vs-engine rows for the v0.6.0 superhuman-band sprint. **Perf Elo** is project-relative:
`anchor + 400*log10(p/(1-p))` when the anchor is set (usually `SF_ELO`).

Auto-updated by `./scripts/host-record-gauntlet.sh` when `RECORD=1` on gauntlet runs.
Manual rows OK — keep handicap + threads in Notes.

| Date | Opponent / handicap | TC | Games | W-L-D | Score % | Perf | Artifact | Notes |
|------|---------------------|-----|-------|-------|---------|------|----------|-------|
| 2026-06-24 | SF UCI_Elo=2500 | 3+2 | 32 | 18-7-7 | 67.2% | 2624 | `baseline_sf2500.txt` | — |
| 2026-06-24 | SF UCI_Elo=2600 | 3+2 | 16 | 6-3-7 | 59.4% | 2666 | `gate_sf2500_smoke.txt` | params=spsa_smoke.best.params |
| 2026-06-24 | SF UCI_Elo=2600 | 3+2 | 32 | 10-12-10 | 46.9% | 2578 | `confirm_sf2600_32g.txt` | params=spsa_smoke.best.params |
| 2026-06-24 | SF UCI_Elo=2500 | 3+2 | 32 | 11-10-11 | 51.6% | 2511 | `gate_sf2500_32g.txt` | params=spsa_s2.best.params |
