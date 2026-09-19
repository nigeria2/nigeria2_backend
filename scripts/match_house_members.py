"""Match 2023 House of Representatives members to Politician profiles.

High-precision matching:
- Exact token set match within state -> MATCH
- Subset match with federal constituency overlap -> MATCH
- Stricter subset match with >= 3 shared tokens -> MATCH
- Otherwise -> Create clean new Politician profile

Supports --dry-run (default) or --apply.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(backend_dir / ".env")
sys.path.insert(0, str(backend_dir))

from app.db import SessionLocal
from app.geo import state_geo_id
from app.models import HouseMember, Politician, PartyHistory
from sqlalchemy import select

TITLES = {
    'hon', 'honorable', 'honourable', 'rt', 'dr', 'engr', 'chief',
    'alhaji', 'arc', 'barr', 'barrister', 'prince', 'hajiya', 'hajia',
    'sen', 'senator', 'pastor', 'rev', 'reverend', 'elder', 'comrade'
}

def clean_tokens(name: str) -> set[str]:
    clean = re.sub(r'[^\w\s]', ' ', name.lower())
    return {w for w in clean.split() if w not in TITLES and len(w) > 1}

def normalize_const(c: str) -> set[str]:
    clean = re.sub(r'[^\w\s]', ' ', (c or '').lower())
    return {w for w in clean.split() if len(w) > 2 and w not in {'north', 'south', 'east', 'west', 'central', 'federal', 'constituency', 'area', 'lga'}}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply changes to database")
    args = parser.parse_args()

    db = SessionLocal()
    all_pols = db.scalars(select(Politician)).all()
    all_history = db.scalars(select(PartyHistory)).all()

    # Index history by politician_id
    history_by_pol: dict[int, list[PartyHistory]] = {}
    for h in all_history:
        if h.politician_id:
            history_by_pol.setdefault(h.politician_id, []).append(h)

    hms = db.scalars(select(HouseMember).order_by(HouseMember.state, HouseMember.name)).all()

    # Index politicians by state
    state_pols: dict[str, list[tuple[Politician, set[str]]]] = {}
    for p in all_pols:
        st = (p.state or "").strip().lower()
        toks = clean_tokens(p.name)
        state_pols.setdefault(st, []).append((p, toks))
        try:
            akas = json.loads(p.aka or "[]")
            for a in akas:
                state_pols.setdefault(st, []).append((p, clean_tokens(str(a))))
        except Exception:
            pass

    matched_results: list[dict] = []
    unmatched_members: list[HouseMember] = []

    for m in hms:
        st = (m.state or "").strip().lower()
        m_tokens = clean_tokens(m.name)
        m_const_toks = normalize_const(m.constituency)
        candidates = state_pols.get(st, [])

        # Check exact token match
        exact_tok = [p for p, toks in candidates if toks == m_tokens]
        exact_unique = list({p.id: p for p in exact_tok}.values())

        chosen_pol = None
        match_type = ""

        if len(exact_unique) == 1:
            chosen_pol = exact_unique[0]
            match_type = "exact_tokens"
        else:
            # Subset candidates
            subset_cands = []
            for p, toks in candidates:
                if len(m_tokens) >= 2 and len(toks) >= 2:
                    if m_tokens.issubset(toks) or toks.issubset(m_tokens):
                        subset_cands.append(p)
            subset_unique = list({p.id: p for p in subset_cands}.values())

            for p in subset_unique:
                hist = history_by_pol.get(p.id, [])
                h_const_toks = set()
                for h in hist:
                    if h.constituency:
                        h_const_toks.update(normalize_const(h.constituency))
                
                shared_const = m_const_toks.intersection(h_const_toks)
                shared_tokens = m_tokens.intersection(clean_tokens(p.name))

                # Condition 1: Shared constituency in same state
                if shared_const:
                    chosen_pol = p
                    match_type = f"subset+constituency ({'/'.join(shared_const)})"
                    break
                # Condition 2: 3 or more distinctive shared name tokens
                elif len(shared_tokens) >= 3:
                    chosen_pol = p
                    match_type = f"subset+3_tokens ({'/'.join(shared_tokens)})"
                    break

        if chosen_pol:
            matched_results.append({
                "hm": m,
                "pol": chosen_pol,
                "type": match_type,
            })
        else:
            unmatched_members.append(m)

    print(f"Total House Members: {len(hms)}")
    print(f"High-confidence matches to existing Politicians: {len(matched_results)}")
    print(f"New Politician profiles to create: {len(unmatched_members)}")

    if not args.apply:
        print("\n--- SAMPLE AUDIT ---")
        for r in matched_results[:10]:
            m = r["hm"]
            p = r["pol"]
            print(f"[{r['type']}] HM: {m.name} ({m.state}) -> POL {p.id}: {p.name}")
        print("\n[DRY RUN] No changes made to database. Pass --apply to execute.")
        return

    print("\n--- APPLYING CHANGES ---")
    linked_existing = 0
    created_new = 0
    added_history = 0

    # 1. Update matched members
    for r in matched_results:
        m = r["hm"]
        p = r["pol"]
        m.politician_id = p.id
        if not m.state_geo:
            m.state_geo = state_geo_id(m.state)
        linked_existing += 1

        # Check if 2023 house history already exists for this pol
        existing_h = db.scalar(
            select(PartyHistory).where(
                PartyHistory.politician_id == p.id,
                PartyHistory.year == "2023",
                PartyHistory.election_type == "house",
            )
        )
        if not existing_h:
            db.add(PartyHistory(
                politician_id=p.id,
                politician_name=p.name,
                party=m.party or p.party,
                state=p.state or m.state,
                state_geo=p.state_geo or state_geo_id(m.state),
                year="2023",
                election_type="house",
                constituency=m.constituency,
                votes=m.votes or 0,
                position=1,
            ))
            added_history += 1

    # 2. Create new politicians for unmatched members
    for m in unmatched_members:
        geo_id = state_geo_id(m.state)
        pol = Politician(
            name=m.name.strip(),
            state=m.state,
            state_geo=geo_id,
            party=m.party or "",
            title=f"Member, House of Representatives ({m.constituency})",
        )
        db.add(pol)
        db.flush()  # assign pol.id

        m.politician_id = pol.id
        if not m.state_geo:
            m.state_geo = geo_id
        created_new += 1

        db.add(PartyHistory(
            politician_id=pol.id,
            politician_name=pol.name,
            party=m.party or "",
            state=m.state,
            state_geo=geo_id,
            year="2023",
            election_type="house",
            constituency=m.constituency,
            votes=m.votes or 0,
            position=1,
        ))
        added_history += 1

    db.commit()
    print(f"\n[DONE] Successfully linked {linked_existing} existing politicians.")
    print(f"[DONE] Successfully created {created_new} new politician profiles.")
    print(f"[DONE] Successfully recorded {added_history} 2023 House of Reps election victories.")

if __name__ == "__main__":
    main()
