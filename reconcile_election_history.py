"""
Reconciles the mined election-result CSVs in ../data/tables/ against the
`party_history` table in the live database: for each (year, election_type)
scope, existing rows are matched to CSV rows by candidate name (same fuzzy
token-overlap matcher `seed.py` already uses), mismatched fields (votes,
party, percent) are queued as updates, and CSV rows with no match are queued
as inserts via the same `_find_or_create_politician` convention every other
seed_* function in seed.py follows. Existing rows that don't match any CSV
row are left completely alone -- nothing is ever deleted.

Scopes covered:
  - 2019 governor   (existing partial data -> reconcile against tables/2019_governor.csv)
  - 2023 governor   (existing partial data -> reconcile against tables/2023_governor.csv)
  - 2023 senate     (existing partial data -> reconcile against tables/2023_senate.csv)
  - 2019 senate     (currently empty -> fill from tables/2019_senate_inec.csv, the
                      richer INEC-PDF source, not the thinner Wikipedia-derived
                      tables/2019_senate.csv)
  - 2019 house      (currently empty -> fill from tables/2019_house_inec.csv;
                      new election_type, no 2023 equivalent exists yet)
  - 2019 presidential is NOT touched: existing 73 rows already matches the
    known candidate count exactly (same official source), verified by spot
    check rather than blanket reconciliation.

SAFETY: defaults to dry-run (prints the full diff, writes nothing). Pass
--apply to actually commit. Always run without --apply first and read the
report before applying anything to this shared, production database.

Usage:
    python reconcile_election_history.py                 # dry run
    python reconcile_election_history.py --apply          # commit changes
    python reconcile_election_history.py --apply --scope 2019_senate
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import PartyHistory, Politician  # noqa: E402
from app.seed import _find_or_create_politician, _pol_tokens  # noqa: E402

TABLES_DIR = Path(__file__).resolve().parent.parent / "data" / "tables"
PLACEHOLDER_NAMES = {"TBD", "N/A", "UNKNOWN", "TBA", "-"}


def to_int(s: str | None) -> int | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def to_float(s: str | None) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


_PARTY_STOPWORDS = {"of", "the", "for", "a", "and"}


def normalize_party(party: str | None) -> str:
    """The DB stores parties as short acronyms (APC, PDP, ...) throughout, but
    our source CSVs sometimes carry the full registered name instead (mined
    from Wikipedia link text), occasionally exceeding even PartyHistory.party's
    30-char column (let alone Politician.party's 20-char one). Prefer an
    "(ACRONYM)" suffix when the source provides one (guaranteed correct,
    straight from the source); otherwise derive one from initials."""
    party = (party or "").strip()
    if not party:
        return ""
    m = re.search(r"\(([A-Za-z]{1,10})\)\s*$", party)
    if m:
        return m.group(1).upper()
    if len(party) <= 20 and party == party.upper():
        return party
    letters = []
    for w in party.replace("’", "'").split():
        w = re.sub(r"'s$", "", w, flags=re.I)
        w = re.sub(r"[^A-Za-z]", "", w)
        if w and w.lower() not in _PARTY_STOPWORDS:
            letters.append(w[0].upper())
    acronym = "".join(letters)
    return acronym[:20] if acronym else party[:20]


def load_csv(name: str) -> list[dict]:
    path = TABLES_DIR / name
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def names_match(a_tokens: frozenset, b_tokens: frozenset) -> bool:
    """>=2 shared name tokens (or a full subset match for 2-token names). Looser
    than seed.py's global politician matcher on purpose: this only ever compares
    candidates already narrowed to the same state+race, where two genuinely
    different people sharing 2+ name tokens is essentially impossible -- so we
    don't need the subset requirement to guard against cross-state false merges."""
    if not a_tokens or not b_tokens:
        return False
    overlap = a_tokens & b_tokens
    if len(overlap) >= 2:
        return True
    return bool(overlap) and (a_tokens <= b_tokens or b_tokens <= a_tokens)


class Scope:
    def __init__(self, year: str, election_type: str, csv_rows: list[dict],
                 state_field: str = "state", constituency_field: str | None = None,
                 candidate_field: str = "candidate"):
        self.year = year
        self.election_type = election_type
        self.csv_rows = csv_rows
        self.state_field = state_field
        self.constituency_field = constituency_field
        self.candidate_field = candidate_field


def reconcile(db, scope: Scope):
    """Returns (inserts, updates, unmatched_existing).
    inserts: list of csv row dicts (with state/constituency already resolved)
    updates: list of (PartyHistory row, field, old, new)
    unmatched_existing: list of PartyHistory rows with no CSV counterpart
    """
    existing = db.scalars(
        select(PartyHistory).where(
            PartyHistory.year == scope.year, PartyHistory.election_type == scope.election_type
        )
    ).all()

    def group_key_db(r: PartyHistory) -> tuple[str, str]:
        return (r.state, r.constituency if scope.constituency_field else "")

    def group_key_csv(r: dict) -> tuple[str, str]:
        return (r[scope.state_field], r.get(scope.constituency_field, "") if scope.constituency_field else "")

    existing_by_group: dict[tuple[str, str], list[PartyHistory]] = defaultdict(list)
    for r in existing:
        existing_by_group[group_key_db(r)].append(r)

    csv_by_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
    skipped_placeholder = 0
    for r in scope.csv_rows:
        name = (r.get(scope.candidate_field) or "").strip()
        if not name or name.upper() in PLACEHOLDER_NAMES:
            skipped_placeholder += 1
            continue
        csv_by_group[group_key_csv(r)].append(r)
    if skipped_placeholder:
        print(f"  (skipped {skipped_placeholder} placeholder row(s) with no real candidate name, e.g. 'TBD')")

    inserts: list[dict] = []
    updates: list[tuple] = []
    unmatched_existing: list[PartyHistory] = []
    name_mismatches: list[tuple] = []  # (db_row, csv_row) matched only by votes -- name spelling differs

    all_groups = set(existing_by_group) | set(csv_by_group)
    for key in all_groups:
        pool = list(existing_by_group.get(key, []))
        used = [False] * len(pool)
        pool_tokens = [_pol_tokens(r.politician_name) for r in pool]
        unresolved_csv_rows = []

        # Pass 1: fuzzy name-token match (same as _find_or_create_politician's logic).
        for row in csv_by_group.get(key, []):
            candidate = row[scope.candidate_field].strip()
            ct = _pol_tokens(candidate)
            match_idx = None
            for i, pt in enumerate(pool_tokens):
                if not used[i] and names_match(ct, pt):
                    match_idx = i
                    break
            if match_idx is not None:
                used[match_idx] = True
                _queue_field_updates(pool[match_idx], row, updates)
            else:
                unresolved_csv_rows.append(row)

        # Pass 2: exact-votes fallback for names that didn't token-match (nicknames,
        # missing middle names, spelling variants) -- vote count is close to a unique
        # fingerprint within a single race, so an exact match here is strong evidence
        # it's the same result under a different name spelling, not a new candidate.
        remaining_csv = []
        for row in unresolved_csv_rows:
            votes = to_int(row.get("votes"))
            match_idx = None
            if votes is not None and votes > 0:
                for i, r in enumerate(pool):
                    if not used[i] and r.votes == votes:
                        match_idx = i
                        break
            if match_idx is not None:
                used[match_idx] = True
                name_mismatches.append((pool[match_idx], row))
                _queue_field_updates(pool[match_idx], row, updates)
            else:
                remaining_csv.append(row)

        # Pass 3: same party + >=1 shared name token, for candidates with no votes
        # to fall back on (many minor candidates are recorded with 0). A party only
        # ever fields one candidate per race, so same-party + any shared token
        # within the same state+race is still strong evidence of the same person
        # (e.g. "Laz Ogbe" in the DB vs "Lazarus Ogbe" in the CSV, both PDP, Ebonyi).
        final_csv = []
        for row in remaining_csv:
            candidate = row[scope.candidate_field].strip()
            ct = _pol_tokens(candidate)
            party = normalize_party(row.get("party")).lower()
            match_idx = None
            if party:
                for i, r in enumerate(pool):
                    if used[i] or normalize_party(r.party).lower() != party:
                        continue
                    if ct & pool_tokens[i]:
                        match_idx = i
                        break
            if match_idx is not None:
                used[match_idx] = True
                name_mismatches.append((pool[match_idx], row))
                _queue_field_updates(pool[match_idx], row, updates)
            else:
                final_csv.append(row)
        remaining_csv = final_csv

        inserts.extend(remaining_csv)
        for i, used_flag in enumerate(used):
            if not used_flag:
                unmatched_existing.append(pool[i])

    return inserts, updates, unmatched_existing, name_mismatches


def _queue_field_updates(db_row: PartyHistory, row: dict, updates: list[tuple]) -> None:
    votes = to_int(row.get("votes"))
    party = normalize_party(row.get("party"))
    percent = to_float(row.get("percent"))
    if votes is not None and votes != db_row.votes:
        updates.append((db_row, "votes", db_row.votes, votes))
    if party and party != normalize_party(db_row.party):
        updates.append((db_row, "party", db_row.party, party))
    if percent is not None and db_row.percent is None:
        updates.append((db_row, "percent", db_row.percent, percent))


def apply_inserts(db, scope: Scope, inserts: list[dict], politician_cache: dict) -> int:
    n = 0
    for row in inserts:
        state = row[scope.state_field]
        candidate = row[scope.candidate_field].strip()
        party = normalize_party(row.get("party"))
        votes = to_int(row.get("votes")) or 0
        percent = to_float(row.get("percent"))
        constituency = row.get(scope.constituency_field, "") if scope.constituency_field else ""
        title = f"{scope.year} {scope.election_type} candidate ({party})" if party else f"{scope.year} {scope.election_type} candidate"
        pol = _find_or_create_politician(db, politician_cache, candidate, state, party, title)
        db.add(PartyHistory(
            politician_id=pol.id, politician_name=candidate, party=party, state=state,
            year=scope.year, election_type=scope.election_type, votes=votes,
            position=0, percent=percent, constituency=constituency or "",
        ))
        n += 1
    return n


def apply_updates(updates: list[tuple]) -> int:
    for db_row, field, _old, new in updates:
        setattr(db_row, field, new)
    return len(updates)


def report_scope(label: str, inserts: list[dict], updates: list[tuple], unmatched: list,
                  name_mismatches: list[tuple], candidate_field: str) -> None:
    print(f"\n=== {label} ===")
    print(f"  {len(inserts)} to insert, {len(updates)} field(s) to update, "
          f"{len(name_mismatches)} matched by votes only (name spelling differs), "
          f"{len(unmatched)} existing rows unmatched (left alone)")
    if inserts:
        print("  sample inserts:")
        for row in inserts[:5]:
            print(f"    + {row.get('state')} | {row[candidate_field].strip()} ({row.get('party')}) votes={row.get('votes')}")
    if updates:
        print("  sample updates:")
        for db_row, field, old, new in updates[:5]:
            print(f"    ~ {db_row.state} | {db_row.politician_name}: {field} {old!r} -> {new!r}")
    if name_mismatches:
        print("  sample vote-matched name variants (DB name kept as-is, not renamed):")
        for db_row, row in name_mismatches[:8]:
            print(f"    = {db_row.state} | DB: {db_row.politician_name!r}  <->  CSV: {row[candidate_field].strip()!r} (votes={db_row.votes})")
    if unmatched:
        print("  sample unmatched existing (not touched):")
        for r in unmatched[:5]:
            print(f"    ? {r.state} | {r.politician_name} ({r.party}) votes={r.votes}")


def build_scopes() -> list[Scope]:
    return [
        Scope("2019", "governor", load_csv("2019_governor.csv")),
        Scope("2023", "governor", load_csv("2023_governor.csv")),
        Scope("2023", "senate", load_csv("2023_senate.csv"), constituency_field="district"),
        Scope("2019", "senate", load_csv("2019_senate_inec.csv"), constituency_field="district", candidate_field="candidate"),
        Scope("2019", "house", load_csv("2019_house_inec.csv"), constituency_field="constituency", candidate_field="candidate"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry run)")
    parser.add_argument("--scope", default=None, help="Only run one scope, e.g. 2019_senate")
    args = parser.parse_args()

    if SessionLocal is None:
        print("DATABASE_URL is not configured (check backend/.env)")
        return 1

    db = SessionLocal()
    try:
        scopes = build_scopes()
        if args.scope:
            scopes = [s for s in scopes if f"{s.year}_{s.election_type}" == args.scope]
            if not scopes:
                print(f"Unknown scope: {args.scope}")
                return 1

        total_inserts = total_updates = 0
        politician_cache: dict = {}
        for p in db.scalars(select(Politician)).all():
            politician_cache[(p.name.strip().lower(), p.state)] = p

        for scope in scopes:
            inserts, updates, unmatched, name_mismatches = reconcile(db, scope)
            label = f"{scope.year} {scope.election_type}"
            report_scope(label, inserts, updates, unmatched, name_mismatches, scope.candidate_field)
            total_inserts += len(inserts)
            total_updates += len(updates)

            if args.apply:
                n_ins = apply_inserts(db, scope, inserts, politician_cache)
                n_upd = apply_updates(updates)
                db.commit()
                print(f"  APPLIED: {n_ins} inserted, {n_upd} field updates committed.")

        print(f"\n=== TOTAL ===\n{total_inserts} rows to insert, {total_updates} field updates, across {len(scopes)} scope(s).")
        if not args.apply:
            print("\nDRY RUN ONLY -- nothing was written. Re-run with --apply to commit.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
