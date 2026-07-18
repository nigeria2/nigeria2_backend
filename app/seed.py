"""Seed the predictions table with illustrative, already-aggregated data.

Real data would be crunched from raw contributor traces upstream; this just
gives the map something to render across weeks and election types.
"""
import csv
import difflib
import gzip
import hashlib
import itertools
import json
import pathlib
import re
from collections import defaultdict

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .data_2023 import PAST_ELECTION_2023
from .lga_2023 import LGA_RESULTS_2023
from .models import Analysis, ElectionSheet, Governor, GovernorHistory, HouseMember, Lga, LegislativeResult, LgaPartyResult, LgaResult, Party, PartyElection, PartyHistory, PollingUnit, Politician, PoliticianAssessment, PoliticianPhoto, Prediction, ProblemUnit, Senator, State, StatePrediction, StatePresidential, Ward, WardResult
from .senators_data import SENATORS
from .state_data import STATE_DATA

# Bump when the seed logic changes so deployments refresh the illustrative data.
SEED_VERSION = 3

# Parties in play per election type (order = display order on sliders/maps).
PARTY_ORDER = ["APC", "PDP", "LP", "NNPP", "APGA", "SDP"]  # governor / senate
PRES_PARTIES = ["APC", "PDP", "NDC", "NNPP", "ADC", "LP"]  # presidential


def _pool(election_type: str) -> list[str]:
    return PRES_PARTIES if election_type == "presidential" else PARTY_ORDER

WEEKS = ["2026-06-08", "2026-06-15", "2026-06-22", "2026-06-29", "2026-07-06"]

# Base leanings (latest week): state -> {governor: (party, pct), presidential: (party, pct)}
BASE = {
    "Sokoto": (("APC", 47), ("APC", 52)), "Zamfara": (("PDP", 42), ("APC", 45)), "Katsina": (("APC", 50), ("APC", 55)),
    "Kano": (("NNPP", 43), ("NNPP", 49)), "Jigawa": (("APC", 47), ("APC", 50)), "Yobe": (("APC", 56), ("APC", 61)),
    "Borno": (("APC", 58), ("APC", 60)), "Kebbi": (("APC", 53), ("APC", 56)), "Niger": (("APC", 46), ("APC", 48)),
    "Kaduna": (("APC", 41), ("APC", 44)), "Bauchi": (("PDP", 44), ("APC", 43)), "Gombe": (("APC", 49), ("APC", 52)),
    "Adamawa": (("PDP", 41), ("PDP", 45)), "Kwara": (("APC", 48), ("APC", 50)), "FCT": (("LP", 40), ("LP", 59)),
    "Plateau": (("PDP", 43), ("LP", 47)), "Nasarawa": (("APC", 42), ("LP", 41)), "Taraba": (("PDP", 44), ("PDP", 46)),
    "Kogi": (("APC", 45), ("APC", 47)), "Benue": (("APC", 39), ("LP", 44)), "Oyo": (("PDP", 46), ("APC", 44)),
    "Osun": (("PDP", 46), ("APC", 43)), "Ekiti": (("APC", 51), ("APC", 54)), "Ondo": (("APC", 49), ("APC", 52)),
    "Ogun": (("APC", 47), ("APC", 46)), "Lagos": (("APC", 44), ("LP", 47)), "Edo": (("PDP", 42), ("LP", 45)),
    "Enugu": (("LP", 44), ("LP", 63)), "Ebonyi": (("APC", 46), ("LP", 52)), "Anambra": (("APGA", 47), ("LP", 60)),
    "Imo": (("APC", 41), ("LP", 55)), "Abia": (("LP", 45), ("LP", 66)), "Delta": (("PDP", 48), ("PDP", 50)),
    "Bayelsa": (("PDP", 55), ("PDP", 58)), "Rivers": (("PDP", 49), ("PDP", 47)), "Akwa Ibom": (("PDP", 52), ("PDP", 54)),
    "Cross River": (("APC", 43), ("APC", 44)),
}


def _rand(*parts) -> float:
    """Deterministic pseudo-random in [0, 1) from the given key parts."""
    h = hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _base_scores(leader: str, pct: int, pool: list[str]) -> dict[str, float]:
    others = [p for p in pool if p != leader][:3]
    rem = 100 - pct
    scores = {leader: float(pct)}
    for p, frac in zip(others, (0.5, 0.3, 0.2)):
        scores[p] = round(rem * frac, 1)
    return scores


def _rows():
    n = len(WEEKS)
    for state, (gov, pres) in BASE.items():
        types = {
            "governor": gov,
            "presidential": pres,
            "senate": (gov[0], max(36, gov[1] - 2)),  # senate tracks the governorship, slightly softer
        }
        for etype, (leader, pct) in types.items():
            base = _base_scores(leader, pct, _pool(etype))
            for wi, week in enumerate(WEEKS):
                # latest week == base leanings; earlier weeks drift more, so the
                # leader flips in genuinely close states as you step back in time.
                factor = (n - 1 - wi) / (n - 1)
                raw = {p: max(1.0, s + (_rand(state, etype, p, wi) - 0.5) * 30 * factor) for p, s in base.items()}
                total = sum(raw.values())
                for party, v in raw.items():
                    yield Prediction(
                        state=state,
                        election_type=etype,
                        party=party,
                        score=round(v / total * 100, 1),
                        measurement_week=week,
                    )


def seed_predictions(db: Session) -> int:
    """Seed illustrative predictions once. Preserves admin-tuned values on later
    startups (admins set the official per-week numbers from the admin panel)."""
    if db.scalar(select(func.count()).select_from(Prediction)):
        return 0
    rows = list(_rows())
    db.add_all(rows)
    db.commit()
    return len(rows)


CONTRIBUTORS = [
    ("Amaka Okafor", "amaka.o@gmail.com"), ("Ibrahim Musa", "i.musa@gmail.com"),
    ("Chidi Eze", "chidi.eze@gmail.com"), ("Funke Adeyemi", "funke.a@gmail.com"),
    ("Tari Briggs", "tari.b@gmail.com"), ("Nneka Obi", "nneka.obi@gmail.com"),
    ("Sadiq Bello", "sadiq.b@gmail.com"), ("Grace Emmanuel", "grace.e@gmail.com"),
    ("Yusuf Aliyu", "yusuf.a@gmail.com"), ("Blessing Peter", "blessing.p@gmail.com"),
    ("Halima Sani", "halima.s@gmail.com"), ("Tunde Bakare", "tunde.b@gmail.com"),
]

NOTES = [
    "Security is the deciding issue on the ground.",
    "Cost of living is driving the mood here.",
    "Strong youth turnout expected.",
    "Infrastructure and jobs dominate local talk.",
    "Incumbent still has a solid ground game.",
    "Momentum is shifting week on week.",
    "Federal-control debate is front and centre.",
    "Turnout looks soft in the rural wards.",
]

ETYPES = ["governor", "presidential", "senate"]
DISTRICTS = ["Central", "North", "South", "East", "West"]


def _analysis_rows():
    states = list(BASE.keys())
    for wi, week in enumerate(WEEKS):
        for k in range(7):
            st = states[int(_rand("astate", wi, k) * len(states))]
            et = ETYPES[int(_rand("aet", wi, k) * len(ETYPES))]
            leader, pct = BASE[st][1] if et == "presidential" else BASE[st][0]
            base = _base_scores(leader, pct, _pool(et))
            scores = {p: max(1, round(s + (_rand("asc", st, et, p, wi, k) - 0.5) * 20)) for p, s in base.items()}
            lead = max(scores, key=lambda p: scores[p])
            name, email = CONTRIBUTORS[int(_rand("ac", wi, k) * len(CONTRIBUTORS))]
            district = f"{st} {DISTRICTS[int(_rand('asd', wi, k) * len(DISTRICTS))]}" if et == "senate" else ""
            yield Analysis(
                contributor_name=name,
                contributor_email=email,
                election_type=et,
                state=st,
                lga="",
                senatorial_district=district,
                leading_party=lead,
                scores=json.dumps(scores),
                notes=NOTES[int(_rand("an", wi, k) * len(NOTES))],
                measurement_week=week,
            )


def seed_analyses(db: Session) -> int:
    """Seed sample analyses once; preserves any real user submissions."""
    if db.scalar(select(func.count()).select_from(Analysis)):
        return 0
    rows = list(_analysis_rows())
    db.add_all(rows)
    db.commit()
    return len(rows)


