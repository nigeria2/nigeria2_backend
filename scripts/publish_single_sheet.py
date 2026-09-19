#!/usr/bin/env python
"""Publish a single transcribed polling unit sheet live to the database,
making its results live on api.nigeria2.com & nigeria2.com, and assigning
the votes to the matching Federal Constituency politician."""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import select, delete, text
from app.db import SessionLocal
from app import confidence as C
from app import geo
from app.models import (
    Evidence, EvidenceParty, PuSheet,
    PuResult, PuResultParty, PollingUnit,
    HouseMember, LegislativeResult, Lga,
    WardResultV, WardResultParty,
    LgaResultV, LgaResultParty,
)

OFFICE_TO_ET = {
    "presidential": "presidential",
    "governorship": "governor",
    "senatorial": "senate",
    "house-of-reps": "house",
}

# Pre-cached mapping of (state, lga_name_lower) -> constituency_name
_CONSTITUENCY_CACHE: dict[tuple[str, str], str] = {}


def _clean_slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve_constituency(db, state_name: str, lga_name: str) -> str | None:
    """Find the Federal Constituency for a given state and LGA."""
    key = (state_name.strip().lower(), lga_name.strip().lower())
    if key in _CONSTITUENCY_CACHE:
        return _CONSTITUENCY_CACHE[key]

    lga_slug = _clean_slug(lga_name)
    members = db.scalars(
        select(HouseMember).where(HouseMember.state.ilike(f"%{state_name}%"))
    ).all()

    best_match = None
    for m in members:
        # Check if LGA name or parts of it appear in the constituency name
        parts = re.split(r"[/–-]", m.constituency)
        for p in parts:
            p_slug = _clean_slug(p)
            if lga_slug in p_slug or p_slug in lga_slug:
                best_match = m.constituency
                break
            # Handle prefixes/suffixes (e.g. Calabar Municipality -> Calabar Municipal)
            if len(lga_slug) > 5 and len(p_slug) > 5:
                if lga_slug[:6] == p_slug[:6]:
                    best_match = m.constituency
                    break
        if best_match:
            break

    if best_match:
        _CONSTITUENCY_CACHE[key] = best_match
    return best_match


