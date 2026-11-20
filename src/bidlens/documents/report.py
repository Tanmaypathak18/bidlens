"""Write outputs/18_extraction from whichever extraction runs exist (steps 3.3 and 3.4)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(".")
CACHE = ROOT / "data" / "interim" / "docs"
OUT = ROOT / "outputs" / "18_extraction"


def label(mode: str, model: str) -> str:
    if mode == "hosted":
        return f"Hosted (optional Claude API): {model}"
    return f"Local (Ollama, on this machine): {model}"


def write_extraction_report(contract: str) -> None:
    runs = {
        p.stem.removeprefix("extraction_"): json.loads(p.read_text())
        for p in sorted((CACHE / contract).glob("extraction_*.json"))
    }
    if not runs:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    sections = []
    for mode, res in runs.items():
        items = pd.DataFrame(res["items"])
        items.to_csv(OUT / f"extracted_{mode}.csv", index=False)
        pd.DataFrame(res["rejected"]).to_csv(OUT / f"rejected_{mode}.csv", index=False)
        cited = items["page"].notna().all() and items["file"].notna().all()
        calls = pd.DataFrame(res["calls"])
        model = res.get("model") or (calls["model"].dropna().iloc[0] if "model" in calls else "")
        secs = calls["seconds"].sum()
        lines = [
            "| Category | Items kept | Returned by the model | Seconds |",
            "| --- | ---: | ---: | ---: |",
        ]
        for r in calls.itertuples():
            lines.append(f"| {r.category} | {r.kept} | {r.returned} | {r.seconds} |")
        sample = items[items["category"] != "quantities"].groupby("category").head(2)
        ex = ["| Topic | Finding | Value | Source |", "| --- | --- | --- | --- |"]
        for r in sample.itertuples():
            src = f"{r.document}, page {r.page}" + (f" ({r.section})" if r.section else "")
            ex.append(f"| {r.category_name} | {r.statement} | {r.value} | {src} |")
        sections.append(f"""
## {label(res.get("mode", mode).split("_")[0], model)}

Run time {secs / 60:.1f} minutes for {len(calls)} topics.
{len(items):,} items, of which {int((items["category"] == "quantities").sum())} are bid items
with quantities read straight from the bid item list. Every item cites a document and page:
**{"yes" if cited else "no"}**. The model's answers that quoted text not found in the cited
passage were dropped: {len(res["rejected"])}.

{chr(10).join(lines)}

Examples (two per topic):

{chr(10).join(ex)}
""")
    body = f"""
What BidLens reads out of the bid documents for contract {contract}, with the page each
finding comes from (steps 3.3 and 3.4).

## How it works (decision D-052)

For each topic an estimator cares about (scope, time and damages, lane closures,
environmental limits, hazardous materials, site conditions, utilities, bid requirements,
submittals and payment terms), BidLens finds the most relevant passages in the special
provisions, addenda and information handout, and asks a language model to list the facts
on that topic. The model must copy a short exact quote for each one. BidLens then checks
that the quote really is in the passage and takes the document, page and section from
the passage itself, so a citation can never be made up. Bid items and quantities are not
read by the model at all: they come from the bid item list (stage 17).
{"".join(sections)}
## Files

- `extracted_<mode>.csv`: every finding with its quote, document, page and section.
- `rejected_<mode>.csv`: model answers dropped because their quote was not in the passage.

## How it was produced

`uv run python -m bidlens.documents.extract {contract} --model <ollama model>`, once per
local model, one model loaded at a time (D-053, D-054). Everything runs on this machine at
no cost; the documents never leave it. The optional `--mode hosted` (Claude API, needs the
user's own key) is not used here. File names use the run's name, e.g. `local_qwen3-8b`.
Code in `src/bidlens/documents/extract.py`. Generated {date.today().isoformat()}.
"""
    (OUT / "README.md").write_text(
        "# 18 Extraction with citations\n\n" + body.strip() + "\n", encoding="utf-8"
    )
    from bidlens.outputs import write_index

    write_index()
