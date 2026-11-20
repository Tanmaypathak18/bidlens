# BidLens model card

What the models in BidLens v1 do, what they were tested on, how well they did, and where they should not be trusted. Written for estimators first; the technical detail is in the linked notebooks and `outputs/` folders. Every number here comes from a committed stage report.

## In one paragraph

BidLens prices the bid items of a Caltrans heavy civil contract from past low bids, gives each price a low / likely / high range and the 10 most similar past bids, predicts how many contractors will bid and where the low bid will land against the engineer's estimate, and reads the bid documents for scope, risks and requirements with page citations. It runs entirely on the user's computer with free, open models. It is a first-pass aid for an estimator, not an estimate.

## Intended use

- **Users:** estimators and preconstruction teams bidding Caltrans work, and anyone studying public bid prices.
- **Use:** a fast, evidence-backed first draft of item prices and a reading aid for the bid package, to be reviewed, adjusted and approved by the estimator. Every number links to its evidence: comparable bids for prices, the quoted page for document findings.
- **Not intended for:** submitting a bid without estimator review; pricing work outside Caltrans Districts 4 and 5 or outside highway construction; private work; judging or ranking individual contractors (BidLens works at market level and never names a bidder); replacing a reading of the contract documents.

## The models

| Part | What it does | Model | Licence |
| --- | --- | --- | --- |
| Unit prices | Likely low-bid unit price for each of the 100 highest-value Caltrans items | NVIDIA Kumo Tabular, small, v1.0.1 (pretrained, not trained on our data; reads a table of earlier bids) | Code Apache-2.0; weights OpenMDW-1.1 |
| Price ranges | Low and high (10th and 90th percentiles) around the likely price | Kumo's own percentiles, recalibrated each quarter on past results (conformalized quantile regression) | as above |
| Other items | Prices for items outside the 100 | Median of earlier low bids for the same item, then same description, then same family and unit | none needed |
| Comparable bids | The 10 most similar earlier low bids for the same item | Distance on quantity, date, district and contract size | none needed |
| Market context | Low bid vs the engineer's estimate, and number of bidders, with 80% ranges | Kumo Tabular, recalibrated each quarter | as above |
| Document reading | Findings on 10 topics, each quoting its page | qwen3:8b and llama3.1:8b through Ollama, plus plain pattern rules; closure charts rebuilt by code | Apache-2.0 (qwen3); Llama 3.1 Community License (llama3.1) |

**Refreshed every quarter.** Before pricing a quarter, the pricing and market models see every bid opened before that quarter, and never one from the quarter being priced (decision D-045). This walk-forward setup was adopted after models frozen at the end of 2023 drifted high in the test years, because the statewide cost index rose much faster than these low bids ([notebook 04](../notebooks/04_kumo_tabular.ipynb)).

**Compared and not chosen:** XGBoost and LightGBM (gradient-boosted trees) and the historical median. The choice of Kumo was made on 2023 bids before the test years were looked at (decision D-046).

## Data

- **Source:** public Caltrans records. Item prices from the Caltrans Contract Cost Data site (sv08data.dot.ca.gov), collected at one request every 2 seconds; engineer's estimates, working days, bid totals and bidder counts from Caltrans bid summary PDFs, downloaded by hand. Details: [notebook 01](../notebooks/01_data_overview.ipynb), `outputs/01_` to `06_`.
- **Scope:** Caltrans Districts 4 (Bay Area) and 5 (Central Coast); bids opened 2018 to November 2026; the 100 bid items with the most low-bid dollars. 72,113 bid prices on 848 contract openings; 672 usable bid summaries.
- **Prices** are brought to the bid date with Caltrans' highway construction cost index, using only the quarters published before the bid ([notebook 02](../notebooks/02_price_escalation.ipynb)).
- **Cleaning:** unusual prices are flagged, not deleted; contracts where the two Caltrans sources disagree on the low bidder are left out of testing.
- **Privacy:** no bidder names, addresses or phone numbers are stored in outputs or shown in the app; bids are identified by rank. Phone numbers and email addresses in bid documents are masked.
- **Documents:** one sample package, contract 04-0W0504 (6 PDFs). Bid documents are not redistributed; only a manifest is committed.

## How it was tested

- **Time split, never random:** models learn from bids opened before 1 January 2024 and are tested on bids opened from then to 3 November 2026: 4,507 low-bid item prices on 238 contracts, and 208 contracts for the market models.
- **Item metric:** median miss against the low bidder's unit price (half of the predictions miss by less), and the share within 15%.
- **Contract metric (the headline):** every line of each test contract is priced and added up; the total is compared with the engineer's estimate and the actual low bid on the 178 test contracts where at least 90% of lines have price history.
- **Documents:** 89 gold facts written before any model output was opened; every finding judged blind (precision, recall, citation accuracy).

