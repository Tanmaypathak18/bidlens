# 19 Extraction evaluation

How well each local model reads the bid documents for contract 04-0W0504 (step 3.5).
Both models ran on this machine through Ollama with the same prompts
and settings; no document left the machine and no paid service was used.

## Result

**Default model: qwen3:8b** (highest F1, the rule set before judging).

| Model | Items | Precision | Gold facts found | Recall | F1 | Citation accuracy | Quotes rejected | Minutes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| llama3.1:8b | 97 | 64.9% | 34 of 89 | 38.2% | 48.1% | 87.6% | 72 of 303 | 44.7 |
| qwen3:8b | 155 | 69.7% | 49 of 89 | 55.1% | 61.5% | 80.6% | 68 of 309 | 58.6 |

- **Precision:** share of the model's findings that are true and on topic.
- **Recall:** share of the 89 gold facts found by at least one correct finding.
- **Citation accuracy:** share of findings whose cited page actually supports them. Every
  kept finding already quotes text that exists on its page; this checks that
  the quote backs up the statement.
- **Quotes rejected:** answers dropped automatically because the quoted text was not on
  the cited page.

Recall by topic (a gold fact counts as found whichever topic's answer found it):

| Topic | Gold facts | llama3.1:8b recall | qwen3:8b recall |
| --- | ---: | ---: | ---: |
| bid_requirements | 10 | 80.0% | 60.0% |
| environmental | 9 | 0.0% | 88.9% |
| geotechnical | 3 | 66.7% | 33.3% |
| hazardous | 14 | 35.7% | 50.0% |
| payment | 10 | 30.0% | 50.0% |
| scope | 5 | 40.0% | 60.0% |
| submittals | 12 | 41.7% | 50.0% |
| time_damages | 10 | 70.0% | 70.0% |
| traffic | 13 | 0.0% | 23.1% |
| utilities | 3 | 66.7% | 100.0% |

## Who labeled, and how

The gold facts were written **with an AI assistant, not a human
estimator**. They were labeled from the passages each topic retrieves (what the models
see) and committed to git before either model's output was opened. Every finding from both
models was then pooled, shuffled and judged with the model name hidden
(`judging_sheet.csv`). A human estimator's review of `gold_facts.csv` and of the
judging is still open (listed for final review).

Judging rules, applied to every finding the same way:

- A finding is **correct** if its statement is true according to its cited page and it
  belongs to its topic. Quotes are capped at 300 characters, so a quote can stop
  before the words that back the statement; the page decides.
- A true finding filed under the wrong topic is correct if it states a gold fact of
  another topic (the fact was found), and wrong otherwise (off-topic noise, such as rows
  copied from the list of other nearby contracts).
- A statement that drops a condition or changes a number is wrong even if its quote is
  real.

Limits:

- One contract only, so the numbers are indicative, not precise.
- Recall is measured given retrieval: a fact the search never shows the model is not
  counted. A check of must-have facts found that the special provisions never state a
  per-day liquidated damages amount for the contract, so no model can report one.
- The ramp and connector closure charts lose their hour columns in the PDF text layer,
  so the allowed closure hours can't be read reliably by either model (a parsing limit,
  stage 17).

## Files

- `gold_facts.csv`: the 89 hand-labeled facts with their pages.
- `judging_sheet.csv`: every finding, blind, with its verdict, the gold facts it covers
  and whether its citation supports it.
- `metrics.csv`: all metrics, including recall and precision per topic.

## How it was produced

`uv run python -m bidlens.documents.evaluate 04-0W0504 blind`, hand judging, then
`uv run python -m bidlens.documents.evaluate 04-0W0504 score`. Code in
`src/bidlens/documents/evaluate.py`. Generated 2026-11-20.
