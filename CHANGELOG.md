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
