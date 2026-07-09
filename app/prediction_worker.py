"""Resumable background job that generates model predictions for every state.

Design for robustness:
- All progress lives in the DB (`prediction_scenarios.cursor` / `status`), never
  only in memory. Each state is computed and committed independently, so a job
  that is killed mid-run resumes from the exact state it stopped on.
- A tiny in-process registry (`_TASKS`) stops the same scenario being run twice
  concurrently in one worker process.
- On startup the app calls `resume_running()` to relaunch any scenario still
  marked "running" (i.e. one whose process died), so it self-heals.
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import (
    PredictionScenario,
    ScenarioPolitician,
    ScenarioTrend,
    StatePrediction,
    StatePresidential,
)
from . import prediction_engine as engine

# scenario_id -> running asyncio.Task (this process only)
_TASKS: dict[int, asyncio.Task] = {}

_STEP_DELAY = 0.35  # seconds between states — keeps progress observable and yields


def _states_with_baseline(db: Session) -> list[str]:
    return sorted({s for (s,) in db.execute(select(StatePresidential.state)).all()})


def _log_append(scenario: PredictionScenario, line: str) -> None:
    try:
        log = json.loads(scenario.log) if scenario.log else []
    except Exception:
        log = []
    log.append(line)
    scenario.log = json.dumps(log[-60:])  # keep the last 60 lines


def _load_config(db: Session, scenario_id: int) -> tuple[list[dict], list[dict]]:
    pols = db.scalars(select(ScenarioPolitician).where(ScenarioPolitician.scenario_id == scenario_id)).all()
    trends = db.scalars(select(ScenarioTrend).where(ScenarioTrend.scenario_id == scenario_id)).all()
    pol_dicts = [
        {
            "id": p.politician_id,
            "name": p.politician_name,
            "new_party": p.new_party,
            "delta_popularity": p.delta_popularity,
            "influence_pct": p.influence_pct,
            "scope": p.scope,
            "home_state": p.home_state,
            "old_party": engine.resolve_old_party(db, p.politician_id),
        }
        for p in pols
    ]
    trend_dicts = [
        {
            "name": t.name,
            "shift_pct": t.shift_pct,
            "target_party": t.target_party,
            "scope_states": _load_list(t.scope_states),
        }
        for t in trends
    ]
    return pol_dicts, trend_dicts


def _load_list(s: str) -> list:
    try:
        return json.loads(s) if s else []
    except Exception:
        return []


def _upsert(db: Session, scenario: PredictionScenario, detail: dict) -> None:
    existing = db.scalar(
        select(StatePrediction).where(
            StatePrediction.scenario_id == scenario.id,
            StatePrediction.state == detail["state"],
            StatePrediction.election_type == scenario.election_type,
        )
    )
    scores = detail["result_pct"]
    leader = detail["leader"]
    notes = (
        f"{scenario.name}: modelled {scenario.target_year} {scenario.election_type} "
        f"projection — leads {leader or 'n/a'} on {len(detail['steps'])} adjustment(s)."
    )
    if existing is None:
        existing = StatePrediction(
            user_id=None,
            state=detail["state"],
            election_type=scenario.election_type,
            source="model",
            scenario_id=scenario.id,
        )
        db.add(existing)
    existing.author_name = scenario.name
    existing.author_email = ""
    existing.label = scenario.name
    existing.source = "model"
    existing.scenario_id = scenario.id
    existing.leading_party = leader
    existing.scores = json.dumps(scores)
    existing.detail = json.dumps(detail)
    existing.notes = notes
    existing.year = scenario.target_year


async def run_scenario(scenario_id: int) -> None:
    """Worker coroutine. Processes states from the stored cursor to the end,
    committing after every state so it is fully resumable."""
    db = SessionLocal()
    try:
        states = _states_with_baseline(db)
        pol_dicts, trend_dicts = _load_config(db, scenario_id)
        while True:
            db.expire_all()
            scenario = db.get(PredictionScenario, scenario_id)
            if scenario is None or scenario.status != "running":
                return  # deleted, paused, or stopped elsewhere
            scenario.total = len(states)
            if scenario.cursor >= len(states):
                scenario.status = "done"
                scenario.message = f"Done — {len(states)} states projected."
                _log_append(scenario, scenario.message)
                db.commit()
                return
            state = states[scenario.cursor]
            try:
                detail = engine.compute_state(db, state, pol_dicts, trend_dicts)
                if detail is not None:
                    _upsert(db, scenario, detail)
                    leader = detail["leader"] or "n/a"
                else:
                    leader = "no baseline"
                scenario.cursor += 1
                scenario.message = f"{state} → leads {leader} ({scenario.cursor}/{len(states)})"
                _log_append(scenario, scenario.message)
                db.commit()
            except Exception as exc:  # per-state failure — mark and stop; resumable
                db.rollback()
                scenario = db.get(PredictionScenario, scenario_id)
                if scenario is not None:
                    scenario.status = "error"
                    scenario.message = f"Error on {state}: {exc}"[:300]
                    _log_append(scenario, scenario.message)
                    db.commit()
                return
            await asyncio.sleep(_STEP_DELAY)
    finally:
        db.close()


def start_scenario(scenario_id: int) -> None:
    """Launch (or relaunch) the worker for a scenario if not already running here."""
    task = _TASKS.get(scenario_id)
    if task is not None and not task.done():
        return
    new_task = asyncio.create_task(run_scenario(scenario_id))
    _TASKS[scenario_id] = new_task
    new_task.add_done_callback(lambda t: _TASKS.pop(scenario_id, None))


def resume_running() -> int:
    """On startup, relaunch every scenario left in 'running' state (crash recovery)."""
    if SessionLocal is None:
        return 0
    with SessionLocal() as db:
        ids = [s.id for s in db.scalars(select(PredictionScenario).where(PredictionScenario.status == "running")).all()]
    for sid in ids:
        start_scenario(sid)
    return len(ids)