def publish_single_sheet_data(
    pu_code: str,
    parsed: dict,
    sheet_url: str = "",
    office: str = "house-of-reps",
    year: str = "2023",
    db=None,
) -> dict:
    """Publish a single parsed EC8A sheet directly into PostgreSQL,
    make it live in pu_results, and assign votes to the politician."""
    own_db = False
    if db is None:
        db = SessionLocal()
        own_db = True

    try:
        et = OFFICE_TO_ET.get(office, office)
        status = parsed.get("status", "valid")
        an = parsed.get("analysis", {})
        poll = parsed.get("poll", {})
        parties = parsed.get("parties", [])
        vv = parsed.get("valid_votes")
        raw = parsed.get("raw", "{}")

        # 1. Lookup polling unit details
        pu = db.scalar(select(PollingUnit).where(PollingUnit.pu_code == pu_code))
        state_geo = pu.state_geo if pu else None
        lga_id = pu.lga_id if pu else None
        ward_code = pu.ward_code if pu else (pu_code.rsplit("/", 1)[0] if "/" in pu_code else "")
        state_name = pu.state if pu else ""
        lga_name = pu.lga if pu else ""

        # 2. Compute confidence score
        if status == "valid":
            score = C.SCORE_VALID  # 85
        elif status == "unsure":
            score = C.SCORE_UNSURE  # 75
        elif status == "blurry":
            score = C.SCORE_BLURRY  # 10
        else:
            score = 50

        # 3. Upsert evidence & evidence_parties
        ev = db.scalar(
            select(Evidence).where(
                Evidence.pu_code == pu_code,
                Evidence.election_type == et,
                Evidence.year == year,
                Evidence.kind == "llm",
            )
        )
        if ev is None:
            ev = Evidence(
                pu_code=pu_code, election_type=et, year=year,
                state_geo=state_geo, kind="llm", source="LLM (qwen3.5-9b)",
                method=status, registered_voters=poll.get("registered_voters"),
                accredited_voters=poll.get("accredited_voters"),
                valid_votes=vv, rejected_votes=poll.get("rejected_votes"),
                total_used_ballots=poll.get("total_used_ballots"),
                confidence=score, raw=raw,
            )
            db.add(ev)
            db.flush()
        else:
            ev.method = status
            ev.registered_voters = poll.get("registered_voters")
            ev.accredited_voters = poll.get("accredited_voters")
            ev.valid_votes = vv
            ev.rejected_votes = poll.get("rejected_votes")
            ev.total_used_ballots = poll.get("total_used_ballots")
            ev.confidence = score
            ev.raw = raw
            db.execute(delete(EvidenceParty).where(EvidenceParty.evidence_id == ev.id))

        for party, votes in parties:
            db.add(EvidenceParty(evidence_id=ev.id, party=party, votes=votes, votes_words=""))

        # 4. Upsert pu_sheets
        sheet = db.scalar(
            select(PuSheet).where(
                PuSheet.pu_code == pu_code,
                PuSheet.election_type == et,
                PuSheet.year == year,
            )
        )
        sheet_status = "saved" if sheet_url else ("blurry" if status == "blurry" else "")
        if sheet is None:
            sheet = PuSheet(
                pu_code=pu_code, election_type=et, year=year, state_geo=state_geo,
                sheet_url=sheet_url, sheet_status=sheet_status,
                source_image=an.get("source_image", ""),
                status=status, legibility=an.get("legibility", ""),
                model=an.get("model", "qwen3.5-9b"),
                sum_check_passed=an.get("sum_check_passed"),
                totals_consistent=an.get("totals_consistent"),
                validity_notes=an.get("validity_notes", ""),
                discrepancies=an.get("discrepancies", ""),
                transcriptions=json.dumps([json.loads(raw)]) if raw else "[]",
            )
            db.add(sheet)
        else:
            sheet.status = status
            if sheet_url:
                sheet.sheet_url = sheet_url
                sheet.sheet_status = "saved"
            sheet.legibility = an.get("legibility", "")
            sheet.validity_notes = an.get("validity_notes", "")
            sheet.transcriptions = json.dumps([json.loads(raw)]) if raw else "[]"

        # 5. Make result live in pu_results if valid or unsure
        pu_res = None
        if status in ("valid", "unsure") and parties:
            valid_parties = [(p, v) for p, v in parties if v is not None and v >= 0]
            valid_parties.sort(key=lambda x: -x[1])
            winner = valid_parties[0][0] if valid_parties else ""
            runner = valid_parties[1][0] if len(valid_parties) > 1 else ""
            tot = sum(v for _, v in valid_parties) if valid_parties else (vv or 0)

            pu_res = db.scalar(
                select(PuResult).where(
                    PuResult.pu_code == pu_code,
                    PuResult.election_type == et,
                    PuResult.year == year,
                )
            )
            if pu_res is None:
                pu_res = PuResult(
                    pu_code=pu_code, election_type=et, year=year, state_geo=state_geo,
                    lga_id=lga_id, ward_code=ward_code, winner=winner, runner_up=runner,
                    total_votes=tot, valid_votes=vv, registered_voters=poll.get("registered_voters"),
                    source="official", method="confidence-ranked",
                    confidence=score, confidence_band=C.band(score),
                )
                db.add(pu_res)
                db.flush()
            else:
                pu_res.winner = winner
                pu_res.runner_up = runner
                pu_res.total_votes = tot
                pu_res.valid_votes = vv
                pu_res.confidence = score
                pu_res.confidence_band = C.band(score)
                db.execute(delete(PuResultParty).where(PuResultParty.pu_result_id == pu_res.id))

            for party, votes in valid_parties:
                db.add(PuResultParty(pu_result_id=pu_res.id, party=party, votes=votes))
            db.flush()

        # 6. Assign votes to the Federal Constituency Politician (for House)
        assigned_politician = None
        member_new_votes = None
        constituency = None
        if et == "house" and state_name and lga_name:
            constituency = resolve_constituency(db, state_name, lga_name)
            if constituency:
                members = db.scalars(
                    select(HouseMember).where(
                        HouseMember.state.ilike(f"%{state_name}%"),
                        HouseMember.constituency == constituency,
                    )
                ).all()

                parts = re.split(r"[/–-]", constituency)
                lga_rows = db.scalars(select(Lga).where(Lga.state_geo == state_geo)).all()
                constituent_lga_ids = [
                    l.id for l in lga_rows
                    if any(_clean_slug(part) in _clean_slug(l.name) or _clean_slug(l.name) in _clean_slug(part) for part in parts)
                ]
                if not constituent_lga_ids and lga_id:
                    constituent_lga_ids = [lga_id]

                for m in members:
                    calc_sql = text("""
                        SELECT COALESCE(SUM(prp.votes), 0)
                        FROM pu_result_parties prp
                        JOIN pu_results pr ON pr.id = prp.pu_result_id
                        WHERE pr.election_type = 'house'
                          AND pr.year = :year
                          AND prp.party = :party
                          AND pr.lga_id = ANY(:lga_ids)
                    """)
                    total_cand_votes = db.execute(calc_sql, {
                        "year": year,
                        "party": m.party,
                        "lga_ids": constituent_lga_ids,
                    }).scalar()

                    m.votes = int(total_cand_votes or 0)
                    assigned_politician = m.name
                    member_new_votes = m.votes

                    leg = db.scalar(
                        select(LegislativeResult).where(
                            LegislativeResult.election_type == "house",
                            LegislativeResult.year == year,
                            LegislativeResult.constituency == constituency,
                            LegislativeResult.party == m.party,
                        )
                    )
                    if leg is None:
                        leg = LegislativeResult(
                            election_type="house", year=year, state=state_name,
                            state_geo=state_geo, constituency=constituency,
                            candidate=m.name, party=m.party, votes=m.votes,
                            elected=True, politician_id=m.politician_id,
                        )
                        db.add(leg)
                    else:
                        leg.votes = m.votes

        db.commit()

        return {
            "pu_code": pu_code,
            "status": status,
            "confidence": score,
            "constituency": constituency,
            "assigned_politician": assigned_politician,
            "politician_votes": member_new_votes,
            "total_pu_votes": pu_res.total_votes if pu_res else 0,
            "winner": pu_res.winner if pu_res else "",
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        if own_db:
            db.close()


def publish_sheet_from_record(
    ward_path: str,
    img_stem: str,
    record: dict,
    status: str,
    db=None,
) -> dict:
    """Helper that parses ward_path (e.g. 'cross_river/house-of-reps/2023/04_bakassi/01_abana')
    and img_stem (e.g. '001') to construct canonical pu_code, extracts raw votes, and publishes."""
    parts = ward_path.replace("\\", "/").strip("/").split("/")
    state_dir = parts[0]
    office = parts[1] if len(parts) > 1 else "house-of-reps"
    year = parts[2] if len(parts) > 2 else "2023"
    lga_dir = parts[3] if len(parts) > 3 else ""
    ward_dir = parts[4] if len(parts) > 4 else ""

    l_match = re.match(r"(\d+)", lga_dir)
    w_match = re.match(r"(\d+)", ward_dir)
    l_idx = int(l_match.group(1)) if l_match else 1
    w_idx = int(w_match.group(1)) if w_match else 1
    pu_num = img_stem.split("_")[0]

    state_clean = state_dir.replace("_", " ")
    gid = geo.state_geo_id(state_clean)
    state_code = None
    if db is None:
        local_db = SessionLocal()
        state_code = local_db.execute(
            text("select substring(pu_code from 1 for 2) from polling_units where state_geo = :gid limit 1"),
            {"gid": gid}
        ).scalar()
        local_db.close()
    else:
        state_code = db.execute(
            text("select substring(pu_code from 1 for 2) from polling_units where state_geo = :gid limit 1"),
            {"gid": gid}
        ).scalar()

    if not state_code:
        state_code = "01"

    pu_code = f"{state_code}/{l_idx:02d}/{w_idx:02d}/{pu_num}"

    parsed = {
        "status": status,
        "analysis": {
            "source_image": record.get("source_image", f"{img_stem}.jpg"),
            "legibility": record.get("transcription_notes", {}).get("legibility", "readable"),
            "model": record.get("transcription_notes", {}).get("method", "qwen3.5-9b"),
            "sum_check_passed": record.get("validity", {}).get("sum_check_passed", True),
            "totals_consistent": record.get("validity", {}).get("totals_consistent", True),
            "validity_notes": record.get("validity", {}).get("validity_notes", ""),
            "discrepancies": record.get("validity", {}).get("discrepancies", ""),
        },
        "poll": {
            "registered_voters": _to_int(record.get("poll_summary", {}).get("registered_voters")),
            "accredited_voters": _to_int(record.get("poll_summary", {}).get("accredited_voters")),
            "rejected_votes": _to_int(record.get("poll_summary", {}).get("total_rejected_votes")),
            "total_used_ballots": _to_int(record.get("poll_summary", {}).get("total_used_ballots")),
        },
        "valid_votes": _to_int(record.get("poll_summary", {}).get("total_valid_votes")),
        "raw": json.dumps(record),
        "parties": [
            (r["party"], _to_int(r.get("votes_figures")))
            for r in record.get("party_results", [])
            if r.get("party") and _to_int(r.get("votes_figures")) is not None
        ],
    }

    return publish_single_sheet_data(pu_code, parsed, office=office, year=year, db=db)


def _to_int(val) -> int | None:
    if val is None or val == "":
        return None
    try:
        cleaned = re.sub(r"[^\d-]", "", str(val))
        return int(cleaned) if cleaned else None
    except Exception:
        return None

