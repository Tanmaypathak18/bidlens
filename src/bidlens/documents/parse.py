"""Step 3.2: parse the bid package into pages, sections, chunks and the bid item list.

Usage:
    uv run python -m bidlens.documents.parse 04-0W0504   # writes outputs/17_document_parsing

Page text is cached in data/interim/docs/<contract>/pages.parquet; sections and chunks are
written next to it. Every chunk sits inside one page and one section, so anything later
extracted from it cites an exact page.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(".")
PACKAGES = ROOT / "data" / "raw" / "bid_package"
CACHE = ROOT / "data" / "interim" / "docs"
OUT = ROOT / "outputs" / "17_document_parsing"
CHUNK_CHARS = 1200

SEPARATOR = re.compile(r"^\^{10,}$")
FOOTER = re.compile(r"^Contract No\. \d{2}-[0-9A-Z]{6}$")
PRINTED_PAGE = re.compile(r"^\d{1,4}$")
DIVISION_HEADING = re.compile(r"^(\d{1,2}) ([A-Z][A-Z ,&'/()-]{3,})$")
DIVISION_LINE = re.compile(r"^DIVISION [IVXL]+ [A-Z ,&'-]+$")
FRONT_HEADINGS = ("NOTICE TO BIDDERS", "BID ITEM LIST", "SPECIAL PROVISIONS")
SECTION_REF = re.compile(r"\bsections? (\d{1,2}-\d+\.\d+[A-Z]?\d*)")
ITEM_ROW = re.compile(r"^(\d{4}) (\d{6}) (.*)$")
ITEM_TAIL = re.compile(
    r"^(?P<desc>.*?) (?P<unit>[A-Z]{2,5}) (?P<qty>LUMP SUM|[\d,]+(?:\.\d+)?)(?: .*)?$"
)
DELETED = "ITEM DELETED PER ADDENDUM"


# ----------------------------------------------------------------- documents


def documents(contract: str) -> list[dict]:
    """The files BidLens reads, from the manifest (step 3.1)."""
    m = pd.read_csv(ROOT / "data" / "bid_package_manifest.csv")
    m = m[(m["contract"] == contract) & m["read_by_bidlens"]]
    docs = []
    for r in m.itertuples():
        stem = r.file.split(".")[0].removeprefix(contract)
        kind = (
            "special_provisions"
            if stem == "sp"
            else "addendum"
            if stem.startswith("ad")
            else "information_handout"
            if stem == "IH"
            else "forms_for_bid"
        )
        docs.append(
            {
                "file": r.file,
                "kind": kind,
                "title": r.kind,
                "order": int(stem[2:]) if kind == "addendum" else 0,
            }
        )
    return docs


def extract_pages(contract: str, refresh: bool = False) -> pd.DataFrame:
    """Text of every page of every document read, cached."""
    path = CACHE / contract / "pages.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    import pdfplumber

    rows = []
    for d in documents(contract):
        with pdfplumber.open(PACKAGES / contract / d["file"]) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                rows.append(
                    {
                        "file": d["file"],
                        "kind": d["kind"],
                        "title": d["title"],
                        "page": i,
                        "text": page.extract_text() or "",
                    }
                )
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


# ----------------------------------------------------------------- sections and chunks


@dataclass
class Line:
    file: str
    kind: str
    title: str
    page: int
    printed_page: str
    section: str
    subsection: str
    text: str


def page_lines(text: str) -> tuple[list[str], str]:
    """Body lines of a page without the footer, and the printed page number."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    printed = ""
    if lines and PRINTED_PAGE.match(lines[-1]):
        printed = lines.pop()
    lines = [ln for ln in lines if not FOOTER.match(ln)]
    return lines, printed