# --- registered political parties (INEC) and their national officials ---
# fields: acronym, name, chairman, secretary, treasurer, financial_secretary, legal_adviser, address
PARTIES_DATA = [
    ("AA", "Action Alliance", "Hon. Adekunle Rufai Omoaje (by court order)", "Miller C. Orgwu (by court order)", "Sani Darma (by court order)", "", "", ""),
    ("A", "Accord", "Bar. Maxwell Mgbudem", "Hon. Adebukola Abiola Ajaja", "Salaudeen Abdulazeez Oyeniyi", "Hon (Mrs) Margret Elabo", "", ""),
    ("NRM", "National Rescue Movement", "Prince (Dr) Chinedu Obi", "Alh. Hassan Aminu Ibrahim", "Shedrach Oka", "Rev. Emmanuel Olorunmagba", "", ""),
    ("LP", "Labour Party", "", "", "", "", "", ""),
    ("BP", "Boot Party", "Adenuga Sunday", "Egwuatu Maryann C.", "", "Evelyn Oshevire", "", "House 11 Road C1 F.H.A"),
    ("APP", "Action Peoples Party", "Uchenna Nnadi", "Abu Ibrahim Sossan", "Chioma Okoli", "Clement Christian", "Peter Abang", ""),
    ("APM", "Allied Peoples Movement", "Yusuf Mamman Dantalle", "Oyadeyi Ayodele Adebayo", "Zavvalo Badon", "Labarin Yunusa", "", ""),
    ("APGA", "All Progressives Grand Alliance", "Barrister Sylvester Ezeokenwa", "Ibrahim Mani", "Engr. Uche Onyemere", "Alhaji Habibu Aliyu", "", ""),
    ("APC", "All Progressives Congress", "Prof. Nentawe Yilwatda Goshwe", "Sen. Surajudeen Ajibola Basiru PhD, BL", "Mr. Uguru Mathew Ofoke", "Alh. Bashir", "", ""),
    ("ADP", "Action Democratic Party", "Engr. Yabagi Yusuf Sani", "Victor Fingesi", "Pst. Okey Udoh", "Mustapha Muhammad Gado", "", ""),
    ("ADC", "African Democratic Congress", "Sen. David Mark", "Ogbeni Rauf Aregbesola", "Dr. Mani Ibrahim Ahmad", "Akibu Dalhatu", "", ""),
    ("AAC", "African Action Congress", "Omoyele Sowore", "Oshiokhue Philip Ikpeminoghena", "Erupre Gift Precious", "Faith Enattah Orinya", "Inibehe Effiong", ""),
    ("NDP", "National Democratic Party", "Hon. Ada Elizabeth Fredrick Okwori (by court order)", "Mr. Silva", "", "", "", ""),
    ("NDC", "Nigeria Democratic Congress", "Sen. Cleopas Moses Zuwoghe (by court order)", "Barr. Ikenna", "", "", "", ""),
    ("DLA", "Democratic Leadership Alliance", "Barr. Samuel M. Memeh (Ag.)", "Grace E. Obekpa", "Anene N. Mirian", "Umar Shehu Aliyu", "", ""),
    ("ZLP", "Zenith Labour Party", "Chief Dan Nwanyanwu", "Yahaya Makama", "Hassana El Abdullahi", "Hon. Mrs Francisca Effiom", "", ""),
    ("YP", "Youth Party", "Dr. Umar Muhammed (Ag.)", "Mrs Helen Adoh (Ag.)", "Mr. Ifeanyi Nwoye", "Mr. Abiodun (Ag.)", "", ""),
    ("YPP", "Young Progressive Party", "Comrade Bishop Amakiri", "Barr. Vidiyeno Bamaiyi", "Usman Haruna", "Azeez Adewale Ahmed", "Tanze", ""),
    ("SDP", "Social Democratic Party", "Prof. Sadiq Umar Abubakar Gombe", "Dr. Olu Agunloye", "Hajia Maggie Mariam", "Mr. Bello Ado Huseni", "", ""),
    ("PRP", "Peoples Redemption Party", "Dr. Hakeem Baba-Ahmed", "Mr. Kanu Sunday Uchenna", "Dr. Bayawo Yunusa Abdullahi", "Mr. Chuka Patrick", "", ""),
    ("PDP", "Peoples Democratic Party", "Hon. Abdulrahman Mohammed", "Senator Samuel Anyanwu", "Odeyemei Mackson Oladiran", "Eyim Donatus Henry", "", ""),
    ("NNPP", "New Nigeria Peoples Party", "Dr. Agbo Gilbert Major", "Com. Olaposi Sunday Oginni", "Prince Adetoyese Omokanye", "Mr. Anthony Kelechi", "", ""),
]

# Which parties are considered relevant for each election type.
PARTY_ELECTIONS = {
    "presidential": PRES_PARTIES,
    "governor": PARTY_ORDER,
    "senate": PARTY_ORDER,
}


def seed_parties(db: Session) -> int:
    """Seed the registered parties once."""
    if db.scalar(select(func.count()).select_from(Party)):
        return 0
    for acr, name, chair, sec, treas, fin, legal, addr in PARTIES_DATA:
        db.add(Party(
            acronym=acr, name=name, chairman=chair, secretary=sec,
            treasurer=treas, financial_secretary=fin, legal_adviser=legal, address=addr,
        ))
    db.commit()
    return len(PARTIES_DATA)


def seed_party_elections(db: Session) -> int:
    """Seed the party-to-election-type relevance mapping once."""
    if db.scalar(select(func.count()).select_from(PartyElection)):
        return 0
    n = 0
    for etype, acronyms in PARTY_ELECTIONS.items():
        for acr in acronyms:
            db.add(PartyElection(party_acronym=acr, election_type=etype))
            n += 1
    db.commit()
    return n


# --- 2023 problem polling units (flagged anomalies) ---
PU_LGAS = {
    "Rivers": ["Port Harcourt", "Obio/Akpor", "Emohua", "Ikwerre"],
    "Lagos": ["Alimosho", "Kosofe", "Ojo", "Amuwo-Odofin"],
    "Kano": ["Kano Municipal", "Nassarawa", "Ungogo", "Gwale"],
    "Kaduna": ["Kaduna North", "Zaria", "Chikun", "Igabi"],
    "Imo": ["Owerri Municipal", "Orlu", "Okigwe", "Mbaitoli"],
    "Anambra": ["Onitsha North", "Idemili North", "Awka South", "Nnewi North"],
    "Akwa Ibom": ["Uyo", "Ikot Ekpene", "Eket", "Oron"],
    "Delta": ["Warri South", "Ughelli North", "Oshimili South", "Sapele"],
    "Benue": ["Makurdi", "Gboko", "Otukpo", "Katsina-Ala"],
    "Plateau": ["Jos North", "Jos South", "Barkin Ladi", "Riyom"],
    "Enugu": ["Enugu North", "Nsukka", "Udi", "Enugu East"],
    "Bayelsa": ["Yenagoa", "Sagbama", "Nembe", "Brass"],
    "Ebonyi": ["Abakaliki", "Afikpo North", "Ohaozara", "Izzi"],
    "Cross River": ["Calabar Municipal", "Ogoja", "Ikom", "Obudu"],
    "Sokoto": ["Sokoto North", "Wamako", "Bodinga", "Tambuwal"],
    "Borno": ["Maiduguri", "Jere", "Konduga", "Bama"],
}
PU_PLACES = [
    "Central Primary School", "Town Hall", "Community Secondary School", "Health Centre",
    "Open Space by Market", "Village Square", "Model Primary School", "District Head's Compound",
    "Motor Park", "Civic Centre", "Ward Council Office", "St. Mary's School",
]
ANOMALY_TYPES = [
    ("Over-voting", "Total votes cast exceeded the number of accredited voters recorded on the BVAS."),
    ("Turnout over 100%", "Accredited voters exceeded the registered voters on the roll for this unit."),
    ("Votes exceed registration", "Total votes surpassed the number of registered voters."),
    ("Single-party sweep", "One party recorded almost all votes while every other party polled zero."),
    ("IReV portal mismatch", "The announced result differed materially from the result sheet uploaded to IReV."),
    ("Turnout spike", "Turnout was far above the ward, LGA and national averages."),
]
_HIGH = {"Over-voting", "Turnout over 100%", "Votes exceed registration", "Single-party sweep"}


def _pu_rows():
    idx = 0
    for si, state in enumerate(PU_LGAS.keys()):
        lgas = PU_LGAS[state]
        for k in range(3):  # a few flagged units per state
            atype, desc = ANOMALY_TYPES[(si + k) % len(ANOMALY_TYPES)]
            reg = 400 + int(_rand("pureg", state, k) * 800)
            if atype in ("Turnout over 100%", "Votes exceed registration"):
                acc = reg + 25 + int(_rand("puacc", state, k) * 220)
                votes = acc
            elif atype == "Over-voting":
                acc = int(reg * (0.5 + _rand("puacc2", state, k) * 0.35))
                votes = acc + 40 + int(_rand("puov", state, k) * 200)
            else:
                acc = int(reg * (0.82 + _rand("puacc3", state, k) * 0.15))
                votes = acc
            ward = f"Ward {(k + si) % 12 + 1:02d}"
            lga = lgas[k % len(lgas)]
            pu = f"{PU_PLACES[idx % len(PU_PLACES)]}"
            code = f"{20 + si % 30:02d}/{10 + k:02d}/{5 + k:02d}/{idx * 7 % 30 + 1:03d}"
            yield ProblemUnit(
                state=state, lga=lga, ward=ward, polling_unit=pu, pu_code=code,
                anomaly_type=atype, severity=("High" if atype in _HIGH else "Medium"),
                description=desc, registered_voters=reg, accredited_voters=acc,
                votes_cast=votes, election_year="2023",
            )
            idx += 1


