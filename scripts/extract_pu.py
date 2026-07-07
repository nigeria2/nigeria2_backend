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
    """norm(PU-Code) -> (registered, known_votes)."""
    reg = {}
    votes = {}
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
                    kv = sum((_int(row.get(p)) or 0) for p in PARTIES)
                    if kv > 0:
                        votes[code] = kv
    return reg, votes


def main():
    reg, votes = load_2023()
    print(f"2023: registered for {len(reg):,} PUs | known votes for {len(votes):,} PUs")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    matched_reg = matched_votes = 0
    with open(PU_CSV, encoding="utf-8", newline="") as fh, gzip.open(OUT, "wt", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        w.writerow(["state", "lga", "ward", "ward_code", "pu_name", "pu_code", "registered_voters", "known_votes"])
        for row in csv.DictReader(fh):
            state = canon_state(row.get("state", ""))
            if state is None:
                continue
            code = (row.get("code") or "").strip()
            ncode = norm_code(code)
            ward_code = code.rsplit("/", 1)[0] if "/" in code else ""
            r = reg.get(ncode)
            kv = votes.get(ncode)
            if r is not None:
                matched_reg += 1
            if kv is not None:
                matched_votes += 1
            w.writerow([
                state,
                (row.get("lg") or "").strip().title(),
                (row.get("ward") or "").strip().title(),
                ward_code,
                (row.get("location") or "").strip(),
                code,
                r if r is not None else "",
                kv if kv is not None else "",
            ])
            n += 1

    print(f"polling units written: {n:,}")
    print(f"  with registered voters: {matched_reg:,} ({100*matched_reg/n:.0f}%)")
    print(f"  with known votes:       {matched_votes:,} ({100*matched_votes/n:.0f}%)")
    print(f"Wrote {OUT}  ({OUT.stat().st_size // 1024} KB gzipped)")


if __name__ == "__main__":
    main()
