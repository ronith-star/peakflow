# Reuse-Ready second audit (work order item 20)

Auditor: independent session with no memory of the build. Date: 2026-09-25. Specification: audit/SPEC.md, including "Later instructions (2026-09-25, after the first audit)"; figure rules from scratch/standards/STANDARDS.md. Machine-readable list: audit/gaps_v2.csv. The first audit (audit/AUDIT.md, audit/gaps.csv) is unchanged.

## Verdict

**Usable for the brief with fixes; not usable as is for the cooling-water-quality claims.** Both first-audit blockers are resolved. A clean clone with every raw download deleted rebuilds end to end in 1,058 s with exit 0, and all 108 tests pass. `fetch --verify` now fails on missing or unrecorded files. I recomputed the headline numbers independently and they reproduce: the Falls calibration (135,000 gal/day average, 4.4 MGD peak day, 5.94 percent wet hours), the table cells, the 7Q10 (1,794.85 cfs), the 22/24 and 5/17/2 supply-screen counts, and the 10-mile buffers. No new blocker was found.

Two major weaknesses remain in the evidence base:

- **Cycles section (G11, N02).** It rests entirely on literature water quality. The Water Quality Portal was never reached, no permittee reports silica, and a parsing rule discards all Delaware effluent chemistry.
- **Citations and provenance (G08, G09, G10).** results.md is still hand-maintained, and several citations are weak: a placeholder repository URL, and a township source that is now dead and carries a site (DRB33).

The remaining items are minor presentation and hygiene issues. Fixing all open items is estimated at about 21 hours.

## 1. Reproduction

| Check | Result |
|---|---|
| Environment | Existing conda env `reuse-ready` in clean workspace clones (rsync excluding scratch/ and .git). No new env was created. |
| Build 1: clone, `make clean && make all`, cached raw data | EXIT 0, 72.75 s wall. Only notice: "Matplotlib is building the font cache; this may take a moment." |
| Build 2: clone with data/raw and data/processed emptied (kept MANIFEST.md, two tracker CSVs, two URL CSVs) | EXIT 0, 1,058.15 s wall (gis 599.5 s, echo 328.9 s, isd 51.9 s). Both `fetch --verify` runs: "all 357 MANIFEST rows present with matching SHA-256; no unrecorded raw files". |
| Warnings or errors (both logs, verbatim) | Build 2 line 8: "fetch: 6 re-downloaded file(s) differ from the previously recorded SHA-256 (new hash recorded): ['usgs/dv_01463500.rdb', 'drbc/datacenters.html', 'press/amazon_falls_campus_2026.html', 'press/falls_herald_2026.html', 'press/falls_keystone_2026.html', 'press/falls_levittown_2026.html']". No warning, error or traceback lines. The colorspacious SyntaxWarning and fontTools messages are suppressed in code (G23). |
| Tests | 108 passed, 0 failed (4.73 s and 4.75 s). |
| Verify failure path | Deleting lbnl_2024.pdf gives exit 1 ("lbnl_2024.pdf: missing"). Adding an extra file gives exit 1 ("extra.txt: no MANIFEST row"). |
| Rebuild against committed | results CSV and JSON, figure PNGs and _data.csv files are byte-identical. PDF and SVG differ in metadata only; the committed copies were not built under SOURCE_DATE_EPOCH (N01). wqp_status.json differs in the error text only. In the clean clone the last provisional gauge day moved from 5,460 to 5,400 cfs, with no effect on results. |
| Required files | Present: all figures (png, pdf, svg, caption, data CSV), results (calibration.json, exclusions.csv, supply_screen.csv, table_blindspot csv/md/png, results.md), references.bib (47 entries), sources.md, data/raw/MANIFEST.md (357 rows), tests (14 modules). Missing: none. Present but orphaned: data/sites/planned_sites_research*.csv (N08). Should have been deleted: assets/fonts/Inter-* (G02). |

## 2. Data completeness (full datasets)

**Weather** (data/processed/weather_hourly.parquet, 350,640 rows):

- Both KTTN and KPHL cover 2005-01-01 00:00 to 2024-12-31 23:00 UTC: 20 full years, 175,320 of 175,320 expected hours, no duplicate hours. The 2025 partial year has exclusion rows for both stations.
- Wet-bulb missing fraction: KTTN 0.920 percent (1,613 h), KPHL 0.107 percent (187 h).
- **The only year above 5 percent missing is KTTN 2005, at 10.18 percent.** Next highest: KTTN 2024 1.81 percent, KTTN 2007 1.02 percent, KPHL 2024 0.47 percent.
- The wet-bulb series matches my own Stull (2011) and Magnus computation to 0.0 C.

