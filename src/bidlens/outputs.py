"""Write the numbered, self-explaining output folders.

Usage:
    uv run python -m bidlens.outputs            # regenerates outputs/01..06

Every CSV here is free of bidder names, addresses and phone numbers; bids are identified
by bid rank. Bid summary PDFs are never copied; the manifest points to their source.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import duckdb

from bidlens.ingest.cache import RawCache
from bidlens.ingest.caltrans import BASE_URL
from bidlens.ingest.parse_sv08 import ParseError, parse_details, parse_results

ROOT = Path(".")
OUT = ROOT / "outputs"
DB = ROOT / "data" / "bidlens.duckdb"
INTERIM = ROOT / "data" / "interim"
CACHE = ROOT / "data" / "raw" / "sv08data"
PDFS = ROOT / "data" / "raw" / "bid_summaries"
FIXTURES = ROOT / "tests" / "fixtures" / "caltrans"
BID_SUMMARY_SITE = "https://ppmoe.dot.ca.gov/cc?id=cc_bid_summary"
DETAILS_URL = BASE_URL + "details.php?Num="

STAGES = {
    "01_source_review": "Where the data comes from: the Caltrans sites, their rules, and sample pages.",
    "02_price_collection": "Every request made to the Caltrans cost database and every bid price collected.",
    "03_bid_summaries": "The bid summary PDFs: what was downloaded, what was read, and any problems.",
    "04_cross_check": "Prices from the cost database compared with the same prices in the bid summaries.",
    "05_data_quality": "Missing values and data quality checks on the combined database.",
    "06_item_master": "The official Caltrans item list, item families, and how bid items map to it.",
}


def _write_csv(path: Path, header: list[str], rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            w.writerow(["" if v is None else v for v in row])
            n += 1
    return n


def _copy_query(con: duckdb.DuckDBPyConnection, sql: str, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({sql}) TO '{path}' (HEADER, DELIMITER ',')")
    return con.execute(f"SELECT count(*) FROM read_csv_auto('{path}')").fetchone()[0]


def _readme(folder: Path, title: str, body: str) -> None:
    (folder / "README.md").write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")


def _move_report(src: Path, dst: Path) -> None:
    """Move a report from docs/results into its stage folder (kept if already moved)."""
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), dst)


# --------------------------------------------------------------------------- stages


def stage_01() -> dict:
    d = OUT / "01_source_review"
    _move_report(ROOT / "docs/results/source_review.md", d / "source_review.md")
    names = sorted(p.name for p in FIXTURES.glob("*.html"))
    _readme(
        d,
        "01 Source review",
        f"""
{STAGES["01_source_review"]}

- `source_review.md` is the review itself. It covers the Caltrans Contract Cost Data site, the HQ bid summary site and the item list, with their conditions of use and what each one contains.
- One saved page per endpoint used ({len(names)} files, no bidder names) is kept only as test fixtures in `tests/fixtures/caltrans/`, so the parsers are tested on the site's real layout.

