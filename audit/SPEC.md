# SPEC: original prompt and every user follow-up, verbatim, in order

This file reproduces the task as the user gave it. Attachments are inlined. Automated reviewer notes and context summaries are omitted; only user-authored messages appear.

## Message 1: Original task prompt (PeakFlow spec)

User text accompanying the attachment: Follow the given prompt and don't deviate.

```
You are a research engineer producing analysis for "PeakFlow," a 3-page concept brief for the Water Center at Penn's Student Water Innovation Award (due Sep 27, 2026). PeakFlow is a GIS siting screen plus a model-derived water term sheet for data center community benefit agreements in the Delaware River Basin (DRB). Your job: a public, reproducible repo with two publication-grade deliverables, a map and a table, backed by real primary data. Work in Python. Never invent a number. If a dataset cannot be obtained, record that in results.md and continue with what is real.

=== CONTEXT ===
- Anchor case: Amazon data center, Keystone Trade Center, Fairless Hills, Falls Township, Bucks County, PA. Township filings (local press, Jul-Aug 2026): average draw ~19,000 gal/day; peak cooling demand 4.4 million gal/day; outside-air cooling ~94% of the year, water cooling ~6%; ~40% return flow to an on-site industrial WWTP; supplied by Morrisville Municipal Authority's 25 MGD industrial system.
- Second case: contested data center application, former steel mill site, Conshohocken, Plymouth Township, on the Schuylkill.
- DRBC: ~24 data centers planned in the basin, none has applied for Commission review as of June 2026.
- The DRBC review trigger is an average-based withdrawal threshold. Find and verify the exact figure and averaging period from DRBC's own rules or website before using it anywhere.

=== PIPELINE (prerequisites, keep them lean) ===

P1. Weather. 20 years of hourly temperature, dew point, and pressure for Trenton-Mercer (KTTN) and Philadelphia Intl (KPHL) from NOAA ISD (meteostat or NCEI). Compute hourly wet-bulb (Stull 2011 approximation; cite it). Parquet in data/processed/.

P2. Cooling demand model. Hybrid dry/wet cooling: zero makeup below switchover wet-bulb T_sw; above it, evaporative makeup proportional to wet-bulb-driven heat rejection with a part-load curve. Parameters: P_IT (MW), PUE, WUE (L per IT kWh, Green Grid definition), T_sw, cycles of concentration. Calibrate T_sw and part-load shape to hit the three Falls targets (19,000 gal/day average, 4.4 MGD peak, ~6% wet hours). Report best fit, residual on each target, and whether all three are simultaneously feasible. If they are not, say so; that is a result, not a failure. Also implement two reference architectures: full evaporative tower and air-cooled chiller (near-zero makeup), with WUE ranges cited from LBNL 2024 US Data Center Energy Usage Report and Mytton 2021 (npj Clean Water).

P3. River flow. Daily discharge for USGS 01463500 (Delaware at Trenton) via dataretrieval. Compute 7Q10 and daily flow percentiles by day of year. Search DRBC's site for historical drought warning/emergency declaration dates and record them if found.

=== DELIVERABLE A: TABLE (Task 4, the regulatory blind spot) ===

For site sizes 50, 100, 200, 400 MW IT and the three architectures (evaporative tower, calibrated hybrid, air-cooled chiller), compute at Trenton climate:
- 30-day rolling average makeup (gal/day), annual mean of the rolling average and its annual maximum
- Peak-day makeup (gal/day, 99th percentile and absolute max)
- Below/above DRBC trigger on the 30-day average (verified threshold)
- Days per year above the trigger on a daily basis
- Share of those days on which Trenton flow is below its 25th percentile, and below 7Q10

Output the table three ways: results/table_blindspot.md (markdown), results/table_blindspot.csv, and figures/table_blindspot.png rendered as a designed table (use great_tables or a hand-built matplotlib table). Design: one bold headline row stating the finding ("N of 12 configurations are invisible to DRBC review on average yet exceed the trigger on peak days"), light horizontal rules only, right-aligned numbers with thousands separators, units in the header, a single accent color to shade the cells that are below-trigger-on-average AND above-trigger-on-peak. No default matplotlib table styling.

=== DELIVERABLE B: MAP (Task 5, the supply screen) ===

Data:
- DRB boundary: DRBC GIS open data, or USGS Watershed Boundary Dataset HUC-02 region 0204. Record which.
- Rivers: NHDPlus flowlines for the Delaware mainstem and Schuylkill only (keep it uncluttered).
- WWTPs: EPA ECHO/ICIS-NPDES major permittees (design flow > 1 MGD) in DRB counties of PA, NJ, DE, NY. Pull 3 years of DMR monthly effluent flow and available chemistry (TSS, BOD, NH3, total P, chloride, TDS, silica). Median flow per plant.
- Planned data center sites: padatacenterproposals.com, county planning filings, PJM interconnection queue, local press. Geocode with Nominatim. Every site carries a source URL and a verified/unverified flag. Do not fabricate sites; if you can only locate 15 of 24, map 15 and say so.
- Buffers: 10-mile radius around each site, in an equal-area projection (EPSG:5070 or a UTM zone 18N), then reproject for display.

Analysis: for each site, the nearest WWTP within 10 miles, its median effluent flow, and whether that single plant's median flow exceeds the site's modeled peak-day makeup at 100 MW hybrid (from P2). Classify sites: matchable (single plant covers peak), partial (plant within 10 miles but under peak), none (no major plant within 10 miles). Save results/supply_screen.csv.

Map design (this is the centerpiece, treat it like an FT or Reuters graphic, not a GIS export):
- Basemap: contextily CartoDB Positron (light, muted) at appropriate zoom, in Web Mercator for display. No satellite, no OSM default.
- DRB boundary as a thin dark outline with the outside of the basin lightly desaturated or masked so the basin reads as the subject.
- Rivers as thin blue-gray lines, labeled once each along the line.
- WWTPs as circles scaled by median effluent flow (area-scaled, not radius-scaled), fill in a muted teal, thin white stroke. Legend shows three reference sizes (5, 25, 100 MGD).
- Data center sites as diamonds or squares in a single warm accent (amber or coral), colored by class: matchable = solid, partial = half-tone, none = outlined. Unverified sites get a dashed outline.
- 10-mile buffers as very light fills (5-8% opacity) with no stroke, so they suggest coverage without cluttering.
- Direct-label Falls Township and Plymouth Township sites and their matched plants with leader lines. Label at most 6 other things.
- Two insets: Lower Bucks (Falls, Morrisville) and Conshohocken/Schuylkill, each with its own scale bar.
- Title as a sentence stating the finding ("N of M planned sites sit within 10 miles of a treatment plant that could cover their peak cooling demand"), subtitle with the data window and the 100 MW hybrid assumption, small source line at bottom (DRBC, EPA ECHO, USGS, NOAA, site sources).
- Typography: one sans family (Inter, Source Sans 3, or IBM Plex Sans; install via matplotlib font manager), clear hierarchy, no bold everywhere. Colorblind-safe palette (verify with a simulation). Small north arrow and scale bar, thin. No gridlines, no axis ticks, no frame.
- Export figures/supply_screen_map.png at 300 dpi at 180 mm width (half-page landscape), and figures/supply_screen_map.pdf (vector) for print. Also export figures/supply_screen_map.svg.
- Also produce an interactive version, figures/supply_screen_map.html (folium or plotly), same data and colors, with hover cards showing site source, matched plant, effluent flow, and class. This is for the Oct 14 talk.
- Companion bar: figures/supply_screen_bar.png, a single horizontal stacked bar of site counts by class (matchable / partial / none), same palette, no axes clutter.

=== REPO ===

Structure:
  README.md (what this is, one-paragraph findings, how to reproduce in 3 commands, data licenses)
  pyproject.toml + uv.lock (or environment.yml), pinned versions
  Makefile with targets: data, model, table, map, all, clean
  src/peakflow/ (weather.py, wetbulb.py, cooling_model.py, calibration.py, flow.py, blindspot.py, echo.py, sites.py, supply_screen.py, plotting/, styles.py with the shared palette and font)
  data/raw/ (gitignored; downloaded by `make data`), data/processed/ (small parquet/csv committed if under 20 MB), data/sites/planned_sites.csv (committed, with source URLs and verified flag)
  results/ (results.md, table_blindspot.md/.csv, supply_screen.csv, calibration.json with fitted parameters and residuals)
  figures/ (all outputs above)
  sources.md (every dataset and claim: title, publisher, date, URL, the exact figure used, and a verified/unverified flag; open the actual page, not a snippet)
  tests/ (wet-bulb function against known values; calibration reproduces stored parameters; supply screen classification on a fixture)
  LICENSE (MIT for code; note data licenses separately), CITATION.cff

results.md: under 900 words. One paragraph per deliverable with the key numbers, then an assumptions list, then caveats (DMR monthly resolution understates peak variability; unverified sites; DRBC threshold interpretation). Written so sentences can be pasted into the brief.

=== RULES ===
- Verify the DRBC threshold from DRBC sources before Deliverable A. Quote the rule text in sources.md.
- State every assumption in results.md.
- If the Falls targets do not reconcile in P2, report the closest feasible fit and the residuals, and do not smooth it over.
- Prefer primary sources: DRBC, USGS, EPA, NOAA, township filings, peer-reviewed papers.
- Every figure must render from `make all` on a clean clone.
- Finish by printing: fitted model parameters, the blind-spot headline count, the supply-screen headline count, the number of sites located vs the 24 claimed, and a list of anything you could not verify.
You are a research engineer producing analysis for "PeakFlow," a 3-page concept brief for the Water Center at Penn's Student Water Innovation Award (due Sep 27, 2026). PeakFlow is a GIS siting screen plus a model-derived water term sheet for data center community benefit agreements in the Delaware River Basin (DRB). Your job: a public, reproducible repo with two publication-grade deliverables, a map and a table, backed by real primary data. Work in Python. Never invent a number. If a dataset cannot be obtained, record that in results.md and continue with what is real.

=== CONTEXT ===
- Anchor case: Amazon data center, Keystone Trade Center, Fairless Hills, Falls Township, Bucks County, PA. Township filings (local press, Jul-Aug 2026): average draw ~19,000 gal/day; peak cooling demand 4.4 million gal/day; outside-air cooling ~94% of the year, water cooling ~6%; ~40% return flow to an on-site industrial WWTP; supplied by Morrisville Municipal Authority's 25 MGD industrial system.
- Second case: contested data center application, former steel mill site, Conshohocken, Plymouth Township, on the Schuylkill.
- DRBC: ~24 data centers planned in the basin, none has applied for Commission review as of June 2026.
- The DRBC review trigger is an average-based withdrawal threshold. Find and verify the exact figure and averaging period from DRBC's own rules or website before using it anywhere.

=== PIPELINE (prerequisites, keep them lean) ===

P1. Weather. 20 years of hourly temperature, dew point, and pressure for Trenton-Mercer (KTTN) and Philadelphia Intl (KPHL) from NOAA ISD (meteostat or NCEI). Compute hourly wet-bulb (Stull 2011 approximation; cite it). Parquet in data/processed/.

P2. Cooling demand model. Hybrid dry/wet cooling: zero makeup below switchover wet-bulb T_sw; above it, evaporative makeup proportional to wet-bulb-driven heat rejection with a part-load curve. Parameters: P_IT (MW), PUE, WUE (L per IT kWh, Green Grid definition), T_sw, cycles of concentration. Calibrate T_sw and part-load shape to hit the three Falls targets (19,000 gal/day average, 4.4 MGD peak, ~6% wet hours). Report best fit, residual on each target, and whether all three are simultaneously feasible. If they are not, say so; that is a result, not a failure. Also implement two reference architectures: full evaporative tower and air-cooled chiller (near-zero makeup), with WUE ranges cited from LBNL 2024 US Data Center Energy Usage Report and Mytton 2021 (npj Clean Water).

P3. River flow. Daily discharge for USGS 01463500 (Delaware at Trenton) via dataretrieval. Compute 7Q10 and daily flow percentiles by day of year. Search DRBC's site for historical drought warning/emergency declaration dates and record them if found.

=== DELIVERABLE A: TABLE (Task 4, the regulatory blind spot) ===

For site sizes 50, 100, 200, 400 MW IT and the three architectures (evaporative tower, calibrated hybrid, air-cooled chiller), compute at Trenton climate:
- 30-day rolling average makeup (gal/day), annual mean of the rolling average and its annual maximum
- Peak-day makeup (gal/day, 99th percentile and absolute max)
- Below/above DRBC trigger on the 30-day average (verified threshold)
- Days per year above the trigger on a daily basis
- Share of those days on which Trenton flow is below its 25th percentile, and below 7Q10

Output the table three ways: results/table_blindspot.md (markdown), results/table_blindspot.csv, and figures/table_blindspot.png rendered as a designed table (use great_tables or a hand-built matplotlib table). Design: one bold headline row stating the finding ("N of 12 configurations are invisible to DRBC review on average yet exceed the trigger on peak days"), light horizontal rules only, right-aligned numbers with thousands separators, units in the header, a single accent color to shade the cells that are below-trigger-on-average AND above-trigger-on-peak. No default matplotlib table styling.

=== DELIVERABLE B: MAP (Task 5, the supply screen) ===

Data:
- DRB boundary: DRBC GIS open data, or USGS Watershed Boundary Dataset HUC-02 region 0204. Record which.
- Rivers: NHDPlus flowlines for the Delaware mainstem and Schuylkill only (keep it uncluttered).
- WWTPs: EPA ECHO/ICIS-NPDES major permittees (design flow > 1 MGD) in DRB counties of PA, NJ, DE, NY. Pull 3 years of DMR monthly effluent flow and available chemistry (TSS, BOD, NH3, total P, chloride, TDS, silica). Median flow per plant.
- Planned data center sites: padatacenterproposals.com, county planning filings, PJM interconnection queue, local press. Geocode with Nominatim. Every site carries a source URL and a verified/unverified flag. Do not fabricate sites; if you can only locate 15 of 24, map 15 and say so.
- Buffers: 10-mile radius around each site, in an equal-area projection (EPSG:5070 or a UTM zone 18N), then reproject for display.

Analysis: for each site, the nearest WWTP within 10 miles, its median effluent flow, and whether that single plant's median flow exceeds the site's modeled peak-day makeup at 100 MW hybrid (from P2). Classify sites: matchable (single plant covers peak), partial (plant within 10 miles but under peak), none (no major plant within 10 miles). Save results/supply_screen.csv.

Map design (this is the centerpiece, treat it like an FT or Reuters graphic, not a GIS export):
- Basemap: contextily CartoDB Positron (light, muted) at appropriate zoom, in Web Mercator for display. No satellite, no OSM default.
- DRB boundary as a thin dark outline with the outside of the basin lightly desaturated or masked so the basin reads as the subject.
- Rivers as thin blue-gray lines, labeled once each along the line.
- WWTPs as circles scaled by median effluent flow (area-scaled, not radius-scaled), fill in a muted teal, thin white stroke. Legend shows three reference sizes (5, 25, 100 MGD).
- Data center sites as diamonds or squares in a single warm accent (amber or coral), colored by class: matchable = solid, partial = half-tone, none = outlined. Unverified sites get a dashed outline.
- 10-mile buffers as very light fills (5-8% opacity) with no stroke, so they suggest coverage without cluttering.
- Direct-label Falls Township and Plymouth Township sites and their matched plants with leader lines. Label at most 6 other things.
- Two insets: Lower Bucks (Falls, Morrisville) and Conshohocken/Schuylkill, each with its own scale bar.
- Title as a sentence stating the finding ("N of M planned sites sit within 10 miles of a treatment plant that could cover their peak cooling demand"), subtitle with the data window and the 100 MW hybrid assumption, small source line at bottom (DRBC, EPA ECHO, USGS, NOAA, site sources).
- Typography: one sans family (Inter, Source Sans 3, or IBM Plex Sans; install via matplotlib font manager), clear hierarchy, no bold everywhere. Colorblind-safe palette (verify with a simulation). Small north arrow and scale bar, thin. No gridlines, no axis ticks, no frame.
- Export figures/supply_screen_map.png at 300 dpi at 180 mm width (half-page landscape), and figures/supply_screen_map.pdf (vector) for print. Also export figures/supply_screen_map.svg.
- Also produce an interactive version, figures/supply_screen_map.html (folium or plotly), same data and colors, with hover cards showing site source, matched plant, effluent flow, and class. This is for the Oct 14 talk.
- Companion bar: figures/supply_screen_bar.png, a single horizontal stacked bar of site counts by class (matchable / partial / none), same palette, no axes clutter.

=== REPO ===

Structure:
  README.md (what this is, one-paragraph findings, how to reproduce in 3 commands, data licenses)
  pyproject.toml + uv.lock (or environment.yml), pinned versions
  Makefile with targets: data, model, table, map, all, clean
  src/peakflow/ (weather.py, wetbulb.py, cooling_model.py, calibration.py, flow.py, blindspot.py, echo.py, sites.py, supply_screen.py, plotting/, styles.py with the shared palette and font)
  data/raw/ (gitignored; downloaded by `make data`), data/processed/ (small parquet/csv committed if under 20 MB), data/sites/planned_sites.csv (committed, with source URLs and verified flag)
  results/ (results.md, table_blindspot.md/.csv, supply_screen.csv, calibration.json with fitted parameters and residuals)
  figures/ (all outputs above)
  sources.md (every dataset and claim: title, publisher, date, URL, the exact figure used, and a verified/unverified flag; open the actual page, not a snippet)
  tests/ (wet-bulb function against known values; calibration reproduces stored parameters; supply screen classification on a fixture)
  LICENSE (MIT for code; note data licenses separately), CITATION.cff

results.md: under 900 words. One paragraph per deliverable with the key numbers, then an assumptions list, then caveats (DMR monthly resolution understates peak variability; unverified sites; DRBC threshold interpretation). Written so sentences can be pasted into the brief.

=== RULES ===
- Verify the DRBC threshold from DRBC sources before Deliverable A. Quote the rule text in sources.md.
- State every assumption in results.md.
- If the Falls targets do not reconcile in P2, report the closest feasible fit and the residuals, and do not smooth it over.
- Prefer primary sources: DRBC, USGS, EPA, NOAA, township filings, peer-reviewed papers.
- Every figure must render from `make all` on a clean clone.
- Finish by printing: fitted model parameters, the blind-spot headline count, the supply-screen headline count, the number of sites located vs the 24 claimed, and a list of anything you could not verify.

=== CITATIONS, DATA, AND QUALITY REQUIREMENTS (override anything above where they conflict) ===

Citations
- Maintain references.bib (BibTeX) with a stable key for every source: datasets, rules, papers, filings, press. Each entry has author or publisher, title, year, URL, and accessed date.
- sources.md is generated from references.bib and adds, for each key, the exact figure or fact taken from it and a verified/unverified flag. Open each page or dataset; a search snippet does not count.
- Every number in results.md carries a citation key in square brackets, for example [drbc_rules_2024]. Every table cell that comes from a source rather than from the model is footnoted with its key. Model-derived values are marked as such in a footnote.
- Every figure has a source line at the bottom listing the citation keys used, and a separate caption file figures/<name>_caption.md with a complete formal caption, the assumptions, and the keys.
- For every planned site, data/sites/planned_sites.csv includes source_url, source_title, source_date, and verified flag. Unverified sites appear on the map with a dashed outline and are counted separately in every headline.

Data behind every output
- Each figure ships with its underlying data: figures/<name>_data.csv containing exactly the values plotted, one row per plotted element. The table ships as .csv and .md with the same values as the .png.
- Use the full datasets. All 20 years of hourly weather, all daily flow records for the gauge period, all major permittees in the DRB counties, all months of DMR data available. No sampling, no truncation to "recent years," no dropping of stations or plants for convenience. If a record is excluded, log why in results/exclusions.csv with one row per exclusion.
- Record raw data provenance: data/raw/MANIFEST.md with file name, source URL, download timestamp, row count, and SHA-256 hash.
- Report completeness: fraction of missing hours per weather station, missing days per gauge, permittees with no DMR flow, and how each gap was handled. No silent interpolation.

Writing and presentation
- All prose (README, results.md, captions, table headline, map title and subtitle) is formal, in complete sentences, with correct grammar. No em dashes anywhere; use commas, colons, or separate sentences. No hedging filler, no bullet fragments in prose sections, no exclamation marks.
- Figures contain only titles, subtitles, axis labels, legends, direct labels with leader lines, scale bars, and the source line. No free-floating annotations, callout boxes, arrows pointing at nothing, or text overlapping map features. Every label must clear other labels and symbols; check for collisions before export.
- Consistent style across all figures via styles.py: one font family, one palette, one title size, one source-line format.
- Round consistently: gallons per day to the nearest thousand in headlines, three significant figures elsewhere. Units in every header and axis label.
- No default matplotlib or GIS
```

