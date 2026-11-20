"""Write outputs/18_extraction from whichever extraction runs exist (steps 3.3 and 3.4)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(".")
CACHE = ROOT / "data" / "interim" / "docs"
OUT = ROOT / "outputs" / "18_extraction"
MODES = {"hosted": "Hosted (Claude API)", "local": "Local (Ollama, on this machine)"}


def write_extraction_report(contract: str) -> None:
    runs = {
        m: json.loads(p.read_text())
        for m in MODES
        if (p := CACHE / contract / f"extraction_{m}.json").exists()
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
        model = calls["model"].dropna().iloc[0] if "model" in calls else ""
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
## {MODES[mode]}{f": {model}" if model else ""}

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

`uv run python -m bidlens.documents.extract {contract} --mode hosted` (or `--mode local`).
Code in `src/bidlens/documents/extract.py`. Generated {date.today().isoformat()}.
"""
    (OUT / "README.md").write_text(
        "# 18 Extraction with citations\n\n" + body.strip() + "\n", encoding="utf-8"
    )
    from bidlens.outputs import write_index

    write_index()
