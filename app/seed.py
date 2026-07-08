"""Seed the predictions table with illustrative, already-aggregated data.

Real data would be crunched from raw contributor traces upstream; this just
gives the map something to render across weeks and election types.
"""
import csv
import gzip
import hashlib
import itertools
import json
import pathlib
import re
from collections import defaultdict

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .data_2023 import PAST_ELECTION_2023
from .lga_2023 import LGA_RESULTS_2023
from .models import Analysis, Governor, GovernorHistory, Lga, LgaResult, Party, PartyElection, PartyHistory, PollingUnit, Politician, PoliticianAssessment, PoliticianPhoto, Prediction, ProblemUnit, Senator, State, StatePrediction, Ward, WardResult
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

def seed_lgas(db: Session) -> int:
    """Seed the canonical LGA table from the verified 2023 LGA results (the source
    the assessment picker and state pages use). Other rows reference LGAs by id."""
    if db.scalar(select(func.count()).select_from(Lga)):
        return 0
    seen: set[tuple[str, str]] = set()
    n = 0
    for state, lga in db.execute(select(LgaResult.state, LgaResult.lga).distinct()).all():
        if not state or not lga:
            continue
        state, lga = state.strip(), lga.strip()
        key = (state.lower(), lga.lower())
        if key in seen:
            continue
        seen.add(key)
        db.add(Lga(state=state, name=lga))
        n += 1
    db.commit()
    return n


def _lga_norm(s: str) -> str:
    return "".join(c for c in str(s).lower() if c.isalnum())


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
