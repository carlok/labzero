# Superhuman-band ladder (3+2 gauntlet)

Engine-vs-engine rows for the v0.6.0 superhuman-band sprint. **Perf Elo** is project-relative:
`anchor + 400*log10(p/(1-p))` when the anchor is set (usually `SF_ELO`).

Auto-updated by `./scripts/host-record-gauntlet.sh` when `RECORD=1` on gauntlet runs (also `elo_series.csv` + [timeline](elo_timeline.md)).
Manual rows OK — keep handicap + threads in Notes.

| Date | Opponent / handicap | TC | Games | W-L-D | Score % | Perf | Artifact | Notes |
|------|---------------------|-----|-------|-------|---------|------|----------|-------|
| 2026-06-24 | SF UCI_Elo=2500 | 3+2 | 32 | 18-7-7 | 67.2% | 2624 | `baseline_sf2500.txt` | — |
| 2026-06-24 | SF UCI_Elo=2600 | 3+2 | 16 | 6-3-7 | 59.4% | 2666 | `gate_sf2500_smoke.txt` | params=spsa_smoke.best.params |
| 2026-06-24 | SF UCI_Elo=2600 | 3+2 | 32 | 10-12-10 | 46.9% | 2578 | `confirm_sf2600_32g.txt` | params=spsa_smoke.best.params |
| 2026-06-24 | SF UCI_Elo=2500 | 3+2 | 32 | 11-10-11 | 51.6% | 2511 | `gate_sf2500_32g.txt` | params=spsa_s2.best.params |
| 2026-06-25 | SF UCI_Elo=2500 | 3+2 | 16 | 6-3-7 | 59.4% | 2566 | `gate_sf2500_v060_16g.txt` | — |
| 2026-06-25 | SF UCI_Elo=2500 | 3+2 | 32 | 15-8-9 | 60.9% | 2577 | `gate_sf2500_v060_32g.txt` | — |
| 2026-06-25 | SF UCI_Elo=2600 | 3+2 | 16 | 7-5-4 | 56.2% | 2644 | `gate_sf2600_idtime_16g.txt` | id-time-depth |
| 2026-06-25 | SF UCI_Elo=2600 | 3+2 | 32 | 13-9-10 | 56.2% | 2644 | `gate_sf2600_idtime_32g.txt` | id-time-depth; **18/32 W-equiv — keep** |
| 2026-06-26 | SF UCI_Elo=2700 | 3+2 | 16 | 2-4-10 | 43.8% | 2656 | `gate_sf2700_baseline_16g.txt` | — |
| 2026-06-26 | SF UCI_Elo=2600 | 3+2 | 16 | 7-6-3 | 53.1% | 2622 | `gate_sf2600_lmrhist_16g.txt` | — |
| 2026-06-26 | SF UCI_Elo=2700 | 3+2 | 16 | 2-5-9 | 40.6% | 2634 | `gate_sf2700_lmrhist_16g.txt` | — |
| 2026-06-26 | SF UCI_Elo=2600 | 3+2 | 16 | 4-6-6 | 43.8% | 2556 | `gate_sf2600_cm_16g.txt` | — |
| 2026-06-26 | SF UCI_Elo=2600 | 3+2 | 16 | 4-5-7 | 46.9% | 2578 | `gate_sf2600_tt2_16g.txt` | — |
