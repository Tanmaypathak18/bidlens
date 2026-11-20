"""Step 3.5: score the local extraction runs against the hand-labeled gold facts (D-055).

Usage:
    uv run python -m bidlens.documents.evaluate 04-0W0504 blind   # write the blind judging sheet
    uv run python -m bidlens.documents.evaluate 04-0W0504 score   # score and write the report

`blind` pools every kept item from every local run, shuffles them with a fixed seed and
writes them without the model name to `judging_sheet.csv` (plus a private key file in the
interim cache). The labeler fills in `verdict` (correct / wrong), `fact_ids` (gold facts
the item covers, separated by `;`) and `citation_ok` (1 if the cited page supports the
statement). `score` joins the sheet back to the runs and computes precision, recall,
F1 and citation accuracy per model.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(".")
CACHE = ROOT / "data" / "interim" / "docs"
OUT = ROOT / "outputs" / "19_extraction_evaluation"
SEED = 2026


def runs(contract: str) -> dict[str, dict]:
    return {
        p.stem.removeprefix("extraction_"): json.loads(p.read_text())
        for p in sorted((CACHE / contract).glob("extraction_local_*.json"))
    }


def blind(contract: str) -> Path:
    rows = []
    for run, res in runs(contract).items():
        for i, it in enumerate(res["items"]):
            if it["category"] == "quantities":
                continue  # read from the bid item list, not the model
            rows.append({"run": run, "item": i, **it})
    random.Random(SEED).shuffle(rows)
    df = pd.DataFrame(rows)
    df.insert(0, "blind_id", [f"x{n:03d}" for n in range(len(df))])
    df[["blind_id", "run", "item"]].to_csv(CACHE / contract / "judging_key.csv", index=False)
    from bidlens.documents.report import mask

    sheet = mask(df[["blind_id", "category", "statement", "value", "evidence", "document", "page"]])
    sheet = sheet.assign(verdict="", fact_ids="", citation_ok="")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "judging_sheet.csv"
    sheet.to_csv(path, index=False)
    return path


def score(contract: str) -> pd.DataFrame:
    gold = pd.read_csv(OUT / "gold_facts.csv")
    sheet = pd.read_csv(OUT / "judging_sheet.csv", dtype=str).fillna("")
    key = pd.read_csv(CACHE / contract / "judging_key.csv")
    j = sheet.merge(key, on="blind_id")
    if (j["verdict"] == "").any():
        raise SystemExit("judging sheet is incomplete")
    out = []
    for run, res in runs(contract).items():
        d = j[j["run"] == run]
        correct = d[d["verdict"] == "correct"]
        covered = {f for ids in correct["fact_ids"] for f in ids.split(";") if f}
        unknown = covered - set(gold["fact_id"])
        if unknown:
            raise SystemExit(f"unknown fact ids: {sorted(unknown)}")
        calls = pd.DataFrame(res["calls"])
        answers = len(res["rejected"]) + int(calls["returned"].sum())
        p = len(correct) / len(d) if len(d) else 0.0
        r = len(covered) / len(gold)
        out.append(
            {
                "run": run,
                "model": res.get("model", run),
                "items_kept": len(d),
                "correct": len(correct),
                "precision": p,
                "gold_facts_found": len(covered),
                "recall": r,
                "f1": 2 * p * r / (p + r) if p + r else 0.0,
                "citation_accuracy": (d["citation_ok"] == "1").mean() if len(d) else 0.0,
                "answers_returned": answers,
                "quote_rejected": len(res["rejected"]),
                "quote_rejection_rate": len(res["rejected"]) / answers if answers else 0.0,
                "minutes": calls["seconds"].sum() / 60,
            }
        )
        for topic, g in gold.groupby("topic"):
            dt = d[d["category"] == topic]
            out[-1][f"recall_{topic}"] = len(covered & set(g["fact_id"])) / len(g)
            out[-1][f"precision_{topic}"] = (
                (dt["verdict"] == "correct").mean() if len(dt) else float("nan")
            )
    return pd.DataFrame(out)


def pick(m: pd.DataFrame) -> pd.Series:
    """D-055: higher F1; within 2 points, higher citation accuracy, then faster."""
    m = m.sort_values("f1", ascending=False).reset_index(drop=True)
    if len(m) > 1 and m.at[0, "f1"] - m.at[1, "f1"] < 0.02:
        a, b = m.iloc[0], m.iloc[1]
        if abs(a["citation_accuracy"] - b["citation_accuracy"]) >= 0.02:
            return a if a["citation_accuracy"] > b["citation_accuracy"] else b
        return a if a["minutes"] <= b["minutes"] else b
    return m.iloc[0]


def write_report(contract: str, m: pd.DataFrame, best: pd.Series) -> None:
    m.to_csv(OUT / "metrics.csv", index=False)
    pct = lambda x: f"{100 * x:.1f}%"  # noqa: E731
    rows = [
        "| Model | Items | Precision | Gold facts found | Recall | F1 | Citation accuracy "
        "| Quotes rejected | Minutes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    gold = pd.read_csv(OUT / "gold_facts.csv")
    for r in m.itertuples():
        rows.append(
            f"| {r.model} | {r.items_kept} | {pct(r.precision)} | {r.gold_facts_found} of "
            f"{len(gold)} | {pct(r.recall)} | {pct(r.f1)} | {pct(r.citation_accuracy)} | "
            f"{r.quote_rejected} of {r.answers_returned} | {r.minutes:.1f} |"
        )
    topics = sorted(gold["topic"].unique())
    trows = ["| Topic | Gold facts | " + " | ".join(f"{x} recall" for x in m["model"]) + " |"]
    trows.append("| --- | ---: |" + " ---: |" * len(m))
    for t in topics:
        vals = " | ".join(pct(v) for v in m[f"recall_{t}"])
        trows.append(f"| {t} | {int((gold['topic'] == t).sum())} | {vals} |")
    (OUT / "README.md").write_text(
        f"""# 19 Extraction evaluation