def seed_problem_units(db: Session) -> int:
    """Seed illustrative flagged polling units once."""
    if db.scalar(select(func.count()).select_from(ProblemUnit)):
        return 0
    rows = list(_pu_rows())
    db.add_all(rows)
    db.commit()
    return len(rows)


# --- shared per-state predictions board ---
def _state_prediction_rows():
    # The "Past Election" expert opinion: the verified 2023 presidential result per state.
    for state, d in PAST_ELECTION_2023.items():
        yield StatePrediction(
            user_id=None,
            author_name="Past Election",
            author_email="",
            state=state,
            election_type="presidential",
            source="past_performance",
            label="2023 verified presidential result",
            leading_party=d["leader"],
            scores=json.dumps(d["scores"]),
            notes=(
                f"Verified 2023 presidential result — {d['total_votes']:,} votes across "
                f"{d['polling_units']:,} crosschecked polling units."
            ),
            year="2023",
        )


def seed_state_predictions(db: Session) -> int:
    """Seed the shared predictions board with the verified 2023 'Past Election' opinion."""
    if db.scalar(select(func.count()).select_from(StatePrediction)):
        return 0
    rows = list(_state_prediction_rows())
    db.add_all(rows)
    db.commit()
    return len(rows)


# --- political heavyweights per state ---
POLITICIANS = [
    ("Godswill Akpabio", "Akwa Ibom", "Senate President", "APC"),
    ("Umo Eno", "Akwa Ibom", "Governor", "PDP"),
    ("Udom Emmanuel", "Akwa Ibom", "Former Governor", "PDP"),
]


def seed_politicians(db: Session) -> int:
    """Seed the (small) set of state political heavyweights once."""
    if db.scalar(select(func.count()).select_from(Politician)):
        return 0
    for name, state, title, party in POLITICIANS:
        db.add(Politician(name=name, state=state, title=title, party=party))
    db.commit()
    return len(POLITICIANS)


_STATE_INT_FIELDS = [
    "area_sq_km", "census_1991", "census_2006", "population_projection",
    "active_phone_2021", "active_phone_2020", "newly_registered_voters_2022",
    "voters_presidential_2019", "buhari_votes_2019", "atiku_votes_2019",
    "total_votes_2019", "votes_2023", "nin_total", "nin_male", "nin_female",
]


def seed_states(db: Session) -> int:
    """Seed the canonical states table with facts and statistics."""
    if db.scalar(select(func.count()).select_from(State)):
        return 0
    for name, d in STATE_DATA.items():
        kwargs = {f: d.get(f) for f in _STATE_INT_FIELDS}
        db.add(State(name=name, code=d.get("code", ""), capital=d.get("capital", ""), **kwargs))
    db.commit()
    return len(STATE_DATA)


_GOV_TITLE = {1: "Won 2019 governorship", 2: "2019 governorship runner-up", 3: "2019 governorship candidate"}


def seed_party_history(db: Session) -> int:
    """Seed the 2019 governor races as party-history entries, creating/linking a
    politician for each candidate (find-or-create by name + state)."""
    if db.scalar(select(func.count()).select_from(PartyHistory)):
        return 0
    existing: dict[tuple[str, str], Politician] = {}
    for p in db.scalars(select(Politician)).all():
        existing[(p.name.strip().lower(), p.state)] = p
    n = 0
    for name, d in STATE_DATA.items():
        for g in d.get("governor_2019", []):
            cname = g["name"].strip()
            key = (cname.lower(), name)
            pol = existing.get(key)
            if pol is None:
                pol = Politician(name=cname, state=name, party=g["party"], title=_GOV_TITLE.get(g["position"], ""))
                db.add(pol)
                db.flush()
                existing[key] = pol
            db.add(PartyHistory(
                politician_id=pol.id, politician_name=cname, party=g["party"], state=name,
                year="2019", election_type="governor", votes=g["votes"], position=g["position"],
            ))
            n += 1
    db.commit()
    return n


_ELECTIONS_DIR = pathlib.Path(__file__).resolve().parent / "data" / "elections"


def _find_or_create_politician(db: Session, cache: dict, name: str, state: str, party: str, title: str) -> Politician:
    key = (name.strip().lower(), state)
    pol = cache.get(key)
    if pol is None:
        pol = Politician(name=name.strip(), state=state, party=party or "", title=title)
        db.add(pol)
        db.flush()
        cache[key] = pol
    return pol


def _gov_run_title(office: str, year: int, position: int) -> str:
    rank = "Won" if position == 1 else ("runner-up" if position == 2 else "candidate")
    if position == 1:
        return f"Won {year} {office.lower()}ship"
    return f"{year} {office.lower()}ship {rank}"


def seed_governor_2023_results(db: Session) -> int:
    """Load the mined 2023 gubernatorial results: one party-history row per
    candidate that gained votes, with a find-or-create politician each. This is
    the vote-pull dataset (how many votes each politician can pull)."""
    path = _ELECTIONS_DIR / "governor_2023.json"
    if not path.exists():
        return 0
    # idempotent: skip if 2023 governor rows already present
    if db.scalar(select(func.count()).select_from(PartyHistory).where(PartyHistory.year == "2023", PartyHistory.election_type == "governor")):
        return 0
    cache: dict[tuple[str, str], Politician] = {}
    for p in db.scalars(select(Politician)).all():
        cache[(p.name.strip().lower(), p.state)] = p
    n = 0
    for elec in json.loads(path.read_text(encoding="utf-8")):
        state = elec["state"]
        for c in elec.get("candidates", []):
            if c.get("votes") is None:
                continue  # ran but no tally in source
            title = _gov_run_title("Governor", 2023, c["position"])
            pol = _find_or_create_politician(db, cache, c["name"], state, c.get("party", ""), title)
            db.add(PartyHistory(
                politician_id=pol.id, politician_name=c["name"].strip(), party=c.get("party", ""), state=state,
                year="2023", election_type="governor", votes=c["votes"], position=c["position"],
                percent=c.get("percent"), running_mate=c.get("running_mate") or "",
            ))
            n += 1
    db.commit()
    return n


def seed_governors_history(db: Session) -> int:
    """Seed the per-state governor timeline (2007 onward). Substantive (non-acting)
    governors are also find-or-created as politicians so past governors become
    clickable profiles with their vote history."""
    path = _ELECTIONS_DIR / "governors_history.json"
    if not path.exists():
        return 0
    if db.scalar(select(func.count()).select_from(GovernorHistory)):
        return 0
    cache: dict[tuple[str, str], Politician] = {}
    for p in db.scalars(select(Politician)).all():
        cache[(p.name.strip().lower(), p.state)] = p
    n = 0
    for entry in json.loads(path.read_text(encoding="utf-8")):
        state = entry["state"]
        for g in entry.get("governors", []):
            pol_id = None
            if not g.get("acting"):
                span = f"{g.get('term_start', '')}–{g.get('term_end', '')}".replace("–present", "–present")
                title = f"Governor of {state} State ({span})"
                pol = _find_or_create_politician(db, cache, g["name"], state, g.get("party", ""), title)
                pol_id = pol.id
            db.add(GovernorHistory(
                state=state, name=g["name"].strip(), party=g.get("party", ""),
                term_start=str(g.get("term_start", "")), term_end=str(g.get("term_end", "")),
                acting=bool(g.get("acting")), seq=g.get("order", 0), politician_id=pol_id,
            ))
            n += 1
    db.commit()
    return n


def seed_presidential_2023(db: Session) -> int:
    """Seed the 2023 presidential result as national politician runs. Each of the
    four candidates is find-or-created (so Obi/Kwankwaso attach to their existing
    governor profiles) and gets a presidential PartyHistory row with their national
    vote total. Running mates are recorded as politicians too (significant national
    figures)."""
    path = _ELECTIONS_DIR / "presidential_2023.json"
    if not path.exists():
        return 0
    if db.scalar(select(func.count()).select_from(PartyHistory).where(PartyHistory.year == "2023", PartyHistory.election_type == "presidential")):
        return 0
    cache: dict[tuple[str, str], Politician] = {}
    for p in db.scalars(select(Politician)).all():
        cache[(p.name.strip().lower(), p.state)] = p
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for c in data.get("candidates", []):
        state = c["home_state"]
        title = "Won 2023 presidential election" if c.get("won") else f"2023 Presidential candidate ({c['party']})"
        pol = _find_or_create_politician(db, cache, c["name"], state, c.get("party", ""), title)
        db.add(PartyHistory(
            politician_id=pol.id, politician_name=c["name"].strip(), party=c.get("party", ""), state=state,
            year="2023", election_type="presidential", votes=c.get("votes") or 0, position=c.get("position") or 0,
            percent=c.get("percent"), running_mate=c.get("running_mate") or "", constituency="Nigeria (national)",
        ))
        n += 1
        # running mate as a politician too (no separate vote run — shared ticket)
        rm, rm_state = c.get("running_mate"), c.get("running_mate_state")
        if rm and rm_state:
            _find_or_create_politician(db, cache, rm, rm_state, c.get("party", ""), f"2023 Vice-Presidential candidate ({c['party']})")
    db.commit()
    return n


