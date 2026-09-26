# Allowable cycles of concentration by matched plant

Source: results/cycles_by_plant.csv [cycles_by_plant.csv], produced by `python -m peakflow.cycles`. Every row is marked 'assumed' because Water Quality Portal records were not retrieved for the matched plants [wqp_status.json]. Silica, calcium and alkalinity are literature values [vidic_2009, hem_1985], TDS and phosphate are the plant's own DMR medians where reported [epa_echo], and chloride is a TDS-based proxy because no matched plant reports chloride [epa_echo]. Return flow is defined as blowdown / makeup = 1/C.

| Plant | NPDES | Sites | C silica | C chloride | C phosphate | C LSI | Binding | Allowable C (range) | Makeup/E | Blowdown/E | Min return flow % | C without phosphate | Status |
|---|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---|
| Catasauqua Mun Sew Auth | PA0021580 | DRB25 | 10.7 | 8.2 | 0.9 | 7.0 | Phosphate | 0.9 (0.9 to 0.9) |  |  |  | 7.0 (LSI) | assumed |
| Trenton Sewer Utility | NJ0020923 | DRB12 | 10.7 | 5.9 | 1.0 | 6.5 | Phosphate | 1.0 (1.0 to 1.0) | 152.28 | 151.28 | 99 | 5.9 (Chloride) | assumed |
| Matsunk Stp | PA0026085 | DRB31 | 10.7 | 8.2 | 1.2 | 7.0 | Phosphate | 1.2 (1.2 to 1.2) | 5.74 | 4.74 | 83 | 7.0 (LSI) | assumed |
| Morrisville Borough Stp | PA0026701 | same-state option for DRB12 | 10.7 | 4.6 | 1.4 | 6.9 | Phosphate | 1.4 (1.4 to 1.4) | 3.28 | 2.28 | 69 | 4.6 (Chloride) | assumed |
| Millville (Wtp) City Of | NJ0029467 | DRB07 | 10.7 | 8.8 | 1.5 | 6.0 | Phosphate | 1.5 (1.5 to 1.5) | 3.07 | 2.07 | 67 | 6.0 (LSI) | assumed |
| East Stroudsburg Borough Wwtp | PA0020168 | DRB27 | 10.7 | 8.2 | 1.5 | 7.0 | Phosphate | 1.5 (1.5 to 1.5) | 3.03 | 2.03 | 67 | 7.0 (LSI) | assumed |
| Pennsville Sewerage Authority | NJ0021598 | DRB02, DRB03 | 10.7 | 5.5 | 1.8 | 6.6 | Phosphate | 1.8 (1.8 to 1.8) | 2.23 | 1.23 | 55 | 5.5 (Chloride) | assumed |
| Coaldale Lansford Summit Hll Sew | PA0026476 | DRB15, DRB40 | 10.7 | 8.2 | 1.9 | 7.0 | Phosphate | 1.9 (1.9 to 1.9) | 2.14 | 1.14 | 53 | 7.0 (LSI) | assumed |
| Lca Allentown Division Wwtp | PA0026000 | DRB24 | 10.7 | 8.2 | 1.9 | 7.0 | Phosphate | 1.9 (1.9 to 1.9) | 2.14 | 1.14 | 53 | 7.0 (LSI) | assumed |
| North Coventry Stp | PA0025437 | DRB33, DRB34 | 10.7 | 8.2 | 3.1 | 7.0 | Phosphate | 3.1 (2.4 to 3.1) | 1.48 | 0.48 | 33 | 7.0 (LSI) | assumed |
| Bangor Boro Auth Wwtp | PA0028568 | DRB37, DRB39 | 10.7 | 11.0 | 3.1 | 5.7 | Phosphate | 3.1 (2.1 to 3.1) | 1.48 | 0.48 | 32 | 5.7 (LSI) | assumed |
| Willingboro Water Pollution Control Plant | NJ0023361 | DRB04 | 10.7 | 7.0 | 3.1 | 6.3 | Phosphate | 3.1 (2.2 to 3.1) | 1.47 | 0.47 | 32 | 6.3 (LSI) | assumed |
| Gr Hazleton Jt Sew Auth Wwtp | PA0026921 | DRB16 | 10.7 | 8.2 | 4.1 | 7.0 | Phosphate | 4.1 (2.4 to 4.1) | 1.32 | 0.32 | 24 | 7.0 (LSI) | assumed |
| Newton Wastewater Treatment Plant | NJ0020184 | DRB10 | 10.7 | 5.3 | 24.5 | 6.6 | Chloride | 5.3 (2.3 to 5.3) | 1.23 | 0.23 | 19 | 5.3 (Chloride) | assumed |
| Northampton Boro/ Sew | PA0031127 | DRB38 | 10.7 | 9.4 | 9.2 | 5.9 | LSI | 5.9 (2.1 to 9.2) | 1.20 | 0.20 | 17 | 5.9 (LSI) | assumed |
| Francis S. Doyle Jr Treatment Facility | NJ0024821 | DRB05 | 10.7 | 6.6 | 7.7 | 6.3 | LSI | 6.3 (2.2 to 6.6) | 1.19 | 0.19 | 16 | 6.3 (LSI) | assumed |
| Pennridge Wwtp | PA0020460 | DRB14 | 10.7 | 8.2 | 7.0 | 7.0 | Phosphate | 7.0 (2.4 to 7.0) | 1.17 | 0.17 | 14 | 7.0 (LSI) | assumed |
| Upper Montgomery Joint Authority Stp | PA0020532 | DRB32 | 10.7 | 8.2 | 15.7 | 7.0 | LSI | 7.0 (2.4 to 8.2) | 1.17 | 0.17 | 14 | 7.0 (LSI) | assumed |
| West Chester Taylor Run Stp | PA0026018 | DRB22 | 10.7 | 8.2 | 16.3 | 7.0 | LSI | 7.0 (2.4 to 8.2) | 1.17 | 0.17 | 14 | 7.0 (LSI) | assumed |

The model assumes 4 cycles [peakflow_model], which implies makeup of 1.33 times evaporation and a minimum return flow of 25 percent [peakflow_model]. Blank makeup and blowdown cells mark plants whose makeup already exceeds a tower limit (allowable C at or below 1), which require treatment before use. The range brackets the favourable and adverse literature silica, calcium and alkalinity [vidic_2009, PDF p. 30].
