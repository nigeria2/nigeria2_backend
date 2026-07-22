"""Push the local LLM EC8A transcriptions (data_private/jsons_local) into the DB as
polling-unit EVIDENCE (kind='llm').

Every recorded figure is a GUESS — this is one model's reading of a scanned INEC
sheet, stored as evidence alongside any other evidence for the same unit. There is
NO "definitive" and NO submitted_by. A separate rollup/merge pass (the picker) turns
evidence into ward/lga/state results; this script only loads the raw PU evidence.

Data layout (per file, ~213k files):
    jsons_local/<state>/<office>/2023/<NN_lga>/<NN_ward>/<PPP>_<model>_<status>.json
The pu_code is reconstructed deterministically from the path (verified 100% against
polling_units on AK/Lagos/Kano):
    pu_code = <SS>/<lga_idx:02>/<ward_idx:02>/<PPP>
where SS = the state's INEC code (first segment of any pu_code in that state — NB it
is NOT the geo index; Lagos=nga_25 but code 24), lga_idx/ward_idx come from the NN_
folder prefixes, PPP is the zero-padded PU number in the filename. Only PUs present in
the canonical polling_units table are loaded (that also gives us ward_code + lga_id).

Idempotent: clears prior kind='llm' evidence for each (state, office) before loading,
using a correlated subquery (a 100k-element IN-list blows psycopg's param limit).
Bulk inserts per (state, office) — per-row over the remote DB would time out.

Run LOCALLY (prod DATABASE_URL in backend/.env):
    python scripts/push_jsons_local.py                 # all states, all offices
    python scripts/push_jsons_local.py --states akwa_ibom,lagos
    python scripts/push_jsons_local.py --offices presidential
    python scripts/push_jsons_local.py --include-unsure=false   # valid only
    python scripts/push_jsons_local.py --dry-run       # scan + map, no writes
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import re
import sys
import threading
import time
import urllib.parse

# UTF-8 console for the ✓/█ box glyphs (Windows cp1252 default breaks them).
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import psycopg

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

BACKEND = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app import geo  # noqa: E402

# Paths are relative to the repo root (override the private-data location with DATA_PRIVATE_DIR
# if it lives elsewhere). Never hard-code an absolute developer path.
DATA_PRIVATE = pathlib.Path(os.environ.get("DATA_PRIVATE_DIR") or (REPO_ROOT / "data_private"))
JROOT = DATA_PRIVATE / "jsons_local"
# Harvested INEC IReV API metadata (same state/office/2023/lga/ward path shape), one file
# per ward listing its PUs — each PU's `document.url` is the real INEC result-sheet PDF.
API_ROOT = DATA_PRIVATE / "pdfs" / "_api"
MODEL = "qwen3.5-9b"
SOURCE = f"LLM ({MODEL})"
# NB: the election year is read from the folder path (<state>/<office>/<year>/...), NOT
# hard-coded — off-cycle governorships have their own years (Anambra 2021/2025, Edo 2020/2024).

OFFICE_TO_ET = {"presidential": "presidential", "governorship": "governor", "senatorial": "senate"}
# statuses we treat as loadable evidence (blurry/truncated are too unreliable)
DEFAULT_STATUSES = {"valid", "unsure"}


# --- DB helpers -----------------------------------------------------------------
def get_raw_dsn():
    """Return a libpq DSN for a direct psycopg connection (COPY needs the raw driver)."""
    for line in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip()
            break
    else:
        sys.exit("DATABASE_URL not found in backend/.env")
    # psycopg accepts postgres:// and postgresql:// directly; strip the +driver if present
    return url.replace("postgresql+psycopg://", "postgresql://").replace("postgres+psycopg://", "postgres://")


def state_lookup(raw, state_geo):
    """Return (state_code, {pu_code: (ward_code, lga_id)}) for a state from polling_units."""
    lk = {}
    code = None
    with raw.cursor() as c:
        c.execute("select pu_code, ward_code, lga_id from polling_units where state_geo=%s",
                  (state_geo,))
        for pu_code, ward_code, lga_id in c.fetchall():
            if pu_code:
                lk[pu_code] = (ward_code, lga_id)
                if code is None:
                    code = pu_code.split("/")[0]
    return code, lk


# --- parsing --------------------------------------------------------------------
_NUM = re.compile(r"-?\d+")


# Sane per-polling-unit ceilings. Transcriptions occasionally carry an OCR-mangled figure
# with too many digits (e.g. a party with "1610126415" votes, or "65785113956" registered)
# — one such value destroys every downstream sum. A real PU has at most ~1,500 voters, so a
# single party can't exceed a few thousand; poll-summary counts stay in the low thousands.
# Anything above these ceilings is noise → drop it (None). (Also guards the int4 column.)
_PARTY_VOTE_CAP = 5000       # one party's votes at a single PU
_POLL_SUMMARY_CAP = 20000    # registered / accredited / valid / etc. at a single PU


def _int(v, cap=None):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    m = _NUM.search(s)
    if not m:
        return None
    n = int(m.group())
    if n < 0 or (cap is not None and n > cap):
        return None
    return n


def _idx(folder):
    m = re.match(r"(\d+)", folder)
    return int(m.group(1)) if m else None


def parse_file(path: pathlib.Path):
    """Return a dict with the parsed votes/poll PLUS the model's analysis and the FULL raw
    JSON, or None. Nothing the model produced is dropped — `raw` is the verbatim text."""
    try:
        text = path.read_text(encoding="utf-8")
        d = json.loads(text)
    except Exception:
        return None
    parties = []
    for pr in d.get("party_results", []):
        party = (pr.get("party") or "").strip().upper()
        if not party:
            continue
        parties.append((party, _int(pr.get("votes_figures"), cap=_PARTY_VOTE_CAP)))
    ps = d.get("poll_summary", {}) or {}
    poll = {
        "registered_voters": _int(ps.get("1_registered_voters"), cap=_POLL_SUMMARY_CAP),
        "accredited_voters": _int(ps.get("2_accredited_voters"), cap=_POLL_SUMMARY_CAP),
        "valid_votes": _int(ps.get("7_total_valid_votes"), cap=_POLL_SUMMARY_CAP),
        "rejected_votes": _int(ps.get("6_rejected_ballots"), cap=_POLL_SUMMARY_CAP),
        "total_used_ballots": _int(ps.get("8_total_used_ballot_papers"), cap=_POLL_SUMMARY_CAP),
    }
    dt = _int((d.get("declared_total_valid_votes") or {}).get("figures"), cap=_POLL_SUMMARY_CAP)
    vv = poll["valid_votes"] if poll["valid_votes"] is not None else dt
    # the model's own read of the sheet — the analysis + comment the user wants surfaced
    val = d.get("validity", {}) or {}
    notes = d.get("transcription_notes", {}) or {}
    analysis = {
        "status": (val.get("status") or "").strip(),
        "legibility": (notes.get("legibility") or "").strip(),
        "model": (notes.get("method") or "").replace("openrouter:", "").strip() or MODEL,
        "sum_check_passed": val.get("sum_check_passed"),
        "totals_consistent": val.get("totals_internally_consistent"),
        "validity_notes": (val.get("validity_notes") or "").strip() or None,
        "discrepancies": (notes.get("discrepancies") or "").strip() or None,
        "source_image": (d.get("source_image") or "").strip(),
    }
    return {"parties": parties, "poll": poll, "valid_votes": vv,
            "analysis": analysis, "raw": text}


# --- board (rich TUI) -----------------------------------------------------------
class Board:
    def __init__(self, plan, offices, workers_note, dry, quiet=False):
        self.plan = plan                 # list of (state_folder, geo, file_total)
        self.offices = offices
        self.note = workers_note
        self.dry = dry
        self.quiet = quiet               # --no-tui: print log lines instead of the Live board
        self.cur = None
        self.cur_state = None
        self.cur_done = 0
        self.cur_total = 0
        self.state_done = {}
        self.done_files = {}             # state -> files processed (frozen once done)
        self.ev_written = 0
        self.ep_written = 0
        self.skipped_unmapped = 0
        self.parse_fail = 0
        self.recent = []
        self.start = time.time()

    def log(self, line):
        self.recent = (self.recent + [line])[-9:]
        if self.quiet:
            print(f"[{time.strftime('%H:%M:%S')}] {line}", flush=True)

    def __rich__(self):
        el = int(time.time() - self.start)
        grand_total = sum(t for _, _, t in self.plan)
        grand_done = sum(self.done_files.get(s, 0) for s, _, _ in self.plan)
        gp = (grand_done / grand_total * 100) if grand_total else 100.0

        title = Text.assemble(
            ("  jsons_local ", "bold white on dark_blue"),
            ("→ evidence (kind=llm)  ", "bold white on dark_blue"),
            (f"  {SOURCE}", "dim"),
            ("   DRY-RUN" if self.dry else "", "bold yellow"),
            (f"   offices: {', '.join(self.offices)}", "dim"))

        tbl = Table.grid(padding=(0, 1))
        tbl.add_column(width=3)
        tbl.add_column(width=14)
        tbl.add_column()
        tbl.add_column(justify="right")
        for s, _, tot in self.plan:
            done = self.done_files.get(s, 0)
            pct = (done / tot * 100) if tot else 100.0
            if self.state_done.get(s) or (tot and done >= tot):
                mark = Text("✓", "bold green")
                bar = Text("█" * 14, "green")
            elif s == self.cur_state:
                fill = int(14 * done / tot) if tot else 0
                mark = Text("▶", "bold yellow")
                bar = Text("█" * fill, "yellow") + Text("░" * (14 - fill), "dim")
            else:
                mark = Text(" ", "")
                bar = Text("░" * 14, "dim")
            style = "bold yellow" if s == self.cur_state else ("green" if self.state_done.get(s) else "white")
            tbl.add_row(mark, Text(s, style), bar, Text(f"{pct:5.1f}%  {done}/{tot}", "dim"))

        overall = Text.assemble(
            ("  OVERALL  ", "bold"), (f"{grand_done}/{grand_total}", "bold cyan"),
            (f"  ({gp:.1f}%)", "cyan"),
            ("    elapsed ", "dim"), (f"{el // 3600}h{el % 3600 // 60:02d}m{el % 60:02d}s", "white"))
        stats = Text.assemble(
            ("  evidence ", "dim"), (f"{self.ev_written}", "bold green"),
            ("  party rows ", "dim"), (f"{self.ep_written}", "green"),
            ("  unmapped ", "dim"), (f"{self.skipped_unmapped}", "yellow"),
            ("  parse-fail ", "dim"), (f"{self.parse_fail}", "red"))

        rt = Table.grid()
        for r in self.recent:
            rt.add_row(Text(r, "white"))
        recent_panel = Panel(rt if self.recent else Text("…", "dim"),
                             title="[bold]recent", border_style="blue", padding=(0, 1))

        return Group(
            title,
            Panel(tbl, title="[bold]states", border_style="green", padding=(0, 1)),
            overall, stats, recent_panel)


# --- core -----------------------------------------------------------------------
# INEC result-sheet URL resolution — ported verbatim from data_private/download_sheets.py so
# we store the URL THAT ACTUALLY SERVES, not the harvested (broken) one. Two rules:
#   * dead hosts (docs.inecelectionresults.net, irevx.ams3) don't serve — drop / alias them
#   * the lon1 bucket keys files under a LEADING <election-id>/ segment the harvested `url`
#     drops (elections_prod/<id>/... 403s; <id>/elections_prod/<id>/... is 200)
# `document.document_url` is usually already the id-prefixed lon1 URL that works.
_DEAD_HOST_ALIAS = {
    "iiirev.incportals.com": "inc-s3-cache.incportals.com",
    "irevx.ams3.cdn.digitaloceanspaces.com": "irev-results.lon1.digitaloceanspaces.com",
}
_DROP_HOSTS = {"docs.inecelectionresults.net"}
_LON1_MISSING_ID = re.compile(
    r"^(https://irev-results\.lon1\.digitaloceanspaces\.com)/elections_prod/(\d+)/(.*)$")


def _alias(url: str):
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return None
    live = _DEAD_HOST_ALIAS.get(p.netloc.lower())
    return urllib.parse.urlunparse(p._replace(netloc=live)) if live else None


def _lon1_fix(url: str):
    m = _LON1_MISSING_ID.match(url or "")
    if not m:
        return None
    base, eid, rest = m.groups()
    return f"{base}/{eid}/elections_prod/{eid}/{rest}"


def _best_sheet_url(doc: dict) -> str:
    """Pick the INEC URL that actually serves, mirroring download_sheets.candidate_urls:
    id-prefixed lon1 first, then aliased variants, dropping dead hosts."""
    raw = [doc.get("document_url"), doc.get("url"), doc.get("backup_url")]
    src, path = doc.get("source"), doc.get("document_path")
    if src and path:
        raw.append(src.rstrip("/") + "/" + path.lstrip("/"))
    candidates = []
    for u in raw:
        if not u:
            continue
        for v in ([_alias(u)] if _alias(u) else []) + [u]:
            fx = _lon1_fix(v)
            if fx:
                candidates.append(fx)   # fixed url first
            candidates.append(v)
    for u in candidates:
        host = urllib.parse.urlparse(u).netloc.lower()
        if host and host not in _DROP_HOSTS:
            return u
    return ""


def load_sheet_urls(state_folder: str, office: str, year: str) -> dict[str, tuple[str, str]]:
    """Build {pu_code: (sheet_url, status)} for a (state, office, year) from the harvested IReV
    API metadata under pdfs/_api, choosing the URL that ACTUALLY serves (see _best_sheet_url).
    Returns {} if that state/office/year wasn't harvested."""
    base = API_ROOT / state_folder / office / year
    out: dict[str, tuple[str, str]] = {}
    if not base.is_dir():
        return out
    for lga_dir in base.iterdir():
        if not lga_dir.is_dir():
            continue
        for wf in lga_dir.glob("*.json"):
            try:
                pus = json.loads(wf.read_text(encoding="utf-8"))
            except Exception:
                continue
            for pu in (pus if isinstance(pus, list) else []):
                code = (pu.get("pu_code") or "").strip()
                if not code:
                    continue
                url = _best_sheet_url(pu.get("document") or {})
                status = "saved" if url else ("no_sheet" if pu.get("is_zero_pu") else "")
                out[code] = (url, status)
    return out