def seed_presidential_2019(db: Session) -> int:
    """Seed the official 2019 presidential result (all 73 candidates) as national
    runs. To avoid flooding the state boards with dozens of one-off candidates we do
    NOT create politicians here — instead each row links to an existing politician
    where a confident name match exists (so e.g. Atiku's profile gains his 2019 run),
    and is otherwise stored as a national record (politician_id null)."""
    path = _ELECTIONS_DIR / "presidential_2019.json"
    if not path.exists():
        return 0
    if db.scalar(select(func.count()).select_from(PartyHistory).where(PartyHistory.year == "2019", PartyHistory.election_type == "presidential")):
        return 0
    # index existing politicians by token set for a conservative subset match
    existing = [(p, _pol_tokens(p.name)) for p in db.scalars(select(Politician)).all()]
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for c in data.get("candidates", []):
        ct = _pol_tokens(c["name"])
        match = None
        for p, pt in existing:
            if len(ct & pt) >= 2 and (ct <= pt or pt <= ct):  # reordered / fuller name
                match = p
                break
        db.add(PartyHistory(
            politician_id=match.id if match else None,
            politician_name=c["name"].strip(), party=c.get("party", ""), state="Nigeria",
            year="2019", election_type="presidential", votes=c.get("votes") or 0,
            position=c.get("position") or 0, percent=c.get("percent"),
            constituency="Nigeria (national)",
        ))
        n += 1
    db.commit()
    return n


def seed_presidential_states(db: Session) -> int:
    """Seed the official 2023 presidential result by state (Tinubu/Atiku/Obi/Kwankwaso)."""
    path = _ELECTIONS_DIR / "presidential_states_2023.json"
    if not path.exists():
        return 0
    if db.scalar(select(func.count()).select_from(StatePresidential)):
        return 0
    n = 0
    for s in json.loads(path.read_text(encoding="utf-8")).get("states", []):
        parties = {"APC": s.get("APC", 0), "PDP": s.get("PDP", 0), "LP": s.get("LP", 0), "NNPP": s.get("NNPP", 0)}
        winner = max(parties, key=parties.get)
        db.add(StatePresidential(
            state=s["state"], year=2023, apc=s.get("APC", 0), pdp=s.get("PDP", 0), lp=s.get("LP", 0),
            nnpp=s.get("NNPP", 0), others=s.get("others", 0), total_votes=s.get("total", 0),
            turnout=s.get("turnout"), winner=winner,
        ))
        n += 1
    db.commit()
    return n


def seed_presidential_states_2019(db: Session) -> int:
    """Seed the official 2019 presidential result by state (Buhari/APC vs Atiku/PDP).
    State-level only — no verified 2019 presidential LGA/ward breakdown is held."""
    path = _ELECTIONS_DIR / "presidential_states_2019.json"
    if not path.exists():
        return 0
    if db.scalar(select(func.count()).select_from(StatePresidential).where(StatePresidential.year == 2019)):
        return 0
    from . import geo
    n = 0
    for s in json.loads(path.read_text(encoding="utf-8")).get("states", []):
        apc, pdp = int(s.get("APC", 0)), int(s.get("PDP", 0))
        db.add(StatePresidential(
            state=s["state"], state_geo=geo.state_geo_id(s["state"]), year=2019,
            apc=apc, pdp=pdp, lp=0, nnpp=0, others=0, total_votes=apc + pdp,
            winner=("APC" if apc >= pdp else "PDP"),
        ))
        n += 1
    db.commit()
    return n


def seed_presidential_primaries(db: Session) -> int:
    """Seed the 2022 APC/PDP presidential primary results. Each contestant is
    find-or-created (linking to their existing profile) with a 'primary' party-history
    row — recorded but excluded from general-election vote-pull."""
    path = _ELECTIONS_DIR / "presidential_primaries_2023.json"
    if not path.exists():
        return 0
    if db.scalar(select(func.count()).select_from(PartyHistory).where(PartyHistory.election_type == "primary")):
        return 0
    cache: dict[tuple[str, str], Politician] = {}
    for p in db.scalars(select(Politician)).all():
        cache[(p.name.strip().lower(), p.state)] = p
    n = 0
    for pr in json.loads(path.read_text(encoding="utf-8")).get("primaries", []):
        party, label = pr["party"], pr["label"]
        for i, c in enumerate(pr.get("candidates", []), 1):
            title = f"{party} presidential aspirant (2023)"
            pol = _find_or_create_politician(db, cache, c["name"], c["state"], party, title)
            db.add(PartyHistory(
                politician_id=pol.id, politician_name=c["name"].strip(), party=party, state=c["state"],
                year="2022", election_type="primary", votes=c.get("votes") or 0, position=i,
                percent=c.get("percent"), constituency=label,
            ))
            n += 1
    db.commit()
    return n


def seed_house_members(db: Session) -> int:
    """Seed the (partial) 2023-2027 House of Representatives roster. Each member is
    linked to an existing politician when their name already appears (by name or aka,
    within the state) — but no new politician is created, to keep the heavyweight
    boards focused on figures we actually have vote data for."""
    path = _ELECTIONS_DIR / "house_2023.json"
    if not path.exists():
        return 0
    if db.scalar(select(func.count()).select_from(HouseMember)):
        return 0
    # name/aka -> politician id, per state
    idx: dict[tuple[str, str], int] = {}
    for p in db.scalars(select(Politician)).all():
        idx[(p.state, p.name.strip().lower())] = p.id
        for a in json.loads(p.aka or "[]"):
            idx.setdefault((p.state, str(a).strip().lower()), p.id)
    n = 0
    for m in json.loads(path.read_text(encoding="utf-8")):
        pid = idx.get((m["state"], m["name"].strip().lower()))
        db.add(HouseMember(
            state=m["state"], constituency=m["constituency"], name=m["name"].strip(),
            party=m.get("party", ""), politician_id=pid,
        ))
        n += 1
    db.commit()
    return n


def seed_senate_2023(db: Session) -> int:
    """Load the mined 2023 Senate results: one party-history row per candidate
    (winners AND losers), find-or-creating a politician for each. Where Wikipedia
    lists vote tallies they are stored; where not, the run is recorded with 0 votes
    (so it shows the contest without inflating vote-pull)."""
    path = _ELECTIONS_DIR / "senate_2023.json"
    if not path.exists():
        return 0
    if db.scalar(select(func.count()).select_from(PartyHistory).where(PartyHistory.year == "2023", PartyHistory.election_type == "senate")):
        return 0
    cache: dict[tuple[str, str], Politician] = {}
    for p in db.scalars(select(Politician)).all():
        cache[(p.name.strip().lower(), p.state)] = p
    n = 0
    for elec in json.loads(path.read_text(encoding="utf-8")):
        state = elec["state"]
        district = elec.get("district", "")
        for c in elec.get("candidates", []):
            won = c.get("position") == 1
            title = f"Senator-elect, {district}" if won else f"2023 Senate candidate, {district}"
            pol = _find_or_create_politician(db, cache, c["name"], state, c.get("party", ""), title)
            db.add(PartyHistory(
                politician_id=pol.id, politician_name=c["name"].strip(), party=c.get("party", ""), state=state,
                year="2023", election_type="senate", votes=c.get("votes") or 0, position=c.get("position") or 0,
                percent=c.get("percent"), constituency=district,
            ))
            n += 1
    db.commit()
    return n


def seed_governors_current(db: Session) -> int:
    """Seed current (incumbent) governors + link/create a politician for each."""
    path = _ELECTIONS_DIR / "governors_current.json"
    if not path.exists():
        return 0
    if db.scalar(select(func.count()).select_from(Governor)):
        return 0
    cache: dict[tuple[str, str], Politician] = {}
    for p in db.scalars(select(Politician)).all():
        cache[(p.name.strip().lower(), p.state)] = p
    n = 0
    for g in json.loads(path.read_text(encoding="utf-8")).get("governors", []):
        state = g["state"]
        title = f"Governor of {state} State"
        pol = _find_or_create_politician(db, cache, g["name"], state, g.get("party", ""), title)
        db.add(Governor(
            state=state, name=g["name"].strip(), party=g.get("party", ""),
            party_elected=g.get("party_elected", ""), term_start=g.get("term_start", ""),
            term_end=g.get("term_end", ""), politician_id=pol.id,
        ))
        n += 1
    db.commit()
    return n