## Message 2: Original task prompt resent (identical content)

User text accompanying the attachment: run this

```
(same file as Message 1)
```

## Message 3

Status check: which task are you on, what has been written to disk so far, what is currently running, and is anything blocked or failing? Reply in five lines, then continue.

## Message 4

Three instructions.

1. P_IT must not be a free parameter. Search the Falls filings, PECO or PJM interconnection records, and Bucks County press for the stated IT or campus capacity of the Keystone Trade Center project. If a figure exists, fix P_IT to it and refit only T_sw and the part-load exponent; report the new residuals. If no figure exists, keep 467 MW as fitted but state explicitly in results.md that capacity was inferred, not sourced. Either way, the finding that the three published targets cannot be met simultaneously stands and goes in results.md as written.

2. For WUE ranges, replace LBNL with sources you can open: The Green Grid WUE white paper (definition), the Uptime Institute Global Data Center Survey (industry WUE distribution), and the published fleet WUE figures in Microsoft, Meta, and Google environmental reports. Cite each with the exact figure taken. Keep LBNL in references.bib marked unverified pending a local PDF; if a PDF appears at data/raw/lbnl_2024.pdf, use it.

3. Do not scrape trackdatacenters.com. A hand-built data/sites/planned_sites.csv will be provided; ingest it as the primary site list and merge with what the sub-agent finds from DRBC, county filings, and press. Every row keeps its source URL and verified flag. Continue ECHO downloads and re-run the summary with the basin flags.