How it was produced: by hand in step 1.1, with plain web requests at least 2 seconds apart. The HQ bid summary site's robots.txt disallows automated access, so no script ever requests it.
""",
    )
    return {"samples": len(names)}


def stage_02(con: duckdb.DuckDBPyConnection) -> dict:
    d = OUT / "02_price_collection"
    cache = RawCache(CACHE)
    log_rows = []
    with (CACHE / "manifest.jsonl").open() as fh:
        for line in fh:
            e = json.loads(line)
            e["params"] = [tuple(p) for p in e["params"]]
            url = BASE_URL + e["endpoint"] + ("?" + urlencode(e["params"]) if e["params"] else "")
            rows_parsed = ""
            if e["status"] == "ok" and e["path"]:
                body = cache.read(cache.entry(e["endpoint"], e["params"]))
                try:
                    if e["endpoint"] == "results.php":
                        rows_parsed = len(parse_results(body))
                    else:
                        parse_details(body)
                        rows_parsed = 1
                except ParseError:
                    rows_parsed = 0
            log_rows.append(
                (
                    e["fetched_at"],
                    e["endpoint"],
                    url,
                    e["status"],
                    e["http_status"],
                    rows_parsed,
                    e["bytes"],
                    e["message"],
                )
            )
    n_log = _write_csv(
        d / "request_log.csv",
        [
            "fetched_at_utc",
            "page",
            "url",
            "status",
            "http_status",
            "rows_parsed",
            "bytes",
            "message",
        ],
        log_rows,
    )
    n_prices = _copy_query(
        con,
        f"""
        SELECT c.contract_number, strftime(c.bid_open_date, '%Y-%m-%d') AS bid_open_date,
               c.district, c.county, n.item_code, n.item_description, n.item_family,
               n.unit, n.quantity::DOUBLE AS quantity, n.unit_price::DOUBLE AS unit_price,
               n.total::DOUBLE AS total, n.bid_rank,
               '{DETAILS_URL}' || n.source_row_id AS source_url
        FROM bid_normalized n JOIN contract c USING (contract_id)
        ORDER BY c.bid_open_date, c.contract_number, n.item_code, n.bid_rank
        """,
        d / "bid_prices.csv",
    )
    status = Counter(r[3] for r in log_rows)
    pages = Counter(r[1] for r in log_rows)
    _readme(
        d,
        "02 Price collection",
        f"""
{STAGES["02_price_collection"]}

| File | Rows | What it is |
| --- | --- | --- |
| `request_log.csv` | {n_log:,} | One row per page requested from sv08data.dot.ca.gov: time, page, full URL, outcome, HTTP status, rows read from the page, and size |
| `bid_prices.csv` | {n_prices:,} | Every bid price collected: contract, bid date, district, county, item, family, unit, quantity, unit price, total, bid rank (1 = low bidder) and a link to the price on the Caltrans site |

**Requests:** {dict(pages)}. Outcomes: {dict(status)}. A dropped connection that recovered on retry is logged once, with its final outcome.

**How it was produced:** `uv run python -m bidlens.ingest.caltrans all` (step 1.2), with one request at a time, at least 2 seconds apart. First, 8 searches listed the contracts for Districts 4 and 5, 2018 to 2026, through four items nearly every contract has. Then 827 contract pages gave county and type of work, and 1,800 searches (100 items × 2 districts × 9 years) gave the prices. The scope is set in `config/scope.yaml`.

