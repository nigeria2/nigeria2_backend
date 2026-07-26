#!/usr/bin/env python
"""Load the 2023 crosschecked/unsure transcriptions as polling-unit EVIDENCE.

Source: data/2023_data/{STATE}_crosschecked.csv and {STATE}_unsure.csv — the human-
crosschecked 2023 PRESIDENTIAL dataset (APC/LP/PDP/NNPP votes + accredited/registered
voters per polling unit). Each row becomes one piece of evidence:

    kind          = '2023_transcription'
    source        = '2023_transcription'
    election_type = 'presidential'   (this dataset is presidential only)
    method        = 'crosscheck'  (from *_crosschecked.csv) | 'unsure' (from *_unsure.csv)
    confidence    = 90 (crosschecked) | 70 (unsure)      <-- based on the FILE it came from
    + evidence_parties rows for APC / LP / PDP / NNPP

CONFIDENCE comes from the filename: rows in an *_unsure.csv score 70, everything else
(the *_crosschecked.csv rows) scores 90.

PU codes in the CSV use dashes (01-01-01-001); the DB uses slashes (01/01/01/001) — we
convert. state_geo is resolved from the State column.

IDEMPOTENT: deletes ALL existing kind='2023_transcription' evidence (+ its party rows)
first, then reloads — so re-running replaces rather than duplicates, and also backfills
confidence onto any previously-loaded rows.

Run LOCALLY against $DATABASE_URL. Dry-run prints what it WOULD load; --commit writes.

    python -m scripts.load_2023_transcriptions            # dry run
    python -m scripts.load_2023_transcriptions --commit   # write
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select, text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app import geo  # noqa: E402
from app.models import Evidence, EvidenceParty  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "2023_data"
PARTIES = ["APC", "LP", "PDP", "NNPP"]

CONF_CROSSCHECKED = 90
CONF_UNSURE = 70


def _int(v):
    """Parse an int cell; blank/garbage -> None; negatives -> None."""
    s = str(v or "").strip()
    if not s or not re.fullmatch(r"-?\d+", s):
        return None
    n = int(s)
    return n if n >= 0 else None


def _code(csv_code: str) -> str:
    """CSV PU-Code '01-01-01-001' -> DB pu_code '01/01/01/001'."""
    return (csv_code or "").strip().replace("-", "/")


def _rows_from(path: Path, method: str, confidence: int, geo_cache: dict):
    """Yield (pu_code, state_geo, reg, acc, valid, parties[list], method, confidence)
    for each usable row in one CSV. Skips rows with no code or no result found."""
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = _code(row.get("PU-Code", ""))
            if not code or code.count("/") != 3:
                continue
            if str(row.get("Results_Found", "")).strip().lower() not in ("true", "1", "yes"):
                continue
            state = (row.get("State") or "").strip()
            if state not in geo_cache:
                geo_cache[state] = geo.state_geo_id(state) if state else None
            parties = [(p, _int(row.get(p))) for p in PARTIES]
            # keep only parties with a real figure; drop the row if none present
            parties = [(p, v) for p, v in parties if v is not None]
            if not parties:
                continue
            valid = sum(v for _, v in parties)
            yield {
                "pu_code": code, "state_geo": geo_cache[state],
                "registered_voters": _int(row.get("Registered_Voters")),
                "accredited_voters": _int(row.get("Accredited_Voters")),
                "valid_votes": valid, "method": method, "confidence": confidence,
                "parties": parties,
            }


def _collect():
    """All usable evidence rows across every state's crosschecked + unsure CSVs.
    Crosschecked wins if a PU appears in both (higher confidence)."""
    if not DATA_DIR.is_dir():
        sys.exit(f"no such data dir: {DATA_DIR}")
    geo_cache: dict[str, str | None] = {}
    by_code: dict[str, dict] = {}
    # load unsure first, then crosschecked overwrites (so crosschecked's 90 wins a dup)
    for path in sorted(DATA_DIR.glob("*_unsure.csv")):
        for r in _rows_from(path, "unsure", CONF_UNSURE, geo_cache):
            by_code[r["pu_code"]] = r
    for path in sorted(DATA_DIR.glob("*_crosschecked.csv")):
        for r in _rows_from(path, "crosscheck", CONF_CROSSCHECKED, geo_cache):
            by_code[r["pu_code"]] = r
    return list(by_code.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="write to the DB (default: dry run)")
    args = ap.parse_args()

    rows = _collect()
    n_cross = sum(1 for r in rows if r["method"] == "crosscheck")
    n_unsure = sum(1 for r in rows if r["method"] == "unsure")
    print(f"Usable 2023 presidential transcription rows: {len(rows):,}")
    print(f"  crosschecked (confidence {CONF_CROSSCHECKED}): {n_cross:,}")
    print(f"  unsure       (confidence {CONF_UNSURE}): {n_unsure:,}")

    db = SessionLocal() if SessionLocal else None
    if db is None:
        sys.exit("DATABASE_URL not set — aborting.")
    try:
        existing = db.execute(text(
            "SELECT count(*) FROM evidence WHERE kind='2023_transcription'")).scalar()
        print(f"Existing kind='2023_transcription' evidence (will be replaced): {existing:,}")

        if not args.commit:
            for r in rows[:4]:
                print(f"  e.g. {r['pu_code']} conf={r['confidence']} valid={r['valid_votes']} "
                      f"parties={r['parties']}")
            print("\nDRY RUN — no writes. Re-run with --commit.")
            return

        # 1) wipe prior 2023_transcription evidence (+ children) via subquery
        print("\nClearing prior 2023_transcription evidence...")
        idq = select(Evidence.id).where(Evidence.kind == "2023_transcription")
        db.execute(delete(EvidenceParty).where(EvidenceParty.evidence_id.in_(idq)))
        db.execute(delete(Evidence).where(Evidence.kind == "2023_transcription"))
        db.flush()

        # 2) bulk insert evidence rows
        print(f"Inserting {len(rows):,} evidence rows...")
        db.bulk_insert_mappings(Evidence, [{
            "pu_code": r["pu_code"], "election_type": "presidential", "year": "2023",
            "state_geo": r["state_geo"], "kind": "2023_transcription",
            "source": "2023_transcription", "method": r["method"],
            "registered_voters": r["registered_voters"],
            "accredited_voters": r["accredited_voters"], "valid_votes": r["valid_votes"],
            "confidence": r["confidence"],
        } for r in rows])
        db.flush()

        # 3) map (pu_code) -> new evidence id, then bulk insert party rows
        id_by_code = dict(db.execute(select(Evidence.pu_code, Evidence.id).where(
            Evidence.kind == "2023_transcription")).all())
        party_maps = []
        for r in rows:
            eid = id_by_code.get(r["pu_code"])
            if eid is None:
                continue
            for p, v in r["parties"]:
                party_maps.append({"evidence_id": eid, "party": p, "votes": v})
        print(f"Inserting {len(party_maps):,} party rows...")
        db.bulk_insert_mappings(EvidenceParty, party_maps)
        db.commit()

        print("\nDone. Distribution:")
        for conf, n in db.execute(text(
                "SELECT confidence, count(*) FROM evidence WHERE kind='2023_transcription' "
                "GROUP BY confidence ORDER BY confidence")).all():
            print(f"  confidence {conf}: {n:,}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
