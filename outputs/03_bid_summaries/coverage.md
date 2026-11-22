# Bid summary coverage

Status of the bid summary PDFs for the BidLens slice (Districts 4 and 5, 2018 to 2026), checked 2026-11-19 by `bidlens.ingest.check_bid_summaries`. The list holds contract numbers and dates only. The PDFs themselves stay git-ignored.

## Summary

| | Bid openings |
| --- | --- |
| In the download checklist | 827 |
| Usable bid summary | **665** |
| Not on the Caltrans site | 151 |
| No usable summary exists (Caltrans errors, listed below) | 11 |

Seven more files hold earlier openings of in-scope contracts. These are real bid summaries and are kept as their own contract records, which gives **672 usable bid summaries** in all, covering bids opened 2019-01-08 to 2026-11-03. The Caltrans archive has no 2018 bid summaries.

**How usable files were checked:**
- **631 files with a text layer.** The item rows match the stated number of items, and the low bidder's items sum exactly to the low bid.
- **41 files read by OCR.** Caltrans serves these with broken fonts (confirmed by the maintainer: the site has no other copy). 37 pass the same exact-sum check. In the other 4, a few item lines were misread, so their item lines are left out. Their contract-level fields are still confirmed by the header check below.
- **Header check, all 672 files:** the engineer's estimate × (1 + printed % over/under) reproduces the low bid, within rounding.

In 43 contracts, one or more listed bids carry no rank. These are most likely irregular bids. The ranked count is used as the bidder count. In 16 OCR files, the printed bidder count was not readable, so the count of listed bids is used.

## No usable summary exists (11)

The maintainer re-downloaded all of these on 2026-11-19. The site serves the same files byte for byte.

| Contract | Bid opened | Problem |
| --- | --- | --- |
| 04-1A6614 | 2020-08-26 | Caltrans attached the wrong PDF (postponed contract 03-2F5704) to this record |
| 04-0P1104 | 2021-05-20 | Caltrans attached the summary of an earlier opening (2019-05-01); no summary exists for this one |
| 04-4J9704 | 2022-04-21 | Caltrans attached the summary of an earlier opening (2021-10-14); no summary exists for this one |
| 05-0T9914 | 2023-03-29 | Caltrans attached the summary of an earlier opening (2022-07-27); no summary exists for this one |
| 04-2W5104 | 2023-05-25 | Caltrans attached the summary of an earlier opening (2022-11-03); no summary exists for this one |
| 05-1P5374 | 2023-07-11 | Caltrans attached the summary of an earlier opening (2022-11-30); no summary exists for this one |
| 05-1P5354 | 2023-08-17 | Caltrans attached the summary of an earlier opening (2023-03-15); no summary exists for this one |
| 05-1P5364 | 2024-07-09 | Caltrans attached the summary of an earlier opening (2023-01-24); no summary exists for this one |
| 04-0Q2104 | 2024-07-25 | Caltrans attached the summary of an earlier opening (2024-01-11); no summary exists for this one |
| 04-3W5604 | 2024-08-07 | Caltrans attached the summary of an earlier opening (2023-11-08); no summary exists for this one |
| 05-1Q4704 | 2024-08-28 | Caltrans attached the summary of an earlier opening (2024-03-14); no summary exists for this one |

## Not on the Caltrans site (151)