**Notes:**
- Prices are in the units Caltrans published. No conversion was needed (see `06_item_master`).
- Bid rank is the bidder's overall rank on the contract, not on the item.
- The cost database leaves out irregular bids. No bidder names are collected.
""",
    )
    return {"request_log": n_log, "bid_prices": n_prices}


def stage_03(con: duckdb.DuckDBPyConnection) -> dict:
    d = OUT / "03_bid_summaries"
    _move_report(ROOT / "docs/results/bid_summary_coverage.md", d / "coverage.md")
    check = {r["file"]: r for r in csv.DictReader((INTERIM / "bid_summary_check.csv").open())}
    parsed = {
        r[0]: r
        for r in con.execute(f"""
            SELECT source_file, project_id IS NULL AS older_layout, read_by_ocr, items_complete
            FROM read_parquet('{INTERIM / "bid_summaries.parquet"}')
        """).fetchall()
    }
    cost_link = dict(
        con.execute(f"""
            SELECT contract_number || '_' || strftime(bid_open_date, '%Y-%m-%d'),
                   '{DETAILS_URL}' || min(b.source_row_id)
            FROM bid b JOIN bid_item USING (bid_item_id) JOIN contract USING (contract_id)
            GROUP BY 1
        """).fetchall()
    )
    manifest = []
    for pdf in sorted(PDFS.glob("*.pdf")):
        c = check.get(pdf.name, {})
        p = parsed.get(pdf.name)
        contract, bid_date = c.get("contract", ""), c.get("bid_open_date", "")
        if p is None:
            status = "not usable"
        elif p[3]:
            status = "usable"
        else:
            status = "usable, contract fields only"
        layout = "" if p is None else ("older (BID211)" if p[1] else "newer")
        problems = c.get("problems", "")
        named = pdf.stem.split("_")[0]
        manifest.append(
            (
                pdf.name,
                named,
                contract,
                bid_date,
                hashlib.sha256(pdf.read_bytes()).hexdigest(),
                layout,
                "OCR" if p and p[2] else ("text" if p else ""),
                status,
                problems,
                BID_SUMMARY_SITE,
                f"{named} (bid opened {bid_date})" if bid_date else named,
                cost_link.get(f"{contract}_{bid_date}", ""),
            )
        )
    n_manifest = _write_csv(
        d / "pdf_manifest.csv",
        [
            "file",
            "contract_number_in_file_name",
            "contract_number_in_pdf",
            "bid_open_date_in_pdf",
            "sha256",
            "layout",
            "read_by",
            "parse_status",
            "problems",
            "caltrans_source_page",
            "search_the_source_page_for",
            "same_contract_in_cost_database",
        ],
        manifest,
    )
    n_contracts = _copy_query(
        con,
        f"""
        SELECT contract_number, strftime(bid_open_date, '%Y-%m-%d') AS bid_open_date,
               district, county, location, type_of_work, n_items, proposals_issued,
               working_days, n_bidders_reported, n_bidders_ranked AS n_bidders,
               engineers_estimate, pct_over_under_reported, is_a_plus_b,
               low_bid_cost, low_bid_total, second_bid_total, read_by_ocr,
               items_complete, header_check, source_file
        FROM read_parquet('{INTERIM / "bid_summaries.parquet"}')
        ORDER BY bid_open_date, contract_number
        """,
        d / "parsed_contracts.csv",
    )
    n_items = _copy_query(
        con,
        f"""
        SELECT contract_number, strftime(bid_open_date, '%Y-%m-%d') AS bid_open_date,
               item_no AS line, item_code, description, unit, quantity, unit_price, amount,
               1 AS bid_rank, final_pay
        FROM read_parquet('{INTERIM / "bid_summary_items.parquet"}')
        ORDER BY bid_open_date, contract_number, line
        """,
        d / "parsed_item_prices.csv",
    )
    issues = [(m[0], m[2], m[3], m[7], m[8]) for m in manifest if m[8] or m[7] != "usable"]
    n_issues = _write_csv(
        d / "parse_issues.csv",
        ["file", "contract_number_in_pdf", "bid_open_date_in_pdf", "parse_status", "problem"],
        issues,
    )
    status = Counter(m[7] for m in manifest)
    by = Counter(m[6] for m in manifest)
    _readme(
        d,
        "03 Bid summaries",
        f"""
{STAGES["03_bid_summaries"]}

| File | Rows | What it is |
| --- | --- | --- |
| `pdf_manifest.csv` | {n_manifest:,} | Every downloaded PDF: contract and bid date read from it, SHA-256 hash, layout, whether it was read from text or OCR, parse status, problems, and where to find the original |
| `parsed_contracts.csv` | {n_contracts:,} | Contract fields from each usable PDF: engineer's estimate, working days, bidder counts, low and second bid, A+B flag and checks. `type_of_work` is blank for older-layout files, whose description wraps into the location text. The database takes type of work from the cost database instead |
| `parsed_item_prices.csv` | {n_items:,} | The low bidder's price for every item, from PDFs whose item lines fully reconcile |
| `parse_issues.csv` | {n_issues:,} | Every PDF with a problem, and what the problem is |
| `coverage.md` | | Which contracts have a usable summary, and why the others do not |

**Parse status:** {dict(status)}. Read by: {dict(by)}.

