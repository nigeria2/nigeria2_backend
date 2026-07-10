"""Build the authoritative 774-LGA canonical list -> backend/app/data/lgas.json.

Sources:
  - data/unstructured_data/Nigeria_Wards_Lat-Long1.csv  (774 LGAs, full names — the
    official ward dataset; the single most complete LGA name list we have)
  - data/svg/nigeria-lga.geojson                        (GADM polygons -> geo_id)

For each LGA we emit {state, geo_id, name}. Names come from the wards CSV (cleaned for
stray spacing + a short high-confidence typo map); geo_id is matched to the geojson LGA
(exact / prefix / close). geo_id is best-effort (a handful have no confident geojson
match and are emitted null). Run: python backend/scripts/build_lgas.py
"""
import csv
import difflib
import json
import pathlib
import re
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.geo import _STATE_BY_NUM, state_geo_id  # noqa: E402

WARDS_CSV = ROOT / "data" / "unstructured_data" / "Nigeria_Wards_Lat-Long1.csv"
GEOJSON = ROOT / "data" / "svg" / "nigeria-lga.geojson"
OUT = ROOT / "backend" / "app" / "data" / "lgas.json"

# clear typos in the source ward dataset (base name -> corrected). Conservative:
# only unambiguous misspellings, not accepted spelling variants.
_FIX = {
    "Esan Centtral": "Esan Central",
    "Badagary": "Badagry",
    "Tundun Wada": "Tudun Wada",
    "Dutsin-Ma": "Dutsin-Ma",
    "Malumfashi": "Malumfashi",
}


def norm(s: str) -> str:
    return "".join(c for c in str(s or "").lower() if c.isalnum())


def clean(name: str) -> str:
    n = " ".join(name.split())
    n = re.sub(r"\s*-\s*", "-", n)
    n = re.sub(r"\s*/\s*", "/", n)
    return _FIX.get(n, n)


def main() -> None:
    gj = json.load(open(GEOJSON, encoding="utf-8"))
    geo_by_state: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for f in gj["features"]:
        m = re.match(r"NGA\.(\d+)\.(\d+)_1", f["properties"]["ID_2"])
        if not m:
            continue
        s, l = int(m.group(1)), int(m.group(2))
        geo_by_state[s].append((norm(f["properties"]["NAME_2"]), f"nga_{s}_{l}"))

    lga_by_state: dict[int, set[str]] = defaultdict(set)
    for r in csv.DictReader(open(WARDS_CSV, encoding="utf-8-sig")):
        gid = state_geo_id((r.get("State") or "").strip())
        if not gid:
            continue
        name = clean((r.get("LGA") or "").strip())
        if name:
            lga_by_state[int(gid.split("_")[1])].add(name)

    def match_geo(sidx: int, name: str, used: set[str]):
        n = norm(name)
        cands = geo_by_state.get(sidx, [])
        for gn, gid in cands:
            if gn == n and gid not in used:
                return gid
        pref = [gid for gn, gid in cands if n.startswith(gn) and len(gn) >= 4 and gid not in used]
        if len(pref) == 1:
            return pref[0]
        pref2 = [gid for gn, gid in cands if gn.startswith(n) and len(n) >= 4 and gid not in used]
        if len(pref2) == 1:
            return pref2[0]
        close = difflib.get_close_matches(n, [gn for gn, g in cands if g not in used], n=1, cutoff=0.86)
        if close:
            for gn, gid in cands:
                if gn == close[0] and gid not in used:
                    return gid
        return None

    out = []
    for sidx in sorted(lga_by_state):
        state = _STATE_BY_NUM[sidx]
        used: set[str] = set()
        for name in sorted(lga_by_state[sidx]):
            gid = match_geo(sidx, name, used)
            if gid:
                used.add(gid)
            out.append({"state": state, "geo_id": gid, "name": name})

    OUT.write_text(json.dumps({"lgas": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: {len(out)} LGAs | with geo_id {sum(1 for x in out if x['geo_id'])}")


if __name__ == "__main__":
    main()
