"""Recurring push: every 2 hours, load the freshly-transcribed governorship evidence into
the DB and rebuild the governor results — so the database keeps up while transcription runs.

Each cycle:
  1. push_jsons_local.py --offices governorship --no-tui   (load new evidence + pu_sheets)
  2. for each governor year present: void inflated misreads (--zero-inflated) then
     rebuild ONLY the governor results (--build-results --election governor)
  3. sleep 2h

Runs LOCALLY (needs the local jsons_local files + backend/.env). Idempotent — a cycle
that overlaps a mid-transcription state just re-loads it fully next time. Errors in one
step are logged and the loop continues. Stop it by closing the window / Ctrl-C.

    python scripts/push_loop.py                 # every 2h, governorship
    python scripts/push_loop.py --once          # run a single cycle and exit
    python scripts/push_loop.py --interval 3600 # custom interval (seconds)
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime

HERE = pathlib.Path(__file__).resolve().parent      # backend/scripts
BACKEND = HERE.parent                                # backend/
OFFICE = "governorship"                              # folder office being transcribed
ET = "governor"                                      # its election_type in the DB

# the picker reads DATABASE_URL from the environment (not .env) — load it once here
for _line in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if _line.startswith("DATABASE_URL="):
        os.environ["DATABASE_URL"] = _line.split("=", 1)[1].strip()
        break


def _sa_url() -> str:
    u = os.environ["DATABASE_URL"]
    return "postgresql+psycopg://" + u.split("://", 1)[1]


def run(*args: str) -> int:
    """Run a project script as a subprocess (output inherits our stdout). Returns exit code."""
    print(f"  $ python {' '.join(args)}", flush=True)
    return subprocess.run([sys.executable, *args], cwd=str(BACKEND)).returncode


def governor_years() -> list[str]:
    """Distinct election years present in governor evidence (adapts as new states/years load)."""
    from sqlalchemy import create_engine, text
    eng = create_engine(_sa_url())
    with eng.connect() as c:
        return sorted(r[0] for r in c.execute(
            text("select distinct year from evidence where election_type='governor'")).all())


def cycle(n: int) -> None:
    print(f"\n=== [{datetime.now():%Y-%m-%d %H:%M:%S}] push cycle {n} ===", flush=True)
    # 1) load the latest governorship transcriptions
    if run("scripts/push_jsons_local.py", "--offices", OFFICE, "--no-tui") != 0:
        print("  ! loader returned non-zero — continuing", flush=True)
    # 2) per governor year: void inflated misreads, then rebuild governor results only
    years = governor_years()
    print(f"  governor years present: {years}", flush=True)
    for y in years:
        run("scripts/pick_definitive_results.py", "--zero-inflated", "--year", y, "--commit")
        run("scripts/pick_definitive_results.py", "--build-results", "--year", y,
            "--election", ET, "--commit")
    print(f"=== cycle {n} done ===", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=2 * 3600, help="seconds between cycles (default 7200)")
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = ap.parse_args()

    n = 0
    while True:
        n += 1
        try:
            cycle(n)
        except Exception as e:  # noqa: BLE001 — never let one bad cycle kill the loop
            print(f"  ! cycle {n} error: {e}", flush=True)
        if args.once:
            break
        mins = args.interval // 60
        print(f"--- sleeping {mins} min (next cycle at "
              f"{datetime.fromtimestamp(time.time() + args.interval):%H:%M}) ---", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