**How it was produced:**
1. The maintainer downloaded the PDFs by hand from the Caltrans bid summary site. Its robots.txt bars scripts.
2. `uv run python -m bidlens.ingest.check_bid_summaries` read each file. It handles two report layouts. Files that Caltrans serves with broken fonts are read with OCR.

**Checks:**
- **Exact sum:** the low bidder's items must add up exactly to the low bid.
- **Header check:** the engineer's estimate × (1 + printed % over/under) must reproduce the low bid.

**The PDFs are not in this repository.** They list bidder names and contact details. To open one:
1. Go to the `caltrans_source_page` (the Caltrans bid summary search).
2. Search it for the contract number and bid date in `search_the_source_page_for`. The site has no stable link per record.
3. `same_contract_in_cost_database` links straight to the same contract's prices on the public cost database.
4. The `sha256` column confirms a downloaded copy is the same file.

**No bidder names, addresses or phone numbers are stored.** Bids are identified by rank.
""",
    )
    return {"manifest": n_manifest, "contracts": n_contracts, "items": n_items, "issues": n_issues}


def stage_04(con: duckdb.DuckDBPyConnection) -> dict:
    d = OUT / "04_cross_check"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE xc AS
        WITH s AS (
            SELECT contract_number || '_' || strftime(bid_open_date, '%Y-%m-%d') AS contract_id,
                   item_code, unit_price AS pdf_price, quantity AS pdf_qty, amount AS pdf_total
            FROM read_parquet('{INTERIM / "bid_summary_items.parquet"}')
        ),
        db AS (
            SELECT i.contract_id, i.item_code, i.unit, i.quantity, b.unit_price, b.total,
                   b.source_row_id
            FROM bid b JOIN bid_item i USING (bid_item_id) WHERE b.bid_rank = 1
        ),
        pairs AS (
            SELECT db.*, s.pdf_price, s.pdf_total,
                   abs(db.unit_price - s.pdf_price) < 0.005 AS same
            FROM db JOIN s USING (contract_id, item_code)
            WHERE s.pdf_qty IS NULL OR abs(s.pdf_qty - db.quantity) < 0.001
        ),
        per_contract AS (
            SELECT contract_id, avg((NOT same)::INT) AS share_diff FROM pairs GROUP BY 1
        )
        SELECT p.*, pc.share_diff FROM pairs p JOIN per_contract pc USING (contract_id)
    """)
    n = _copy_query(
        con,
        f"""
        SELECT c.contract_number, strftime(c.bid_open_date, '%Y-%m-%d') AS bid_open_date,
               x.item_code, x.unit, x.quantity::DOUBLE AS quantity,
               x.unit_price::DOUBLE AS cost_database_unit_price,
               x.pdf_price AS bid_summary_unit_price,
               x.total::DOUBLE AS cost_database_total, x.pdf_total AS bid_summary_total,
               CASE WHEN x.same THEN 'yes' ELSE 'no' END AS match,
               CASE WHEN x.same THEN ''
                    WHEN x.share_diff >= 0.5 THEN
                      'Sources disagree on the low bidder for this contract (most prices differ)'
                    ELSE 'Price differs on this item only' END AS reason,
               '{DETAILS_URL}' || x.source_row_id AS cost_database_url,
               s.source_file AS bid_summary_file
        FROM xc x JOIN contract c USING (contract_id)
        LEFT JOIN read_parquet('{INTERIM / "bid_summaries.parquet"}') s
          ON s.contract_number = c.contract_number AND s.bid_open_date = c.bid_open_date
        ORDER BY c.bid_open_date, c.contract_number, x.item_code
        """,
        d / "cross_check.csv",
    )
    pairs, same = con.execute("SELECT count(*), sum(same::INT) FROM xc").fetchone()
    contracts_diff = con.execute(
        "SELECT count(DISTINCT contract_id) FROM xc WHERE share_diff >= 0.5"
    ).fetchone()[0]
    other_diff = con.execute(
        "SELECT count(*) FROM xc WHERE NOT same AND share_diff < 0.5"
    ).fetchone()[0]
    bidders = con.execute("""
        SELECT count(*), sum((n_bidders_sv08 = n_bidders)::INT),
               sum((n_bidders_sv08 < n_bidders)::INT), sum((n_bidders_sv08 > n_bidders)::INT)
        FROM contract WHERE has_bid_summary AND n_bidders_sv08 IS NOT NULL
    """).fetchone()
    summary = f"""
## Summary

| Check | Result |
| --- | --- |
| Low bidder's item prices compared (same contract, item and quantity) | {pairs:,} |
| Identical to the cent | {same:,} ({same / pairs:.1%}) |
| Different, in contracts where the sources disagree on the low bidder | {pairs - same - other_diff:,} prices in {contracts_diff} contracts |
| Different on a single item only | {other_diff:,} |
| Bidder count: cost database highest rank = ranked bidders in the summary | {bidders[1]} of {bidders[0]} contracts ({bidders[2]} fewer, {bidders[3]} more) |

**What the differences mean:** in each flagged contract, the bidder ranked first in the cost database is not the low bidder in the bid summary, so almost every item price differs. This points to a ranking change (for example, a low bid that was later rejected), not to wrong numbers. Step 1.6 marks these contracts, and the models treat their rank-1 prices with care.
"""
    (d / "summary.md").write_text("# Cross-check summary\n" + summary, encoding="utf-8")
    _readme(
        d,
        "04 Cross-check",
        f"""
{STAGES["04_cross_check"]}

| File | Rows | What it is |
| --- | --- | --- |
| `cross_check.csv` | {n:,} | Every compared price: contract, item, quantity, the unit price and total from each source, whether they match, the reason if not, and a link to each source |
| `summary.md` | | The totals below, with an explanation |

**How it was produced:** the low bidder's price (bid rank 1) from the cost database was matched with the low bidder's price in the bid summary PDF. A pair is compared when the contract, bid date, item code and quantity all match. Items whose quantity differs between the sources are not compared.
{summary}""",
    )
    return {"cross_check": n, "pairs": pairs, "same": same}