def seed_senators(db: Session) -> int:
    """Seed the 10th National Assembly senators (2023-2027). Each senator is also
    surfaced as a politician (find-or-create by name + state) so they appear on
    state pages and the politicians board."""
    if db.scalar(select(func.count()).select_from(Senator)):
        return 0
    existing: dict[tuple[str, str], Politician] = {}
    for p in db.scalars(select(Politician)).all():
        existing[(p.name.strip().lower(), p.state)] = p
    n = 0
    for s in SENATORS:
        name = s["name"].strip()
        key = (name.lower(), s["state"])
        pol = existing.get(key)
        if pol is None:
            title = s.get("leadership") or f"Senator, {s['state']} {s['district']}"
            pol = Politician(name=name, state=s["state"], party=s.get("party", ""), title=title)
            db.add(pol)
            db.flush()
            existing[key] = pol
        db.add(Senator(
            name=name, state=s["state"], district=s["district"], party=s.get("party", ""),
            gender=s.get("gender") or "", age=s.get("age"), terms=s.get("terms"),
            leadership=s.get("leadership") or "", politician_id=pol.id,
        ))
        n += 1
    db.commit()
    return n


_WARDS_CSV = pathlib.Path(__file__).resolve().parent / "data" / "wards.csv"
_STATE_ALIAS = {"federal capital territory": "FCT", "nassarawa": "Nasarawa"}


def _canon_state(s: str) -> str:
    s = (s or "").strip()
    return _STATE_ALIAS.get(s.lower(), s)


def seed_wards(db: Session) -> int:
    """Seed all electoral wards (name + coordinates) from the bundled CSV, once."""
    if db.scalar(select(func.count()).select_from(Ward)):
        return 0
    if not _WARDS_CSV.exists():
        return 0
    n = 0
    with open(_WARDS_CSV, encoding="utf-8-sig", newline="") as fh:
        batch = []
        for row in csv.DictReader(fh):
            ward = (row.get("Ward") or "").strip()
            if not ward:
                continue
            try:
                lat = float(row["Latitude"])
                lng = float(row["Longitude"])
            except (TypeError, ValueError, KeyError):
                continue
            batch.append(Ward(
                state=_canon_state(row.get("State", "")), lga=(row.get("LGA") or "").strip(),
                ward=ward, latitude=lat, longitude=lng,
            ))
            n += 1
            if len(batch) >= 1000:
                db.add_all(batch)
                db.flush()
                batch = []
        if batch:
            db.add_all(batch)
    db.commit()
    return n


_PU_CSV = pathlib.Path(__file__).resolve().parent / "data" / "polling_units.csv.gz"
_WARD_RESULTS_CSV = pathlib.Path(__file__).resolve().parent / "data" / "ward_results.csv.gz"


def _optint(v):
    return int(v) if v not in (None, "") else None


def seed_polling_units(db: Session) -> int:
    """Seed all polling units (2023 registered voters, party votes, winner, runner-up) once."""
    if db.scalar(select(func.count()).select_from(PollingUnit)):
        return 0
    if not _PU_CSV.exists():
        return 0
    n = 0
    batch = []
    with gzip.open(_PU_CSV, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            batch.append({
                "state": row["state"], "lga": row["lga"], "ward": row["ward"],
                "ward_code": row["ward_code"], "pu_name": row["pu_name"], "pu_code": row["pu_code"],
                "registered_voters": _optint(row["registered_voters"]),
                "votes_apc": _optint(row["apc"]), "votes_lp": _optint(row["lp"]),
                "votes_pdp": _optint(row["pdp"]), "votes_nnpp": _optint(row["nnpp"]),
                "known_votes": _optint(row["known_votes"]),
                "winner": row["winner"] or "", "runner_up": row["runner_up"] or "",
            })
            n += 1
            if len(batch) >= 5000:
                db.execute(PollingUnit.__table__.insert(), batch)
                batch = []
        if batch:
            db.execute(PollingUnit.__table__.insert(), batch)
    db.commit()
    return n


def seed_ward_results(db: Session) -> int:
    """Seed aggregated 2023 ward results (winner + runner-up) once."""
    if db.scalar(select(func.count()).select_from(WardResult)):
        return 0
    if not _WARD_RESULTS_CSV.exists():
        return 0
    rows = []
    with gzip.open(_WARD_RESULTS_CSV, "rt", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "state": r["state"], "lga": r["lga"], "ward": r["ward"], "ward_code": r["ward_code"],
                "votes_apc": int(r["apc"]), "votes_lp": int(r["lp"]), "votes_pdp": int(r["pdp"]), "votes_nnpp": int(r["nnpp"]),
                "total_votes": int(r["total_votes"]), "winner": r["winner"], "runner_up": r["runner_up"],
            })
    if rows:
        db.execute(WardResult.__table__.insert(), rows)
        db.commit()
    return len(rows)


# --- ward-level estimation ---------------------------------------------------
#
# A ticket's projected vote in a ward is built from several sources, each a component:
#   - Candidate Popularity  : the presidential candidate's own proven vote — his 2023
#                             result in that ward, retained with some decay.
#   - Running-mate Popularity: the VP's proven vote — the votes he personally delivered
#                             in a past election (his 2023 party result in the ward),
#                             transferred to the joint ticket at some rate. This is why
#                             the VP is linked as a politician: we match him against what
#                             he actually delivered last time.
#   - Supporter Popularity  : a politician who backs the ticket without being on it (an
#                             endorsement) — e.g. a sitting governor delivering a share of
#                             the base his party commands in the ward. Linked as a
#                             politician too, matched against the votes he delivered.
#   - Party Popularity      : structural support the party organises independently of the
#                             names — a small share of the ward's turnout.
# The prediction's votes is the sum of its components.

_2023_PARTY_COL = {"APC": "votes_apc", "LP": "votes_lp", "PDP": "votes_pdp", "NNPP": "votes_nnpp"}


def _pol_2023_party(db: Session, pol: "Politician | None") -> str | None:
    """The party a politician commanded in 2023, preferring the presidential race, then
    governorship, then any 2023 record. Used to find the base of votes he can deliver."""
    if pol is None:
        return None
    from .models import PartyHistory
    for et in ("presidential", "governor"):
        p = db.scalar(select(PartyHistory.party).where(
            PartyHistory.politician_id == pol.id,
            PartyHistory.election_type == et, PartyHistory.year == "2023").limit(1))
        if p:
            return p
    return db.scalar(select(PartyHistory.party).where(
        PartyHistory.politician_id == pol.id, PartyHistory.year == "2023").limit(1))


def _ward_2023_votes(db: Session, ward, pol: "Politician | None") -> int:
    """The votes the base `pol` commands in this ward — the 2023 result of the party he
    led (0 if we can't place him). Governors have no ward-level gubernatorial figures, so
    this proxies with the presidential vote of their party in the ward."""
    col = _2023_PARTY_COL.get(_pol_2023_party(db, pol) or "")
    return int(getattr(ward, col, 0) or 0) if col else 0


# The 2027 tickets we project, and the assumptions behind each component.
# retention   = share of the candidate's own 2023 vote he keeps.
# vp_transfer = share of the VP's 2023 personal vote that moves to the joint ticket.
# party_share = party structural vote as a fraction of the ward's 2023 turnout.
# supporters  = endorsing politicians; each delivers `transfer` of the base he commands.
_OBI_TICKET = {"candidate": "peter obi", "running_mate": "rabiu musa kwankwaso",
               "retention": 0.90, "vp_transfer": 0.70, "party_share": 0.04, "supporters": []}
_TINUBU_TICKET = {"candidate": "bola tinubu", "running_mate": "kashim shettima",
                  "retention": 0.92, "vp_transfer": 0.70, "party_share": 0.05, "supporters": []}


