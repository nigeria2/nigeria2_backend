"""Join all polling units with their 2023 registered voters + known votes.

Reads:
  data/Nigeria_polling_units.csv            (176k PUs: state/lg/ward/code/location)
  data/2023_data/*_{crosschecked,unsure,notfound}.csv  (registered voters + votes)

Writes:
  backend/app/data/polling_units.csv.gz     (slim, pre-joined; seeded into the DB)

Run:  python backend/scripts/extract_pu.py
"""
import csv
import glob
import gzip
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PU_CSV = ROOT / "data" / "Nigeria_polling_units.csv"
DATA_DIR = ROOT / "data" / "2023_data"
OUT = ROOT / "backend" / "app" / "data" / "polling_units.csv.gz"
OUT_WARDS = ROOT / "backend" / "app" / "data" / "ward_results.csv.gz"

PARTIES = ["APC", "LP", "PDP", "NNPP"]
APP_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
    "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba",
    "Yobe", "Zamfara",
]
_BYNORM = {re.sub(r"[^a-z]", "", s.lower()): s for s in APP_STATES}
_BYNORM["federalcapitalterritory"] = "FCT"
_BYNORM["fct"] = "FCT"
_BYNORM["abuja"] = "FCT"
_BYNORM["nassarawa"] = "Nasarawa"


def canon_state(s):
    return _BYNORM.get(re.sub(r"[^a-z]", "", (s or "").lower()))


def norm_code(s):
    return re.sub(r"[^0-9]", "", s or "")


def _int(v):
    try:
        n = int(str(v).strip())
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def load_2023():
    """norm(PU-Code) -> registered, and -> {party: votes} (from crosschecked)."""
    reg = {}
    pvotes = {}
    for path in glob.glob(str(DATA_DIR / "*.csv")):
        crosschecked = path.endswith("_crosschecked.csv")
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                code = norm_code(row.get("PU-Code", ""))
                if not code:
                    continue
                r = _int(row.get("Registered_Voters"))
                if r is not None and code not in reg:
                    reg[code] = r
                if crosschecked:
                    v = {p: (_int(row.get(p)) or 0) for p in PARTIES}
                    if sum(v.values()) > 0:
                        pvotes[code] = v
    return reg, pvotes


def top2(v: dict) -> tuple:
    ranked = sorted(PARTIES, key=lambda p: v[p], reverse=True)
    return ranked[0], ranked[1]


def main():
    import collections

    reg, pvotes = load_2023()
    print(f"2023: registered for {len(reg):,} PUs | party votes for {len(pvotes):,} PUs")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    matched_reg = matched_votes = 0
    ward_agg = collections.defaultdict(lambda: {p: 0 for p in PARTIES})
    ward_meta = {}

    with open(PU_CSV, encoding="utf-8", newline="") as fh, gzip.open(OUT, "wt", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        w.writerow(["state", "lga", "ward", "ward_code", "pu_name", "pu_code", "registered_voters",
                    "apc", "lp", "pdp", "nnpp", "known_votes", "winner", "runner_up"])
        for row in csv.DictReader(fh):
            state = canon_state(row.get("state", ""))
            if state is None:
                continue
            code = (row.get("code") or "").strip()
            ncode = norm_code(code)
            ward_code = code.rsplit("/", 1)[0] if "/" in code else ""
            lga = (row.get("lg") or "").strip().title()
            ward = (row.get("ward") or "").strip().title()
            r = reg.get(ncode)
            v = pvotes.get(ncode)
            if r is not None:
                matched_reg += 1
            winner = runner = ""
            kv = ""
            va = vl = vp = vn = ""
            if v is not None:
                matched_votes += 1
                kv = sum(v.values())
                va, vl, vp, vn = v["APC"], v["LP"], v["PDP"], v["NNPP"]
                winner, runner = top2(v)
                agg = ward_agg[ward_code]
                for p in PARTIES:
                    agg[p] += v[p]
                ward_meta[ward_code] = (state, lga, ward)
            w.writerow([state, lga, ward, ward_code, (row.get("location") or "").strip(), code,
                        r if r is not None else "", va, vl, vp, vn, kv, winner, runner])
            n += 1

    print(f"polling units written: {n:,}")
    print(f"  with registered voters: {matched_reg:,} ({100*matched_reg/n:.0f}%)")
    print(f"  with a winner:          {matched_votes:,} ({100*matched_votes/n:.0f}%)")
    print(f"Wrote {OUT}  ({OUT.stat().st_size // 1024} KB gzipped)")

    # ward results
    nw = 0
    with gzip.open(OUT_WARDS, "wt", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        w.writerow(["state", "lga", "ward", "ward_code", "apc", "lp", "pdp", "nnpp", "total_votes", "winner", "runner_up"])
        for ward_code, agg in ward_agg.items():
            total = sum(agg.values())
            if total <= 0:
                continue
            state, lga, ward = ward_meta[ward_code]
            winner, runner = top2(agg)
            w.writerow([state, lga, ward, ward_code, agg["APC"], agg["LP"], agg["PDP"], agg["NNPP"], total, winner, runner])
            nw += 1
    print(f"ward results written: {nw:,}  ({OUT_WARDS.stat().st_size // 1024} KB gzipped)")


if __name__ == "__main__":
    main()