def stage_05(con: duckdb.DuckDBPyConnection) -> dict:
    d = OUT / "05_data_quality"
    _move_report(ROOT / "docs/results/contract_missing_data.md", d / "missing_data.md")
    fields = ["county", "engineers_estimate", "working_days", "n_bidders", "low_bid_total"]
    rows = con.execute(f"""
        SELECT contract_number, strftime(bid_open_date, '%Y-%m-%d'), has_bid_summary,
               bid_summary_ocr, {", ".join(fields)}
        FROM contract ORDER BY bid_open_date, contract_number
    """).fetchall()
    out = []
    for r in rows:
        missing = [f for f, v in zip(fields, r[4:], strict=True) if v is None]
        if missing:
            reason = "OCR could not read the value" if r[2] else "No usable bid summary"
            out.append((r[0], r[1], "; ".join(missing), reason))
    n = _write_csv(
        d / "missing_data.csv",
        ["contract_number", "bid_open_date", "missing_fields", "reason"],
        out,
    )
    _readme(
        d,
        "05 Data quality",
        f"""
{STAGES["05_data_quality"]}

| File | Rows | What it is |
| --- | --- | --- |
| `missing_data.csv` | {n:,} | Every contract opening missing a contract-level field, which fields, and why |
| `missing_data.md` | | The same, as a report with totals (step 1.5) |
| `data_quality.md` | | Checks on prices and contracts (step 1.6): what was checked, how many failed, and what it means |
| `bid_flags.csv` | | Every flagged bid price, with its flag, detail and source link |
| `contract_flags.csv` | | Every flagged contract |

**How it was produced:** from `data/bidlens.duckdb`, which `uv run python -m bidlens.db.load` builds. `uv run python -m bidlens.db.checks` runs the checks. Both are part of `make data`. Flagged data is never deleted. Most missing fields come from contracts that have no usable bid summary (see `03_bid_summaries/coverage.md`).
""",
    )
    return {"missing_data": n}