def estimate_lga_predictions(db: Session, lga_id: int, tickets: list[dict], clear: bool = False) -> int:
    """Build reasoned 2027 per-ward predictions for one LGA. Each ticket gets one
    prediction per ward, decomposed into Candidate / Running-mate / Supporter(s) / Party
    components (see the note above); the running mate and each supporter are linked as
    politicians and matched against the votes they delivered in 2023. With `clear=True`
    any existing predictions for this LGA are wiped first; otherwise it is a no-op if the
    LGA already has predictions (first-run guard)."""
    from .models import WardPrediction, PredictionComponent
    lga = db.get(Lga, lga_id)

    if clear:
        old = db.scalars(select(WardPrediction.id).where(WardPrediction.lga_id == lga_id)).all()
        if old:
            db.execute(delete(PredictionComponent).where(PredictionComponent.ward_prediction_id.in_(old)))
            db.execute(delete(WardPrediction).where(WardPrediction.id.in_(old)))
    elif db.scalar(select(func.count()).select_from(WardPrediction).where(WardPrediction.lga_id == lga_id)):
        return 0

    def pol(name: str | None):
        return db.scalar(select(Politician).where(func.lower(Politician.name) == name)) if name else None

    wards = db.scalars(select(WardResult).where(WardResult.lga_id == lga_id)).all()
    n = 0
    for t in tickets:
        cand = pol(t["candidate"])
        mate = pol(t["running_mate"])
        if cand is None:
            continue
        # A supporter's deliverable base is the vote his party commands in this LGA.
        # Where we have his REAL 2023 governorship total (lga_party_results), use it and
        # spread it across wards by each ward's share of that party's presidential vote —
        # so the ward pattern is preserved but the magnitude matches what he actually
        # polled. Otherwise fall back to the presidential vote itself (scale 1.0).
        supporters = []
        for s in t.get("supporters", []):
            spol = pol(s["name"])
            if spol is None:
                continue
            party = _pol_2023_party(db, spol)
            col = _2023_PARTY_COL.get(party or "")
            if not col:
                continue
            pres_lga = sum(int(getattr(w, col, 0) or 0) for w in wards)
            gov_lga = db.scalar(select(func.coalesce(func.sum(LgaPartyResult.votes), 0)).where(
                LgaPartyResult.election_type == "governor", LgaPartyResult.year == "2023",
                LgaPartyResult.lga_id == lga_id, LgaPartyResult.party == party)) or 0
            scale = (gov_lga / pres_lga) if (gov_lga and pres_lga) else 1.0
            supporters.append((s, spol, col, scale))
        for w in wards:
            comps = [
                ("Candidate Popularity", round(_ward_2023_votes(db, w, cand) * t["retention"]),
                 cand.id if cand else None),
                ("Running-mate Popularity", round(_ward_2023_votes(db, w, mate) * t["vp_transfer"]),
                 mate.id if mate else None),
            ]
            for s, spol, col, scale in supporters:
                base = int(getattr(w, col, 0) or 0) * scale
                comps.append(("Supporter Popularity", round(base * s["transfer"]), spol.id))
            comps.append(("Party Popularity", round((w.total_votes or 0) * t["party_share"]), None))
            total = sum(v for _r, v, _p in comps)
            wp = WardPrediction(
                election_type="presidential", year="2027",
                state_geo=(lga.state_geo if lga else None), lga_id=lga_id,
                ward_code=w.ward_code, politician_id=cand.id,
                running_mate_id=(mate.id if mate else None), party=(cand.party or ""),
                votes=total, label="Base projection", importance=60,
            )
            db.add(wp)
            db.flush()  # need wp.id for the components
            for seq, (reason, votes, pid) in enumerate(comps):
                db.add(PredictionComponent(
                    ward_prediction_id=wp.id, reason=reason, votes=votes, seq=seq, politician_id=pid,
                ))
            n += 1
    db.commit()
    return n


def _amac_lga_id(db: Session) -> int | None:
    """The municipal LGA where Peter Obi did best in 2023 (AMAC)."""
    top = db.execute(
        select(WardResult.lga_id, func.sum(WardResult.votes_lp).label("v"))
        .where(WardResult.lga_id.isnot(None))
        .group_by(WardResult.lga_id).order_by(func.sum(WardResult.votes_lp).desc()).limit(1)
    ).first()
    return top.lga_id if top and top.v else None


_IKOT_EKPENE_LGA_ID = 214


def estimate_municipal_predictions(db: Session, clear: bool = False) -> int:
    """AMAC (municipal): Obi/Kwankwaso vs Tinubu/Shettima, no supporters."""
    lga_id = _amac_lga_id(db)
    if lga_id is None:
        return 0
    return estimate_lga_predictions(db, lga_id, [_OBI_TICKET, _TINUBU_TICKET], clear=clear)


def estimate_ikot_ekpene_predictions(db: Session, clear: bool = False) -> int:
    """Ikot Ekpene (Akwa Ibom): same two tickets, but the sitting PDP governor Umo Eno
    backs Tinubu/Shettima and delivers half of the PDP base he commands in each ward."""
    tinubu = {**_TINUBU_TICKET,
              "supporters": [{"name": "umo eno", "transfer": 0.50}]}
    return estimate_lga_predictions(db, _IKOT_EKPENE_LGA_ID, [_OBI_TICKET, tinubu], clear=clear)


def estimate_all_lga_predictions(db: Session, clear: bool = False) -> int:
    """Run every LGA estimation we have written."""
    return (estimate_municipal_predictions(db, clear=clear)
            + estimate_ikot_ekpene_predictions(db, clear=clear))


def seed_ward_predictions(db: Session) -> int:
    """First-run seed of the reasoned per-ward predictions (see estimate_lga_predictions)."""
    return estimate_all_lga_predictions(db, clear=False)


def seed_prediction_components(db: Session) -> int:
    """Deprecated: components are now created inline by estimate_lga_predictions."""
    return 0


def seed_lga_predictions(db: Session) -> int:
    """Seed our first real per-LGA prediction: assign Peter Obi (LP) the votes he
    polled in the single LGA where he did best in 2023 (his strongest ground). We read
    that straight from the verified per-ward results, so it tracks the data."""
    from .models import LgaPrediction
    if db.scalar(select(func.count()).select_from(LgaPrediction)):
        return 0
    top = db.execute(
        select(WardResult.lga_id, func.sum(WardResult.votes_lp).label("v"))
        .where(WardResult.lga_id.isnot(None))
        .group_by(WardResult.lga_id)
        .order_by(func.sum(WardResult.votes_lp).desc())
        .limit(1)
    ).first()
    if not top or not top.v:
        return 0
    lga_id, votes = top.lga_id, int(top.v)
    lga = db.get(Lga, lga_id)
    obi = db.scalar(select(Politician).where(func.lower(Politician.name) == "peter obi"))
    db.add(LgaPrediction(
        election_type="presidential", year="2027", party="LP", lga_id=lga_id,
        state_geo=(lga.state_geo if lga else None),
        politician_id=(obi.id if obi else None), votes=votes,
    ))
    db.commit()
    return 1


# --- verified 2023 results per LGA per party (presidential + governor) ------------

_DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
_GOV_2023_CSV = _DATA_DIR / "gov_2023_lga.csv"
# per-LGA governorship declarations by election year (tidy: state,lga,party,votes)
_GOV_CSVS = {"2023": _GOV_2023_CSV, "2019": _DATA_DIR / "gov_2019_lga.csv"}


def _lga_key(name: str) -> str:
    """Match key for an LGA name: lowercase, alphanumerics only ('Kaura-Namoda' == 'Kaura Namoda')."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _match_lga(name: str, state_index: dict[str, Lga]) -> Lga | None:
    """Resolve an LGA name to its canonical row within one state (exact key, then close match)."""
    m = state_index.get(_lga_key(name))
    if m:
        return m
    near = difflib.get_close_matches(_lga_key(name), list(state_index), n=1, cutoff=0.85)
    return state_index[near[0]] if near else None


def load_lga_party_results(db: Session) -> tuple[int, list[str]]:
    """(Re)load the verified per-LGA per-party results into lga_party_results:
      - presidential 2023: aggregated from ward_results (APC/LP/PDP/NNPP)
      - governor 2023 + 2019: from the collected per-LGA declarations
        (app/data/gov_2023_lga.csv, app/data/gov_2019_lga.csv)
    LGAs are linked to canonical lga_id. Clears the table first so it always reflects the
    current sources. Returns (rows written, unmatched 'State/LGA' names)."""
    from . import geo
    lgas = db.scalars(select(Lga)).all()
    lga_by_id = {l.id: l for l in lgas}
    # per-state index of canonical LGAs, keyed by match-key
    by_state: dict[str, dict[str, Lga]] = defaultdict(dict)
    for l in lgas:
        by_state[l.state.lower()][_lga_key(l.name)] = l
    # names in our declarations that differ from the canonical table (renames/typos)
    _aliases = {
        "adamawa": {"girei": "girie", "toungo": "teungo"},
        "ogun": {"yewanorth": "egbadonorth", "yewasouth": "egbadosouth"},
        "delta": {"aniochanorth": "aniochan", "aniochasouth": "aniochas", "ikanortheast": "ikanorth", "ethiopeeast": "ethiopee"},
        "rivers": {"emohua": "emuoha", "andoni": "andoniodual"},
        "imo": {"ihitteuboma": "ihitteubomaisinweke", "onuimo": "unuimo"},
        "abia": {"obingwa": "obomangwa"},
        "kebbi": {"aliero": "aleiro", "wasagudanko": "dankowasagu"},
        "niger": {"kontagora": "kontogur"},
        "enugu": {"agwu": "awgu"},
        "nasarawa": {"eggon": "nassarawaegon"},
    }
    for st, amap in _aliases.items():
        idx = by_state.get(st, {})
        for pasted, canon in amap.items():
            if canon in idx:
                idx[pasted] = idx[canon]

    db.execute(delete(LgaPartyResult))
    n = 0

    # presidential — aggregate the verified ward results up to LGA
    pres = db.execute(
        select(
            WardResult.state, WardResult.state_geo, WardResult.lga_id,
            func.sum(WardResult.votes_apc), func.sum(WardResult.votes_lp),
            func.sum(WardResult.votes_pdp), func.sum(WardResult.votes_nnpp),
        ).where(WardResult.lga_id.isnot(None)).group_by(WardResult.state, WardResult.state_geo, WardResult.lga_id)
    ).all()
    for state, sgeo, lga_id, apc, lp, pdp, nnpp in pres:
        name = lga_by_id[lga_id].name if lga_id in lga_by_id else ""
        for party, v in (("APC", apc), ("LP", lp), ("PDP", pdp), ("NNPP", nnpp)):
            db.add(LgaPartyResult(election_type="presidential", year="2023", state=state,
                                  state_geo=sgeo, lga_id=lga_id, lga=name, party=party, votes=int(v or 0)))
            n += 1

    # governor — from the collected per-LGA declarations, per election year
    unmatched: list[str] = []
    for year, path in _GOV_CSVS.items():
        if not path.exists():
            continue
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                state, lga, party = r["state"], r["lga"], r["party"]
                votes = int(r["votes"]) if str(r["votes"]).strip() else 0
                canon = _match_lga(lga, by_state.get(state.lower(), {}))
                if canon is None:
                    tag = f"{year} {state}/{lga}"
                    if tag not in unmatched:
                        unmatched.append(tag)
                db.add(LgaPartyResult(
                    election_type="governor", year=year, state=state,
                    state_geo=(canon.state_geo if canon else geo.state_geo_id(state)),
                    lga_id=(canon.id if canon else None),
                    lga=(canon.name if canon else lga), party=party.upper(), votes=votes))
                n += 1
    db.commit()
    return n, unmatched


_LEGIS_2019_CSV = _DATA_DIR / "legislative_2019.csv"


def _name_key(name: str) -> str:
    """Match key for a person's name: uppercase alphanumerics only, spaces collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", (name or "").upper())).strip()


