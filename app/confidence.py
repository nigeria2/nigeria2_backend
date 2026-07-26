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
SCORE_INFLATED = 0
SCORE_BLURRY = 10
SCORE_MISSING_SHEET = 20
SCORE_UNSURE = 85
SCORE_VALID = 100

# The roll-up default: a unit's result must score at least this to count in ward/LGA/state.
MIN_ROLLUP_CONFIDENCE = 80

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
