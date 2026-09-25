# Pending approvals

The following items need a decision from the repository owner. The rest of the pipeline does not depend on any of them.

1. Git initialisation. The build environment does not permit `git init`, so the repository is not yet under version control. Run `git init && git add -A && git commit -m "Reuse-Ready"` and set the repository URL in references.bib (key reuse_ready_model) and CITATION.cff.
2. Six datacenterdynamics.com source pages refuse automated requests. The sites they support are marked unverified (dashed outline) until someone opens them by hand.
3. The v2 source line adds "U.S. Census Bureau" to the wording in the figure instruction, because the v2 and v3 maps draw Census cartographic boundaries. Approve the addition or name an alternative.
4. The Sierra Club page on the Falls campus returns a redirect loop and was not opened. Its unverified 400 to 500 MW figure is not used.

## Work order of 2026-09-25 (Parts 1 to 6): decisions taken while you were away

5. results.md word limit. Resolved by the owner on 2026-09-25: the 900-word cap is lifted; results.md stays
   sectioned and opens with a summary of about 150 words.
6. Network access. Sub-agents were told not to request new domains. Where a domain is blocked they use a
   sourced literature value marked "assumed" and add the domain to the batched list at the end of this file.
7. Calibration primary switched to the peak-day reading (audit G04), as instructed. Every per-MW rate
   downstream changed from 13,567 to 13,286 gal/day per MW of IT load; no site changed bin.

## Monte Carlo P90 headline (logged 2026-09-25, awaiting your choice)

The item-14 Monte Carlo draws IT load for the 16 sites that publish no capacity from the eight stated active-site loads (242 to 1,250 MW). Under that draw, P90 peak-day makeup exceeds the nearest eligible plant's median flow at 21 of the 22 sites that have a plant within 10 mi; only DRB24 (Allentown Warehouse Conversion) remains covered [reuse_ready_model]. With the 16 unstated sites held at the screen's 100 MW, P90 is covered at 6 of 24 sites [reuse_ready_model]. Most of the difference comes from the capacity assumption, not the cooling uncertainty. A second caveat: LBNL hybrid WUE multiplied by the Falls peak-to-average ratio exceeds full evaporation in 92 percent of hybrid draws, which are capped [shehabi_2024; reuse_ready_model].

Conservative choice taken: results.md and brief_numbers.md will report the stated-load draw as primary and the 100 MW case alongside it in the same sentence, so neither is hidden. Tell me if you want the 100 MW case to lead instead.

## Table A layout versus the 180 mm figure rule (logged 2026-09-25)

figures/table_blindspot.png is 330 mm wide and carries a bold headline and subtitle inside the image, which the original spec requires for the table ("one bold headline row") but which departs from the 85 or 180 mm width rule and the no-titles-in-image rule applied to figures [reuse_ready_model]. Its 13 columns need at least 221 mm at 7 pt. Conservative choice taken: keep the spec layout for the full table, and use results/table_blindspot_brief.csv (6 rows, 5 columns) for the brief. A 180 mm version would require splitting the table into two panels or moving the headline and footnotes into the caption; tell me if you want either.