How well each local model reads the bid documents for contract {contract} (step 3.5,
decision D-055). Both models ran on this machine through Ollama with the same prompts
and settings (D-054); no document left the machine and no paid service was used.

## Result

**Default model: {best["model"]}** (highest F1; rule in D-055).

{chr(10).join(rows)}

- **Precision:** share of the model's findings that are true and on topic.
- **Recall:** share of the {len(gold)} gold facts found by at least one correct finding.
- **Citation accuracy:** share of findings whose cited page actually supports them. Every
  kept finding already quotes text that exists on its page (D-052); this checks that
  the quote backs up the statement.
- **Quotes rejected:** answers dropped automatically because the quoted text was not on
  the cited page.

Recall by topic (a gold fact counts as found whichever topic's answer found it):

{chr(10).join(trows)}

## Who labeled, and how

The gold facts were written by **Claude, the AI assistant building BidLens, not by a human
estimator**. They were labeled from the passages each topic retrieves (what the models
see) and committed to git before either model's output was opened. Every finding from both
models was then pooled, shuffled and judged with the model name hidden
(`judging_sheet.csv`). A human estimator's review of `gold_facts.csv` and of the
judging is still open (listed for final review).

Judging rules, applied to every finding the same way:

- A finding is **correct** if its statement is true according to its cited page and it
  belongs to its topic. Quotes are capped at 300 characters (D-058), so a quote can stop
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

- `gold_facts.csv`: the {len(gold)} hand-labeled facts with their pages.
- `judging_sheet.csv`: every finding, blind, with its verdict, the gold facts it covers
  and whether its citation supports it.
- `metrics.csv`: all metrics, including recall and precision per topic.

## How it was produced

`uv run python -m bidlens.documents.evaluate {contract} blind`, hand judging, then
`uv run python -m bidlens.documents.evaluate {contract} score`. Code in
`src/bidlens/documents/evaluate.py`. Generated {date.today().isoformat()}.
""",
        encoding="utf-8",
    )
    from bidlens.outputs import write_index

    write_index()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    ap.add_argument("action", choices=["blind", "score"])
    args = ap.parse_args(argv)
    if args.action == "blind":
        print(blind(args.contract))
        return 0
    m = score(args.contract)
    best = pick(m)
    write_report(args.contract, m, best)
    print(m.T.to_string())
    print(f"default: {best['model']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
