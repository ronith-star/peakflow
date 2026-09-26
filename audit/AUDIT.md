# Audit of the PeakFlow repository

Audit date: 2026-09-25. Specification: audit/SPEC.md, including every follow-up message, with later instructions superseding earlier ones (135,000 gal/day recalibration, v2 and v3 figure redesigns, the Msg 16 font rule). The auditor wrote only this report and audit/gaps.csv and modified no other file in the repository.

## Verdict

The repository is **usable for the brief with fixes, but not as is.** Its analytical core holds up. An independent recomputation from the full hourly weather file reproduces the three Falls calibration targets, the 30-day statistics and the blind-spot table cells to machine precision. An independent geodesic nearest-plant search reproduces all 24 site-to-plant matches. The DRBC trigger of a 30-day average above 100,000 gal/day is quoted verbatim from the rule and applied correctly in the review columns. The capacity-independent headline (22 of 24 sites within 10 miles of an eligible municipal plant) is robust. Three problems prevent use as is. First, the pipeline cannot be rebuilt from a clean clone: `make all` fails at the docs step after 740 s because the DRBC rule, the DRBC data-center page and four press pages are never downloaded, and `fetch --verify` reports success anyway (G01, G03). Second, every committed figure except the v3 map is stale and embeds the Inter font that Msg 16 prohibits (G03). Third, several substantive choices weaken the brief without being disclosed:
- the primary calibration reads the 4.4 MGD peak as an hourly rate although every source calls it a daily withdrawal (G06);
- all 18 Delaware permittees, including the 64 MGD Wilmington plant, are dropped because ECHO lists no design flow for them (G05);
- the table column labelled as days above the trigger counts single days rather than 30-day averages (G11);
- the matchable count moves by 10 sites across the capacity sensitivity without being flagged, although the user asked to be told of any move above two (G07);
- no silica data were obtained (G11).

The audit found 3 blockers, 9 major gaps and 11 minor gaps. The estimated total effort is about 41 hours (about five working days).

## Ranked gap list

Gaps are ordered by how much they weaken the brief, blockers first. The same rows, with the same identifiers, are in audit/gaps.csv.

### G01 [blocker] Reproduction

**Finding.** A true clean clone cannot complete `make all`: it fails at the docs step, and 8 raw files listed in MANIFEST.md cannot be recreated by any fetch step.

**Evidence.** Clone with data/raw emptied except the two hand-supplied tracker CSVs and MANIFEST.md: EXIT=2 after 740 s, final line 'docs: a regulatory passage was not found verbatim in its raw copy'. Never re-created: drbc/admin_manualCFR.pdf, drbc/datacenters.html, press/{amazon_falls_campus,falls_herald,falls_keystone,falls_levittown}_2026.html, natural_earth/ne_10m_populated_places_simple.zip and lbnl_2024.pdf. fetch.py STEPS has no step for the DRBC rule PDF, datacenters.html or the press pages. With the Desktop cache copied in, the same build passes in 46 s, so the README claim that the pipeline 'runs from a clean clone with three commands' is false.

**Proposed fix.** Add a fetch step for each DRBC and press file (with the URL recorded in MANIFEST), or commit them under an explicit data-license note. Make docs.py fail with a message naming the missing file. Add a CI-style check that runs `make all` from an empty data/raw.

**Effort.** 0.5 day

### G02 [blocker] Figures

**Finding.** Every committed figure except map v3 is stale: they embed Inter, which Msg 16 prohibits, and do not match what the current code produces.

**Evidence.** PDF /BaseFont in the committed files: table_blindspot.pdf Inter-Bold/Regular/SemiBold; supply_screen_map.pdf, supply_screen_map_v2.pdf, supply_screen_bar_v2.pdf and falls_plymouth_detail_v2.pdf Inter-*. The rebuilt files use Helvetica or Arial Narrow. The rebuild differs from the committed copy in 20 figure files, and supply_screen_map_v2_data.csv label offsets differ for sites 10, 15, 17 and 22. Only supply_screen_map_v3.png and its data CSV are byte-identical. assets/fonts still ships Inter, and inter_font remains in references.bib.

