**0 of 12 configurations escape DRBC review by averaging, and all 8 that would trigger it escape if they buy water from an existing system**

Modeled daily cooling makeup compared with the DRBC review threshold of 100,000 gal/day, averaged over any 30 consecutive days.

| IT load (MW) | Configuration | 30-day avg, annual mean (gal/d)¹ | 30-day avg, max (gal/d)¹ | Peak day p99 (gal/d)¹ | Peak day max (gal/d)¹ | Below trigger on 30-day avg² | Days/yr, 30-day avg > 100,000 gal/d² | Days/yr, single day > 100,000 gal (not the trigger test)¹ | Of those, flow < DOY p25³ | Of those, flow < 7Q10³ | Review if self-supplied² | Review if purchased from an existing system⁵ |
| ---: | :--- | ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | :---: | :---: |
| 50 | Evaporative tower | 751,000 | 751,000 | 751,000 | 751,000 | No | 365 | 365 | 24.9% | 0% | Yes | No |
| 50 | Hybrid (calibrated) | 20,400 | 212,000 | 352,000 | 664,000 | No | 24.8 | 27.1 | 23.9% | 0% | Yes | No |
| 50 | Air-cooled chiller | 0 | 0 | 0 | 0 | Yes | 0 | 0 | n/a | n/a | No | No |
| 100 | Evaporative tower | 1,500,000 | 1,500,000 | 1,500,000 | 1,500,000 | No | 365 | 365 | 24.9% | 0% | Yes | No |
| 100 | Hybrid (calibrated) | 40,700 | 424,000 | 705,000 | 1,330,000 | No | 56.8 | 35.8 | 24.1% | 0% | Yes | No |
| 100 | Air-cooled chiller | 0 | 0 | 0 | 0 | Yes | 0 | 0 | n/a | n/a | No | No |
| 200 | Evaporative tower | 3,010,000 | 3,010,000 | 3,010,000 | 3,010,000 | No | 365 | 365 | 24.9% | 0% | Yes | No |
| 200 | Hybrid (calibrated) | 81,400 | 849,000 | 1,410,000 | 2,660,000 | No | 88.4 | 41.3 | 24.5% | 0% | Yes | No |
| 200 | Air-cooled chiller | 0 | 0 | 0 | 0 | Yes | 0 | 0 | n/a | n/a | No | No |
| 400 | Evaporative tower | 6,010,000 | 6,010,000 | 6,010,000 | 6,010,000 | No | 365 | 365 | 24.9% | 0% | Yes | No |
| 400 | Hybrid (calibrated) | 163,000 | 1,700,000 | 2,820,000 | 5,310,000 | No | 105 | 44.6 | 25.3% | 0% | Yes | No |
| 400 | Air-cooled chiller | 0 | 0 | 0 | 0 | Yes | 0 | 0 | n/a | n/a | No | No |
| n/a | Falls Twp (AWS Keystone), reported | 135,000⁴ | 1,410,000¹ | n/a | 4,400,000⁴ | No | n/a | n/a | n/a | n/a | Yes | No |

No configuration in the grid falls in the averaging blind spot, defined as below the threshold on every 30-day average but above 100,000 gal on at least one day. Under a looser annual-mean test, 3 of 12 configurations would qualify. The Falls row is a reference and is not counted.  
¹ Model-derived: PUE 1.2, 4 cycles of concentration, hybrid parameters from results/calibration.json primary, KTTN hourly wet-bulb 2005-2024 [noaa_isd, stull_2011, alduchov_1996]. Makeup is treated as gross withdrawal. 101 of 7,305 local days are missing, and 30-day windows require at least 27 valid days.  
² A withdrawal is excluded from review when the daily average gross withdrawal during any 30 consecutive day period does not exceed 100,000 gallons [drbc_admin_manual] (DRBC Administrative Manual Part 1, Article 3 and 18 CFR 401.35(a)(2)-(3)). Days/yr, 30-day avg counts days whose trailing 30-day average exceeds 100,000 gal/d (the trigger test). Days/yr, single day counts days whose own makeup exceeds 100,000 gal and is not the trigger test. Both are divided by the number of valid years (valid days or valid windows / 365.25).  
³ Delaware River at Trenton daily mean flow on days above 100,000 gal, compared with its 2005-2024 day-of-year 25th percentile and the full-record LP3 7Q10 of 1,795 cfs [usgs_nwis_01463500].  
⁴ Reported: average cooling service water 135,000 gal/day [falls_levittown_2026] and peak 4.4 million gal/day [falls_levittown_2026, falls_herald_2026].  
⁵ The thresholds apply to a project's own withdrawal, so a data center that buys water from an existing public or authority system is not itself reviewed [drbc_datacenters_2026, drbc_admin_manual]. Falls is supplied by the Morrisville Municipal Authority service-water system, whose allocation is reported as 243 million gal/day [falls_levittown_2026].  

Sources: [drbc_admin_manual], [drbc_datacenters_2026], [usgs_nwis_01463500], [falls_levittown_2026], [falls_herald_2026], [noaa_isd], [stull_2011], [alduchov_1996].
