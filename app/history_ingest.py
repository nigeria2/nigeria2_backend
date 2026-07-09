"""Ingest historical election CSVs (1999–2022 governorship & presidential) into the
generic `election_results` table.

The CSVs are heterogeneous — party columns differ per year, winner cells come in
several shapes (`PDP`, `(PDP) NAME`, `NAME (PDP)`, `APGA(NAME)`), some state cells
carry an off-cycle year like `Anambra (2013)`, and the 2007 presidential file is
national-by-candidate rather than per-state. This module normalises all of that
into one row shape: {year, office, state, scores{PARTY: votes}, winner_party,
winner_name, registered_voters, total_votes, source}.
"""
from __future__ import annotations

import csv
import json
import pathlib
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import ElectionResult

# --- canonical states ------------------------------------------------------
_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
    "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba",
    "Yobe", "Zamfara",
]
_STATE_KEY = {re.sub(r"[^a-z]", "", s.lower()): s for s in _STATES}
_STATE_ALIASES = {
    "abuja": "FCT", "fctabuja": "FCT", "fedcaptterr": "FCT",
    "crossrivers": "Cross River", "kastina": "Katsina", "bornu": "Borno",
    "bauch": "Bauchi", "nassarawa": "Nasarawa", "nasarrawa": "Nasarawa",
    "sokto": "Sokoto",
}

# non-party header names (everything else in a header row is treated as a party)
_NON_PARTY = {
    "state", "winner", "regvoters", "registeredvoters", "totvotes", "totalvotes",
    "validvotes", "voteperc", "candidate", "party", "votes", "",
}

# acronym -> full party name (best-effort, for the party pages)
PARTY_NAMES = {
    "PDP": "Peoples Democratic Party", "APC": "All Progressives Congress",
    "ANPP": "All Nigeria Peoples Party", "AD": "Alliance for Democracy",
    "APP": "All Peoples Party", "AC": "Action Congress",
    "ACN": "Action Congress of Nigeria", "APGA": "All Progressives Grand Alliance",
    "LP": "Labour Party", "CPC": "Congress for Progressive Change",
    "NNPP": "New Nigeria Peoples Party", "SDP": "Social Democratic Party",
    "ADC": "African Democratic Congress", "PPA": "Progressive Peoples Alliance",
    "DPP": "Democratic Peoples Party", "NDP": "National Democratic Party",
    "PCP": "Peoples Coalition Party", "PRP": "Peoples Redemption Party",
    "ADP": "Action Democratic Party", "AAC": "African Action Congress",
    "APM": "Allied Peoples Movement", "PDM": "Peoples Democratic Movement",
    "AD-APP": "AD–APP Alliance", "OTHERS": "Other parties",
}


def _norm_party(h: str) -> str:
    h = h.strip().lower()
    if h in ("otherparties", "otherparies", "otherparty", "otherpartis"):
        return "OTHERS"
    return h.upper().replace(" ", "")


def _norm_state(raw: str) -> tuple[str, int | None]:
    """Return (canonical state, off-cycle year or None). Handles 'Anambra (2013)'."""
    year = None
    m = re.search(r"\((\d{4})\)", raw)
    if m:
        year = int(m.group(1))
    s = re.sub(r"\(.*?\)", "", raw).strip()
    s = re.sub(r"\bstate\b", "", s, flags=re.I).strip()
    key = re.sub(r"[^a-z]", "", s.lower())
    return _STATE_ALIASES.get(key) or _STATE_KEY.get(key) or s.title(), year


def _num(v: str) -> int | None:
    if v is None:
        return None
    v = v.strip().replace(",", "").replace(" ", "")
    if v in ("", "-", "–", "nil", "n/a"):
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


_ACRONYM = re.compile(r"^[A-Za-z][A-Za-z]{1,6}$")


def _looks_party(t: str, known: set[str]) -> bool:
    t = t.strip()
    if not t:
        return False
    if t.upper() in known:
        return True
    return " " not in t and bool(_ACRONYM.match(t)) and t.upper() == t