**Gauge** (01463500):

- 41,630 daily values, 1912-10-01 to 2026-09-24. Missing days: 2 (2026-07-15, 2026-07-16). 566 provisional days (from 2025-03-06) and 1,019 estimated days.
- 7Q10 on the full record: my independent LP3 (method of moments, climatic years April to March, complete years only) gives 1,794.85 cfs from 113 years (CY1914 to 2026, skew -0.2568). Approved-only data give 1,787.34 cfs from 111 years. Both match flow_stats.json.

**WWTPs (ECHO NPDES majors):**

| State | Majors in DRB counties (ECHO) | Retained | With DMR effluent flow | With any chemistry | With silica | With chloride |
|---|---|---|---|---|---|---|
| DE | 18 | 9 | 9 | **0** | 0 | 0 |
| NJ | 101 | 82 | 77 | 77 | 0 | 1 |
| NY | 45 | 34 | 11 | 31 | 0 | 0 |
| PA | 152 | 133 | 122 | 125 | 0 | 13 |
| Total | 316 | 258 | 219 | 233 | **0** | 14 |

- The accounting closes: 917 statewide majors = 601 outside DRB counties + 58 below threshold or with no flow + 258 retained.
- No plant in a DRB county with any ECHO flow field above 5 MGD is absent. Wilmington (63.33 MGD), Gloucester County UA (16.46), Kent County (11.89) and Ewing-Lawrence (6.85) are all retained with 36 DMR months each.
- The Delaware chemistry count of 0 is a parsing defect, not missing data (N02).
- The 23 NY plants without effluent flow report influent flow only (N07). None is closer to a site than the matched plant, so no site class is affected.

**Sites:**

- 24 active sites against DRBC's 24 (Khalil p. 22, confirmed on the live PDF). The state split is 17/4/3 against DRBC's 18/3/3; the difference is disclosed.
- Location: 16 exact, 6 approximate, 2 uncertain. Unverified: 10 (3 source: DRB07, DRB32, DRB33; 8 location; DRB07 in both).
- Live fetch of each site source URL: 21 return 200. DRB07 returns 403. DRB27 returns 406, which is new. DRB33's replacement (limerickpa.org) returns 404 across the domain (G10).

**Exclusions:** no record vanished. The reconciliation by stage:

- ECHO: 917 = 659 exclusion rows + 258 retained.
- Supply screen: 258 - 180 eligible = 78 exclusion rows (54 non-POTW, 24 with fewer than 12 flow months).
- Sites: 63 = 24 active + 39 exclusion rows (11 inactive, 23 near-miss outside the basin, 5 not data center records).
- Weather: 2 rows for 2025.

## 3. Model and calibration

- **Calibration targets.** calibration.json reports all three Falls targets with residuals: average -2.2e-16, peak 0.0, wet share -0.93 percent, all_three_feasible_within_1pct true. I reran the hourly model independently from the KTTN series and the stored parameters: annual mean of daily makeup 135,000.0 gal/day, peak day 4,400,000 gal/day, wet-hour fraction 0.059445, max 30-day average 1,405,677 gal/day, p99 day 2,333,587. All match the stored diagnostics exactly. The 2 percent sensitivity is reported as infeasible (peak 7.18 MGD, or average about 82,000 gal/day).
- **Reconciliation.** Per Message 12, results.md keeps 19,000 gal/day as cited potable demand and calibrates to the filed 135,000 gal/day average. The infeasibility of the original 19,000 gal/day average against a 4.4 MGD peak on about 6 percent of hours is not stated in one sentence (N13, minor). The 4.4 MGD, 135,000, 6 percent, 19,000 and 243 million figures all appear in the stored press copy.
- **WUE and PUE.**
  - The WUE ranges of 1.72 to 2.78 and 0 to 1.56 L/kWh match the digitized LBNL Figure 4.4 whiskers (p. 46).
  - The 0.36 L/kWh US average is on p. 48, and the "0.1 to 0.3 L/kWh" hyperscale adiabatic statement is on p. 47.
  - Microsoft 0.27 and 0.30 were confirmed on the live page.
  - PUE 1.15 to 1.35 is LBNL's projected 2028 fleet average (p. 47), not a per-facility range, and is cited as p. 48 (N04).