def label_lines(pages: pd.DataFrame) -> list[Line]:
    """Every body line with its document, page, section and most recent section number."""
    out: list[Line] = []
    for (file, kind, title), doc in pages.groupby(["file", "kind", "title"], sort=False):
        section = title if kind != "special_provisions" else "Cover And Contents"
        subsection, after_sep = "", False
        for r in doc.sort_values("page").itertuples():
            lines, printed = page_lines(r.text)
            for pos, ln in enumerate(lines):
                if SEPARATOR.match(ln):
                    after_sep = True
                    continue
                if kind == "special_provisions":
                    # Front-matter headings start a page; the cover's title line does not.
                    if ln in FRONT_HEADINGS and pos < 2 and r.page > 1:
                        section, subsection = ln.title(), ""
                    elif after_sep and DIVISION_LINE.match(ln):
                        continue  # "DIVISION I GENERAL PROVISIONS" precedes the heading
                    elif after_sep and (m := DIVISION_HEADING.match(ln)):
                        section, subsection = f"{m.group(1)} {m.group(2).title()}", ""
                    after_sep = False
                    refs = SECTION_REF.findall(ln)
                    if refs:
                        subsection = refs[-1]
                out.append(Line(file, kind, title, r.page, printed, section, subsection, ln))
    return out


def chunk(lines: list[Line], max_chars: int = CHUNK_CHARS) -> pd.DataFrame:
    """Group consecutive lines into chunks within one page and one section."""
    rows, buf, n = [], [], {}

    def flush():
        if not buf:
            return
        first = buf[0]
        k = (first.file, first.page)
        n[k] = n.get(k, 0) + 1
        rows.append(
            {
                "chunk_id": f"{first.file}:p{first.page}:c{n[k]}",
                "file": first.file,
                "kind": first.kind,
                "title": first.title,
                "page": first.page,
                "printed_page": first.printed_page,
                "section": first.section,
                "subsection": buf[-1].subsection or first.subsection,
                "text": "\n".join(x.text for x in buf),
            }
        )
        buf.clear()

    for ln in lines:
        if buf and (
            ln.file != buf[0].file
            or ln.page != buf[0].page
            or ln.section != buf[0].section
            or sum(len(x.text) + 1 for x in buf) + len(ln.text) > max_chars
        ):
            flush()
        buf.append(ln)
    flush()
    return pd.DataFrame(rows)


# ----------------------------------------------------------------- bid item list


def parse_item_rows(lines: list[str]) -> list[dict]:
    """Bid item rows from bid item list lines; continuation lines extend the description."""
    items: list[dict] = []
    for ln in lines:
        m = ITEM_ROW.match(ln)
        if m:
            no, code, rest = m.groups()
            if rest.strip() == DELETED:
                items.append({"item_no": no, "item_code": code, "deleted": True})
                continue
            t = ITEM_TAIL.match(rest)
            if not t:
                items.append(
                    {
                        "item_no": no,
                        "item_code": code,
                        "description": rest,
                        "unit": None,
                        "quantity": None,
                        "deleted": False,
                    }
                )
                continue
            qty = t["qty"]
            items.append(
                {
                    "item_no": no,
                    "item_code": code,
                    "description": t["desc"].strip(),
                    "unit": t["unit"],
                    "quantity": None if qty == "LUMP SUM" else float(qty.replace(",", "")),
                    "deleted": False,
                }
            )
        elif (
            items
            and not items[-1]["deleted"]
            and ln.isupper()
            and "PER ADDENDUM" not in ln
            and not ln.startswith(("ITEM ", "BID ITEM"))
            and "Item Code" not in ln
        ):
            items[-1]["description"] += " " + ln
    for it in items:
        if not it["deleted"]:
            it["final_pay"] = it["description"].startswith("(F) - ")
            it["description"] = it["description"].removeprefix("(F) - ")
    return items


