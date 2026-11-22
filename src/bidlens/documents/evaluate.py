"""Step 3.5: score the local extraction runs against the hand-labeled gold facts.

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
    """Pick the default: higher F1; within 2 points, higher citation accuracy, then faster."""
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

How well each local model reads the bid documents for contract {contract} (step 3.5).
Both models ran on this machine through Ollama with the same prompts
and settings; no document left the machine and no paid service was used.

## Result

**Default model: {best["model"]}** (highest F1, the rule set before judging).

{chr(10).join(rows)}

- **Precision:** share of the model's findings that are true and on topic.
- **Recall:** share of the {len(gold)} gold facts found by at least one correct finding.
- **Citation accuracy:** share of findings whose cited page actually supports them. Every
  kept finding already quotes text that exists on its page; this checks that
  the quote backs up the statement.
- **Quotes rejected:** answers dropped automatically because the quoted text was not on
  the cited page.

Recall by topic (a gold fact counts as found whichever topic's answer found it):

{chr(10).join(trows)}

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


# ----------------------------------------------------------------- round 2

OUT2 = ROOT / "outputs" / "20_extraction_round2"
ROUND2 = {
    "local_qwen3-8b_v2": "qwen3:8b, checklist",
    "local_llama3.1-8b_v2": "llama3.1:8b, checklist",
    "patterns": "pattern rules only",
    "qwen_patterns": "qwen3:8b checklist + patterns",
    "combined": "combined: both models + patterns",
}
KEY = ["category", "statement", "evidence", "document", "page"]


def _key(df: pd.DataFrame) -> pd.Series:
    return df[KEY].astype(str).agg("\x1f".join, axis=1)


def _scored(items: list[dict]) -> pd.DataFrame:
    from bidlens.documents.extract import TABLES

    return pd.DataFrame([i for i in items if i["category"] not in TABLES])


def round2_runs(contract: str) -> dict[str, dict]:
    from bidlens.documents.extract import load, merge

    out = {name: load(contract, name) for name in ROUND2 if name not in ("qwen_patterns",)}
    out["qwen_patterns"] = merge(
        contract, [out["patterns"], out["local_qwen3-8b_v2"]], "qwen_patterns"
    )
    return out


def round1_verdicts(contract: str) -> pd.DataFrame:
    """Step 3.5 verdicts keyed by finding, for findings that come back unchanged."""
    sheet = pd.read_csv(OUT / "judging_sheet.csv", dtype=str).fillna("")
    return sheet.assign(key=_key(sheet))[["key", "verdict", "fact_ids", "citation_ok"]]


def blind2(contract: str) -> Path:
    from bidlens.documents.report import mask

    runs = round2_runs(contract)
    pool = pd.concat(
        [
            _scored(runs[n]["items"])
            for n in ("local_qwen3-8b_v2", "local_llama3.1-8b_v2", "patterns")
        ]
    )
    pool = mask(pool[[*KEY, "value"]]).assign(key=lambda d: _key(d)).drop_duplicates("key")
    old = round1_verdicts(contract).drop_duplicates("key")
    pool = pool.merge(old, on="key", how="left").fillna("")
    pool["from_step_3_5"] = (pool["verdict"] != "").map({True: "yes", False: ""})
    pool = pool.sample(frac=1, random_state=SEED).reset_index(drop=True)
    pool.insert(0, "blind_id", [f"y{n:03d}" for n in range(len(pool))])
    OUT2.mkdir(parents=True, exist_ok=True)
    path = OUT2 / "judging_sheet.csv"
    pool.drop(columns="key").to_csv(path, index=False)
    return path


def score2(contract: str) -> pd.DataFrame:
    from bidlens.documents.report import mask

    gold = pd.read_csv(OUT / "gold_facts.csv")
    sheet = pd.read_csv(OUT2 / "judging_sheet.csv", dtype=str).fillna("")
    if (sheet["verdict"] == "").any():
        raise SystemExit("round 2 judging sheet is incomplete")
    sheet = sheet.assign(key=_key(sheet)).set_index("key")
    out = []
    for name, res in round2_runs(contract).items():
        d = mask(_scored(res["items"])[KEY])
        d = d.assign(key=_key(d)).join(sheet[["verdict", "fact_ids", "citation_ok"]], on="key")
        if d["verdict"].isna().any():
            raise SystemExit(f"{name}: findings missing from the judging sheet")
        correct = d[d["verdict"] == "correct"]
        covered = {f for ids in correct["fact_ids"] for f in ids.split(";") if f}
        unknown = covered - set(gold["fact_id"])
        if unknown:
            raise SystemExit(f"unknown fact ids: {sorted(unknown)}")
        calls = pd.DataFrame(res["calls"])
        answers = len(res["rejected"]) + int(calls["returned"].sum())
        p, r = len(correct) / len(d), len(covered) / len(gold)
        row = {
            "run": name,
            "model": ROUND2[name],
            "items_kept": len(d),
            "correct": len(correct),
            "precision": p,
            "gold_facts_found": len(covered),
            "recall": r,
            "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "citation_accuracy": (d["citation_ok"] == "1").mean(),
            "answers_returned": answers,
            "quote_rejected": len(res["rejected"]),
            "quote_rejection_rate": len(res["rejected"]) / answers if answers else 0.0,
            "minutes": calls["seconds"].sum() / 60,
            "truncated_calls": int(
                calls.get("truncated", pd.Series(dtype=bool)).fillna(False).sum()
            ),
            "covered": ";".join(sorted(covered)),
        }
        for topic, g in gold.groupby("topic"):
            row[f"recall_{topic}"] = len(covered & set(g["fact_id"])) / len(g)
        out.append(row)
    return pd.DataFrame(out)


def write_report2(contract: str, m: pd.DataFrame) -> None:
    from bidlens.documents.report import mask

    OUT2.mkdir(parents=True, exist_ok=True)
    m.to_csv(OUT2 / "metrics.csv", index=False)
    old = pd.read_csv(OUT / "metrics.csv")
    gold = pd.read_csv(OUT / "gold_facts.csv")
    sheet = pd.read_csv(OUT2 / "judging_sheet.csv", dtype=str).fillna("")
    pct = lambda x: f"{100 * x:.1f}%"  # noqa: E731
    head = (
        "| Run | Findings | Precision | Gold facts found | Recall | F1 | Citation accuracy "
        "| Minutes |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    rows = [head]
    for r in old.itertuples():
        rows.append(
            f"| Step 3.5: {r.model}, open list | {r.items_kept} | {pct(r.precision)} | "
            f"{r.gold_facts_found} | {pct(r.recall)} | {pct(r.f1)} | "
            f"{pct(r.citation_accuracy)} | {r.minutes:.1f} |"
        )
    for r in m.itertuples():
        rows.append(
            f"| **{r.model}** | {r.items_kept} | {pct(r.precision)} | {r.gold_facts_found} | "
            f"{pct(r.recall)} | **{pct(r.f1)}** | {pct(r.citation_accuracy)} | {r.minutes:.1f} |"
        )
    topics = sorted(gold["topic"].unique())
    trow = ["| Topic | Gold facts | Step 3.5 qwen3 | " + " | ".join(m["model"]) + " |"]
    trow.append("| --- | ---: | ---: |" + " ---: |" * len(m))
    q1 = old[old["model"] == "qwen3:8b"].iloc[0]
    for t in topics:
        vals = " | ".join(pct(v) for v in m[f"recall_{t}"])
        trow.append(
            f"| {t} | {int((gold['topic'] == t).sum())} | {pct(q1[f'recall_{t}'])} | {vals} |"
        )
    best = m.sort_values("f1", ascending=False).iloc[0]
    qwen = m[m["run"] == "local_qwen3-8b_v2"].iloc[0]
    reused = int((sheet["from_step_3_5"] == "yes").sum())
    runs = round2_runs(contract)
    for name, res in runs.items():
        mask(_scored(res["items"])).to_csv(OUT2 / f"extracted_{name}.csv", index=False)
    tab = pd.DataFrame(runs["patterns"]["items"])
    hours = tab[tab["category"] == "closure_hours"]
    dmg = tab[tab["category"] == "closure_damages"]
    hours[["chunk_id", "page", "statement"]].to_csv(OUT2 / "closure_hours.csv", index=False)
    dmg[["chunk_id", "page", "statement", "evidence"]].to_csv(
        OUT2 / "closure_damages.csv", index=False
    )
    (OUT2 / "README.md").write_text(
        f"""# 20 Extraction, round 2