## 4. Regulatory threshold

The stored DRBC Administrative Manual (data/raw/drbc/admin_manualCFR.pdf) contains the 18 CFR 401.35(a)(2) and (a)(3) text "the daily average gross withdrawal during any 30 consecutive day period does not exceed 100,000 gallons". This matches sources.md verbatim, and make docs confirms all six passages. The table applies it as a trailing 30-day mean of daily makeup, with at least 27 valid days per window, compared against 100,000 gal/day. That is correct.

## 5. Table (Deliverable A)

- **Recomputed cells.** I recomputed every hybrid-row cell, and the 50 MW tower cell, from the model outputs:
  - Max 30-day average: 212,219 / 424,437 / 848,874 / 1,697,749.
  - p99 day: 352,308 / 704,615 / 1,409,231 / 2,818,462.
  - Peak day: 664,279 / 1,328,559 / 2,657,117 / 5,314,235.
  - Days per year (30-day test): 24.8 / 56.8 / 88.4 / 105.0.
  - Days per year (single day): 27.1 / 35.8 / 41.3 / 44.6.
  - 50 MW tower: 751,423.
  - All match the CSV at 3 significant figures. The averaging band of 7.53 to 23.6 MW reproduces.
  - The annual-mean column is a mean of calendar-year means (40,718 against the pooled 40,563 at 100 MW); this is defined nowhere (N12).
- **Consistency across formats.** The .md and .csv agree cell for cell (13 rows, 0 mismatches). The PNG, read at 100 percent, shows the same values.
- **Headline against shading.** "0 of 12 ... escape by averaging" matches 0 shaded cells (Shaded = No in all 13 rows), and "all 8 that would trigger it" matches 8 Yes cells in "Review if self-supplied" across the 12 grid rows.
- **Footnotes.** Every sourced cell carries a footnote marker: ¹ model, ² DRBC, ³ USGS, ⁴ Falls filings, ⁵ purchased supply. Each footnote carries citation keys.
- **Brief table.** table_blindspot_brief.csv is 6 rows by 5 columns, with the renamed columns and the order Falls, three hybrids, tower, air-cooled, as specified. The full PNG is 330 mm wide with an in-image title; the departure is logged in pending_approvals.md (N05).

## 6. Map (Deliverable B)

