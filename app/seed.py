"""Seed the predictions table with illustrative, already-aggregated data.

Real data would be crunched from raw contributor traces upstream; this just
gives the map something to render across weeks and election types.
"""
import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .data_2023 import PAST_ELECTION_2023
from .lga_2023 import LGA_RESULTS_2023
from .models import Analysis, LgaResult, Party, PartyElection, Politician, Prediction, ProblemUnit, StatePrediction

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