## Message 5

The LBNL PDF is on my Desktop at ~/Desktop/lbnl-2024-united-states-data-center-energy-usage-report_1.pdf. Move it into the repo at data/raw/lbnl_2024.pdf and treat it as verified

## Message 6: Planned-site list supplied by the user

```
Both site files are in data/raw/: trackdatacenters_drb.csv (40 rows, main list) and trackdatacenters_drb_nearmiss.csv (23 rows, outside the boundary). Ingest as follows. Main list 1. Filter to record_type = Data Center for the map and all counts. Keep zoning ordinances, site advertisements, and zoning challenges in the CSV but off the map. 2. Classify status as active (proposed, preliminary, delayed, construction) or inactive (rejected, withdrawn). Map only active sites. Report the inactive count in results.md. The headline count is active data center projects, which should come to 24; compare this against DRBC's figure of about 24 and state that the two counts agree. 3. location_confidence: exact gets a solid outline; approximate and uncertain get the dashed outline the spec calls unverified. Report the counts of each. 4. Where stated_mw is missing, assume 100 MW IT for the supply screen and mark the row as assumed capacity. Where stated_mw is present, treat it as total campus power, convert to IT load using the calibrated PUE, and say so. 5. Verify that Project Gold (Lackawanna County, 1,500 MW) falls inside the basin polygon at its exact coordinates, since every other Lackawanna County entry fell outside. If it is within 2 km of the boundary, flag it on the map and in results.md. 6. Cite the tracker once in references.bib as the site list, noting its data license if the site states one. Each row's source_url is that site's primary citation; fetch each and confirm it resolves. Near-miss list 7. Keep it out of the main map and all headline counts. Add one footnote to results.md: two preliminary sites in Schuylkill County, New Castle Data Center at 0.2 km and Nebius Butler Township at 1.1 km outside the boundary (the latter 1,200 MW), sit close enough to the basin divide that their water source could be in either basin; they are excluded from the counts. Then re-run the supply screen using the calibrated hybrid model's peak-day makeup against each active site's nearest major WWTP within 10 miles, and regenerate the map, the bar chart, supply_screen.csv, and results.md so every count agrees.
```

