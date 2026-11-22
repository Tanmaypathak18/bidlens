"""Step 4.2: the draft estimate workbook has live formulas that add up to the draft total."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "data" / "sample" / "app" / "04-0W0504"  # committed


def test_workbook_formulas_recompute_the_draft_total():
    from openpyxl import load_workbook

    from bidlens.export import workbook

    wb = load_workbook(io.BytesIO(workbook("04-0W0504", root=ROOT)))
    assert wb.sheetnames == ["Estimate", "Comparables", "Risk register", "Closure hours", "About"]
    ws = wb["Estimate"]
    top = next(r for r in range(1, 30) if ws.cell(row=r, column=1).value == "Item")
    total = 0.0
    r = top + 1
    while ws.cell(row=r, column=1).value is not None:
        assert ws.cell(row=r, column=10).value == f"=E{r}*G{r}"
        assert ws.cell(row=r, column=15).value == f'=IF(N{r}="",J{r},E{r}*N{r})'
        total += ws.cell(row=r, column=5).value * ws.cell(row=r, column=7).value
        r += 1
    m = re.fullmatch(r"=SUM\(J(\d+):J(\d+)\)", ws.cell(row=r, column=10).value)
    assert m and int(m.group(1)) == top + 1 and int(m.group(2)) == r - 1
    s = json.loads((APP / "summary.json").read_text())
    assert total == pytest.approx(s["estimate_total"], rel=1e-6)
    text = " ".join(str(c.value) for row in wb["Risk register"].iter_rows() for c in row)
    assert not re.search(r"@[A-Za-z0-9.-]+\.[a-z]{2,}", text)  # no email addresses
