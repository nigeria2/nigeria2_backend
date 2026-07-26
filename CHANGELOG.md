# Changelog

All notable changes to Nigeria 2.0 (the site, the API, and the underlying data
pipeline) are recorded here. Newest first.

The format is one dated section per change-set. Each entry is a short,
user-facing sentence — what changed and why it matters — grouped under
**Added**, **Changed**, **Fixed**, **Data**, or **Removed**.

> **Rule for contributors (human and AI):** every change to this repository must
> add an entry to the top of this file, under a section for today's date. See
> [CLAUDE.md](CLAUDE.md) for the enforced wording.

## 2026-07-26

### Changed
- Results pages now say **"Estimated Results"** throughout (headings, breadcrumbs and
  captions), making clear these are our estimates transcribed from INEC result sheets,
  not official declared figures.
- The **"Declared"** evidence badge is now labelled **"Online Reports"** to reflect
  what those figures actually are.
- The changelog page now uses a smaller, more compact font.

### Added
- Each polling-unit result now carries a **confidence score (0–100)**, shown top-right
  of the result. The first signal is the quality of the INEC result sheet the figure
  came from: a missing sheet location, a blurry/illegible scan, or an auto-voided
  inflated misread scores low; a clean sheet scores high.
- Ward, LGA and state totals now **exclude low-confidence polling units** (score below
  80) from the roll-up. Those units still appear on their own page — they just don't
  count toward the aggregate — so the published totals lean on trustworthy sheets.

### Fixed
- The evidence table on a polling-unit page no longer hides parties outside the
  four national ones. It now shows a column for any party with a recorded vote in
  the evidence, so a local winner (e.g. BP with 247 votes) is visible instead of
  looking like the evidence disagreed with the result above it.

### Added
- New **Changelog** page (`/changelog`) rendering this file, plus a repository
  rule that every change must record an entry here.
- Ward result tables now show an extra column for any party that **won at least
  one polling unit** in the ward, so locally significant parties (e.g. BP in
  Aba North) are no longer hidden behind the fixed APC/LP/PDP/NNPP columns.
- Accredited-voter figures now appear per polling unit on ward pages, sourced
  from the transcribed EC8A evidence (previously shown only for the handful of
  flagged "problem" units).

### Changed
- Polling-unit pages now group each election's **result sheet(s) and evidence
  directly under that election's result**, with the sheet links at the bottom of
  each election's block — instead of pooling all sheets and evidence at the
  bottom of the page.
- Result-sheet links are now served from the `pu_sheets` table (all 37 states),
  so sheets appear on every polling-unit page, not just Akwa Ibom and Adamawa.

### Removed
- Dropped the redundant legacy `election_sheets` table (and its CSV loader),
  which only ever covered Akwa Ibom and Adamawa. All sheet data now lives in the
  single `pu_sheets` table.