- **Basin boundary.** The boundary is WBD HUC4 0204 (13,610 sq mi in EPSG:5070, which matches the published DRB area).
- **Rivers.** The Delaware and Schuylkill are each labelled once on v3.
- **Circle scaling.** Plant circles are area-scaled: marker area / flow = 3.0 pt² per MGD for 179 of 180 plants. Millersville 0.547 MGD has 1.64 pt² and Phila Southwest 172.5 MGD has 517.5 pt², a ratio of 315.36 in both flow and area. There is one floor at 0.9 pt² (Walden 0.025 MGD, outside the basin).
- **Site classes.** The class for each of the 24 sites equals supply_screen.csv (crosstab diagonal 5/17/2). All 10 dashed outlines are unverified and all 14 solid outlines are verified.
- **Buffers.** Buffers are 16,093.44 m circles in an Albers equal-area CRS. Measured geodesically, DRB12, DRB23 and DRB01 give 9.997 to 10.003 mi.
- **Insets and layout.** The insets (falls_plymouth_detail_v2) are present, each with a km and mi scale bar. The QA check reports no text overlaps, nothing outside the figure and a minimum font of 7.0 pt (6.5 pt in the brief version). I found no overlap or floating text at 100 percent. The source line is present.
- **Frame and graticule.** A neat line and edge-only graticule ticks are present, which Message 13+ (SPEC line 290) permits and which supersede the original "no frame". There are no interior gridlines.
- **Colour vision.** Under deuteranopia and protanopia simulation the fill-encoded colours are at least 12.0 apart (delta-E, half against water). Water against the county line is 9.1 and 10.6 (G20).
- **Consistency of counts.** The title count, bar, supply_screen.csv and results.md all state 22 of 24 and 5/17/2 with 1 and 9 unverified.
- **HTML hover cards.** All 24 sites have a card with a source link, matched plant with distance and median flow, class, and verification status (44 of 48 card instances contain flow; the other 4 are the two no-plant sites, which correctly show none). Tiles are Esri (G19).
- **Distance spot-checks** (geodesic WGS84 against the repo's EPSG:5070 distance):

  | Site | Plant | Geodesic (mi) | Repo, EPSG:5070 (mi) |
  |---|---|---|---|
  | DRB12 | Trenton Sewer Utility | 1.936 | 1.928 |
  | DRB14 | Pennridge WWTP | 0.965 | 0.959 |
  | DRB24 | LCA Allentown | 2.608 | 2.622 |

  Across all 24 sites, the nearest-plant choice agrees with the repo in every case.

## 7. Citations and prose

- **Live URL check** for all 47 bib entries and 24 site URLs (url_live_check.csv in the audit workspace):
  - 56 of 71 return 200.
  - Not checkable here (sandbox proxy): stull_2011, mytton_2021.
  - Broken or refusing:
    - reuse_ready_model: placeholder, 404.
    - limerick_cu_hearings_2026 and DRB33: 404, domain down.
    - amazon_falls_campus_2026, alduchov_1996, limerick_laurel_chestnuthill_2026 and DRB07: 403.
    - DRB27: 406.
    - epa_echo: redirect loop.
    - usgs_nwis: 503, transient.
    - dzombak_2012 and midkiff_1977 (OSTI): SSL errors, intermittent.
- **Cited figures.** Figures cited in sources.md were confirmed on the live page for falls_keystone (4.4 million), falls_levittown and falls_herald (quotes), Microsoft (0.27, 0.30), Meta (0.19), Google (7,787), Khalil (18/3/3, 24), WFMZ (753 acres), the DRBC drought page (December 2024, June 2025), shehabi_2024, uptime_survey_2025 and the other quoted press pages (16 quotes found).
  - Not confirmable from the landing page: geiger_1993 (the value is in the PDF), cleanview (already marked unverified), trackdatacenters (page renders by JavaScript).
- **Prose.** results.md, README.md, brief_numbers.md and all 15 caption files contain 0 em dashes, 0 en dashes, 0 exclamation marks, 0 informal terms, 0 contractions and no fragments. Every results.md sentence with a number carries a key; the only flagged lines are list numerals. Captions have about 49 numeric sentences without keys (N09).

## 8. Status of first-audit gaps G01 to G23

| ID | Status | Evidence (short) |
|---|---|---|
| G01 | Resolved | Clean clone with raw data deleted: exit 0 in 1,058 s. All 8 previously non-re-creatable files are now fetched. |
| G02 | Partly resolved | PDFs are Helvetica/Arial only and the font test exists. Inter TTFs, NOTICE.md and the README line remain. |
| G03 | Resolved | Verify exits 1 on missing and on unrecorded files. |
| G04 | Resolved | Peak-day primary (331 MW, 0.429). "Exactly determined" is stated. |
| G05 | Resolved | DE 0 to 9 retained; Wilmington, Gloucester, Kent and Ewing-Lawrence have DMRs; exclusion reasons split. |
| G06 | Resolved | 30-day-window column per valid window-year reproduces. |
| G07 | Resolved | Spread of 10 is flagged in results.md. |
| G08 | Partly resolved | Content added, but results.md is still hand-written and kept by clean. |
| G09 | Partly resolved | Placeholder URL, dead Limerick link, several 403s (see section 7). |
| G10 | Partly resolved | Wayback overrides for DRB01, 04 and 05. DRB33 replacement is now dead and DRB27 returns 406. |
| G11 | Open | WQP never fetched; silica 0 of 258. |
| G12 | Partly resolved | `urls` separated and lock file added. No git (the user will run it). |
| G13 | Resolved | 17/4/3 against 18/3/3 disclosed; unverified count of 10 consistent. |
| G14 | Resolved | Bin renamed everywhere. |
| G15 | Resolved | 39 of 39 site drops have exclusion rows. |
| G16 | Resolved | Prose grep clean; enforced by a test. |
| G17 | Partly resolved | 6 unused keys, including 4 spec-named sources; L_v unsourced. |
| G18 | Resolved | Provisional days disclosed; approved-only sensitivity of 1,787 cfs. |
| G19 | Partly resolved | Rivers labelled and bar resized. HTML still uses Esri tiles. |
| G20 | Partly resolved | Pair exempted from the test, not fixed (9.1 and 10.6). |
| G21 | Resolved | Technical appendix with a license table. |
| G22 | Resolved | Achieved-average WUE is 0.0442. |
| G23 | Partly resolved | Log is clean because warnings are suppressed; .DS_Store files on disk. |

## 9. Ranked open gaps

No open blockers.

**Major**

1. **G11 (WQP / cycles).** No WQP data and no silica in ECHO, so all cycles inputs are literature-assumed. Fix: fetch and cache WQP data, and label the figure and brief as assumed until then. About 3 h.
2. **N02 (ECHO chemistry for Delaware).** chem_medians() ignores DAILY AV, so all 9 DE plants lose chemistry (Wilmington has 36 TSS and CBOD5 months). Fix: add the same fallback monthly_flow() uses, plus a test. About 1 h.
3. **G09 (bib URLs).** Placeholder repository URL, a dead Limerick source marked verified, and 403 or SSL failures. Fix: set the URL after git, add Wayback captures, and re-mark entries as unverified where needed. About 2 h.
4. **G10 (site URLs).** DRB33 (dead replacement), DRB27 (406) and DRB07 (403). Fix: add Wayback captures to source_url_overrides.csv. About 1 h.
5. **G08 (results.md provenance).** Still hand-maintained, and the test covers only part of the numbers. Fix: generate it from a template, or extend expected_phrases(). About 4 h.

**Minor** (in order of effect on the brief)

1. N04: PUE range is a 2028 fleet projection, and its page is cited wrongly.
2. N10: Morrisville capacity is 243 MGD allocation against 25 MGD physical capacity.
3. N13: add the infeasibility sentence for the original 19,000 gal/day target.
4. N07: ambiguous no-flow sentence; NY plants report influent flow only.
5. N03: raw drift is silently re-hashed; a frozen mode is needed.
6. N11: figures are macOS-font-dependent.
7. G17: unused spec-named sources; L_v unsourced.
8. G20: county line against water fails the delta-E threshold under colour-vision simulation.
9. N09: unkeyed numbers in captions.
10. N05: superseded v1 and v2 figures still shipped.
11. G02: delete the Inter files.
12. G19: Esri tiles in the HTML map.
13. N12: define the annual-mean statistic.
14. N01: committed PDF and SVG were built outside make.
15. G12: git, the user's step.
16. G23: suppressed warnings and .DS_Store files.
17. N06: brief_numbers.md is 306 words, above the 300 cap.
18. N08: orphan research CSVs.

## 10. Done well (do not change during fixes)

- Hermetic data layer. Every raw file has a MANIFEST row with URL, timestamp, rows and SHA-256. A clean clone rebuilds from nothing, and verify fails correctly.
- Model transparency. calibration.json stores targets, achieved values, residuals, feasibility flags, sensitivities and diagnostics. My independent recompute matched it to machine precision.
- Exclusion accounting closes at every stage: ECHO 917, supply screen 258, sites 63.
- The table pipeline writes CSV, MD and PNG from one source, and they agree cell for cell. Footnotes carry keys, and the headline is computed.
- Regulatory quotes are verified automatically against the stored rule text.
- Map QA. Area-true circles, equal-area buffers, automated overlap checks saved to *_check.json, and site classes identical to supply_screen.csv.
- Honest caveats in results.md: provisional-day and approved-only 7Q10, KTTN 2005 gap, the exactly determined fit, 2 percent infeasibility, capacity sensitivity spread, and literature-assumed cycles.
- The prose test (test_prose_rules) enforces no dashes and keyed numbers in results.md.

## 11. Proposed fix order and effort

1. N02 (1 h), then G11 (3 h). Rerun echo, wqp and cycles together.
2. G09 and G10 URL repairs and verification flags (3 h).
3. N04, N10, N13, N07, N12 and N06 text corrections in results.md, captions and brief_numbers (1.5 h).
4. G08 results.md generation or broader test coverage (4 h). Do this after step 3 so the template captures the corrected text.
5. N09 caption keys and extending test_prose_rules to captions (1 h).
6. G20 county-line colour, G19 HTML tiles, N05 archiving old figures (2 h).
7. N03 frozen fetch mode and N11 font portability note or vendored font (3 h).
8. G17 citations (1 h).
9. Pre-commit housekeeping: G02, N08, G23 and N01 (rebuild via make all), then the user runs git init, sets the URLs (G12) and tags (1.2 h).

**Total: about 21 hours (about 3 working days).** This is down from about 41 hours at the first audit.
