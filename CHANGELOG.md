# Changelog

## v1.1.0 (25 November 2026): live evaluation

BidLens now works as a live tool, not only a report on one sample job.

- **Evaluate a bid** (the new first page). Pick any of about 200 Caltrans jobs bid in 2024 to 2026 (search by contract number, district, county or work type, or click one of ten example jobs), or upload your own bid item list as CSV or Excel. Press Evaluate and watch five steps run for real: load the items, price each item, build the price ranges, the market view and the risk summary, each showing its numbers and a chart as it finishes.
- **A dashboard on every result:** the draft total, the engineer's estimate, the actual low bid when the job has been bid, the expected number of bidders, the items with the widest ranges, the top 10 items by dollars, and the number of risks when the bid documents are available.
- **Check my bid.** If the uploaded list has unit prices, each one is marked inside, above or below the BidLens range, with a chart, and the items that move the total most are ranked. For past jobs, the same check runs on the actual low bid.
- **Look at one item:** its price history, its range and its 10 most comparable earlier bids, each linked to its Caltrans page.
- **Track record page:** all 178 test jobs on one chart (BidLens and the engineer's estimate against the actual low bid), plus the typical gap between the second-lowest and the lowest bid (6.4%) as a yardstick.
- **Which model prices it.** Kumo Tabular, the production model, everywhere. The listed past jobs open instantly with the prices computed for the track record, so their totals match it to the dollar; an uploaded list is priced live (about 15 seconds on a laptop, 1 to 3 minutes on the free hosted demo). LightGBM is kept as a lighter fallback where Kumo can't be installed; on the same 178 jobs it was closer than the engineer's estimate on 52% of them, against 58% for Kumo (`outputs/22_live_evaluation/`).
- The live engine runs on a compact bundle of public Caltrans low bids committed in `data/sample/engine/` (about 1 MB, no bidder names), so a fresh clone and the hosted demo run the same computation.
- The sample job's pages (Overview, Package, Prices, Market, Export) are unchanged, under "Sample job with bid documents".

## v1.0.0 (21 November 2026)

The first release of BidLens: an AI estimating copilot for heavy civil bids, built on public Caltrans bid data. It takes an estimator from a new bid package to a draft estimate they can review.

**Live demo:** https://huggingface.co/spaces/tanmaypathak4/bidlens (a real Caltrans package, already bid, so the draft can be checked against the actual result).

### What you can do with it

- **Read the bid package.** BidLens reads the special provisions, addenda and other bid documents and lists what an estimator prices or plans around: working days and damages, lane closure hours, environmental limits, hazardous materials, bid requirements, submittals and payment terms. Every finding shows its quote and links to its page. A summary that doesn't match its own quote is shown as the quote itself.
- **Price every bid item.** Each item gets a low, likely and high unit price from years of real Caltrans low bids, adjusted to bid-day dollars with Caltrans' own construction cost index, plus the 10 most similar earlier bids, each linked to its Caltrans page.
- **See the market.** How many contractors are likely to bid, and where the low bid is likely to land against the engineer's estimate.
- **Export a draft estimate.** An Excel workbook with live formulas, a column for the estimator's own prices, the comparable bids, a risk register with page citations, and the lane closure charts.

### How well it works

All results were measured on bids the models had never seen (2024 to 2026).

- **Whole contracts:** on 178 test contracts, the BidLens total landed closer to the winning bid than Caltrans' engineer's estimate on 57.9% of them (typical miss 18.4% against 21.2%).
- **Single items:** a typical miss of 38% per item, close to the 27.5% gap between the two lowest bidders on the same item. The low-to-high range held the actual low bid 79% of the time (target 80%).
- **Market:** the expected low bid against the engineer's estimate was off by about 16 points, and the bidder count by about 1.3 bidders.
- **Documents:** on a real package, the reader found about three quarters of the facts an estimator needs, and about 1 in 4 of its findings needs correcting. The gold facts and the judging were done with an AI assistant, not a human estimator; a human review is still open.
- **Sample job:** for contract 04-0W0504, the draft was $14.54M against an actual low bid of $14.09M (+3%); the engineer's estimate was $22.72M.

### What's included

- Data collection and checks for Caltrans Districts 4 and 5, bids opened 2018 to 2026 (848 contract openings, 72,113 bids).
- Pricing models: NVIDIA Kumo Tabular (used), compared side by side with XGBoost, LightGBM and a historical median.
- A document reader that runs fully on your own computer with two free local models (qwen3:8b and llama3.1:8b through Ollama) plus plain pattern rules. No paid service is needed, and documents never leave the machine.
- A Streamlit app with five pages (Home, Package, Prices, Market, Export) that works on a phone.
- Seven notebooks that explain the analysis step by step, a numbered `outputs/` folder for every stage, and a model card.
- A committed sample package, so a fresh copy of the repository runs the app with three commands.

### Known limits

- Built and tested on two Caltrans districts only.
- Item prices are noisy and ranges are wide; contract totals are much more reliable than single items.
- Items outside the 100 modeled items are priced from earlier medians, with no range.
- Document findings are an aid to review, not a substitute for reading the contract.
- The public demo shows saved results for one sample package; it does not read new documents.