def office_years(state_dir: pathlib.Path, office: str) -> list[str]:
    """The election year folder(s) present under <state>/<office>/ (a 4-digit year name).
    Most offices have just 2023, but off-cycle governorships have their own years
    (Anambra 2021/2025, Edo 2020/2024, Ekiti 2022/2026, ...), so we iterate whatever exists."""
    base = state_dir / office
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir()
                  if d.is_dir() and re.fullmatch(r"\d{4}", d.name))


def iter_files(state_dir: pathlib.Path, office: str, year: str, statuses: set[str]):
    """Yield (path, lga_idx, ward_idx, pu_num) for each loadable json under state/office/year."""
    base = state_dir / office / year
    if not base.is_dir():
        return
    for lga_dir in sorted(base.iterdir()):
        if not lga_dir.is_dir():
            continue
        li = _idx(lga_dir.name)
        for ward_dir in sorted(lga_dir.iterdir()):
            if not ward_dir.is_dir():
                continue
            wi = _idx(ward_dir.name)
            for f in ward_dir.iterdir():
                if f.suffix != ".json":
                    continue
                # <PPP>_<model>_<status>.json
                stem = f.stem
                parts = stem.split("_")
                status = parts[-1] if parts else ""
                if status not in statuses:
                    continue
                pu_num = parts[0]
                yield f, li, wi, pu_num, status


