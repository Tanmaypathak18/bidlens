# Changelog

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
