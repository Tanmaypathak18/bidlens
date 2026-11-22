"""Step 4.2: the draft estimate workbook.

Usage:
    uv run python -m bidlens.export 04-0W0504   # outputs/21_app/draft_estimate_<contract>.xlsx

Sheets: Estimate (bid items with live amount formulas and a live total), Comparables,
Risk register (document findings with their pages), Closure hours, and About.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEAD = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor="1F4E79")
MONEY = '"$"#,##0.00'
WHOLE = '"$"#,##0'


def _load(contract: str, root: Path):
    from bidlens.documents.extract import DEFAULT_RUN, RUN_FALLBACKS
    from bidlens.sample import app_dir, docs_dir

    app = app_dir(contract, root)
    s = json.loads((app / "summary.json").read_text())
    est = pd.read_parquet(app / "estimate.parquet")
    cp = app / "comparables.parquet"
    comps = pd.read_parquet(cp) if cp.exists() else pd.DataFrame()
    items, model = pd.DataFrame(), ""
    for run in (DEFAULT_RUN, *RUN_FALLBACKS):
        p = docs_dir(contract, root) / f"extraction_{run}.json"
        if p.exists():
            res = json.loads(p.read_text())
            items, model = pd.DataFrame(res["items"]), res.get("model", run)
            break
    return s, est, comps, items, model


def _header(ws, row: int, names: list[str], widths: list[int]) -> None:
    for j, (n, w) in enumerate(zip(names, widths, strict=True), start=1):
        c = ws.cell(row=row, column=j, value=n)
        c.font, c.fill = HEAD, FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(j)].width = w


def workbook(contract: str, root: Path = Path(".")) -> bytes:
    from bidlens.documents.report import mask

    s, est, comps, items, model = _load(contract, root)
    wb = Workbook()

    # --- Estimate
    ws = wb.active
    ws.title = "Estimate"
    mk = s.get("market") or {}
    info = [
        ("Contract", contract),
        ("Work", s["type_of_work"]),
        ("Bids open", s["bid_open_date"]),
        ("District / county", f"{s['district']} / {s['county']}"),
        ("Working days", s["working_days"]),
        ("Engineer's estimate", s["engineers_estimate"]),
    ]
    if mk:
        info.append(
            (
                "Expected low bid vs estimate",
                f"{100 * mk['spread_kumo']:+.0f}% (likely {100 * mk['spread_low']:+.0f}% to "
                f"{100 * mk['spread_high']:+.0f}%); expected bidders {mk['bidders_kumo']:.0f}",
            )
        )
    for i, (k, v) in enumerate(info, start=1):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        c = ws.cell(row=i, column=2, value=v)
        if k == "Engineer's estimate":
            c.number_format = WHOLE
    top = len(info) + 2
    cols = [
        "Item",
        "Code",
        "Description",
        "Unit",
        "Quantity",
        "Low unit price",
        "Likely unit price",
        "High unit price",
        "Low amount",
        "Likely amount",
        "High amount",
        "Priced from",
        "Comparable bids",
        "Estimator unit price",
        "Estimator amount",
    ]
    _header(ws, top, cols, [7, 9, 44, 7, 11, 14, 14, 14, 15, 15, 15, 40, 12, 14, 15])
    ncomp = comps.groupby("item_no").size() if len(comps) else pd.Series(dtype=int)
    first = top + 1
    for i, r in enumerate(est.itertuples(), start=first):
        qty = 1 if pd.isna(r.quantity) else float(r.quantity)
        vals = [
            r.item_no,
            r.item_code,
            r.description,
            r.unit,
            qty,
            None if pd.isna(r.low) else float(r.low),
            float(r.pred_unit_price),
            None if pd.isna(r.high) else float(r.high),
            f'=IF(F{i}="","",E{i}*F{i})',
            f"=E{i}*G{i}",
            f'=IF(H{i}="","",E{i}*H{i})',
            r.source,
            int(ncomp.get(r.item_no, 0)),
            None,
            f'=IF(N{i}="",J{i},E{i}*N{i})',
        ]
        for j, v in enumerate(vals, start=1):
            c = ws.cell(row=i, column=j, value=v)
            if j in (6, 7, 8, 14):
                c.number_format = MONEY
            elif j in (9, 10, 11, 15):
                c.number_format = WHOLE
    last = first + len(est) - 1
    t = last + 1
    ws.cell(row=t, column=3, value="Total (likely prices)").font = Font(bold=True)
    ws.cell(row=t, column=10, value=f"=SUM(J{first}:J{last})").number_format = WHOLE
    ws.cell(row=t, column=15, value=f"=SUM(O{first}:O{last})").number_format = WHOLE
    for j in (10, 15):
        ws.cell(row=t, column=j).font = Font(bold=True)
    ws.cell(
        row=t + 1,
        column=3,
        value="Low and high bracket 8 in 10 past low bids for modeled items; they are not "
        "totalled, since item lows and highs don't add up to a total range.",
    )
    ws.cell(
        row=t + 2,
        column=3,
        value="Type your own unit price in column N; the estimator amount and its total update.",
    )
    ws.freeze_panes = ws.cell(row=first, column=4)
    ws.auto_filter.ref = f"A{top}:O{last}"

    # --- Comparables
    wc = wb.create_sheet("Comparables")
    _header(
        wc,
        1,
        [
            "Item",
            "Rank",
            "Contract",
            "Bid date",
            "District",
            "Quantity",
            "Low bid unit price",
            "In bid-date dollars",
            "Caltrans source",
        ],
        [7, 6, 12, 12, 9, 12, 16, 16, 50],
    )
    for i, r in enumerate(comps.itertuples(), start=2):
        vals = [
            r.item_no,
            int(r.rank),
            r.contract_number,
            pd.Timestamp(r.bid_open_date).date(),
            r.district,
            float(r.quantity),
            float(r.unit_price),
            round(float(r.unit_price_in_query_dollars), 2),
            r.source,
        ]
        for j, v in enumerate(vals, start=1):
            c = wc.cell(row=i, column=j, value=v)
            if j in (7, 8):
                c.number_format = MONEY
            if j == 9:
                c.hyperlink = v
    wc.freeze_panes = "A2"

    # --- Risk register
    from bidlens.documents.extract import TABLES

    wr = wb.create_sheet("Risk register")
    _header(
        wr,
        1,
        [
            "Topic",
            "Finding",
            "Value",
            "Document",
            "PDF page",
            "Printed page",
            "Section",
            "Quote",
            "Priced? (estimator)",
            "Notes (estimator)",
        ],
        [22, 60, 18, 26, 9, 9, 12, 60, 12, 30],
    )
    f = items[~items["category"].isin(TABLES)] if len(items) else items
    if len(f):
        from bidlens.documents.review import tidy

        f = tidy(mask(f))  # same check as the app
    for i, r in enumerate(f.itertuples(), start=2):
        vals = [
            r.category_name,
            f"As written: {r.statement}" if r.as_quoted else r.statement,
            r.value,
            r.document,
            int(r.page),
            r.printed_page,
            r.section_number,
            r.evidence,
            None,
            None,
        ]
        for j, v in enumerate(vals, start=1):
            wr.cell(row=i, column=j, value=v).alignment = Alignment(wrap_text=True, vertical="top")
    wr.freeze_panes = "A2"
    wr.auto_filter.ref = f"A1:J{max(len(f) + 1, 2)}"

    # --- Closure hours and late closure damages
    wh = wb.create_sheet("Closure hours")
    _header(wh, 1, ["Chart and hours", "PDF page"], [120, 9])
    tab = (
        items[items["category"].isin(["closure_hours", "closure_damages"])] if len(items) else items
    )
    for i, r in enumerate(tab.itertuples(), start=2):
        wh.cell(row=i, column=1, value=r.statement).alignment = Alignment(wrap_text=True)
        wh.cell(row=i, column=2, value=int(r.page))

    # --- About
    wa = wb.create_sheet("About")
    notes = [
        "BidLens draft estimate. A starting point for an estimator, not a bid.",
        "Unit prices are in bid-date dollars, from public Caltrans bid history.",
        f"{s['model_lines']} of {s['lines']} items are priced by the pricing model (Kumo "
        "Tabular, refreshed each quarter on all earlier bids) with a low to high range; the "
        "rest from earlier low bids for the same item (see 'Priced from').",
        "Comparable bids link to their Caltrans source pages (sv08data.dot.ca.gov).",
        f"Document findings were read on this computer by {model}; each cites its page. "
        "Check the page before relying on a finding.",
        "No bidder names are included.",
    ]
    wa.column_dimensions["A"].width = 120
    for i, n in enumerate(notes, start=1):
        wa.cell(row=i, column=1, value=n).alignment = Alignment(wrap_text=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    ap.add_argument("--out", default="outputs/21_app")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"draft_estimate_{args.contract}.xlsx"
    path.write_bytes(workbook(args.contract))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