All 2018 openings, plus a few later ones and earlier openings of re-bid contracts. Item prices for these still come from the cost database. Only the contract-level fields (engineer's estimate, working days, bid totals) are missing.

By year: 2018: 120, 2019: 5, 2022: 4, 2023: 4, 2024: 6, 2025: 10, 2026: 2.

04-3G6034 (2018-01-10), 05-1J2004 (2018-01-11), 04-4G8304 (2018-01-17), 05-1H3804 (2018-01-17), 05-1J7404 (2018-01-17), 05-1H6704 (2018-01-23), 05-1J7204 (2018-01-23), 04-4G8504 (2018-01-24), 05-1J2604 (2018-01-24), 05-0G0714 (2018-01-25), 04-3G1404 (2018-01-30), 05-1J7304 (2018-02-01), 04-4H2104 (2018-02-06), 05-1F7104 (2018-02-08), 04-4G8104 (2018-02-14), 05-1J3004 (2018-02-14), 05-1J2804 (2018-02-15), 05-1G5604 (2018-02-21), 04-1K5904 (2018-02-22), 04-3G4424 (2018-02-22), 05-1J5204 (2018-02-22), 04-3J7404 (2018-03-06), 04-4G7904 (2018-03-06), 04-2640N4 (2018-03-07), 04-0Q5104 (2018-03-08), 05-1C9904 (2018-03-08), 04-0Q5004 (2018-03-13), 04-0Q5304 (2018-03-20), 05-1G9104 (2018-03-20), 04-0Q5204 (2018-03-22), 04-2J4604 (2018-03-22), 05-1H6604 (2018-03-28), 04-4S7804 (2018-04-03), 04-2G3504 (2018-04-04), 04-3K5704 (2018-04-10), 04-4H7514 (2018-04-10), 04-4G8904 (2018-04-11), 05-1J1704 (2018-04-11), 05-1G9004 (2018-04-12), 04-1K7804 (2018-04-17), 04-1K6204 (2018-04-18), 04-2J0414 (2018-04-19), 04-3K6504 (2018-04-24), 04-2K1604 (2018-04-26), 04-2K0104 (2018-05-01), 04-3K6704 (2018-05-02), 04-0P6504 (2018-05-03), 04-1K6004 (2018-05-08), 04-1K6104 (2018-05-09), 04-0Q9404 (2018-05-10), 04-3K6104 (2018-05-10), 04-3K6304 (2018-05-15), 04-1K5704 (2018-05-16), 04-0P6804 (2018-05-17), 04-1J0104 (2018-05-17), 05-492824 (2018-05-23), 04-3J5704 (2018-05-30), 05-1J1704 (2018-05-30), 04-0P6104 (2018-05-31), 04-2K0004 (2018-05-31), 04-4A1104 (2018-06-07), 04-1J7504 (2018-06-13), 05-1F3504 (2018-06-13), 04-155004 (2018-07-12), 05-0C6414 (2018-07-18), 04-2J4804 (2018-08-14), 04-2J5504 (2018-08-21), 05-1F0804 (2018-08-29), 04-4G9204 (2018-09-05), 05-1G1404 (2018-09-05), 05-0A0504 (2018-09-13), 04-2A2514 (2018-09-20), 04-2J6704 (2018-09-25), 04-2J0004 (2018-09-26), 04-2J4404 (2018-10-04), 04-1K3404 (2018-10-09), 04-0G2214 (2018-10-10), 05-1C3704 (2018-10-10), 04-3J9004 (2018-10-11), 05-1H2904 (2018-10-11), 04-2J5604 (2018-10-16), 05-1C2504 (2018-10-16), 04-1J3704 (2018-10-17), 05-1C2604 (2018-10-18), 04-2J5704 (2018-10-25), 04-0J1404 (2018-10-30), 04-2J5904 (2018-10-30), 05-1E0204 (2018-10-30), 04-4H9804 (2018-10-31), 04-4J2814 (2018-10-31), 05-1F4304 (2018-10-31), 05-1C6504 (2018-11-01), 05-1F7604 (2018-11-01), 04-1J7004 (2018-11-06), 04-4G1134 (2018-11-07), 05-1A0004 (2018-11-07), 04-4G8804 (2018-11-08), 05-1F75U4 (2018-11-08), 04-0J2104 (2018-11-15), 04-1J0104 (2018-11-15), 04-2J5404 (2018-11-15), 05-1C8904 (2018-11-15), 04-151614 (2018-11-27), 04-2J5004 (2018-11-28), 05-1J2504 (2018-11-28), 04-3K5804 (2018-11-29), 04-4H0804 (2018-11-29), 04-3K6204 (2018-12-04), 05-1J5604 (2018-12-05), 04-0P6404 (2018-12-11), 04-270104 (2018-12-11), 05-1J4904 (2018-12-11), 04-1K0104 (2018-12-12), 04-2J0424 (2018-12-12), 04-3G6904 (2018-12-13), 05-1J2704 (2018-12-13), 04-4G5604 (2018-12-18), 04-0J3804 (2018-12-20), 04-2J1004 (2018-12-20), 04-3K6004 (2018-12-20), 05-1K4004 (2019-01-24), 04-4G8204 (2019-02-13), 04-0P1104 (2019-06-13), 05-1E0104 (2019-10-16), 04-4G8204 (2019-11-13), 05-0N71Y4 (2022-01-31), 05-3307A4 (2022-02-11), 05-1G4104 (2022-07-05), 05-1K03U4 (2022-10-07), 05-3307C4 (2023-02-13), 05-0N74U4 (2023-06-09), 05-0N73Y4 (2023-06-12), 05-1P5334 (2023-08-03), 05-1C9504 (2024-02-01), 05-0N74V4 (2024-03-01), 05-0N7054 (2024-03-05), 04-0Y9804 (2024-05-30), 05-0N72Y4 (2024-07-18), 04-3W9104 (2024-08-12), 04-0Y6804 (2025-02-28), 04-4Y1804 (2025-03-07), 04-0A53T4 (2025-04-28), 04-1Q8204 (2025-05-23), 04-0W0304 (2025-06-10), 04-0X7204 (2025-07-21), 04-0Q0204 (2025-08-26), 04-0K81U4 (2025-09-03), 04-0X6504 (2025-09-26), 05-0N7064 (2025-12-17), 04-2X7004 (2026-07-10), 04-2X8004 (2026-08-14)