def load_state_office(raw, board, state_dir, state_geo, state_code, pu_lookup,
                      office, year, statuses, dry):
    et = OFFICE_TO_ET[office]
    # real INEC result-sheet URLs for this (state, office, year), keyed by pu_code
    sheet_urls = load_sheet_urls(state_dir.name, office, year)
    # gather rows for this (state, office, year)
    ev_rows = []      # dict for Evidence bulk insert (now includes raw JSON)
    ep_rows = []      # (pu_code, party, votes) staged; resolved to evidence_id after flush
    sheet_rows = []   # one pu_sheet per unit: sheet + full transcription JSON + analysis
    seen = set()      # de-dupe pu_code within this office (one evidence per unit)
    processed = 0
    for f, li, wi, pu_num, status in iter_files(state_dir, office, year, statuses):
        processed += 1
        if processed % 400 == 0:
            board.cur_done = board.done_files.get(state_dir.name, 0) + processed
        if li is None or wi is None or state_code is None:
            board.skipped_unmapped += 1
            continue
        pu_code = f"{state_code}/{li:02d}/{wi:02d}/{pu_num}"
        info = pu_lookup.get(pu_code)
        if info is None:
            board.skipped_unmapped += 1
            continue
        key = (pu_code, et)
        if key in seen:      # already have an evidence row for this unit/office
            continue
        parsed = parse_file(f)
        if parsed is None:
            board.parse_fail += 1
            continue
        parties, poll, vv = parsed["parties"], parsed["poll"], parsed["valid_votes"]
        an = parsed["analysis"]
        seen.add(key)
        ev_rows.append({
            "pu_code": pu_code, "election_type": et, "year": year,
            "state_geo": state_geo, "kind": "llm", "source": SOURCE,
            "method": status,  # valid | unsure — the model's own confidence flag
            "registered_voters": poll["registered_voters"],
            "accredited_voters": poll["accredited_voters"],
            "valid_votes": vv,
            "rejected_votes": poll["rejected_votes"],
            "total_used_ballots": poll["total_used_ballots"],
            "raw": parsed["raw"],        # verbatim transcription JSON — nothing dropped
        })
        for party, votes in parties:
            ep_rows.append((pu_code, et, party, votes))
        # one pu_sheet row per unit/office: the sheet + this transcription (as a 1-element
        # JSON array so more transcriptions of the same sheet can be appended later).
        sheet_url, sheet_status = sheet_urls.get(pu_code, ("", ""))
        sheet_rows.append({
            "pu_code": pu_code, "election_type": et, "year": year, "state_geo": state_geo,
            "sheet_url": sheet_url, "sheet_status": sheet_status, "source_image": an["source_image"],
            "status": status, "legibility": an["legibility"], "model": an["model"],
            "sum_check_passed": an["sum_check_passed"], "totals_consistent": an["totals_consistent"],
            "validity_notes": an["validity_notes"], "discrepancies": an["discrepancies"],
            "transcriptions": json.dumps([json.loads(parsed["raw"])]),
        })

    if dry:
        board.ev_written += len(ev_rows)
        board.ep_written += len(ep_rows)
        board.log(f"[dry] {state_dir.name}/{office}/{year}: {len(ev_rows)} ev, {len(ep_rows)} party rows")
        return

    if not ev_rows:
        board.log(f"{state_dir.name}/{office}/{year}: nothing to load")
        return

    # Raw psycopg COPY — the ONLY thing fast enough over the remote DB. bulk_insert_mappings
    # does per-row round-trips (~56k/state) and hangs on the high-latency link. One COPY each
    # for evidence, evidence_parties, and pu_sheets.
    ep_written = _copy_state_office(raw, state_geo, et, year, ev_rows, ep_rows, sheet_rows)

    board.ev_written += len(ev_rows)
    board.ep_written += ep_written
    board.log(f"{state_dir.name}/{office}/{year}: +{len(ev_rows)} evidence, +{ep_written} party rows, "
              f"+{len(sheet_rows)} sheets")


