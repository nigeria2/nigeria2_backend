# Senators roster fix (2026-07-24)

## What was wrong

`app/senators_data.py` (seeded once into the `senators` table by `seed_senators()` in
`app/seed.py`, guarded to run only against an empty table) had 13 wrong entries out of 109,
found by cross-checking every row against the site's own `/api/v1/results/2023/{geo_id}`
senate winners:

- **10 rows pointed at an entirely wrong person** — a losing 2023 candidate instead of the
  actual winner. In every case the losing candidate had also been given a fabricated
  `"Senator, {state} {district}"` title on their `Politician` row by the same seeding code,
  falsely claiming an office they never held.
- **3 rows had a stale party/name** even though `Senator.politician_id` already pointed at
  the correct `Politician` — just a denormalized-copy bug.

## What was *not* a bug

`senators_data.py`'s own docstring documents three intentional deviations from the raw 2023
results, for real post-election events:

- **Anambra South** — Emmanuel Nwachukwu won an Aug 2025 by-election after the original
  winner, Ifeanyi Ubah, died.
- **Yobe East** — Musa Mustapha won a Feb 2024 by-election after Ibrahim Gaidam became
  Minister of Police Affairs.
- **Kano Central** — Rufai Hanga defected from NNPP to NDC in May 2026; the roster
  correctly shows his current party, while the 2023 results endpoint (correctly) shows his
  party at the time of the election.

These looked identical to real bugs on a first pass (name/party not matching the 2023
results) and are called out here so a future audit doesn't re-flag them.

## The fix

1. **`app/senators_data.py`** — corrected the 13 entries (see git diff for the exact
   before/after). Fixes fresh/dev seeding going forward; does nothing for an already-seeded
   database, since `seed_senators()` only runs against an empty table.
2. **`migrations/versions/0053_fix_senator_data_errors.py`** — repairs already-seeded data:
   - 3 field-only `UPDATE senators SET name=..., party=...` (the politician_id was already
     right).
   - 10 `UPDATE politicians SET title = ''` (clearing the fabricated senator title off the
     losing candidate) + `UPDATE senators SET politician_id=<correct>, name=..., party=...,
     gender='', age=NULL, terms=NULL` (repointing to the real winner's existing `Politician`
     row, created independently by the election-results ingestion pipeline). `gender`/`age`/
     `terms` are nulled rather than carried over from the wrong person — we have no verified
     data for those fields on the correct senator, so leaving them blank beats fabricating
     them.
   - The correct politician's own title is left untouched in all 10 cases — it was already
     accurate (e.g. `David Umahi` correctly keeps `"Governor of Ebonyi State (2015–2023)"`,
     his prior and more notable role, rather than being overwritten with a generic senator
     title).
   - `downgrade()` is a no-op — the original seed data was wrong, not worth restoring.

Full per-seat table (wrong name/party → correct name/party/politician_id) is in the commit
message and was reviewed as a plan before implementation.

## Verification status

Confirmed locally: migration syntax valid, `alembic heads` resolves to a single head
(`0053`) with no branch conflicts, `app/senators_data.py` still has 109 entries with no
duplicate names.

**Not yet verified**: actually running `alembic upgrade head` against a database — no local
Postgres credentials were available in the dev environment this was built in. Needs to run
against a real dev/staging DB before merging, or will run automatically via the existing
`run_migrations()` call in `app/main.py`'s `lifespan` on deploy. After it runs, spot-check:
- `/api/politicians/88` (Akobundu) — `title` should be `""`, not `"Senator, Abia Central"`.
- `/api/politicians/360` (Onuigbo) — unchanged, `"Senator-elect, Abia Central"`.
- `/api/senators` — the 13 affected seats show the corrected name/party.