def load_legislative_results(db: Session) -> int:
    """(Re)load the verified 2019 Senate + House of Representatives per-candidate
    results (app/data/legislative_2019.csv, from the INEC constituency sheets) into
    legislative_results. Clears the table first. Links each candidate to a
    politician_id where one matches — reusing the links party_history already carries
    for the same race, then falling back to any politician of that name in the state.
    Returns rows written."""
    from . import geo
    if not _LEGIS_2019_CSV.exists():
        return 0

    # names already resolved to a politician for these NA races (2019 CSV + the
    # 2023 senate seeded into party_history by seed_senate_2023) — keyed by
    # (year, election_type, ...) so a 2019 and 2023 same-name race don't collide
    ph_by_con: dict[tuple[str, str, str, str], int] = {}
    ph_by_state: dict[tuple[str, str, str, str], int] = {}
    for yr, et, name, cons, state, pid in db.execute(
        select(PartyHistory.year, PartyHistory.election_type, PartyHistory.politician_name,
               PartyHistory.constituency, PartyHistory.state, PartyHistory.politician_id)
        .where(PartyHistory.election_type.in_(("house", "senate")),
               PartyHistory.politician_id.isnot(None))
    ).all():
        nk = _name_key(name)
        ph_by_con.setdefault((yr, et, nk, _name_key(cons)), pid)
        ph_by_state.setdefault((yr, et, nk, (state or "").lower()), pid)
    # any politician by name within a state (fallback link)
    pol_by_state: dict[tuple[str, str], int] = {}
    for pid, pname, pstate in db.execute(select(Politician.id, Politician.name, Politician.state)).all():
        pol_by_state.setdefault((_name_key(pname), (pstate or "").lower()), pid)

    db.execute(delete(LegislativeResult))
    n = 0
    with open(_LEGIS_2019_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            et, state, cons = r["election_type"], r["state"], r["constituency"]
            yr = r.get("year", "2019")
            nk = _name_key(r["candidate"])
            pid = (ph_by_con.get((yr, et, nk, _name_key(cons)))
                   or ph_by_state.get((yr, et, nk, state.lower()))
                   or pol_by_state.get((nk, state.lower())))
            db.add(LegislativeResult(
                election_type=et, year=yr, state=state,
                state_geo=geo.state_geo_id(state), constituency=cons, code=r.get("code", ""),
                candidate=r["candidate"], gender=r.get("gender", ""), party=r.get("party", ""),
                votes=int(r["votes"]) if str(r["votes"]).strip() else 0,
                position=int(r["position"]) if str(r["position"]).strip() else 0,
                elected=str(r.get("elected", "")).strip() == "1", politician_id=pid))
            n += 1

    # 2023 Senate — mined from Wikipedia (elections/senate_2023.json), one row per
    # candidate with votes/position. No INEC code (constituency is the senatorial
    # district); winner = position 1 (or an explicit "won" flag).
    senate_json = _ELECTIONS_DIR / "senate_2023.json"
    if senate_json.exists():
        for elec in json.loads(senate_json.read_text(encoding="utf-8")):
            state = elec.get("state", "")
            district = elec.get("district", "")
            for c in elec.get("candidates", []):
                nk = _name_key(c.get("name", ""))
                pos = c.get("position") or 0
                pid = (ph_by_con.get(("2023", "senate", nk, _name_key(district)))
                       or ph_by_state.get(("2023", "senate", nk, state.lower()))
                       or pol_by_state.get((nk, state.lower())))
                db.add(LegislativeResult(
                    election_type="senate", year="2023", state=state,
                    state_geo=geo.state_geo_id(state), constituency=district, code="",
                    candidate=c.get("name", ""), gender=c.get("gender", ""), party=c.get("party", ""),
                    votes=int(c.get("votes") or 0), position=int(pos),
                    elected=bool(c.get("won")) or pos == 1, politician_id=pid))
                n += 1
    db.commit()
    return n


_SHEETS_DIR = _DATA_DIR / "sheets"


def load_election_sheets(db: Session) -> int:
    """(Re)load election_sheets from the bundled per-(state,type) CSVs in app/data/sheets/
    (built by data/build_election_sheets_bundle.py from the IReV download manifests). Each
    row links a polling unit (pu_code) to its INEC sheet URL, our download status, and our
    EC8A transcription JSON where we have one. Clears + reloads so it always reflects the
    current bundle. Returns rows written."""
    from . import geo
    if not _SHEETS_DIR.exists():
        return 0
    db.execute(delete(ElectionSheet))
    geo_cache: dict[str, str | None] = {}
    n = 0
    for path in sorted(_SHEETS_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                st = r.get("state", "")
                if st not in geo_cache:
                    geo_cache[st] = geo.state_geo_id(st) if st else None
                db.add(ElectionSheet(
                    election_type=r["election_type"], year=r.get("year", "2023"), state=st,
                    state_geo=geo_cache[st], pu_code=r["pu_code"],
                    sheet_url=r.get("sheet_url", ""), sheet_status=r.get("sheet_status", ""),
                    json=(r.get("json") or None)))
                n += 1
    db.commit()
    return n


def seed_lga_results(db: Session) -> int:
    """Seed the verified 2023 presidential result per LGA once."""
    if db.scalar(select(func.count()).select_from(LgaResult)):
        return 0
    n = 0
    for state, rows in LGA_RESULTS_2023.items():
        for r in rows:
            db.add(LgaResult(
                state=state, lga=r["lga"], leading_party=r["leader"],
                scores=json.dumps(r["scores"]), total_votes=r["total_votes"], year="2023",
            ))
            n += 1
    db.commit()
    return n


# --- canonical LGAs + reference-by-id integrity -----------------------------

_LGAS_JSON = pathlib.Path(__file__).resolve().parent / "data" / "lgas.json"


def _authoritative_lgas() -> list[dict]:
    """The authoritative 774-LGA list (state, name, geo_id) from data/lgas.json,
    built by scripts/build_lgas.py from the official ward dataset."""
    if not _LGAS_JSON.exists():
        return []
    return json.loads(_LGAS_JSON.read_text(encoding="utf-8")).get("lgas", [])


def _canonical_lgas() -> dict[str, list[str]]:
    """Authoritative LGA names per state (the single source of truth)."""
    out: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for e in _authoritative_lgas():
        st, nm = e["state"], (e.get("name") or "").strip()
        k = (st, nm.lower())
        if nm and k not in seen:
            seen.add(k)
            out[st].append(nm)
    return dict(out)


def seed_lgas(db: Session) -> int:
    """Seed the canonical LGA table (all 774) from data/lgas.json. Every other row
    references an LGA by id, so this is the single source of truth for LGA names."""
    from . import geo
    if db.scalar(select(func.count()).select_from(Lga)):
        return 0
    n = 0
    for e in _authoritative_lgas():
        db.add(Lga(state=e["state"], state_geo=geo.state_geo_id(e["state"]),
                   geo_id=e.get("geo_id"), name=e["name"]))
        n += 1
    db.commit()
    return n


def refresh_lga_names(db: Session) -> int:
    """Correct any canonical LGA rows whose name is stale/truncated relative to the
    code constant, in place (ids stay stable so references keep resolving). Matches
    a stored name to the constant by exact or prefix-normalised form."""
    canon = _canonical_lgas()
    updated = 0
    for l in db.scalars(select(Lga)).all():
        names = canon.get(l.state, [])
        nl = _lga_norm(l.name)
        best = None
        for cn in names:
            ncn = _lga_norm(cn)
            if ncn == nl:
                best = cn
                break
            if len(nl) >= 4 and (ncn.startswith(nl) or nl.startswith(ncn)):
                best = cn
        if best and best != l.name:
            l.name = best
            updated += 1
    if updated:
        db.commit()
    return updated


def _lga_norm(s: str) -> str:
    return "".join(c for c in str(s).lower() if c.isalnum())


_LGA_DIRS = {"north", "south", "east", "west", "central"}


def _lga_dirs(name: str) -> frozenset:
    return frozenset(t for t in str(name or "").lower().replace("-", " ").replace("/", " ").split() if t in _LGA_DIRS)


def _lga_match(cands: list[tuple[str, int, str]], name: str) -> int | None:
    """Match an LGA name to a canonical id (exact/prefix, then close-variant guarded
    against a differing directional word). `cands` = [(norm, id, raw_name)]."""
    import difflib
    n = _lga_norm(name)
    for cn, cid, _raw in cands:
        if cn == n:
            return cid
    pref = [cid for cn, cid, _raw in cands if (cn.startswith(n) or n.startswith(cn)) and min(len(cn), len(n)) >= 4]
    if len(pref) == 1:
        return pref[0]
    d = _lga_dirs(name)
    pool = [(cn, cid) for cn, cid, raw in cands if not (d and _lga_dirs(raw) and d != _lga_dirs(raw))]
    close = difflib.get_close_matches(n, [cn for cn, cid in pool], n=1, cutoff=0.82)
    if close:
        for cn, cid in pool:
            if cn == close[0]:
                return cid
    return None


def link_lga_references(db: Session) -> int:
    """Backfill lga_id on every table that stores an LGA name (lga_results, wards,
    ward_results, polling_units, problem_units) where it is still null — so a freshly
    seeded DB links to the canonical `lga` table the same way the migrations do."""
    canon: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for l in db.scalars(select(Lga)).all():
        if l.state_geo:
            canon[l.state_geo].append((_lga_norm(l.name), l.id, l.name))
    total = 0
    for model in (LgaResult, Ward, WardResult, PollingUnit, ProblemUnit):
        pairs = db.execute(
            select(model.state_geo, model.lga).where(model.lga_id.is_(None)).distinct()
        ).all()
        for sg, raw in pairs:
            if not sg or not raw:
                continue
            lid = _lga_match(canon.get(sg, []), raw)
            if lid is not None:
                total += db.execute(
                    update(model).where(model.state_geo == sg, model.lga == raw, model.lga_id.is_(None)).values(lga_id=lid)
                ).rowcount
    if total:
        db.commit()
    return total


def migrate_assessment_lgas(db: Session) -> int:
    """Convert any assessment influential_lgas still stored as name strings into
    canonical LGA ids (matched within the politician's state, tolerating the old
    truncated forms via prefix match). Idempotent: id-arrays are left untouched."""
    rows = db.scalars(select(PoliticianAssessment)).all()
    if not rows:
        return 0
    by_state: dict[str, list[Lga]] = defaultdict(list)
    for l in db.scalars(select(Lga)).all():
        by_state[l.state].append(l)
    pol_state = {p.id: p.state for p in db.scalars(select(Politician)).all()}
    changed = 0
    for a in rows:
        try:
            vals = json.loads(a.influential_lgas or "[]")
        except Exception:
            vals = []
        if not vals or all(isinstance(v, int) for v in vals):
            continue
        cand = by_state.get(pol_state.get(a.politician_id, ""), [])
        ids: list[int] = []
        for v in vals:
            if isinstance(v, int):
                ids.append(v)
                continue
            nv = _lga_norm(v)
            if not nv:
                continue
            for l in cand:
                nl = _lga_norm(l.name)
                if nv == nl or (len(nv) >= 4 and (nl.startswith(nv) or nv.startswith(nl))):
                    ids.append(l.id)
                    break
        a.influential_lgas = json.dumps(ids)
        changed += 1
    db.commit()
    return changed


# --- politician de-duplication (unify name variants; keep "also known as") ---

# Same person, spelling variants not caught by the token-subset rule below.
_ALIAS_GROUPS: list[tuple[str, list[str]]] = [
    ("Gombe", ["MOHAMMED INUWA YAHAYA", "Muhammad Inuwa Yahaya", "Muhammadu Inuwa Yahaya"]),
    ("Katsina", ["Dikko Umar Radda", "Dikko Umaru Radda"]),
    # verified same-person spelling / nickname variants (hyphens, all-caps, short forms)
    ("Lagos", ["Babajide Sanwo-Olu", "BABAJIDE OLUSOLA SANWOLU"]),
    ("Oyo", ["OLUSEYI MAKINDE", "Seyi Makinde"]),
    ("Ogun", ["ADEDAPO ABIODUN", "Dapo Abiodun"]),
    ("Ekiti", ["Abiodun Oyebanji", "Biodun Oyebanji"]),
    ("Ondo", ["Olajide Ipinsagba", "Jide Ipinsagba"]),
    ("Rivers", ["Allwell Onyeso", "Allwell Onyesoh"]),
    ("Bauchi", ["Samaila Dahuwa Kaila", "Sama'ila Dahuwa Kaila"]),
    ("Abia", ["Austin Akobundu", "Augustine Akobundu"]),
    ("Cross River", ["Ben Ayade", "Benedict Ayade"]),
    ("Yobe", ["Ahmed Lawan", "Ahmad Lawan"]),
    ("Jigawa", ["Ahmed Abdulhamid Mallam Madori", "Ahmad Abdulhamid Malam Madori"]),
    ("Ebonyi", ["David Umahi", "David Nweze Umahi", "DAVID UMAHI NWEZE", "Dave Umahi"]),
]

_FK_MODELS = (PartyHistory, Senator, Governor, GovernorHistory, PoliticianAssessment, PoliticianPhoto)


def _pol_tokens(name: str) -> frozenset:
    clean = "".join(c.lower() if c.isalnum() or c == " " else " " for c in name)
    return frozenset(w for w in clean.split() if len(w) > 1)


def dedupe_politicians(db: Session) -> int:
    """Merge politician records that are the same person under different name
    spellings/orders into one canonical record, repointing every reference by id
    and recording the other spellings as `aka`. Idempotent."""
    pols = db.scalars(select(Politician)).all()
    parent = {p.id: p.id for p in pols}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_state: dict[str, list[Politician]] = defaultdict(list)
    for p in pols:
        by_state[p.state].append(p)
    # token-subset within a state -> same person (reordered / fuller name)
    for group in by_state.values():
        for a, b in itertools.combinations(group, 2):
            ta, tb = _pol_tokens(a.name), _pol_tokens(b.name)
            if len(ta & tb) >= 2 and (ta <= tb or tb <= ta):
                union(a.id, b.id)
    # curated alias groups
    idx = {(p.state, p.name.strip().lower()): p for p in pols}
    for st, names in _ALIAS_GROUPS:
        ids = [idx[(st, n.strip().lower())].id for n in names if (st, n.strip().lower()) in idx]
        for other in ids[1:]:
            union(ids[0], other)

    groups: dict[int, list[Politician]] = defaultdict(list)
    for p in pols:
        groups[find(p.id)].append(p)

    current_ids: set[int] = set()
    for M in (Senator, Governor):
        for pid in db.scalars(select(M.politician_id)).all():
            if pid:
                current_ids.add(pid)

    def refcount(pid: int) -> int:
        return sum(db.scalar(select(func.count()).select_from(M).where(M.politician_id == pid)) or 0 for M in _FK_MODELS)

    merged = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = max(members, key=lambda p: (p.id in current_ids, p.name != p.name.upper(), refcount(p.id), -p.id))
        aka = sorted({m.name for m in members if m.name != keep.name})
        keep.aka = json.dumps(aka, ensure_ascii=False)
        for o in members:
            if o.id == keep.id:
                continue
            for M in _FK_MODELS:
                db.execute(update(M).where(M.politician_id == o.id).values(politician_id=keep.id))
            db.delete(o)
            merged += 1
    db.commit()
    return merged