def bid_item_list(lines: list[Line]) -> tuple[pd.DataFrame, list[dict]]:
    """The bid item list from the special provisions, with every addendum applied."""
    sp = [x for x in lines if x.kind == "special_provisions" and x.section == "Bid Item List"]
    base = {
        it["item_no"]: {**it, "source": f"{sp[0].file} p{sp[0].page}", "changed_by": ""}
        for it in parse_item_rows([x.text for x in sp])
    }
    for it in base.values():  # each row cites its own page
        it["source"] = next(
            f"{x.file} p{x.page}"
            for x in sp
            if x.text.startswith(f"{it['item_no']} {it['item_code']}")
        )
    changes = []
    add = [x for x in lines if x.kind == "addendum"]
    for file in sorted({x.file for x in add}):
        doc = [x for x in add if x.file == file]
        pages = sorted({x.page for x in doc if x.text.startswith("BID ITEM LIST")})
        for p in pages:
            rows = parse_item_rows([x.text for x in doc if x.page == p])
            for it in rows:
                key = it["item_no"]
                if it["deleted"]:
                    old = base.pop(key, None)
                    changes.append(
                        {
                            "addendum": file,
                            "page": p,
                            "item_no": key,
                            "change": "deleted",
                            "was": f"{old['item_code']} {old['description']}" if old else "",
                        }
                    )
                else:
                    changes.append(
                        {
                            "addendum": file,
                            "page": p,
                            "item_no": key,
                            "change": "replaced" if key in base else "added",
                            "was": "",
                            "now": f"{it['item_code']} {it['description']}",
                        }
                    )
                    base[key] = {**it, "source": f"{file} p{p}", "changed_by": file}
    df = pd.DataFrame(sorted(base.values(), key=lambda r: r["item_no"]))
    return df.drop(columns=["deleted"]), changes


def check_against_summary(items: pd.DataFrame, contract: str) -> dict:
    """Compare the parsed list with the bid summary's item lines (codes, units, quantities)."""
    p = ROOT / "data" / "interim" / "bid_summary_items.parquet"
    bs = pd.read_parquet(
        p, columns=["contract_number", "item_no", "item_code", "description", "unit", "quantity"]
    )
    bs = bs[bs["contract_number"] == contract]
    # Items deleted by addendum stay in the bid summary as $0 placeholders.
    placeholders = bs["description"].str.strip() == DELETED
    deleted_in_summary = bs.loc[placeholders, "item_no"].tolist()
    bs = bs[~placeholders].drop(columns="description")
    m = items.merge(bs, on="item_no", how="outer", suffixes=("", "_summary"), indicator=True)
    both = m[m["_merge"] == "both"]
    qty_ok = (both["quantity"].fillna(-1) - both["quantity_summary"].fillna(-1)).abs() < 1e-6
    return {
        "parsed_items": int(len(items)),
        "bid_summary_items": int(len(bs)),
        "bid_summary_deleted_placeholders": deleted_in_summary,
        "only_in_parsed": m.loc[m["_merge"] == "left_only", "item_no"].tolist(),
        "only_in_summary": m.loc[m["_merge"] == "right_only", "item_no"].tolist(),
        "code_mismatches": both.loc[
            both["item_code"] != both["item_code_summary"], "item_no"
        ].tolist(),
        "unit_mismatches": both.loc[both["unit"] != both["unit_summary"], "item_no"].tolist(),
        "quantity_mismatches": both.loc[~qty_ok, "item_no"].tolist(),
    }


# ----------------------------------------------------------------- run


def run(contract: str, refresh: bool = False) -> dict:
    pages = extract_pages(contract, refresh)
    lines = label_lines(pages)
    chunks = chunk(lines)
    items, changes = bid_item_list(lines)
    check = check_against_summary(items, contract)
    folder = CACHE / contract
    chunks.to_parquet(folder / "chunks.parquet", index=False)
    items.to_parquet(folder / "bid_items.parquet", index=False)
    write_outputs(contract, pages, chunks, items, changes, check)
    return check