## Message 7

Parallelize where steps are independent. Run sub-agents for: (1) ECHO DMR downloads and the supply summary, (2) source_url verification across the 22 approved domains, (3) Deliverable A, the blind-spot table, which depends only on the calibrated model and the gauge data. Keep Deliverable B, the map, until the supply screen finishes. Keep a single writer for results.md and references.bib so sub-agents do not overwrite each other; they report to you and you merge. Give me a time estimate for each.

## Message 8

Three adjustments.

1. Broken URLs. For the two 404s (Arrow Real Estate listing, eBrandywine item 237) and the phillyburbs login redirect, look for the same story on the Wayback Machine (web.archive.org) or in another outlet. If found, store the archive or alternate URL as source_url and keep the original in a column called original_url. If not found, mark the row unverified and keep it on the map with the dashed outline.

2. Assumed capacity sensitivity. Sixteen of 24 active sites use the assumed 100 MW. Run the supply screen at 50, 100, and 200 MW IT for those sixteen and report the headline matchable count under each in results.md. The map uses 100 MW; the sentence in the brief will state the range. If the headline changes by more than two sites across the range, tell me.

3. Implied WUE at Falls. Add to results.md the average site WUE implied by 19,000 gal/day at 293 MW and at 253 MW IT, and compare it with LBNL's national average (0.36 L/kWh), Microsoft FY2025 (0.27), and LBNL's range for airside economizer with adiabatic cooling. State whether the Falls average is consistent with that architecture. The point for the brief is that a plausible average can coexist with a very large peak, not that the average is wrong.