_EV_COLS = ["pu_code", "election_type", "year", "state_geo", "kind", "source", "method",
            "registered_voters", "accredited_voters", "valid_votes", "rejected_votes",
            "total_used_ballots", "raw"]
_SHEET_COLS = ["pu_code", "election_type", "year", "state_geo", "sheet_url", "sheet_status",
               "source_image", "status", "legibility", "model", "sum_check_passed",
               "totals_consistent", "validity_notes", "discrepancies", "transcriptions"]


def _copy_state_office(raw, state_geo, et, year, ev_rows, ep_rows, sheet_rows):
    """Idempotently replace this (state, office, year) LLM evidence + pu_sheets using COPY.
    Returns party-row count."""
    with raw.cursor() as cur:
        # idempotent clear (correlated subquery; small per-state scope)
        cur.execute(
            "delete from evidence_parties ep using evidence e "
            "where ep.evidence_id = e.id and e.kind='llm' and e.state_geo=%s "
            "and e.election_type=%s and e.year=%s", (state_geo, et, year))
        cur.execute(
            "delete from evidence where kind='llm' and state_geo=%s and election_type=%s and year=%s",
            (state_geo, et, year))
        cur.execute(
            "delete from pu_sheets where state_geo=%s and election_type=%s and year=%s",
            (state_geo, et, year))

        # COPY evidence
        with cur.copy(f"copy evidence ({', '.join(_EV_COLS)}) from stdin") as cp:
            for r in ev_rows:
                cp.write_row([r[c] for c in _EV_COLS])

        # recover pu_code -> id for the rows we just wrote
        cur.execute(
            "select pu_code, id from evidence where kind='llm' and state_geo=%s "
            "and election_type=%s and year=%s", (state_geo, et, year))
        id_by_code = dict(cur.fetchall())

        # COPY evidence_parties
        n = 0
        with cur.copy("copy evidence_parties (evidence_id, party, votes, votes_words) from stdin") as cp:
            for pc, e, party, votes in ep_rows:
                if e != et:
                    continue
                eid = id_by_code.get(pc)
                if eid is None:
                    continue
                cp.write_row([eid, party, votes, ""])
                n += 1

        # COPY pu_sheets (sheet + full transcription JSON + the model's analysis/comment)
        with cur.copy(f"copy pu_sheets ({', '.join(_SHEET_COLS)}) from stdin") as cp:
            for r in sheet_rows:
                cp.write_row([r[c] for c in _SHEET_COLS])
    raw.commit()
    return n