A second round of document extraction for contract {contract}, scored against the same
{len(gold)} gold facts and judging rules as step 3.5 (stage 19), whose results are kept
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
   table is read into `closure_damages.csv` ({len(dmg)} rows).
4. **Combined mode:** both models plus the pattern rules, merged, with duplicates
   removed (same quote in the same passage, or statements sharing 70% of their words).

## Result

{chr(10).join(rows)}

Best F1: **{best["model"]}**, {pct(best["f1"])}. The qwen3:8b checklist alone scores
{pct(qwen["f1"])}, against 61.5% in step 3.5.

Recall by topic (a gold fact counts as found whichever topic's answer found it):

{chr(10).join(trow)}

The closure tables (hours and late damages) are read by code and are not in the scored
pool, like the bid item quantities. They state gold fact T6 (late closure damages by route)
exactly and give the hours behind R1 and R13.

## How it was judged

Same rules as step 3.5. Every finding new in this round was pooled across runs, shuffled
and judged with the run hidden (`judging_sheet.csv`). {reused} findings came back word for
word from step 3.5 and kept their verdict (`from_step_3_5`). The gold facts and the
judging were done with an AI assistant, not a human estimator; so were
the checklist questions, so the checklist's gain may be somewhat optimistic. A human
review is still open.

## Files

- `metrics.csv`: every metric per run, including recall per topic and the gold facts found.
- `judging_sheet.csv`: every round 2 finding with its verdict.
- `extracted_<run>.csv`: the scored findings of each run.
- `closure_hours.csv`, `closure_damages.csv`: the tables read by code.

## How it was produced

`uv run python -m bidlens.documents.charts {contract}`, then
`uv run python -m bidlens.documents.extract {contract} --mode combined` (runs both models
one at a time, then the patterns, then merges), then
`uv run python -m bidlens.documents.evaluate {contract} blind2`, hand judging, and
`... evaluate {contract} score2`. Generated {date.today().isoformat()}.
""",
        encoding="utf-8",
    )
    from bidlens.outputs import write_index

    write_index()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    ap.add_argument("action", choices=["blind", "score", "blind2", "score2"])
    args = ap.parse_args(argv)
    if args.action == "blind":
        print(blind(args.contract))
        return 0
    if args.action == "blind2":
        print(blind2(args.contract))
        return 0
    if args.action == "score2":
        m = score2(args.contract)
        write_report2(args.contract, m)
        print(m.drop(columns="covered").T.to_string())
        return 0
    m = score(args.contract)
    best = pick(m)
    write_report(args.contract, m, best)
    print(m.T.to_string())
    print(f"default: {best['model']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