## Message 9

Approve web.archive.org for the URL agent.

Four changes to the supply screen and map.

1. Headline: lead results.md with the capacity-independent count, the number of active sites within 10 miles of an eligible POTW (22 of 24). Then report the 50/100/200 MW sensitivity table and state that 16 of 24 active sites publish no capacity.

2. For each active site, compute covered_it_mw: the largest IT load whose calibrated peak-day makeup the nearest eligible plant's median flow covers. Add it to supply_screen.csv. On the map, color sites by covered_it_mw in three bins (under 50, 50 to 200, over 200 MW) instead of matchable/partial/none, and update the bar chart and map title to match. Where stated MW exists, list it beside covered_it_mw in the hover card and the CSV.

3. For Falls, also report the nearest eligible Pennsylvania plant with distance, median flow, and coverage. Note in results.md that the Trenton match crosses the state line.

4. Keep industrial dischargers out of the headline; report the 10/13/1 result as a sensitivity in one sentence.

## Message 10

The laptop slept. Check what is on disk, tell me the last completed step in two lines, and resume from there.

## Message 11: Audit instruction

User text accompanying the attachment: read this and remember

```
The run is done when the map, table, results.md, references.bib, and sources.md are all written and make all succeeds. Then spawn a fresh sub-agent with no memory of this work to run the audit prompt below. Save the original generation prompt and all follow-up instructions I sent into audit/SPEC.md first so the auditor can check against them. Do not fix anything the auditor finds; show me AUDIT.md. You are auditing a repository produced by another session for "PeakFlow," a concept brief on data center water use in the Delaware River Basin. Your job is to find every gap between what was specified and what was delivered, rank the gaps by how much they weaken the brief, and propose a fix for each. You are a skeptical reviewer, not a collaborator. Do not repair anything; report only. Write findings to audit/AUDIT.md and audit/gaps.csv (columns: id, area, severity [blocker/major/minor], finding, evidence, proposed fix, estimated effort). The original specification is in audit/SPEC.md (paste the full generation prompt there before running). Check the repo against it section by section. 1. Reproduction - Clone into a clean directory and run `make all` in a fresh environment. Record whether it completes, wall time, and every warning or error verbatim. - Confirm every file the spec lists exists: figures, results, caption files, per-figure data CSVs, references.bib, sources.md, MANIFEST.md, exclusions.csv, calibration.json, tests. List anything missing. - Run the tests and report pass/fail. 2. Data completeness (use the full datasets, no sampling) - Weather: for each station, report the date range actually retrieved, total hours expected vs present, missing-hour fraction by year, and any year with more than 5% missing. Confirm 20 years, not fewer. - Gauge: date range, missing days, whether 7Q10 was computed on the full record. - WWTPs: count of major permittees in DRB counties per state according to ECHO, count actually retrieved, count with DMR flow, count with any chemistry, count with silica. Name every plant with design flow above 5 MGD that is absent. - Sites: number of sites located vs the 24 DRBC cites, number verified vs unverified, and whether each site row has a working source URL (fetch each one). - Compare exclusions.csv to what was actually dropped. Find any record that vanished without an exclusion row. 3. Model and calibration - Read calibration.json. Check that the three Falls targets and their residuals are reported. Recompute the annual average, peak day, and wet-hour fraction from the model outputs yourself and confirm they match the stored values. - Check that the reconciliation problem (4.4 MGD × 6% of the year vs 19,000 gal/day) is stated in results.md and not hidden. - Confirm the WUE and PUE ranges are cited to the named sources and fall inside what those sources state. 4. Regulatory threshold - Open the DRBC rule cited for the review trigger. Confirm the threshold value and averaging period quoted in sources.md match the rule text. Confirm the table applies it correctly. 5. Table (Deliverable A) - Recompute at least two cells from the model outputs and confirm they match the CSV. - Confirm the .md, .csv, and .png contain identical values. - Confirm the headline count matches the number of shaded cells. - Confirm every sourced cell has a citation key footnote. 6. Map (Deliverable B) - Open the PNG at 100% and the PDF. Check: basin boundary correct (compare to DRBC or WBD 0204 outline), rivers correct and labeled once, WWTP circles area-scaled (measure two), sites classified consistently with supply_screen.csv, buffers 10 miles in an equal-area projection (measure one), insets present with scale bars, no overlapping labels, no floating text, no gridlines or frame, source line present, palette colorblind-safe (simulate deuteranopia and protanopia). - Confirm the title count, bar chart, supply_screen.csv, and results.md all state the same numbers. - Open the HTML version and confirm hover cards show source, matched plant, flow, and class for every site. - Spot-check three site-to-plant matches by computing the distance yourself. 7. Citations and prose - For every key in references.bib, fetch the URL and confirm the cited figure appears on the page. List any that do not. - Grep results.md, README.md, and all caption files for em dashes, sentence fragments, informal phrasing, and exclamation marks. List each occurrence with file and line. - Confirm every number in results.md carries a citation key or a reference to calibration.json. 8. Report - AUDIT.md opens with a one-paragraph verdict: is the repo usable for the brief as is, usable with fixes, or not usable, and why. - Then a ranked gap list, blockers first, each with the evidence you found and the concrete fix. - Then a short list of things that were done well, so they are not accidentally changed during fixes. - End with a proposed fix order and a total effort estimate.
```