def _parse_winner(raw: str, known: set[str]) -> tuple[str, str]:
    """(winner_party, winner_name). Party derived later from scores if unknown."""
    w = (raw or "").strip()
    if not w:
        return "", ""
    m = re.search(r"\(([^)]*)\)", w)
    if m:
        inside = m.group(1).strip()
        outside = (w[: m.start()] + w[m.end():]).strip()
        if _looks_party(inside, known):
            return _norm_party(inside), outside
        if _looks_party(outside, known):
            return _norm_party(outside), inside
        return _norm_party(inside), outside
    if _looks_party(w, known):
        return _norm_party(w), ""
    return "", w  # a bare name — party comes from the scores


def parse_csv(path: pathlib.Path) -> list[dict]:
    name = path.stem  # e.g. 2013-14gov
    office = "presidential" if name.endswith("pres") else "governor"
    base_year = int(re.match(r"(\d{4})", name).group(1))
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]

    # 2007-style national-by-candidate presidential file
    if "candidate" in header and "party" in header:
        ci, pi, vi = header.index("candidate"), header.index("party"), header.index("votes")
        scores: dict[str, int] = {}
        top_name, top_votes = "", -1
        for r in rows[1:]:
            if len(r) <= max(ci, pi, vi):
                continue
            party = _norm_party(re.sub(r"[()]", "", r[pi]))
            votes = _num(r[vi]) or 0
            scores[party] = scores.get(party, 0) + votes
            if votes > top_votes:
                top_votes, top_name = votes, r[ci].strip()
        winner = max(scores, key=lambda p: scores[p]) if scores else ""
        return [{
            "year": base_year, "office": office, "state": "Nigeria", "scores": scores,
            "registered_voters": None, "total_votes": sum(scores.values()),
            "winner_party": winner, "winner_name": top_name, "source": path.name,
        }]

    party_cols = {i: _norm_party(h) for i, h in enumerate(header) if h not in _NON_PARTY}
    known = {p for p in party_cols.values()} | set(PARTY_NAMES)
    idx = {h: i for i, h in enumerate(header)}
    out = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        state, yr = _norm_state(r[0])
        if state == "Nigeria" or not state:
            continue
        scores = {}
        for i, party in party_cols.items():
            if i < len(r):
                v = _num(r[i])
                if v is not None and v > 0:
                    scores[party] = scores.get(party, 0) + v
        wcol = r[idx["winner"]] if "winner" in idx and idx["winner"] < len(r) else ""
        wp, wn = _parse_winner(wcol, known)
        if wp not in scores and scores:
            # winner col was a number/blank/typo — trust the tally (real party, not OTHERS)
            cand = {p: v for p, v in scores.items() if p != "OTHERS"} or scores
            wp = max(cand, key=lambda p: cand[p])
        reg = _num(r[idx["registeredvoters"]]) if "registeredvoters" in idx and idx["registeredvoters"] < len(r) else None
        if reg is None and "regvoters" in idx and idx["regvoters"] < len(r):
            reg = _num(r[idx["regvoters"]])
        tot = None
        for k in ("totalvotes", "totvotes", "validvotes"):
            if k in idx and idx[k] < len(r):
                tot = _num(r[idx[k]])
                if tot is not None:
                    break
        if tot is None and scores:
            tot = sum(scores.values())
        out.append({
            "year": yr or base_year, "office": office, "state": state, "scores": scores,
            "registered_voters": reg, "total_votes": tot,
            "winner_party": wp, "winner_name": wn.title() if wn and wn.isupper() else wn,
            "source": path.name,
        })
    return out


def seed_election_history(db: Session, data_dir: pathlib.Path) -> int:
    """Ingest every *.csv in `data_dir` into election_results. Idempotent."""
    if db.scalar(select(func.count()).select_from(ElectionResult)):
        return 0
    n = 0
    for path in sorted(data_dir.glob("*.csv")):
        for row in parse_csv(path):
            db.add(ElectionResult(
                year=row["year"], office=row["office"], state=row["state"],
                scores=json.dumps(row["scores"]), registered_voters=row["registered_voters"],
                total_votes=row["total_votes"], winner_party=row["winner_party"],
                winner_name=row["winner_name"] or "", source=row["source"],
            ))
            n += 1
    db.commit()
    return n