**Proposed fix.** Run `make all` and commit the regenerated figures. Delete assets/fonts/Inter-* and the inter_font entry. Add a test that greps every figures/*.pdf for /BaseFont and fails on Inter.

**Effort.** 1 hour

### G03 [blocker] Reproduction

**Finding.** `fetch --verify` reports success when files listed in the manifest are missing.

**Evidence.** In the clean clone, both `fetch` and `fetch --verify` printed 'fetch: MANIFEST covers all 293 rows / raw files' although 8 listed files were absent from disk (see G01). An independent SHA-256 pass over the Desktop copy matches all 293 rows, so the manifest itself is correct.

**Proposed fix.** Make --verify check that each listed file exists and that its SHA-256 matches, and exit non-zero on any mismatch.

**Effort.** 1 hour

### G04 [major] Model

**Finding.** The primary calibration reads 4.4 MGD as a maximum hourly rate × 24, but every source describes it as a peak daily withdrawal. The three-parameter, three-target fit is exactly determined, so its near-zero residuals are not evidence of fit quality.

**Evidence.** calibration.json 'design_rate': achieved peak_gpd 4,400,000 is max hourly × 24, while the modelled peak day is 3,972,028 gal/day. Sources: falls_keystone_2026 'maximum peak daily withdrawal of 4.4 million gal/day'; falls_levittown_2026 'peak demand of 4.4 million gallons per day'. The peak-day reading (331 MW, gamma 0.429) is the one that matches the source wording, yet it is labelled secondary. Independent recompute from weather_hourly.parquet with the documented physics reproduces avg 135,000, peak 4,400,000, wet fraction 0.05944, peak day 3,972,028 and max 30-day 1,388,474 exactly. With T_sw, gamma and P_IT free against three targets, the residuals are zero by construction.

**Proposed fix.** Make the peak-day interpretation primary, or justify the design-rate reading with a source. Rerun the supply screen with the corresponding per-MW rate. Say in results.md that the fit is exactly determined and that agreement within 1 percent is not a validation.

**Effort.** 0.5 day

### G05 [major] Data: WWTPs

**Finding.** All 18 Delaware majors, and several large NJ POTWs, are dropped because ECHO reports no design flow for them. The exclusion reason merges 'not reported' with '<= 1 MGD'.

**Evidence.** Majors in DRB counties per ECHO (county intersects the WBD 020401+020402 boundary): PA 152, NJ 101, NY 45, DE 18 (316). Retrieved: PA 133, NJ 62, NY 29, DE 0 (224). 64 of the 92 dropped for 'design flow not greater than 1 MGD (or not reported)' have a null design flow. POTWs inside the basin with reported flow above 5 MGD that are absent: City of Wilmington Regional WWTP DE0020320 (64.36 MGD past-year average), Gloucester County UA NJ0024686 (15.72), Kent County WWTF DE0020338 (11.65), Ewing-Lawrence SA NJ0024759 (7.50). Absent outside the basin: Parsippany-Troy Hills NJ0024970 (8.49). Absent non-POTWs above 5 MGD: Salem GS (280.6), Calpine Mid-Atlantic (92.9), Delaware City Refining (50.1), Hope Creek (11.3), Paulsboro (9.5 actual). The v3 map shows Wilmington with no plant. Re-running the nearest-plant rule with the 9 absent in-basin POTWs above 1 MGD added (past-year flow as proxy) changes no site class, because Wilmington is 10.75 mi from DRB02 and 11.69 mi from DRB01.

**Proposed fix.** Fall back to CWPActualAverageFlowNmbr or PastCalYrAverageFlow (or DMR median) when design flow is null. Split the exclusion reason into 'null design flow' and '<= 1 MGD'. Download the DMRs for these plants, rerun, and state in results.md that DE has 0 retrieved plants until this is fixed.

**Effort.** 0.5 day

### G06 [major] Table

**Finding.** The column meant to count days above the trigger counts days whose daily makeup exceeds 100,000 gal. The trigger itself is a 30-day average, and the two counts differ by up to 2.4 times.

**Evidence.** Independent recompute for the hybrid: daily > 100,000 gives 29.2, 37.4, 42.2 and 44.8 days/yr at 50/100/200/400 MW, which matches the table. A 30-day rolling mean > 100,000 gives 31.0, 61.0, 89.0 and 106.0. The divisor is 20 years, not the 7,204 valid days. The other cells match: hybrid 50 MW 23,000 / 237,000 / 392,000 / 678,000 and tower 50 MW 751,000.

**Proposed fix.** Either relabel the column 'Days/yr with daily makeup > 100,000 gal (not the trigger test)' or add a column for days in a 30-day window above the trigger. Divide by valid years.

**Effort.** 1 hour

### G07 [major] Supply screen

**Finding.** The assumed-capacity sensitivity moves the matchable count by 10 sites, far beyond the two-site threshold the user asked to be told about. results.md does not flag it.

**Evidence.** supply_summary.json assumed-capacity runs: 50 MW 15/7/2, 100 MW 7/15/2, 200 MW 5/17/2 (matchable/partial/none); matchable_spread_max_minus_min = 10. results.md gives '15 ... 7 ... 5' but never says this exceeds the Msg 8 threshold or that the matchable headline depends on the unpublished capacities of 16 of 24 sites.

**Proposed fix.** Add one sentence stating that the matchable count is not robust (spread 10 against a threshold of 2). Keep the capacity-independent '22 of 24' as the lead, as Msg 9 directs.

**Effort.** 30 min

### G08 [major] Results prose

**Finding.** results.md is written by hand, is preserved by `make clean`, and omits several items the spec and later messages require.

**Evidence.** The Makefile KEEP_RESULTS list includes results.md, and no code writes it. Missing: (1) the DMR monthly-resolution caveat (spec); (2) the Msg 6 near-miss footnote naming New Castle Data Center (0.2 km) and Nebius Butler Township (1.1 km, 1,200 MW); (3) the statement that the 24 active sites agree with DRBC's approximately 24 (Msg 6.2); (4) location_confidence counts (exact 16, approximate 6, uncertain 2; Msg 6.3); (5) the 50/100/200 MW sensitivity as a table (Msg 9); (6) the 253 MW implied WUE of 0.0842 (Msg 8).

**Proposed fix.** Add each missing statement with its key. Generate the number-bearing sentences from the results JSON, or add a test that checks every number in results.md against the JSON.

**Effort.** 0.5 day

### G09 [major] Citations

**Finding.** 7 of the 30 references.bib URLs do not resolve to the cited content, and one entry marked verified is a placeholder.

**Evidence.** HTTP 403: amazon_falls_campus_2026, microsoft_datacenters_2025, alduchov_1996. epa_echo: redirect loop (more than 30 redirects). stull_2011 (journals.ametsoc.org) and mytton_2021 (nature.com) are blocked by this audit's network sandbox and remain unchecked. peakflow_model is 'https://github.com/ (repository URL to be set ...)' returning 404, yet it is marked Verified: yes. The cited figure is not on the fetched page for cleanview_keystone_2026 (178 MW absent; the page renders by script) or trackdatacenters_2026 (326 characters). Confirmed on the page: DRBC rule and datacenters passages, Levittown and Herald figures, LBNL 0.36 / 0.32 / 0.1 to 0.3 / PUE 1.15 to 1.35, Meta 0.19, Google 7,787, Uptime 47%.

**Proposed fix.** Set the repository URL or mark the entry unverified. Point epa_echo at a stable ECHO page. Archive every 403 page and cite the Wayback URL in the note field.

**Effort.** 2 hours

### G10 [major] Sites

**Finding.** Six of the 24 site source URLs do not currently return the page, and three more URLs that the repo counts as verified cannot support verification.

**Evidence.** Live fetch today: HTTP 403 for DRB01, DRB04, DRB05 and DRB39 (datacenterdynamics.com) and for DRB07 (scottkompa.com, recorded by the repo as 200 and verified). DRB10 is an image-only PDF with no extractable text. DRB22 is a YouTube video. DRB33 is a Limerick document-session URL that now returns 'Download has expired' yet is marked source_verified. DRB32's page does not name the site (the repo also marks it false).

**Proposed fix.** Replace DRB33 with a permanent URL. Add Wayback snapshots for every source, as done for the three 404s in Msg 8. Mark DRB07 and DRB33 unverified until reconfirmed. Record that the DRB10 and DRB22 checks were manual.

**Effort.** 0.5 day

### G11 [major] Data: WWTPs

**Finding.** No silica data were retrieved for any plant, and chloride is almost absent. results.md does not report this.

**Evidence.** wwtp_majors.csv, 224 rows: TSS 213, BOD 204, NH3 195, TP 155, TDS 79, chloride 14, silica 0 (parameter 00955). 215 plants have some chemistry and 193 have DMR flow. Silica and chloride are the constituents that limit cooling-tower reuse.

**Proposed fix.** State the silica and chloride coverage in the results.md caveats. Try parameter codes 00956 and 01145 and the state reuse-permit data. If nothing is found, drop silica from the claims.

**Effort.** 2 hours

### G12 [major] Reproduction

**Finding.** The build is not deterministic or offline: `make map` performs a live URL check, and the environment is not fully locked.

**Evidence.** sites.run(check=True) fetches each site source. The phillyburbs row changed between runs ('000 CONNECT tunnel failed, response 403' vs '302 ... Maximum (50) redirects followed'), and the audit's sandbox reported blocked outbound connections during the build. There is no git repository ('fatal: not a git repository'). There is no uv.lock (environment.yml is pinned; pyproject.toml is not).

**Proposed fix.** Split the URL check into its own `make check-urls` target and have `make map` read the cached CSV. Run git init and commit. Pin pyproject.toml to the environment.yml versions or export a conda lock file.

**Effort.** 2 hours

### G13 [minor] Sites

**Finding.** The site count by state does not match DRBC, and the unverified counts differ across documents without explanation.

**Evidence.** Active sites by state: PA 17, NJ 4, DE 3, against drbc_khalil_2026 PA 18, NJ 3, DE 3. The totals agree at 24. Unverified: sources.md says 5 not confirmed, pending_approvals.md says six datacenterdynamics pages, and results.md says 11 of 24 unverified. The 11 is the union of source-unverified (5) and location-unverified (8); no document explains this.

**Proposed fix.** State the by-state mismatch and reconcile the three counts in one sentence that defines 'unverified'.

**Effort.** 1 hour

### G14 [minor] Supply screen

**Finding.** The '< 50 MW' bin on the map, bar and title is identical to the 'no eligible plant' class, so it carries no capacity information.

**Evidence.** covered_it_bins: under 50 MW 2, and both sites are the class 'none' sites, with covered_it_mw set to 0. The v1 legend admits this ('under 50 MW (no eligible plant within 10 mi)'); the v2 and v3 legends say only '< 50'.

**Proposed fix.** Rename the bin 'no eligible plant within 10 mi' on every figure, or report the 0 MW sites separately.

**Effort.** 1 hour

### G15 [minor] Exclusions

**Finding.** 39 site records dropped from the map have no rows in exclusions.csv.

**Evidence.** exclusions.csv stages: echo_permittees 693, supply_screen 61, echo_no_dmr_flow 31, weather 2. No site stage. The ECHO accounting closes: 917 = 601 + 92 + 224. The 39 on_map=False rows (11 inactive, 5 non-data-center records, 23 near-miss) appear only in planned_sites.csv, and the 6 research exclusions sit in a separate file.

**Proposed fix.** Log every site dropped from the map to exclusions.csv with stage='sites' and the reason.

**Effort.** 30 min

### G16 [minor] Results prose

**Finding.** Informal phrasing appears in results.md, and two number-bearing sentences carry no key.

**Evidence.** Informal phrasing: results.md:11 'times lower' twice and 'a very large peak'; results.md:23 'just outside'. Numbers without a key: results.md:9 'Both fits meet all three targets within 1 percent.' and results.md:23 'Eleven inactive sites and 23 sites just outside the basin are excluded'. No em dashes, en dashes or exclamation marks in results.md, README.md or any caption file.

**Proposed fix.** Rewrite as ratios ('about one fifth of'), remove the intensifiers, and add [peakflow_model] or [trackdatacenters_2026].

**Effort.** 30 min

### G17 [minor] Citations

**Finding.** Nine bib keys are unused, including sources the spec named. Model constants in results.md lack sources.

**Evidence.** docs.py unused_keys: drbc_drought_page, drbc_khalil_2026, falls_keystone_2026, google_env_2025, helvetica_font, inter_font, meta_sustainability_2025, mytton_2021, uptime_survey_2025. Cycles of concentration = 4 is cited only to [peakflow_model]. Latent heat 2.43 MJ/kg, drift neglected and the use of KTTN rates for every site in the basin are not stated in results.md.

**Proposed fix.** Cite or remove each unused key. Source the value of 4 cycles or present it as an assumption with a range. Add the model constants to the assumptions paragraph.

**Effort.** 1 hour

### G18 [minor] Flow

**Finding.** The 7Q10 includes 391 provisional days, and the choice is not stated in results.md.

**Evidence.** flow_stats.json: record 1912-10-01 to 2026-09-24; 41,630 of 41,632 days (missing 2026-07-15 and 2026-07-16); 566 provisional days from 2025-03-06. The full-record LP3 7Q10 is 1,794.85 cfs over 113 climatic years; an independent recompute gives 1,794.85 with skew -0.2568.

**Proposed fix.** Report the 7Q10 with and without provisional data (through CY2025), or state the inclusion.

**Effort.** 30 min

### G19 [minor] Map

**Finding.** The map layout departs from the spec: portrait, not half-page landscape; an Esri basemap in the HTML instead of CartoDB Positron; no river labels on v2/v3.

**Evidence.** PNG sizes: v1 2125×2880 px (180 × 244 mm), v3 180 × 222 mm, both portrait. bar_v2 1003×354 px, about 85 × 30 mm against 'about 25 mm'. The HTML uses the Esri World Light Gray tile (esri_light_gray). The v3 PNG has no Delaware or Schuylkill label; v1 labels each once.

**Proposed fix.** Confirm the portrait layout with the user or re-lay the map at 180 × about 120 mm. Switch the HTML to CartoDB Positron. Label each river once on v3.

**Effort.** 0.5 day

### G20 [minor] Map

**Finding.** One palette pair falls below the repo's own colorblind threshold.

**Evidence.** Deuteranopia/protanopia simulation, severity 100, CIEDE: accent vs half 42.3/40.8; half vs open 35.2/33.9; half vs water 12.0/12.3; water vs light-gray county line 10.6/9.1, below the styles.py MIN_DELTA_E of 10. The site fills are well separated.

**Proposed fix.** Darken V2_GRAY_LIGHT or V2_WATER slightly and rerun cvd_check.

**Effort.** 30 min

### G21 [minor] README

**Finding.** The README lacks a findings paragraph and a data-license note.

**Evidence.** README.md opens with the question and links to results.md but gives no numbers. Licenses are 'listed in references.bib'. The spec asked for both.

**Proposed fix.** Add a four-sentence findings paragraph (22 of 24; 0 of 12 averaging and 8 of 12 purchased-supply blind spot; Falls 135,000 average vs 4.4 MGD peak; caveats) and a data-license table.

**Effort.** 1 hour

### G22 [minor] Model

**Finding.** The implied WUE for the wet-2% sensitivity is computed from the target average instead of the achieved one.

**Evidence.** The wet-2% fit reaches an average of only 82,013 gal/day, but implied_site_wue_l_per_kwh reports 0.0727, the value for 135,000. Its own diagnostic gives 0.0447.

**Proposed fix.** Compute implied WUE from the achieved average and report both values for the wet-2% case.

**Effort.** 30 min

### G23 [minor] Reproduction

**Finding.** The build emits warnings, and the repo contains stray files.

**Evidence.** Verbatim warnings: 'findfont: Failed to find font weight semibold for Helvetica, now using 700.' (4 times); 'figures_v2.py:155: UserWarning: The GeoSeries you are attempting to plot is empty.' (falls_plymouth_detail panel B, whose frame contains no state border; harmless); 'colorspacious/comparison.py:11: SyntaxWarning: invalid escape sequence' (upstream); '1 extra bytes in post.stringData array' (22 times) and ''created' timestamp seems very low' (14 times) from fontTools. Stray files: _view_001 to _view_008 *.png, map_preview.png, .DS_Store and __pycache__.

**Proposed fix.** Use fontweight='bold' explicitly. Skip plotting empty GeoSeries. Filter the fontTools warnings. Delete the preview PNGs and add them to .gitignore.

**Effort.** 1 hour

## Done well (do not change during fixes)

1. The cooling model and calibration are transparent and exactly reproducible. An independent reimplementation (latent heat 2.43 MJ/kg, cycles of concentration 4, PUE 1.2, Stull wet-bulb, 20-hour day rule) reproduces the values stored in calibration.json: average 135,000, peak 4,400,000, wet-hour fraction 0.05944, peak day 3,972,028 and maximum 30-day average 1,388,474 gal/day. results.md states the reconciliation problem openly: under the <2% wet-hour reading the average cannot exceed about 88,000 gal/day, and the reported peak is about 33 times the average.
2. The regulatory passages are quoted verbatim. docs.py checks them against the raw copies, and the live DRBC rule PDF contains the phrase "30 consecutive day period does not exceed 100,000 gallons". The purchased-supply reframing quotes both DRBC passages, as Msg 12 requested.
3. The blind-spot table is internally consistent. The values in the .md, .csv, _data.csv and PNG are identical, and the headline ("0 of 12 ... all 8 ... escape if they buy water") matches blindspot_summary.json. No cells are shaded because the headline count is zero; this is consistent, not an error.
4. The supply-screen geometry is correct. Buffers are built in EPSG:5070 (measured geodesic radius 9.91 to 10.09 mi; the v3 equal-area circles measure 9.997 to 10.003 mi). Plant circles are area-scaled: marker area divided by MGD equals 3.0 for all 163 plants, giving a 25:5 MGD diameter ratio of 2.236. The dashed outlines for unverified sites match supply_screen.csv for all 24 sites. The map, bar, v1 title, supply_screen.csv and results.md all state 5 / 17 / 2 and 22 of 24.
5. The basin boundary is the dissolve of WBD HUC6 020401 and 020402 (35,250 km2). It correctly excludes HUC6 020403 Mid Atlantic Coastal (11,430 km2), which a HUC4 0204 outline would wrongly include.
6. The raw-data MANIFEST is accurate for the files present: all 293 SHA-256 hashes match the Desktop copy, and no file is unlisted. The ECHO exclusion accounting closes exactly (917 = 601 + 92 + 224).
7. Weather and gauge processing are complete and honest. Both stations have 20 full years (2005 to 2024). Missing hours are counted and not interpolated, and the partial 2025 files are logged as exclusions. The 7Q10 recomputes to 1,794.85 cfs.
8. The HTML map has 24 site cards, each with a source link, nearest plant, distance, class and covered IT load. The v3 collision checker reports zero label overlaps, and visual inspection agrees.
9. Tests pass (19 passed) in both rebuilds. results.md, README.md and the 7 caption files contain no em dashes, en dashes or exclamation marks.

## Verification record by specification section

**1. Reproduction.**
- Rebuild with cached data/raw copied in: `make clean && make all` exits 0 in 46 s (real 0m45.768s).
- True clean clone (data/raw holding only MANIFEST.md and the two hand-supplied tracker CSVs): exits 2 after 740 s at `docs` (G01). Fetch step times were isd 50.9 s, gis 391.8 s and echo 255.3 s. pytest, run by hand in the clone, reports 19 passed in 2.13 s.
- Every artifact class the spec lists is present in the Desktop repo: figures, a _caption.md and _data.csv for every figure, references.bib, sources.md, MANIFEST.md, exclusions.csv, calibration.json, tests, LICENSE and CITATION.cff. The v1 bar has no SVG.
- Warnings are listed verbatim in G23.

**2. Weather completeness** (weather_hourly.parquet, full data, no sampling).
- Both stations cover 2005-01-01 00:00 to 2024-12-31 23:00 UTC: 175,320 hours expected and 175,320 rows present per station, with no duplicate hours.
- Wet-bulb present: KTTN 173,707 hours (0.920% missing); KPHL 175,133 hours (0.107% missing).
- Only KTTN 2005 has more than 5% missing wet-bulb (10.18%). Station pressure alone exceeds 5% missing in 2024 at both stations (KTTN 10.1%, KPHL 8.6%), but the Stull formula does not use pressure.
- The 2025 files end on 2025-08-27 and are correctly excluded.

| Year | KTTN wet-bulb missing (%) | KPHL wet-bulb missing (%) |
|---|---|---|
| 2005 | 10.18 | 0.09 |
| 2006 | 0.15 | 0.07 |
| 2007 | 1.02 | 0.14 |
| 2008 | 0.17 | 0.22 |
| 2009 | 0.33 | 0.13 |
| 2010 | 0.25 | 0.13 |
| 2011 | 0.65 | 0.09 |
| 2012 | 0.42 | 0.03 |
| 2013 | 0.21 | 0.05 |
| 2014 | 0.34 | 0.10 |
| 2015 | 0.10 | 0.01 |
| 2016 | 0.10 | 0.03 |
| 2017 | 0.07 | 0.07 |
| 2018 | 0.05 | 0.14 |
| 2019 | 0.19 | 0.09 |
| 2020 | 0.87 | 0.10 |
| 2021 | 0.21 | 0.07 |
| 2022 | 0.83 | 0.03 |
| 2023 | 0.46 | 0.08 |
| 2024 | 1.81 | 0.47 |

**Gauge.**
- USGS 01463500, 1912-10-01 to 2026-09-24: 41,630 of 41,632 days present (2026-07-15 and 2026-07-16 missing).
- 566 days are provisional and 1,019 estimated.
- The 7Q10 was computed on the full record: 113 climatic years (1914 to 2026), log-Pearson III by method of moments, 1,794.85 cfs. The independent recompute gives 1,794.85 cfs.

**WWTPs** (ECHO majors in the 42 counties that intersect the basin):

| State | ECHO majors in DRB counties | Retrieved | With DMR flow | With any chemistry | With silica |
|---|---|---|---|---|---|
| PA | 152 | 133 | 122 | 125 | 0 |
| NJ | 101 | 62 | 61 | 61 | 0 |
| NY | 45 | 29 | 10 | 29 | 0 |
| DE | 18 | 0 | 0 | 0 | 0 |
| Total | 316 | 224 | 193 | 215 | 0 |

One PA facility (Keystone Generating Station, PA0002062) is included by county name only; its coordinates lie in Armstrong County. Plants above 5 MGD that are absent are named in G05. ECHO reports no design flow for any of them, so their past-calendar-year average flow is quoted instead.

**Sites.**
- 24 active sites were located, against DRBC's approximately 24. By state: PA 17, NJ 4, DE 3, against DRBC's PA 18, NJ 3, DE 3.
- Location confidence: exact 16, approximate 6, uncertain 2.
- Verified 13; unverified 11 (5 source-unverified, 8 location-unverified).
- Live fetch of all 24 source URLs: 19 return HTTP 200 and 5 return 403 (G10).

**Exclusions.** The ECHO and weather exclusions reconcile exactly: every one of the 917 ECHO majors is accounted for, and every retrieved plant has a DMR file. The only records that vanished without an exclusion row are the 39 sites dropped from the map (G15).

**3. Model and calibration.**
- The three Falls targets and their relative residuals are reported. The residuals are zero by construction (G04).
- Independent recompute: annual average 135,000.0 gal/day, design-rate peak 4,400,000, peak day 3,972,028, wet-hour fraction 0.059445. All match calibration.json.
- The reconciliation problem is stated in results.md.
- WUE comparators confirmed on the LBNL page: 0.36 L/kWh (p.48), 0.32 hyperscale median, 0.1 to 0.3 for adiabatic systems. PUE 1.2 lies inside LBNL's 1.15 to 1.35 projection for hyperscale facilities. Meta's 0.19 is also confirmed.
- Not confirmed: the Microsoft 0.27 page returned 403, and Mytton 2021 was blocked by the audit sandbox and is unused.

**4. Regulatory threshold.** The rule (18 CFR 401.35(a)(2) and (a)(3)) sets the threshold as a daily average gross withdrawal of 100,000 gallons over any 30 consecutive days. sources.md quotes it verbatim, and the table's "Below trigger on 30-day avg" and review columns apply it correctly. The days-per-year column does not (G06).

**5. Table.**
- Recomputed hybrid 50 MW: 23,000 / 237,000 / 392,000 / 678,000 gal/day and 29.2 days/yr. Recomputed tower 50 MW: 751,000. All match the CSV.
- The .md, .csv and PNG contain identical values. The headline count (0) equals the number of shaded cells (0).
- Every sourced cell carries a footnote with a citation key. The committed PNG renders the superscripts in Inter (G02).

**6. Map.**
- The boundary, buffers and area scaling are correct (Done well, item 4).
- Site classes match supply_screen.csv (0 mismatches).
- v1 has two insets, each with a scale bar. v2 and v3 are single-panel by Msg 14 design, with the insets moved to falls_plymouth_detail_v2, which also has scale bars. The lat/long ticks and neat line on v2 and v3 follow Msg 14, which supersedes the original "no ticks or frame" rule.
- A source line is present on every figure. Colorblind results are in G20.
- All 24 HTML hover cards are complete; the two class "none" sites have no matched plant or flow, which is correct.
- Distance spot checks, repo vs independent geodesic: DRB12 to Trenton Sewer Utility 1.928 vs 1.936 mi; DRB31 to Matsunk STP 0.780 vs 0.781 mi; DRB25 to Catasauqua 3.326 vs 3.352 mi; DRB02 to Pennsville 5.427 vs 5.466 mi. The differences, 0.7% at most, reflect EPSG:5070 scale distortion. No assignment changes.

**7. Citations and prose.**
- URL results are in G09 and G10.
- Prose occurrences, with file and line, are in G16.
- Two number-bearing sentences in results.md lack a key; every other number carries a key or refers to calibration.json.

**Network limitations of this audit.** journals.ametsoc.org (stull_2011) and www.nature.com (mytton_2021) were blocked by the audit sandbox. Access was not requested, per instructions. The repository's live URL check also triggered blocked outbound connections during the rebuild.

## Proposed fix order and total effort

1. Make the build reproducible and deterministic: G01, G03 and G12 (about 7 h).
2. Settle the calibration interpretation, G04, before anything else is regenerated, because it changes every per-MW rate downstream (about 4 h).
3. Repair plant retrieval and chemistry coverage: G05 and G11 (about 6 h).
4. Correct the table's days column and the wet-2% WUE: G06 and G22 (about 1.5 h).
5. Regenerate every result and figure with `make all`, remove Inter, and add the font test: G02 (about 1 h).
6. Bring results.md, README and exclusions in line with the rerun numbers and the missing spec items: G08, G07, G13, G14, G15, G16, G17, G18 and G21 (about 10 h).
7. Fix citations and site sources, including archive snapshots: G09 and G10 (about 6 h).
8. Polish the figures and the build: G19, G20 and G23 (about 5.5 h).

**Total estimated effort: about 41 hours (about five working days)**: 6 h for blockers, 23.5 h for major gaps and 11.5 h for minor gaps.