## Message 12

Option 1, recalibrate to 135,000 gal/day. Also:
- Keep 19,000 gal/day in results.md as documented potable demand, cited.
- Use 6% wet hours as primary (township filings) and rerun with Amazon's "less than 2%" as a sensitivity; report both.
- Delete the old WUE comparison paragraph and rewrite it with the new implied WUE.
- Reframe the blind-spot table around two mechanisms: (a) the 30-day average trigger misses peak-day demand for configurations below 100,000 gal/day on average, and (b) supply purchased from an existing public or authority system does not trigger Commission review at all, regardless of size. Verify (b) against the DRBC rule text and DRBC's statement about the ~60 existing facilities, and quote both in sources.md. State in results.md that Falls exceeds the trigger on average and still required no review because MMA supplies it.
- Peak-to-average ratio at Falls is now about 33x; update every place 230x appears.
Then rerun the table, supply screen, map, and bar.

## Message 13

Time check: list each unfinished step with an estimate in minutes, then the total. Two lines max per step, then continue.

## Message 14: Figure v2 instruction

```
Save these as new files with a _v2 suffix (for example figures/supply_screen_map_v2.png, supply_screen_bar_v2.png, falls_plymouth_detail_v2.png, and matching _caption, _data, PDF, and SVG files). Do not overwrite or delete the current versions. Add a make target, figures_v2, that builds only the new set.

Redesign both figures (supply_screen_map and supply_screen_bar) as technical figures in the style of a USGS Scientific Investigations Report, not infographics. Keep the data and analysis unchanged, and regenerate both from the latest recalibrated results so they match results.md.

SHARED STYLE (put in styles.py and apply to every figure)
- No titles or subtitles in any image. All explanatory text goes in figures/<name>_caption.md as a formal caption ("Figure 2. ..."), in complete sentences.
- No citation keys, file paths, or sentences inside any image. One short source line at the bottom: "Sources: DRBC; U.S. EPA ECHO; USGS WBD and NHD; NOAA ISD; Natural Earth; trackdatacenters.com." The bar figure lists only the sources it uses.
- Palette: black, grays, one muted blue-gray for water, and one accent (deep blue, #1F3A5F). No browns, oranges, or greens. No glows, gradients, or shadows.
- One sans-serif font, 7 to 8 pt at print size. No bold except legend headings.
- Line weights: 0.8 pt primary outlines, 0.5 pt secondary, 0.25 pt tertiary.
- Export at print width, 300 dpi PNG, plus PDF and SVG.

MAP (figures/supply_screen_map, 180 mm wide)
- Remove the title, subtitle, all on-map callouts (including Project Gold and Project Washington notes), buffer glow, green plant fill, and warm basin tint.
- Base: shaded relief at very low contrast in gray; basin interior white; outside the basin flat light gray. Basin boundary 0.8 pt black. State lines 0.5 pt dark gray dashed. County lines 0.25 pt light gray. Rivers and Delaware Bay in the blue-gray.
- Lat/long ticks on the frame edge only, every 0.5 degrees, no interior gridlines. Thin neat line around the map. Scale bar in km and miles with alternating black and white segments. Simple north arrow.
- Treatment plants: open black circles, area scaled to median flow, no fill.
- Data center sites: squares. Solid accent for over 200 MW covered, half-filled for 50 to 200 MW, open for under 50 MW. Dashed outline for unverified. No other colors.
- 10-mile radii: thin dashed gray circles, no fill.
- Label sites with numbers 1 to 24 only, small, placed without leader lines unless needed to avoid overlap. Write figures/site_key.csv (number, name, municipality, stated MW, covered IT MW, verified) and include the key as a table in the caption file.
- At most five city labels, small gray type.
- Single panel, no insets. Compact boxed legend in one corner: three reference plant circles (5, 25, 100 MGD), four site states, 10-mile radius, basin boundary. No sentences.
- Separately produce figures/falls_plymouth_detail in the same style: two panels, (a) Lower Bucks and (b) Conshohocken, for the appendix and talk only.

BAR (figures/supply_screen_bar, 85 mm wide, about 25 mm tall)
- One horizontal bar of the 24 active sites, three segments matching the map fills exactly: solid accent (over 200 MW), half-tone accent (50 to 200 MW), open with black outline (under 50 MW). Show unverified sites with a thin diagonal hatch in black at low density, not a second color.
- Segment counts printed inside or directly above each segment in small type ("5", "17", "2"). No other text on the bar.
- A single x-axis from 0 to 24 with ticks at 0, 6, 12, 18, 24 and the label "Active planned sites (count)".
- Small key below the axis: three fill swatches with range labels and one hatch swatch labeled "unverified". No sentences.

When done, open both PNGs at 100% zoom, confirm no text overlaps, confirm map and bar use identical fills and counts, and show me both.
```

## Message 15

I am stepping away overnight. Continue through the full queue without waiting for me: recalibration to 135,000 gal/day, the blind-spot table with both mechanisms, the supply screen, the v2 figures, results.md, references.bib, sources.md, and the README. If a step needs my approval, skip it, log it in results/pending_approvals.md, and continue with everything that does not depend on it. When all work is done, run the audit sub-agent as instructed. In the morning I want one summary: what finished, what is pending my approval, and the audit verdict.