## Results

**Whole contracts (178 test contracts)** ([notebook 05](../notebooks/05_model_comparison.ipynb))

| | BidLens total | Engineer's estimate |
| --- | ---: | ---: |
| Closer to the low bid | 57.9% | 42.1% |
| Typical miss | 18.4% | 21.2% |
| Within 15% | 43.3% | 35.4% |
| Median over (+) / under (-) the low bid | +0.8% | +19.9% |

**Single items (4,507 test prices, refreshed each quarter):** Kumo 38.2% median miss and 20.8% within 15%; LightGBM 38.9%; XGBoost 40.1%; historical median 55.0%. For reference, the second-lowest bidder misses the low bidder's price by 27.5% on the same line.

**Where the chosen model loses:** on single items, LightGBM or XGBoost was better in 7 of 18 item families on the test years: general and overhead, striping and markings, earthwork, landscape and erosion control, base and subbase, minor concrete, and steel structures. None cleared the pre-set bar (5 points better on at least 50 validation prices) on 2023 bids, so no exception was made. By kind of item: lump sums 58.6% median miss (frozen model), items priced per unit 34.4%.

**Ranges:** the 80% range held the low bid on 79.0% of test prices (lump sums 77.3%, unit-priced 80.0%); by item family from 71.4% (steel structures, 21 prices) to 86.7% (concrete pavement, 45 prices). Typical width: 4.1x for unit-priced items, 12.6x for lump sums.

**Market context (208 test contracts)** ([notebook 06](../notebooks/06_market_context.ipynb)): the spread (low bid vs engineer's estimate) is missed by 15.7 points on average, and its 80% range held 76.9% of contracts but is about 50 points wide. The bidder count is missed by 1.33 bidders on average; within one bidder on 63.5%; its range held 81.7%. Without the plan-holder count, the bidder miss grows to 1.60.

**Document reading (one package, 89 gold facts)** ([notebook 07](../notebooks/07_document_extraction.ipynb)): the default run found 74.2% of the facts; 76.9% of its findings are correct; 86.4% cite a page that supports them; about 60 minutes on a Mac with 16 GB of memory. Weakest topics: traffic and closures (46% of facts found), payment terms (70%), hazardous materials (71%). The bid item list matched Caltrans' bid summary exactly (118 items).

**End to end:** on the sample package the draft total was 3% above the actual low bid; the engineer's estimate was 61% above it.

## Limitations and risks

- **Two districts, one era.** Tested on Districts 4 and 5 in 2024 to 2026, when low bids came in well under Caltrans' estimates. In another region or market, the margin over the engineer's estimate may shrink or reverse.
- **Single items are noisy.** A single item's price can miss by a lot even when the total is close; read the range and the comparable bids, not just the likely price. Lump sums and quantities far from an item's usual size are the least reliable.
- **Items outside the 100 modeled ones** are priced from medians of earlier bids, with no range; contract-specific items with no history fall back to family medians.
- **Escalation** follows a statewide index; local shocks (a material shortage, a single large project) are not captured.
- **Document reading is an aid, not a substitute.** About 1 finding in 4 needs correcting, and about a quarter of the facts an estimator needs were missed on the test package. The app always shows the quote and page so a finding can be checked in seconds. Only one bid package was evaluated.
- **Who labelled the evaluation.** The 89 gold facts, the judging and the checklist questions were written by Claude, the AI assistant that built BidLens, not by a human estimator. A human review is still open, and the improvement from the checklist may be somewhat optimistic.
- **Leakage controls.** Models see only what is known before bids open; the cost index uses only quarters published before the bid; the actual bids of a package are shown in the app only as a labelled check and never feed the draft.

## Ethical considerations

- Market-level analysis only: no contractor is singled out, and bidder identities are not stored in outputs or shown.
- Runs locally at no cost: bid documents never leave the user's computer. The optional hosted mode (off by default) would send document passages to the Claude API under the user's own key.
- Public data only, collected at a polite rate and within each source's conditions of use; the Caltrans site whose robots.txt disallows automated access is never scripted.

## Maintenance

- The pricing and market models are meant to be refreshed every quarter with the latest bids (`make pricing`, `uv run python -m bidlens.market.context`).
- Re-check the range calibration and the engineer's estimate comparison after each refresh; revisit the model choice if another method beats Kumo on recent validation bids by more than a point.
- Re-run the document evaluation when the local models change, and have a human estimator review the gold facts.

## Versions

Kumo Tabular `structured-data-models` 0.2.1 with weights `nvidia/Kumo-Tabular` v1.0.1 (small); qwen3:8b and llama3.1:8b through Ollama; XGBoost and LightGBM as pinned in `uv.lock`. Decisions behind every choice: the Decision log in `the project notes` (D-034 to D-070).
