"""Confidence scoring for polling-unit results (0-100).

The score answers "how much should we trust THIS unit's result?" The first signal is
SHEET QUALITY — the state of the INEC result sheet the figures came from. More signals
(cross-read agreement, human confirmation, crowd corroboration) can be folded in later
by lowering/raising from this baseline.

Rules (first matching, lowest wins):
  0   inflated/voided misread  — an auto-correction zeroed the sheet (known bad read)
  10  blurry / illegible       — the scan could not be read
  20  missing sheet location   — no sheet URL, or the sheet is dead/absent (no_sheet/dead)
  85  model 'unsure'           — readable but a check disagreed (kept, still trusted enough)
  100 clean valid sheet        — saved, readable, passed its checks

Bands: high >= 80, medium 50-79, low < 50.
"""
from __future__ import annotations

# Score constants — single source of truth (the PS1 backfill mirrors these values).
#
# The scores encode a DELIBERATE TRUST LADDER, because the merge picks the highest-scoring
# reading. Hand-crosschecked transcriptions outrank even a clean LLM read: the human data
# fails our sanity checks far less often (accredited > 1500: 1 case vs the LLM's 5,927;
# votes > registered: 1.0% vs 9.7%). The ladder, highest first:
#
#   90  hand-crosschecked (2023_transcription, *_crosschecked.csv)
#   85  LLM, sheet passed its checks ("valid")
#   75  LLM, sheet readable but a check disagreed ("unsure")
#   70  hand, flagged unsure (*_unsure.csv)
#   20  missing sheet location   |  10 blurry/illegible  |  0 voided inflated misread
#
# Penalty rules (scripts/penalties.py) subtract from these, pushing broken readings below
# the MIN_RESULT_CONFIDENCE floor so they stop being used as a unit's result.
SCORE_INFLATED = 0
SCORE_BLURRY = 10
SCORE_MISSING_SHEET = 20
SCORE_HAND_UNSURE = 70          # hand transcription flagged unsure
SCORE_UNSURE = 75               # LLM read, a check disagreed
SCORE_VALID = 85                # LLM read, checks passed
SCORE_HAND_CROSSCHECKED = 90    # hand-crosschecked — the most trusted reading
# A correction (manual, or the auto-void of an inflated misread) is a deliberate decision
# rather than a reading, so it outranks everything and is never treated as "low quality".
SCORE_CORRECTION = 95

# The roll-up default: a unit's result must score at least this to count in ward/LGA/state.
#
# IMPORTANT: this number is only meaningful relative to the ladder above. It excludes any
# tier scoring below it, so if you rescale the scores you MUST re-check what it now cuts.
# (History: it was set to 80 when clean LLM scored 100. Rescaling the ladder so hand-
# crosschecked ranked top pushed llm-unsure(75) and hand-unsure(70) under it, silently
# dropping ~3.1M presidential and ~14M governor votes from the totals.)
MIN_ROLLUP_CONFIDENCE = 80

# A reading must score at least this to be used as a polling unit's RESULT at all. Every
# penalty rule takes off >= 50, so anything penalised falls under this and is skipped in
# favour of the next-best reading (or no result, if nothing qualifies).
MIN_RESULT_CONFIDENCE = 50

# sheet_status values that mean "there is no usable sheet at this location"
_MISSING_SHEET_STATUSES = {"no_sheet", "dead", ""}


def band(score: int | None) -> str:
    """high (>=80) / medium (50-79) / low (<50); '' when unscored."""
    if score is None:
        return ""
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def score_from_sheet(
    *,
    sheet_url: str | None,
    sheet_status: str | None,
    validity_status: str | None,
    legibility: str | None,
    is_inflated: bool = False,
) -> int:
    """Compute a 0-100 confidence from a sheet's quality signals.

    `validity_status` is pu_sheets.status ('valid' | 'unsure' | ''); `legibility` is
    'readable' | 'illegible' | ''; `is_inflated` marks an auto-voided all-parties-inflated
    misread. Lowest applicable score wins."""
    if is_inflated:
        return SCORE_INFLATED
    if (legibility or "").lower() in ("illegible", "blurry"):
        return SCORE_BLURRY
    if (validity_status or "").lower() == "blurry":
        return SCORE_BLURRY
    url = (sheet_url or "").strip()
    status = (sheet_status or "").strip().lower()
    if not url or status in _MISSING_SHEET_STATUSES:
        return SCORE_MISSING_SHEET
    if (validity_status or "").lower() == "unsure":
        return SCORE_UNSURE
    return SCORE_VALID