## Message 16

Revise the map as supply_screen_map_v3 (keep v2). Changes only:

Keep all colors, fills, shaded relief, line weights, and symbol styles exactly as in v2. Only change the font, the legend, the crop, and the label collisions listed below.

Typography
- Replace the current font everywhere with Helvetica, falling back to Arial, then Liberation Sans. Use Arial Narrow or Liberation Sans Narrow for site numbers and city labels. Regular weight only; the legend heading may be bold. No Inter or other UI fonts in any figure; update styles.py so every figure uses this.


Legend wording
- Replace "EXPLANATION" with no heading, or a small heading "Key".
- Group 1 heading: "Planned site, IT load coverable at peak (MW)". Entries: "> 200", "50 to 200", "< 50", "Unverified".
- Group 2 heading: "Treatment plant, median flow (MGD)". Entries: 5, 25, 100.
- Remaining entries, one line each: "10-mile radius", "Basin boundary", "State boundary".
- Left-align all text, align swatches in one column, consistent spacing.

Symbols and labels
- Plants outside the basin: draw at 40% opacity so plants inside the basin read first.
- Fix label collisions: 14 and 15, Scranton, and the scale bar "50" against "KILOMETERS" (move the unit labels below the bars).
- Check for any other overlaps at 100% zoom before export.


## Later instructions (2026-09-25, after the first audit)

The messages below were given after audit/AUDIT.md and supersede earlier instructions where they conflict. They are quoted verbatim; the attached work order is reproduced in full.

### Later message 1

Attached work order (pasted-text-2026-09-25T11-33-02.txt):

```
One combined work order. Do the parts in order and do not start a part until the previous one passes its checks. Keep the v3 figure style (Helvetica, same palette, captions in _caption.md, data in _data.csv, PNG/PDF/SVG). All prose formal, complete sentences, no em dashes, a citation key on every number.

PART 1: AUDIT TIER 1 (affects the brief)
1. G04: Make the peak-day reading of 4.4 MGD primary (331 MW, gamma 0.429); keep the design-rate reading as a sensitivity. State that the fit is exactly determined, so zero residuals are not validation.
2. G05: When ECHO design flow is null, fall back to actual average flow, then past-year average, then DMR median. Split the exclusion reason into "null design flow" and "1 MGD or less". Pull DMRs for the recovered plants, including Wilmington DE0020320, Gloucester County UA, Kent County, and Ewing-Lawrence.
3. G06: Replace the days column with days per year in a 30-day window above 100,000 gal/day, divided by valid years. Keep the daily count as a separate, clearly labelled column.
4. G14: Rename the lowest bin "No eligible plant within 10 mi" everywhere.
5. G22: Compute implied WUE from the achieved average in the 2% sensitivity.
6. G02: Regenerate every figure in Helvetica. Delete assets/fonts/Inter-* and the inter_font entry. Add a test that fails if any PDF embeds Inter.
7. G07, G08, G11, G13, G16, G17, G18: Update results.md: the matchable count is not robust to capacity (spread of 10 sites) and 22 of 24 stays the lead; the near-miss footnote; DRBC agreement and the by-state difference; location-confidence counts; the capacity sensitivity table; silica and chloride coverage; model constants as stated assumptions; the 7Q10 provisional-data note; one definition of "unverified" that reconciles all counts; remove informal phrasing.
8. Label the Delaware and Schuylkill once each on the v3 map.
Checkpoint: print the new headline numbers (sites within 10 mi, covered-capacity bins, blind-spot counts for both mechanisms, Falls implied IT load and peak day).

PART 2: FALLS FIGURES AND PER-SITE BLIND SPOT
9. figures/falls_duration_curve: daily modelled makeup vs percent of days exceeded (log y), with horizontal reference lines for the 135,000 gal/day average, the 4.4 MGD peak, and the 100,000 gal/day DRBC threshold, each labelled at the line end. Report the peak-to-average ratio.
10. figures/drought_coincidence: daily modelled makeup vs same-day Trenton flow percentile, DRBC drought warning periods highlighted. Report the share of top 5% demand days below the 25th flow percentile and below 7Q10.
11. Run the blind-spot test on each of the 24 active sites (stated or assumed capacity, calibrated hybrid). For each, find the likely water supplier from sources and classify it as public or authority supply, self-supplied, or unknown. Report how many would need no DRBC review because they purchase from an existing system. Cite each supplier source; mark unknowns.

PART 3: CYCLES OF CONCENTRATION (idea 5)
12. No plant reports silica in its DMRs. Use the Water Quality Portal (waterqualitydata.us) to get dissolved silica (and calcium, alkalinity, pH, chloride where missing) at the monitoring station nearest each matched plant's source water or receiving stream as a proxy, and state that municipal effluent silica tracks source water. Where no station exists, use a sourced literature range for secondary effluent and mark it assumed.
13. For each matched plant, compute allowable cycles of concentration limited by silica (cite the tower limit, e.g. 150 mg/L as SiO2, from an industry source), chloride, phosphate, and the Langelier Saturation Index at a stated tower temperature. Report the binding constraint, allowable cycles, makeup and blowdown per unit evaporation, and the implied minimum return-flow percentage for the term sheet. Table: results/cycles_by_plant.csv and .md. Figure: figures/cycles_constraints showing allowable cycles by plant with the binding constraint marked.

PART 4: UNCERTAINTY (idea 6)
14. Monte Carlo, 10,000 draws per site: WUE from LBNL Figure 4.4 ranges by architecture, PUE from LBNL's 1.15 to 1.35 hyperscale range, architecture share (evaporative, hybrid, air-cooled) with stated weights, and capacity drawn from a sourced range where unstated. Report P50 and P90 peak-day makeup per site and whether the nearest plant still covers P90. Figure: figures/peak_uncertainty, per-site P50 to P90 ranges against nearest-plant median flow. State in results.md whether a peak-day cap written at P90 changes any site's coverage.

PART 5: WATER-ENERGY TRADEOFF (idea 7)
15. For each architecture at Trenton climate, compute annual water (gallons per MW-year of IT load) and annual cooling energy (kWh per MW-year, from PUE minus 1 using LBNL Figure 4.4 ranges). Plot the frontier: figures/water_energy_frontier, one point with range bars per architecture, water on x, energy on y. Add the Falls calibrated hybrid as a labelled point. One paragraph in results.md on why developers resist reuse-first terms and where reclaimed water changes the tradeoff.

PART 6: AUDIT TIER 2 AND RELEASE
16. G01, G03, G12: every raw file fetchable from a clean clone; --verify checks existence and hashes and exits non-zero on failure; URL checks in a separate make target; git init and commit; locked environment.
17. G09, G10: Wayback URLs for every 403 page; fix the DRB33 expired link; mark DRB07 and DRB33 unverified until reconfirmed.
18. G15: log every dropped site in exclusions.csv with stage "sites". G20: fix the low-contrast palette pair. G23: fix warnings, delete stray preview files, update .gitignore.
19. G21: Restructure README.md as a technical appendix: one-paragraph findings, the v3 map, the blind-spot table, key numbers with keys, methods, limitations, then reproduction and repo layout. Add a data-license table.
20. Run make all from a clean clone, then run the full audit prompt in audit/SPEC.md again with a fresh sub-agent and save it as audit/AUDIT_v2.md.

Stop after each part and print a five-line status. Do not push to GitHub; I will do that after reviewing AUDIT_v2.md.
```

}","content_type":"text/plain","size_bytes":6098}
Excuse the attached text file prompt. Also considering using multiple agents as stated below.
Part 1 runs first, alone, because the recalibration changes every per-MW rate downstream.
After Part 1 passes its checkpoint, run these as parallel sub-agents:
- Agent A: Part 2 (Falls figures and per-site blind spot)
- Agent B: Part 3 (cycles of concentration)
- Agent C: Part 4 (Monte Carlo)
- Agent D: Part 5 (water-energy tradeoff)
- Agent E: Part 6 items 16, 17, 18 (reproducibility, URLs, exclusions, palette, warnings)
- Agent F: supplier research for item 11 (can start during Part 1, since it only needs the site list)
Rules for sub-agents:
- Each sub-agent writes only its own code module, figures, and result files. You are the single writer for results.md, references.bib, sources.md, README.md, and the Makefile; sub-agents send you text and bib entries, and you merge.
- Each sub-agent adds tests for its own module and must pass them before reporting back.
- Each sub-agent opens its own figures at 100% zoom and fixes collisions before reporting.
- When all agents finish, run item 19 (README), then make all from a clean clone, then item 20 (the fresh-agent audit).
Report which agents are running and a time estimate for each.

