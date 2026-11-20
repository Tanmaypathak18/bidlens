"""Check downloaded bid summaries against the download checklist (step 1.5).

Usage:
    uv run python -m bidlens.ingest.check_bid_summaries

Writes data/interim/bid_summary_check.csv (one row per expected bid opening and per
file) and data/interim/bid_summaries.parquet / bid_summary_items.parquet for files that
read cleanly. Nothing written here contains bidder names or contact details.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import duckdb

from bidlens.ingest.bid_summary import BidSummary, BidSummaryError, read_bid_summary

_CHECK_LINE = re.compile(
    r"^- \[(?P<done>[ xX])\]\s+`(?P<ea>[^`]+)`\s+bid opened (?P<date>\d{4}-\d{2}-\d{2})"
)
_NOT_FOUND_LINE = re.compile(r"^(?P<ea>\d{2}-[0-9A-Z]{6})\s+bid opened (?P<date>\d{4}-\d{2}-\d{2})")
_FILE_NAME = re.compile(r"^(?P<ea>\d{2}-[0-9A-Z]{6})(?:_(?P<date>\d{4}-\d{2}-\d{2}))?\.pdf$", re.I)


@dataclass
class FileResult:
    file: str
    sha1: str
    summary: BidSummary | None
    error: str | None


def _read(path: Path) -> FileResult:
    sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
    try:
        return FileResult(path.name, sha1, read_bid_summary(path), None)
    except BidSummaryError as exc:
        return FileResult(path.name, sha1, None, str(exc))


def load_checklist(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        if m := _CHECK_LINE.match(line.strip()):
            rows.append(
                {
                    "ea": m["ea"],
                    "date": m["date"],
                    "ticked": m["done"] != " ",
                    "note": line.split("—", 1)[1].strip() if "—" in line else "",
                }
            )
    return rows


def load_not_found(path: Path) -> set[tuple[str, str]]:
    out = set()
    for line in path.read_text().splitlines():
        if m := _NOT_FOUND_LINE.match(line.strip()):
            out.add((m["ea"], m["date"]))
    return out


def run(folder: Path, checklist: Path, not_found: Path, out: Path, workers: int = 6) -> dict:
    expected = load_checklist(checklist)
    nf = load_not_found(not_found)
    pdfs = sorted(folder.glob("*.pdf"))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_read, pdfs, chunksize=4))

    by_key: dict[tuple[str, str], list[FileResult]] = {}
    file_rows = []
    sha_count = Counter(r.sha1 for r in results)
    for r in results:
        m = _FILE_NAME.match(r.file)
        problems: list[str] = []
        if not m:
            problems.append("file name not <contract>.pdf or <contract>_<date>.pdf")
        if r.error:
            problems.append(f"unreadable: {r.error}")
        if sha_count[r.sha1] > 1:
            problems.append("identical to another file")
        s = r.summary
        if s is not None:
            if m and s.contract_number != m["ea"]:
                problems.append(f"contract in file is {s.contract_number}")
            if m and m["date"] and s.bid_open_date.isoformat() != m["date"]:
                problems.append(f"bid date in file is {s.bid_open_date}")
            problems += s.checks()
            by_key.setdefault((s.contract_number, s.bid_open_date.isoformat()), []).append(r)
        file_rows.append(
            {
                "file": r.file,
                "contract": s.contract_number if s else "",
                "bid_open_date": s.bid_open_date.isoformat() if s else "",
                "problems": "; ".join(problems),
            }
        )

    exp_rows = []
    for e in expected:
        key = (e["ea"], e["date"])
        files = by_key.get(key, [])
        if files:
            status = "have file" if len(files) == 1 else f"{len(files)} files"
        elif key in nf:
            status = "not on site"
        else:
            status = "missing"
        exp_rows.append({**e, "status": status, "files": " ".join(f.file for f in files)})

    expected_keys = {(e["ea"], e["date"]) for e in expected}
    extra = [k for k in by_key if k not in expected_keys]

    out.mkdir(parents=True, exist_ok=True)
    with (out / "bid_summary_check.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "contract", "bid_open_date", "problems"])
        w.writeheader()
        w.writerows(file_rows)
    with (out / "bid_summary_expected.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ea", "date", "ticked", "status", "files", "note"])
        w.writeheader()
        w.writerows(exp_rows)

    clean = [r.summary for r in results if r.summary is not None]
    _write_tables(clean, out)
    return {
        "files": len(results),
        "unreadable": sum(1 for r in results if r.error),
        "files_with_problems": sum(1 for f in file_rows if f["problems"]),
        "problem_counts": Counter(
            p.split(":")[0].split(" != ")[0]
            for f in file_rows
            for p in f["problems"].split("; ")
            if p
        ),
        "expected": len(expected),
        "expected_status": Counter(e["status"] for e in exp_rows),
        "not_found_listed": len(nf),
        "files_not_in_checklist": extra,
        "by_year": Counter(s.bid_open_date.year for s in clean),
    }


_CONTRACT_SCHEMA = {
    "contract_number": "VARCHAR",
    "bid_open_date": "DATE",
    "project_id": "VARCHAR",
    "location": "VARCHAR",
    "district": "VARCHAR",
    "county": "VARCHAR",
    "type_of_work": "VARCHAR",
    "n_items": "INTEGER",
    "proposals_issued": "INTEGER",
    "working_days": "INTEGER",
    "n_bidders_reported": "INTEGER",
    "n_bidders_ranked": "INTEGER",
    "engineers_estimate": "DOUBLE",
    "pct_over_under_reported": "DOUBLE",
    "is_a_plus_b": "BOOLEAN",
    "low_bid_cost": "DOUBLE",
    "low_bid_total": "DOUBLE",
    "second_bid_total": "DOUBLE",
    "source_file": "VARCHAR",
    "problems": "VARCHAR",
}
_ITEM_SCHEMA = {
    "contract_number": "VARCHAR",
    "bid_open_date": "DATE",
    "item_no": "VARCHAR",
    "final_pay": "BOOLEAN",
    "item_code": "VARCHAR",
    "description": "VARCHAR",
    "unit": "VARCHAR",
    "quantity": "DOUBLE",
    "unit_price": "DOUBLE",
    "amount": "DOUBLE",
}


def _write_tables(summaries: list[BidSummary], out: Path) -> None:
    contracts = [s.contract_record() | {"problems": "; ".join(s.checks())} for s in summaries]
    items = [
        {
            "contract_number": s.contract_number,
            "bid_open_date": s.bid_open_date,
            "item_no": i.item_no,
            "final_pay": i.flag == "F",
            "item_code": i.item_code,
            "description": i.description,
            "unit": i.unit,
            "quantity": i.quantity,
            "unit_price": i.unit_price,
            "amount": i.amount,
        }
        for s in summaries
        for i in s.low_items
    ]
    con = duckdb.connect()
    for name, schema, rows in (
        ("bid_summaries", _CONTRACT_SCHEMA, contracts),
        ("bid_summary_items", _ITEM_SCHEMA, items),
    ):
        cols = list(schema)
        con.execute(
            f"CREATE OR REPLACE TABLE t ({', '.join(f'{c} {t}' for c, t in schema.items())})"
        )
        if rows:
            con.executemany(
                f"INSERT INTO t VALUES ({', '.join('?' for _ in cols)})",
                [[r[c] for c in cols] for r in rows],
            )
        con.execute(
            f"COPY (SELECT * FROM t ORDER BY ALL) TO '{out / (name + '.parquet')}' (FORMAT parquet)"
        )
    con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", type=Path, default=Path("data/raw/bid_summaries"))
    ap.add_argument(
        "--checklist",
        type=Path,
        default=Path("data/raw/bid_summaries/download_checklist_updated.md"),
    )
    ap.add_argument(
        "--not-found", type=Path, default=Path("data/raw/bid_summaries/not_found_list.txt")
    )
    ap.add_argument("--out", type=Path, default=Path("data/interim"))
    args = ap.parse_args(argv)
    result = run(args.folder, args.checklist, args.not_found, args.out)
    for k, v in result.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