def count_files(state_dir, offices, statuses):
    n = 0
    for office in offices:
        for year in office_years(state_dir, office):
            for _ in iter_files(state_dir, office, year, statuses):
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", default="", help="comma list of state folders; default all")
    ap.add_argument("--offices", default="presidential,governorship,senatorial")
    ap.add_argument("--include-unsure", default="true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-tui", action="store_true",
                    help="print plain progress lines instead of the full-screen board "
                         "(for unattended/logged runs, e.g. the recurring 2-hourly push)")
    args = ap.parse_args()

    statuses = {"valid"} if args.__dict__["include_unsure"].lower() in ("false", "0", "no") else DEFAULT_STATUSES
    offices = [o.strip() for o in args.offices.split(",") if o.strip() in OFFICE_TO_ET]

    all_states = sorted(p.name for p in JROOT.iterdir() if p.is_dir())
    want = [s.strip() for s in args.states.split(",") if s.strip()]
    states = [s for s in (want or all_states) if (JROOT / s).is_dir()]

    dsn = get_raw_dsn()

    # plan: (state_folder, geo, file_total)
    plan = []
    for s in states:
        gid = geo.state_geo_id(s.replace("_", " "))
        if not gid:
            continue
        plan.append((s, gid, count_files(JROOT / s, offices, statuses)))

    board = Board(plan, offices, "", args.dry_run, quiet=args.no_tui)
    err = {}

    def worker():
        # dedicated connection for the load; the TUI runs on the main thread and repaints
        # on rich's own tick, so a long COPY never freezes the board.
        raw = psycopg.connect(dsn, autocommit=False)
        try:
            for s, gid, tot in plan:
                board.cur_state = s
                board.cur_total = tot
                board.cur_done = board.done_files.get(s, 0)
                state_code, pu_lookup = state_lookup(raw, gid)
                board.log(f"== {s} ({gid}) code={state_code}  {len(pu_lookup)} canonical PUs ==")
                for office in offices:
                    for year in office_years(JROOT / s, office):
                        load_state_office(raw, board, JROOT / s, gid, state_code, pu_lookup,
                                          office, year, statuses, args.dry_run)
                board.done_files[s] = tot
                board.state_done[s] = True
            board.cur_state = None
        except Exception as e:  # noqa: BLE001
            err["exc"] = e
            board.log(f"ERROR: {str(e)[:80]}")
        finally:
            raw.close()

    if args.no_tui:
        # unattended: run the load inline, plain log lines (see Board.log quiet mode)
        worker()
        print(f"DONE. evidence={board.ev_written} party_rows={board.ep_written} "
              f"unmapped={board.skipped_unmapped} parse_fail={board.parse_fail}"
              + ("  (dry-run — nothing written)" if args.dry_run else ""), flush=True)
        if "exc" in err:
            print(f"FAILED: {err['exc']}", flush=True)
            raise SystemExit(1)
        return

    console = Console(legacy_windows=False)
    t = threading.Thread(target=worker, name="loader", daemon=True)
    with Live(board, console=console, refresh_per_second=4, screen=True, vertical_overflow="crop"):
        t.start()
        while t.is_alive():
            time.sleep(0.25)
        time.sleep(1)

    console.print(f"[bold green]DONE.[/] evidence={board.ev_written} party_rows={board.ep_written} "
                  f"unmapped={board.skipped_unmapped} parse_fail={board.parse_fail}"
                  + ("  [yellow](dry-run — nothing written)[/]" if args.dry_run else ""))
    if "exc" in err:
        console.print(f"[bold red]FAILED:[/] {err['exc']}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