### Later message 2

I will be away. Do not stop for approvals. If a step needs network access or a decision from me, use the most conservative option that keeps the work reproducible, log the choice in results/pending_approvals.md, and continue with everything that does not depend on it. Batch any remaining domain requests into one list at the end.

### Later message 3

Lift the 900-word cap on results.md. Keep it clear and sectioned, with a 150-word summary at the top.

### Later message 4

Additions for when all agents finish:

1. Write results/brief_numbers.md: one formal sentence per headline finding, each with its citation key, in this order: site count and DRBC agreement; Falls potable vs cooling average vs peak day; the two blind-spot mechanisms; the per-site count of the 24 that purchase water and would need no DRBC review; sites within 10 mi of a plant and the capacity sensitivity; Falls implied IT load vs the 253 MW figure; cycles of concentration result; P90 result; water-energy result. Under 300 words total.

2. Export brief-size versions: figures/supply_screen_map_v3_brief at 120 mm wide (same design, fonts rescaled so text stays at least 6.5 pt), and results/table_blindspot_brief.csv with at most 6 rows and 5 columns chosen to show both mechanisms.

3. Lift the 900-word cap on results.md; keep a 150-word summary at the top.

4. After AUDIT_v2.md, fix any new blockers automatically, then stop. Do not push to GitHub.

### Later message 5

Brief table: rename the last two columns "DRBC review if self-supplied" and "DRBC review if purchased". Order the rows Falls first, then the three hybrids by size, then the tower, then air-cooled. No other changes.

### Later message 6

Add two Monte Carlo figures (repo and talk), in the v3 style from styles.py: navy accent, grays, Helvetica, no titles or sentences inside the image, captions and data files alongside.

1. figures/falls_mc_fan: x = day of year, y = modelled daily makeup at Falls (gal/day, log scale). Draw 300 randomly chosen Monte Carlo traces as very thin lines at about 4% opacity in the accent. Overlay the P50 line (solid, 1 pt) and the P10 to P90 band (accent at 20% opacity). Horizontal reference lines, thin gray dashed, labelled at the right end: 100,000 gal/day (DRBC trigger) and 4.4 MGD (reported peak). Light gray vertical shading for June through August. 180 mm wide, 80 mm tall.

2. figures/sites_mc_ridgeline: one kernel density per active site of simulated peak-day makeup (log x, gal/day), stacked vertically with slight overlap, sorted by median, filled in the accent at 30% opacity with a 0.5 pt outline. Mark each site's P90 with a small tick and its nearest plant's median flow with a short black vertical bar on the same row. Label rows at the left with site number and short name. Sites with no plant within 10 mi get a gray fill. 180 mm wide, height as needed for 24 rows.

Report how many sites have P90 above their nearest plant's median flow.
3. For falls_mc_fan, each trace is one Monte Carlo draw of the model parameters run over one of the 20 weather years (2005 to 2024), chosen at random, so traces vary by both parameters and weather. State this in the caption.
4. Also restyle figures/peak_uncertainty to the range-bar layout: one row per active site sorted by P50, a light accent bar from P50 to P90, a dot at P50, a tick at P90, an open black square at the nearest plant's median flow, log x in gal/day, gray rows for sites with no plant within 10 mi, a short right-margin note only for "P90 exceeds plant" and "No plant within 10 mi", row labels from site_key.csv.

### Later message 7

Deploy as many additional sub-agents as useful to finish the existing work faster, for example one polish agent per figure group, but only for tasks already in the work order. Keep G's style rules and H's QA as the single standard, and keep yourself as the single writer for results.md, references.bib, sources.md, README.md, and the Makefile.