def write_outputs(contract, pages, chunks, items, changes, check) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pages = pages.assign(
        chars=pages["text"].str.len(), empty=pages["text"].str.strip().str.len() < 50
    )
    per_doc = (
        pages.groupby(["file", "title"], sort=False)
        .agg(pages=("page", "size"), empty_pages=("empty", "sum"), characters=("chars", "sum"))
        .reset_index()
        .merge(chunks.groupby("file").size().rename("chunks").reset_index(), on="file")
    )
    per_doc.to_csv(OUT / "documents.csv", index=False)
    pages.loc[pages["empty"], ["file", "page"]].to_csv(OUT / "empty_pages.csv", index=False)
    sp = chunks[chunks["kind"] == "special_provisions"]
    sections = (
        sp.groupby("section", sort=False)
        .agg(
            first_page=("page", "min"),
            last_page=("page", "max"),
            chunks=("chunk_id", "size"),
            section_numbers=("subsection", lambda s: len({x for x in s if x})),
        )
        .reset_index()
    )
    sections.to_csv(OUT / "special_provision_sections.csv", index=False)
    items.to_csv(OUT / "bid_item_list.csv", index=False)
    pd.DataFrame(changes).to_csv(OUT / "addendum_changes.csv", index=False)

    dl = ["| Document | Pages | Empty pages | Chunks |", "| --- | ---: | ---: | ---: |"]
    for r in per_doc.itertuples():
        dl.append(f"| {r.title} | {r.pages:,} | {r.empty_pages} | {r.chunks:,} |")
    cl = ["| Addendum | Item | Change | Was | Now |", "| --- | --- | --- | --- | --- |"]
    for c in changes:
        cl.append(
            f"| {c['addendum']} p{c['page']} | {c['item_no']} | {c['change']} | "
            f"{c.get('was', '')} | {c.get('now', '')} |"
        )
    ok = not any(
        check[k]
        for k in (
            "only_in_parsed",
            "only_in_summary",
            "code_mismatches",
            "unit_mismatches",
            "quantity_mismatches",
        )
    )
    verdict = (
        "**They match exactly**: same item numbers, codes, units and quantities."
        if ok
        else "**They differ**; see the list below."
    )
    issues = (
        ""
        if ok
        else "\n".join(f"- {k}: {v}" for k, v in check.items() if isinstance(v, list) and v)
    )
    body = f"""
The bid package turned into text BidLens can search and cite (step 3.2).

## What we did

Each document of contract {contract} that BidLens reads was turned into text page by page.
The special provisions were split into their numbered sections (for example "8 Prosecution
And Progress"), keeping the most recent section number mentioned (for example 8-1.05).
The text was then cut into short passages ("chunks") that never cross a page or a
section, so every fact pulled from them in step 3.3 can cite one exact page.

{chr(10).join(dl)}

Empty pages are scanned images or figures without text; they are listed in
`empty_pages.csv` and not read in v1. The plans are drawings without text and are not read.

## The bid item list

The list on the special provisions' Bid Item List pages was read row by row, and then
every addendum's revised list was applied:

{chr(10).join(cl)}

The result has {check["parsed_items"]} items. Checked against the bid summary's item list
for the same contract ({check["bid_summary_items"]} items): {verdict}
{issues}

## Files

- `documents.csv`: pages, empty pages, characters and chunks per document.
- `special_provision_sections.csv`: each section of the special provisions with its pages.
- `bid_item_list.csv`: the final bid item list with the page each row came from.
- `addendum_changes.csv`: the bid item changes made by addenda.
- `empty_pages.csv`: pages without text.

The page text and chunks themselves are in `data/interim/docs/{contract}/` (not committed).

## How it was produced

`uv run python -m bidlens.documents.parse {contract}` (code in
`src/bidlens/documents/parse.py`). Generated {date.today().isoformat()}.
"""
    (OUT / "README.md").write_text(
        "# 17 Document parsing\n\n" + body.strip() + "\n", encoding="utf-8"
    )
    (OUT / "results.json").write_text(json.dumps(check, indent=2) + "\n")

    from bidlens.outputs import write_index

    write_index()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    ap.add_argument("--refresh", action="store_true", help="re-read the PDFs")
    args = ap.parse_args(argv)
    print(json.dumps(run(args.contract, args.refresh), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
