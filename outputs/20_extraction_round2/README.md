# 20 Extraction, round 2

A second round of document extraction for contract 04-0W0504, scored against the same
89 gold facts and judging rules as step 3.5 (stage 19), whose results are kept
unchanged for comparison. Everything ran on this machine through Ollama; no document left
it and no paid service was used.

## What changed

1. **Closure charts read by code.** The 78 lane, ramp and connector closure charts
   lose their empty cells in the PDF text, so the hour of each symbol was lost. BidLens now
   puts every symbol back in its hour column from its position on the page (no model).
   Two chart pages were checked against their images cell by cell. Result:
   `closure_hours.csv`, one row per chart, and a one-line summary per chart for the model
   in place of the broken grid.
2. **A checklist of estimator questions per topic** instead of "list the facts":
   6 to 9 questions per topic, written to apply to any Caltrans contract.
3. **Pattern rules for simple facts:** working days, start window, engineer's
   estimate, bid opening, prebid meeting (the addendum's date wins), price-firm dates and
   dollar amounts tied to a rate, penalty, withhold or limit. The late closure damages
   table is read into `closure_damages.csv` (31 rows).
4. **Combined mode:** both models plus the pattern rules, merged, with duplicates
   removed (same quote in the same passage, or statements sharing 70% of their words).

## Result

| Run | Findings | Precision | Gold facts found | Recall | F1 | Citation accuracy | Minutes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Step 3.5: llama3.1:8b, open list | 97 | 64.9% | 34 | 38.2% | 48.1% | 87.6% | 44.7 |
| Step 3.5: qwen3:8b, open list | 155 | 69.7% | 49 | 55.1% | 61.5% | 80.6% | 58.6 |
| **qwen3:8b, checklist** | 98 | 73.5% | 57 | 64.0% | **68.4%** | 80.6% | 32.3 |
| **llama3.1:8b, checklist** | 83 | 78.3% | 46 | 51.7% | **62.3%** | 88.0% | 27.2 |
| **pattern rules only** | 19 | 100.0% | 11 | 12.4% | **22.0%** | 100.0% | 0.0 |
| **combined: both models + patterns** | 147 | 76.9% | 66 | 74.2% | **75.5%** | 86.4% | 59.5 |
| **qwen3:8b checklist + patterns** | 106 | 79.2% | 59 | 66.3% | **72.2%** | 85.8% | 32.3 |

Best F1: **combined: both models + patterns**, 75.5%. The qwen3:8b checklist alone scores
68.4%, against 61.5% in step 3.5.

Recall by topic (a gold fact counts as found whichever topic's answer found it):

| Topic | Gold facts | Step 3.5 qwen3 | qwen3:8b, checklist | llama3.1:8b, checklist | pattern rules only | combined: both models + patterns | qwen3:8b checklist + patterns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bid_requirements | 10 | 60.0% | 90.0% | 60.0% | 30.0% | 90.0% | 90.0% |
| environmental | 9 | 88.9% | 77.8% | 55.6% | 0.0% | 88.9% | 77.8% |
| geotechnical | 3 | 33.3% | 66.7% | 66.7% | 33.3% | 66.7% | 66.7% |
| hazardous | 14 | 50.0% | 50.0% | 57.1% | 0.0% | 71.4% | 50.0% |
| payment | 10 | 50.0% | 50.0% | 50.0% | 20.0% | 70.0% | 60.0% |
| scope | 5 | 60.0% | 80.0% | 60.0% | 20.0% | 80.0% | 80.0% |
| submittals | 12 | 50.0% | 75.0% | 41.7% | 0.0% | 75.0% | 75.0% |
| time_damages | 10 | 70.0% | 60.0% | 60.0% | 40.0% | 90.0% | 70.0% |
| traffic | 13 | 23.1% | 46.2% | 30.8% | 0.0% | 46.2% | 46.2% |
| utilities | 3 | 100.0% | 66.7% | 66.7% | 0.0% | 66.7% | 66.7% |

The closure tables (hours and late damages) are read by code and are not in the scored
pool, like the bid item quantities. They state gold fact T6 (late closure damages by route)
exactly and give the hours behind R1 and R13.

## How it was judged

Same rules as step 3.5. Every finding new in this round was pooled across runs, shuffled
and judged with the run hidden (`judging_sheet.csv`). 13 findings came back word for
word from step 3.5 and kept their verdict (`from_step_3_5`). The gold facts and the
judging are by Claude, the AI assistant building BidLens, not a human estimator; so are
the checklist questions, so the checklist's gain may be somewhat optimistic. A human
review is still open.

## Files

- `metrics.csv`: every metric per run, including recall per topic and the gold facts found.
- `judging_sheet.csv`: every round 2 finding with its verdict.
- `extracted_<run>.csv`: the scored findings of each run.
- `closure_hours.csv`, `closure_damages.csv`: the tables read by code.

## How it was produced

`uv run python -m bidlens.documents.charts 04-0W0504`, then
`uv run python -m bidlens.documents.extract 04-0W0504 --mode combined` (runs both models
one at a time, then the patterns, then merges), then
`uv run python -m bidlens.documents.evaluate 04-0W0504 blind2`, hand judging, and
`... evaluate 04-0W0504 score2`. Generated 2026-11-20.

## Charts from the notebook

`notebooks/07_document_extraction.ipynb` explains this stage and saved these charts here: `nb_extraction_runs.png`, `nb_recall_by_topic.png`.
