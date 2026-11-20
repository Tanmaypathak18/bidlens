# Contract-level data: missing-data report (step 1.5)

Generated from `data/bidlens.duckdb`. There are 848 contract openings: the 827 in the D-015 list, plus 14 seen only in item bids and 7 earlier openings found in bid summaries.

| Field | Missing | Where it comes from |
| --- | --- | --- |
| district | 0 | contract number |
| county | 14 | sv08data details, or the bid summary |
| engineer's estimate | 176 | bid summary |
| working days | 180 | bid summary |
| bidder count (ranked, from summary) | 176 | bid summary. A fallback from sv08data bid ranks is missing for only 0 |
| low bid total | 176 | bid summary |

**Why fields are missing:**
- **No bid summary:** 151 openings are not on the Caltrans site, 11 have the wrong PDF attached (D-026), and 14 openings appear only in item bids.
- **OCR misses:** 4 OCR-read summaries lost the working-days value.

**Cross-checks between sources:**
- **Low bidder's item prices:** the cost database and the bid summaries agree to the cent on 11,774 of 11,947 matching items (98.6%). All 173 differences fall in 11 contracts whose rank-1 bidder differs between the sources, which looks like a bid ranking change (for example, a rejected low bid), not bad numbers. Step 1.6 flags these contracts.
- **Bidder counts:** the highest rank in the cost database matches the ranked bidders in the summary for 657 of 665 contracts that have both.

## Contracts with missing fields (180)

| Contract opening | Missing | Reason |
| --- | --- | --- |
| 04-3G6034_2018-01-10 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J2004_2018-01-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G8304_2018-01-17 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1H3804_2018-01-17 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J7404_2018-01-17 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1H6704_2018-01-23 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J7204_2018-01-23 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G8504_2018-01-24 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J2604_2018-01-24 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0G0714_2018-01-25 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3G1404_2018-01-30 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J7304_2018-02-01 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4H2104_2018-02-06 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1F7104_2018-02-08 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G8104_2018-02-14 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J3004_2018-02-14 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J2804_2018-02-15 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1G5604_2018-02-21 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1K5904_2018-02-22 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3G4424_2018-02-22 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J5204_2018-02-22 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3J7404_2018-03-06 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G7904_2018-03-06 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2640N4_2018-03-07 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0Q5104_2018-03-08 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1C9904_2018-03-08 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0Q5004_2018-03-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0Q5304_2018-03-20 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1G9104_2018-03-20 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0Q5204_2018-03-22 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J4604_2018-03-22 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1H6604_2018-03-28 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4S7804_2018-04-03 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2G3504_2018-04-04 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3K5704_2018-04-10 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4H7514_2018-04-10 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G8904_2018-04-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J1704_2018-04-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1G9004_2018-04-12 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1K7804_2018-04-17 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1K6204_2018-04-18 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J0414_2018-04-19 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3K6504_2018-04-24 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2K1604_2018-04-26 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2K0104_2018-05-01 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3K6704_2018-05-02 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0P6504_2018-05-03 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1K6004_2018-05-08 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1K6104_2018-05-09 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0Q9404_2018-05-10 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3K6104_2018-05-10 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3K6304_2018-05-15 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1K5704_2018-05-16 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0P6804_2018-05-17 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1J0104_2018-05-17 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-492824_2018-05-23 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3J5704_2018-05-30 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J1704_2018-05-30 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0P6104_2018-05-31 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2K0004_2018-05-31 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4A1104_2018-06-07 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1J7504_2018-06-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1F3504_2018-06-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-155004_2018-07-12 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0C6414_2018-07-18 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J4804_2018-08-14 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J5504_2018-08-21 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1F0804_2018-08-29 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G9204_2018-09-05 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1G1404_2018-09-05 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0A0504_2018-09-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2A2514_2018-09-20 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J6704_2018-09-25 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J0004_2018-09-26 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J4404_2018-10-04 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1K3404_2018-10-09 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0G2214_2018-10-10 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1C3704_2018-10-10 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3J9004_2018-10-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1H2904_2018-10-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J5604_2018-10-16 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1C2504_2018-10-16 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1J3704_2018-10-17 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1C2604_2018-10-18 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J5704_2018-10-25 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0J1404_2018-10-30 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J5904_2018-10-30 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1E0204_2018-10-30 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4H9804_2018-10-31 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4J2814_2018-10-31 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1F4304_2018-10-31 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1C6504_2018-11-01 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1F7604_2018-11-01 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1J7004_2018-11-06 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G1134_2018-11-07 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1A0004_2018-11-07 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G8804_2018-11-08 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1F75U4_2018-11-08 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0J2104_2018-11-15 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1J0104_2018-11-15 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J5404_2018-11-15 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1C8904_2018-11-15 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-151614_2018-11-27 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J5004_2018-11-28 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J2504_2018-11-28 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3K5804_2018-11-29 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4H0804_2018-11-29 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3K6204_2018-12-04 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J5604_2018-12-05 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0P6404_2018-12-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-270104_2018-12-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J4904_2018-12-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1K0104_2018-12-12 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J0424_2018-12-12 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3G6904_2018-12-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1J2704_2018-12-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G5604_2018-12-18 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0J3804_2018-12-20 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2J1004_2018-12-20 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3K6004_2018-12-20 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1K4004_2019-01-24 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G8204_2019-02-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0P1104_2019-06-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1E0104_2019-10-16 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4G8204_2019-11-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1A6614_2020-08-26 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0P1104_2021-05-20 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0N71Y4_2022-01-31 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-3307A4_2022-02-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4J9704_2022-04-21 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1G4104_2022-07-05 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1K03U4_2022-10-07 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-3307C4_2023-02-13 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4J8504_2023-03-16 | working_days | OCR could not read the value |
| 05-0T9914_2023-03-29 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2W5104_2023-05-25 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0N74U4_2023-06-09 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0N73Y4_2023-06-12 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1P5374_2023-07-11 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1M7304_2023-07-19 | working_days | OCR could not read the value |
| 05-1P5334_2023-08-03 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1P5354_2023-08-17 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1C9504_2024-02-01 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0N74V4_2024-03-01 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0N7054_2024-03-05 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0Y3904_2024-05-14 | working_days | OCR could not read the value |
| 04-0Y9804_2024-05-30 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1P5364_2024-07-09 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0N72Y4_2024-07-18 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0Q2104_2024-07-25 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3W5604_2024-08-07 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3W9104_2024-08-12 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1Q4704_2024-08-28 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0Y6804_2025-02-28 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-4Y1804_2025-03-07 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0A53T4_2025-04-28 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1Q8204_2025-05-23 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0W0304_2025-06-10 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0X7204_2025-07-21 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0Q0204_2025-08-26 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0K81U4_2025-09-03 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0X6504_2025-09-26 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-0N7064_2025-12-17 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-1Y6904_2025-12-18 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X5304_2026-03-25 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X7404_2026-03-26 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X7504_2026-05-07 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 05-1R7704_2026-05-07 | working_days | OCR could not read the value |
| 04-2X7804_2026-05-13 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X7204_2026-05-14 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X7104_2026-05-20 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X7904_2026-05-28 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X8104_2026-05-28 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X7304_2026-06-02 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X7604_2026-06-03 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-3X6904_2026-06-04 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X7004_2026-07-10 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2X8004_2026-08-14 | engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-2W3704_2026-08-25 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
| 04-0W1404_2026-09-16 | county, engineers_estimate, working_days, n_bidders, low_bid_total | No bid summary (see bid_summary_coverage.md) |
