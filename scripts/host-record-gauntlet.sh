#!/usr/bin/env bash
# Append a completed gauntlet .txt summary to docs/strength/superhuman-band.md
# (and a one-liner to docs/lab_log.md).
#
# Called automatically when host-gauntlet.sh finishes with RECORD=1.
#
#   ./scripts/host-record-gauntlet.sh docs/strength/gauntlet_sf_elo2500_3+2_32g.txt
#   ./scripts/host-record-gauntlet.sh --latest   # newest complete gauntlet_*.txt
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LADDER="${ROOT}/docs/strength/superhuman-band.md"
LAB_LOG="${ROOT}/docs/lab_log.md"
STRENGTH_DIR="${ROOT}/docs/strength"

if [[ "${1:-}" == "--latest" ]]; then
  TXT="$(find "${STRENGTH_DIR}" -name 'gauntlet_*.txt' -type f 2>/dev/null \
    | while read -r f; do grep -q 'status:      complete' "$f" && echo "$f"; done \
    | sort | tail -1)"
  if [[ -z "${TXT:-}" ]]; then
    echo "no complete gauntlet_*.txt in ${STRENGTH_DIR}" >&2
    exit 1
  fi
else
  TXT="${1:?usage: host-record-gauntlet.sh <gauntlet.txt> | --latest}"
fi

if [[ ! -f "${TXT}" ]]; then
  echo "file not found: ${TXT}" >&2
  exit 1
fi

export TXT LADDER LAB_LOG ROOT
python3 - <<'PY'
import os
import re
from datetime import datetime, timezone
from pathlib import Path

txt_path = Path(os.environ["TXT"])
ladder_path = Path(os.environ["LADDER"])
lab_log_path = Path(os.environ["LAB_LOG"])
root = Path(os.environ["ROOT"])

body = txt_path.read_text(encoding="utf-8")
if "status:      complete" not in body:
    raise SystemExit(f"not complete (or missing footer): {txt_path}")

run_id = txt_path.stem  # gauntlet_...

def grab(pat, default=""):
    m = re.search(pat, body, re.MULTILINE)
    return m.group(1).strip() if m else default

ts = grab(r"labzero gauntlet\s+(\S+)", datetime.now(timezone.utc).isoformat())
tc = grab(r"time control:\s*(\S+)")
games = grab(r"^games:\s*(\d+)", "?")
b_strength = grab(r"^B strength:\s*(.+)$", "full")
anchor = grab(r"^anchor Elo:\s*(\S+)", "n/a")
wld = grab(r"^score:\s*(\d+-\d+-\d+)")
score_pct = grab(r"labzero %:\s*([\d.]+)")
perf_m = re.search(r"perf est:\s*(\d+|n/a)", body)
perf = perf_m.group(1) if perf_m else "n/a"

# Optional env tags (not in log header today — pass via filename / notes)
notes = ""
if "LABZERO_EVAL_PARAMS" in os.environ:
    notes = f"params={Path(os.environ['LABZERO_EVAL_PARAMS']).name}"
if "LABZERO_NNUE" in os.environ:
    notes = (notes + " " if notes else "") + f"nnue={Path(os.environ['LABZERO_NNUE']).name}"

date = ts[:10] if len(ts) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
artifact = txt_path.name

header = """# Superhuman-band ladder (3+2 gauntlet)

Engine-vs-engine rows for the `codex/superhuman-band` sprint. **Perf Elo** is project-relative:
`anchor + 400*log10(p/(1-p))` when the anchor is set (usually `SF_ELO`).

Auto-updated by `./scripts/host-record-gauntlet.sh` when `RECORD=1` on gauntlet runs.
Manual rows OK — keep handicap + threads in Notes.

| Date | Opponent / handicap | TC | Games | W-L-D | Score % | Perf | Artifact | Notes |
|------|---------------------|-----|-------|-------|---------|------|----------|-------|
"""

row = f"| {date} | {b_strength} | {tc} | {games} | {wld} | {score_pct}% | {perf} | `{artifact}` | {notes or '—'} |"

if not ladder_path.exists():
    ladder_path.parent.mkdir(parents=True, exist_ok=True)
    ladder_path.write_text(header + row + "\n", encoding="utf-8")
else:
    text = ladder_path.read_text(encoding="utf-8")
    if f"| `{artifact}` |" in text or f"| {artifact} |" in text:
        print(f"already recorded: {artifact}")
    else:
        if not text.endswith("\n"):
            text += "\n"
        ladder_path.write_text(text + row + "\n", encoding="utf-8")

log_block = f"""
## Gauntlet {run_id} ({date})

- **Result:** complete — {wld} ({score_pct}%), perf ≈ **{perf}**
- **Opponent:** {b_strength}, TC {tc}, {games} games
- **Artifact:** `docs/strength/{artifact}`
"""
if lab_log_path.exists():
    lab_log_path.write_text(lab_log_path.read_text(encoding="utf-8") + log_block, encoding="utf-8")

print(f"recorded {artifact} -> {ladder_path.relative_to(root)}")
print(f"  score {wld}  ({score_pct}%)  perf ~ {perf}")
PY