def stage_06(con: duckdb.DuckDBPyConnection) -> dict:
    d = OUT / "06_item_master"
    _move_report(ROOT / "docs/results/item_master.md", d / "item_master_report.md")
    n_master = _copy_query(
        con,
        """
        SELECT item_code, description, unit, item_family, spec_section, final_pay,
               is_current, array_to_string(replaced_by, ' ') AS replaced_by
        FROM item_master ORDER BY item_code
        """,
        d / "item_master.csv",
    )
    from bidlens.db.item_master import SECTION_FAMILY

    n_fam = _write_csv(
        d / "item_families.csv",
        ["spec_section", "item_family"],
        sorted(SECTION_FAMILY.items()),
    )
    n_map = _copy_query(
        con,
        """
        SELECT item_code, any_value(item_description) AS description, any_value(item_family)
               AS item_family, bool_and(is_current) AS on_2026_list,
               count(*) AS bid_rows, count(DISTINCT contract_id) AS contracts
        FROM bid_normalized GROUP BY item_code ORDER BY bid_rows DESC
        """,
        d / "item_mapping.csv",
    )
    _readme(
        d,
        "06 Item master",
        f"""
{STAGES["06_item_master"]}

| File | Rows | What it is |
| --- | --- | --- |
| `item_master.csv` | {n_master:,} | Every item code: description, pay unit, family, spec section, final-pay flag, whether it is on the 2026 list, and successors of a retired code |
| `item_families.csv` | {n_fam} | Which 2026 Standard Specifications section belongs to which item family |
| `item_mapping.csv` | {n_map} | The 100 in-scope items: family, whether the code is current, and how many bid rows and contracts use it |
| `item_master_report.md` | | Mapping rate, the unmapped code, and family totals |

**How it was produced:** step 1.4 read the Caltrans 2026 Bid Items list (numerical XLSX, revised 10-19-26) from https://dot.ca.gov/programs/design/2026-ccs-standard-plans-and-standard-specifications. Units follow each code's 2026 pay unit, retired codes are kept and flagged, and families follow the 2026 Standard Specifications sections.
""",
    )
    return {"item_master": n_master, "families": n_fam, "mapping": n_map}


def write_index() -> None:
    lines = [
        "# Outputs",
        "",
        "Every stage of BidLens writes its results to a numbered folder here, so anyone can follow "
        "and check the work in order. Each folder has a README that says what "
        "is inside and how it was produced. No file names a bidder: bids are identified by "
        "rank. The bid summary PDFs are not included; `03_bid_summaries/pdf_manifest.csv` says "
        "where to find each one.",
        "",
        "| Stage | Folder | What it shows |",
        "| --- | --- | --- |",
    ]
    for folder in sorted(p for p in OUT.iterdir() if p.is_dir()):
        desc = STAGES.get(folder.name)
        if desc is None and (folder / "README.md").exists():
            text = (folder / "README.md").read_text().splitlines()
            desc = next((t for t in text[1:] if t.strip()), "")
        num, _, name = folder.name.partition("_")
        lines.append(f"| {num} | [`{folder.name}/`]({folder.name}/README.md) | {desc} |")
    lines += [
        "",
        f"Regenerate stages 01 to 06 with `uv run python -m bidlens.outputs`. Last generated "
        f"{date.today().isoformat()}.",
    ]
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    con = duckdb.connect(str(DB), read_only=True)
    result = {
        "01": stage_01(),
        "02": stage_02(con),
        "03": stage_03(con),
        "04": stage_04(con),
        "05": stage_05(con),
        "06": stage_06(con),
    }
    con.close()
    write_index()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
