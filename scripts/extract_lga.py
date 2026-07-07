"""Build per-LGA 2023 presidential results + per-state LGA SVG geometry.

Combines:
  - data/2023_data/*_crosschecked.csv  (verified per-polling-unit votes, has an LGA column)
  - data/svg/nigeria-lga.geojson        (per-LGA polygons, GADM)

Outputs:
  - backend/app/lga_2023.py             (LGA_RESULTS_2023 -> seeded into the DB)
  - frontend/src/data/lga/<slug>.json   (viewBox + per-LGA path + winner, for the map)

Run:  python backend/scripts/extract_lga.py
"""
import csv
import difflib
import glob
import json
import math
import os
import pathlib
import re
import sys
from collections import defaultdict

sys.setrecursionlimit(50000)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CSV_DIR = ROOT / "data" / "2023_data"
GEOJSON = ROOT / "data" / "svg" / "nigeria-lga.geojson"
OUT_PY = ROOT / "backend" / "app" / "lga_2023.py"
OUT_DIR = ROOT / "frontend" / "src" / "data" / "lga"

PARTIES = ["APC", "LP", "PDP", "NNPP"]
GEO_STATE = {"Federal Capital Territory": "FCT", "Nassarawa": "Nasarawa"}
APP_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
    "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba",
    "Yobe", "Zamfara",
]
CSV_STATE = {s.upper(): s for s in APP_STATES}


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def _int(v) -> int:
    try:
        n = int(str(v).strip())
        return n if n > 0 else 0
    except (TypeError, ValueError):
        return 0


# ---- CSV: aggregate votes per (state, LGA) ----
def load_csv_results():
    res = defaultdict(lambda: defaultdict(lambda: {p: 0 for p in PARTIES}))
    for path in glob.glob(str(CSV_DIR / "*_crosschecked.csv")):
        key = os.path.basename(path).replace("_crosschecked.csv", "").upper()
        state = CSV_STATE.get(key)
        if state is None:
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                lga = (row.get("LGA") or "").strip()
                if not lga:
                    continue
                for p in PARTIES:
                    res[state][lga][p] += _int(row.get(p, 0))
    return res


# ---- geojson: rings per (state, LGA) ----
def load_geojson():
    gj = json.load(open(GEOJSON, encoding="utf-8"))
    out = defaultdict(list)  # state -> [(lga_name, [rings])]
    for f in gj["features"]:
        state = GEO_STATE.get(f["properties"]["NAME_1"], f["properties"]["NAME_1"])
        lga = f["properties"]["NAME_2"]
        geom = f["geometry"]
        rings = geom["coordinates"] if geom["type"] == "Polygon" else [r for poly in geom["coordinates"] for r in poly]
        out[state].append((lga, rings))
    return out


def match_lga(geo_lga: str, csv_lookup: dict):
    """Map a geojson LGA name to a CSV LGA name (exact/prefix/fuzzy)."""
    n = norm(geo_lga)
    if n in csv_lookup:
        return csv_lookup[n]
    cands = [k for k in csv_lookup if (k.startswith(n) or n.startswith(k)) and min(len(k), len(n)) >= 4]
    if len(cands) == 1:
        return csv_lookup[cands[0]]
    close = difflib.get_close_matches(n, list(csv_lookup.keys()), n=1, cutoff=0.82)
    if close:
        return csv_lookup[close[0]]
    return None


# ---- Douglas-Peucker simplification (lon/lat) ----
def centroid(points):
    """Area-weighted centroid of a projected ring (fallback to vertex mean)."""
    n = len(points)
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-9:
        return sum(p[0] for p in points) / n, sum(p[1] for p in points) / n
    a *= 0.5
    return cx / (6 * a), cy / (6 * a)


def dp(pts, eps):
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    denom = math.hypot(dx, dy) or 1e-12
    idx, dmax = 0, 0.0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = abs(dx * (ay - py) - (ax - px) * dy) / denom
        if d > dmax:
            idx, dmax = i, d
    if dmax > eps:
        return dp(pts[: idx + 1], eps)[:-1] + dp(pts[idx:], eps)
    return [pts[0], pts[-1]]


