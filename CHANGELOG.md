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
- **Results are now built from confidence scores rather than a fixed source order.**
  Where several readings of the same polling unit disagree, we now take the one we
  trust most instead of always preferring the machine reading. Hand-crosschecked
  transcriptions rank highest, then clean machine readings, then readings either
  source flagged as unsure. Anything a penalty rule has knocked below 50 is no longer
  used as a unit's result at all — the next-best reading is used instead.
- Ward, LGA and state totals now **only count polling units we are confident in**
  (a score of 80 or more). Units whose only reading is flagged unsure are shown on
  their own page but left out of the totals above them, so an uncertain reading can
  no longer quietly move a state result. This lowers some totals against previous
  figures: the units are still there, but they are no longer counted until we have a
  better reading of them.

### Added
- Confidence scores are now **penalised for obvious misreads**, and hovering a
  confidence badge on a polling-unit page lists exactly what was deducted and why.
  Four rules so far on 2023 presidential readings: (1) −50 where a minor party
  (not APC/LP/PDP/NNPP) is recorded with more than 2,000 votes; (2) −50 where APC, PDP
  and LP all read 0 while two or more minor parties each score over 100 (a mis-aligned
  sheet); (3) −55 where accredited voters read above 1,500 — more than twice the legal
  maximum for a polling unit; (4) −55 where the total votes exceed the unit's registered
  voters, which cannot happen.

### Data
- Loaded the full 2023 crosschecked presidential dataset as evidence — **163,150
  polling units** across all 37 states now carry an independent "2023 transcription"
  reading alongside the LLM one (previously only ~3,900). Each is scored for
  confidence: 90 for crosschecked units, 70 for units flagged unsure.

### Added
- Each transcription in a polling unit's **Evidence** table now shows its own
  **confidence score**, so you can see how much to trust each individual reading
  (not just the merged result).

### Changed
- **Faster deploys.** The site build now prerenders pages in parallel (concurrency)
  with automatic retry on transient network blips — full builds dropped from several
  minutes to ~1.5 minutes and no longer fail on a single flaky fetch. Deploys now
  upload only the files that actually changed and invalidate only those paths, instead
  of re-pushing everything and clearing the whole CDN cache.

### Added
- The ward polling-unit list now shows a **Confidence** column, so you can see each
  unit's 0–100 sheet-quality score alongside its votes.

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
