# Planned data center sites in the Delaware River Basin: research list

This note documents a companion site search dated 2026-09-25. The pipeline reads the hand-built planned_sites.csv, not this list, so the counts and verification flags below describe this search only.

## Counts
- DRBC benchmark: about 24 planned (Khalil presentation, 2026-03-31: PA 18 / NJ 3 / DE 3) or 25 (Pindar presentation, 2026-04-17: PA 18 / NJ 4 / DE 3). The DRBC data-centers page says "approximately 24 new data centers being planned" and that none had applied to DRBC as of June 2026.
- This search located **29 rows**, all inside the DRB (WBD HUC6 020401 + 020402, point-in-polygon). Of these, **24 verified** and **5 unverified**.
- By state: PA 22 (21 verified), NJ 3 (2 verified), DE 4 (1 verified), NY 0.
- Row counts do not correspond one-to-one with DRBC's counts. The Upper Merion Renaissance Boulevard cluster (4 submissions) is a single row. Patch reports eight MLP Ventures projects in Upper Merion. This list names addresses for 7 of them (4 Renaissance + Horizon + Swedeland + River Rd), and the eighth was not identified. DRBC's own list is not published site by site beyond the NJ slides and the Thompson presentations.
- Exclusions (6) are in `planned_sites_research_exclusions.csv`: Hazelnut (outside the DRB), American Tower East Greenwich (withdrawn), Air Products Cetronia Rd (withdrawn), plus three non-proposals.

## Data quality and scope
- **Geocode precision.** 9 address-level, 12 street-level, 3 named-place, 5 municipality-level. The five municipality-level points (Titus Station, East Coventry, Earth Station 76, White Clay and Blue Diamond) are too coarse for a fine-scale screen.
- **900 Conshohocken Rd.** Nominatim resolved the address to Conshohocken State Rd in Lower Merion, which is incorrect, so the point is placed at street level on Conshohocken Rd, Plymouth Twp. DRBC's pin (40.085117, -75.3227566) is likely the more precise location.
- **Status mix.** Most rows are early stage. Pennhurst was denied and is under appeal. Project Washington's current plan is blocked under the Coastal Zone Act. Amazon Falls is under construction. Vineland Phase 1 is reported as newly operational (Montco.today, June 2026), and the row covers the planned Phase 2-3 expansion.
- **Earth Station 76** is unverified. DRBC lists it, but Logan Township officials said no proposal had been received, and the township introduced a data center ban (NJ Advance via Yahoo, 2026-04-13). The DRBC presentation says Salem County. Logan Township is in Gloucester County.
- **Delaware.** The three DBT "exploratory" business-park plans are unverified. They are data-center-capable shells, not confirmed data center applications. No opened source establishes whether DRBC counts them toward its Delaware total of 3.
- **Gouldsboro/Clifton.** The site sits near the Lehigh/Lackawanna (Susquehanna) divide. Both the street point and DRBC's pin fall inside the DRB, but part of the 1,000-acre campus may drain to the Susquehanna.
- **Capacity.** capacity_mw is filled only where an opened source states it: Project Laurel 750, Carbon Node East 350 (expandable to 510), Gouldsboro 1500, Upper Mount Bethel up to 2000, Project Washington 1200, Metrobloks 100, Vineland 350-1000, Earth Station 76 100-150.
- The search excluded trackdatacenters.com and padatacenterproposals.com, which keeps it independent of the proposal trackers. Sources that could not be read: berksconnect tracker (bot checkpoint), ocolo.io (403), nrg-concepts Earth Station page (404), connects.buckscounty.gov, lehighvalleypublicmedia.org and thecentersquare.com (blocked).
- Scope: Philadelphia (no proposals, per the Inquirer), NY (0, per DRBC), Schuylkill County, other Berks sites, Delaware County PA and Mercer, Burlington and Camden counties NJ received a screening-level search.

## Amazon Keystone Trade Center (Falls Twp): stated capacity
**No MW figure for IT or campus capacity was found in any opened page.** What the opened sources say:
- Falls Township, "Falls OKs Data Centers at Keystone Trade Center" (https://www.fallstwp.com/resources/news/article/?id=9844): "While Michael said NorthPoint is under a non-disclosure agreement and could not say how many megawatts of data would be incorporated at the sites, he acknowledged “it’s a significant amount.”"
- The Keystone, 2026-07-20, "Bucks County's first data center will open soon. What you need to know" (https://keystonenewsroom.com/news/infrastructure/bucks-countys-first-data-center-will-open-soon-what-you-need-to-know/): "Amazon has not disclosed how much energy its Falls facility will need."
- Philadelphia Inquirer, 2025-10-23 (https://www.inquirer.com/business/energy/monitor-questions-amazon-peco-data-center-agreement-20251023.html) refers to "a Sept. 23 transmission service agreement between Peco and Amazon Data Services" (FERC filing) for the Keystone campus. The article states no MW figure. The FERC filing itself was not opened, and neither were PJM queue records.
- WHYY, 2026-07-15 (https://whyy.org/articles/amazon-data-center-bucks-county-pa-gas-generators-impact/): DEP plans to approve "280 natural gas-fired generators and three diesel-fired generators" for backup power. It gives no MW rating.