def main():
    csv_res = load_csv_results()
    geo = load_geojson()

    results_py = {}
    matched = unmatched = 0

    for state in APP_STATES:
        lgas_geo = geo.get(state, [])
        csv_lookup = {norm(k): k for k in csv_res.get(state, {})}
        used_csv = set()

        # project bounds for this state
        allpts = [pt for _, rings in lgas_geo for ring in rings for pt in ring]
        if not allpts:
            continue
        minx = min(p[0] for p in allpts); maxx = max(p[0] for p in allpts)
        miny = min(p[1] for p in allpts); maxy = max(p[1] for p in allpts)
        midlat = (miny + maxy) / 2
        kx = math.cos(math.radians(midlat))
        W = 1000.0
        scale = W / max((maxx - minx) * kx, 1e-9)
        H = (maxy - miny) * scale

        def px(x): return round((x - minx) * kx * scale, 1)
        def py(y): return round((maxy - y) * scale, 1)

        eps = (maxx - minx) * 0.004  # ~0.4% of state width
        geo_lgas = []
        state_results = []
        for lga_name, rings in lgas_geo:
            parts = []
            proj_rings = []
            for ring in rings:
                # Drop the closing duplicate vertex so simplification has a real baseline ("Z" recloses).
                r = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
                simp = dp(r, eps) if len(r) > 6 else r
                if len(simp) < 3:
                    continue
                pr = [(px(x), py(y)) for x, y in simp]
                proj_rings.append(pr)
                parts.append("M" + " ".join(f"{x},{y}" for x, y in pr) + "Z")
            if not parts:
                continue
            cx, cy = centroid(max(proj_rings, key=len))
            # attach result
            csv_name = match_lga(lga_name, csv_lookup)
            leader = ""
            pct = 0
            if csv_name and csv_name not in used_csv:
                used_csv.add(csv_name)
                votes = csv_res[state][csv_name]
                total = sum(votes.values())
                if total > 0:
                    scores = {p: round(votes[p] / total * 100, 1) for p in PARTIES}
                    leader = max(PARTIES, key=lambda p: votes[p])
                    pct = round(scores[leader])
                    state_results.append({"lga": lga_name, "leader": leader, "scores": scores, "total_votes": total})
                    matched += 1
                else:
                    unmatched += 1
            else:
                unmatched += 1
            geo_lgas.append({"lga": lga_name, "leader": leader, "pct": pct, "cx": round(cx, 1), "cy": round(cy, 1), "d": "".join(parts)})

        results_py[state] = state_results
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"{slug(state)}.json").write_text(
            json.dumps({"viewBox": f"0 0 1000 {round(H)}", "lgas": geo_lgas}, separators=(",", ":")),
            encoding="utf-8",
        )

    # backend results module
    lines = ['"""Verified 2023 presidential results per LGA (from crosschecked CSVs).',
             "", "Auto-generated by backend/scripts/extract_lga.py. Do not edit.", '"""', "",
             "LGA_RESULTS_2023 = {"]
    for state in APP_STATES:
        rows = results_py.get(state, [])
        if not rows:
            continue
        lines.append(f"    {state!r}: [")
        for r in rows:
            lines.append(f'        {{"lga": {r["lga"]!r}, "leader": {r["leader"]!r}, "scores": {r["scores"]!r}, "total_votes": {r["total_votes"]}}},')
        lines.append("    ],")
    lines.append("}")
    OUT_PY.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tot = matched + unmatched
    print(f"LGAs rendered: {tot} | with results: {matched} ({100*matched/tot:.1f}%) | grey: {unmatched}")
    print(f"Wrote {OUT_PY}")
    print(f"Wrote {len(APP_STATES)} state files -> {OUT_DIR}")
    ai = OUT_DIR / "akwa-ibom.json"
    print("akwa-ibom.json size:", ai.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
