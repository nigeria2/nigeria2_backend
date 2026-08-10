"""fix 13 wrong senator entries

The senators table was seeded once from app/senators_data.py (see seed_senators() in
app/seed.py, guarded to run only against an empty table) with 13 wrong entries: 3 with a
stale party/name (politician_id already correct), and 10 pointing at the wrong person
entirely — a losing 2023 candidate instead of the actual winner. Fixing senators_data.py
alone doesn't touch an already-seeded database, hence this migration. Full rationale for
each seat: see the "Fix wrong senators" plan reviewed 2026-07-24.

Revision ID: 0057
Revises: 0056
Create Date: 2026-07-24

"""
import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (state, district): field-only correction — politician_id already points at the right
# Politician row, only the denormalized name/party copy on the senators row was stale.
_FIELD_FIXES = [
    {"state": "Cross River", "district": "Central", "name": "Eteng Williams", "party": "APC"},
    {"state": "Edo", "district": "South", "name": "Neda Imasuen", "party": "LP"},
    {"state": "Kebbi", "district": "South", "name": "Garba Musa Maidoki", "party": "PDP"},
]

# (state, district): wrong Politician entirely. wrong_politician_id had a fabricated
# "Senator, {state} {district}" title stamped on it by seed_senators() despite losing the
# 2023 race — cleared here. correct_politician_id already exists (created independently by
# the election-results ingestion pipeline) with an accurate title, left untouched.
_IDENTITY_FIXES = [
    {"state": "Abia", "district": "Central", "wrong_politician_id": 88,
     "correct_politician_id": 360, "name": "Samuel Onuigbo", "party": "APC"},
    {"state": "Adamawa", "district": "Central", "wrong_politician_id": 91,
     "correct_politician_id": 372, "name": "Abdul-Aziz Nyako", "party": "APC"},
    {"state": "Adamawa", "district": "North", "wrong_politician_id": 92,
     "correct_politician_id": 374, "name": "Ishaku Elisha Abbo", "party": "APC"},
    {"state": "Ebonyi", "district": "South", "wrong_politician_id": 119,
     "correct_politician_id": 315, "name": "David Umahi", "party": "APC"},
    {"state": "Enugu", "district": "East", "wrong_politician_id": 126,
     "correct_politician_id": 433, "name": "Chimaroke Nnamani", "party": "PDP"},
    {"state": "Jigawa", "district": "South West", "wrong_politician_id": 138,
     "correct_politician_id": 244, "name": "Mustapha Sule Lamido", "party": "PDP"},
    {"state": "Kaduna", "district": "North", "wrong_politician_id": 140,
     "correct_politician_id": 453, "name": "Suleiman Abdu Kwari", "party": "APC"},
    {"state": "Kano", "district": "South", "wrong_politician_id": 144,
     "correct_politician_id": 462, "name": "Kabiru Ibrahim Gaya", "party": "APC"},
    {"state": "Plateau", "district": "North", "wrong_politician_id": 179,
     "correct_politician_id": 502, "name": "Simon Mwadkwon", "party": "PDP"},
    {"state": "Plateau", "district": "South", "wrong_politician_id": 180,
     "correct_politician_id": 504, "name": "Napoleon Bali", "party": "PDP"},
]


def upgrade() -> None:
    conn = op.get_bind()

    for fix in _FIELD_FIXES:
        conn.execute(text("""
            UPDATE senators SET name = :name, party = :party
            WHERE state = :state AND district = :district
        """), fix)

    # politician_id is a hardcoded snapshot taken from production (auto-increment ids are
    # stable for existing rows, but only production's actual history is guaranteed to match
    # these — confirmed against a local test DB seeded from scratch, where the same ids
    # pointed at entirely different people). Refuse to repoint politician_id unless the
    # target row's name matches what we expect, rather than silently mis-attributing data
    # on a database whose seed history doesn't match production's.
    #
    # A plain name == expected check isn't enough: dedupe_politicians() runs on every app
    # startup and can rewrite a politician's canonical `name` to a fuller form while moving
    # the old one into `aka` (observed live: id 315's name became "David Nweze Umahi", with
    # "David Umahi" — this migration's expected value — demoted to aka). So a row counts as
    # matching if the expected name is EITHER the canonical name OR listed in aka.
    for fix in _IDENTITY_FIXES:
        row = conn.execute(
            text("SELECT name, aka FROM politicians WHERE id = :correct_politician_id"), fix
        ).one_or_none()
        correct_name = row[0] if row else None
        try:
            aka_list = json.loads(row[1]) if row and row[1] else []
        except (TypeError, ValueError):
            aka_list = []
        if correct_name != fix["name"] and fix["name"] not in aka_list:
            raise RuntimeError(
                f"politician id {fix['correct_politician_id']} is {correct_name!r} "
                f"(aka {aka_list!r}), expected {fix['name']!r} ({fix['state']} {fix['district']}) — "
                "this database's politician ids don't match the production snapshot "
                "this migration was written against; refusing to repoint senators.politician_id"
            )
        conn.execute(text("UPDATE politicians SET title = '' WHERE id = :wrong_politician_id"), fix)
        conn.execute(text("""
            UPDATE senators
            SET politician_id = :correct_politician_id, name = :name, party = :party,
                gender = '', age = NULL, terms = NULL
            WHERE state = :state AND district = :district
        """), fix)


def downgrade() -> None:
    # the original seed data was wrong; not worth restoring
    pass
