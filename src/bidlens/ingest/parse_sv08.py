"""Parsers for the Caltrans Contract Cost Data site (sv08data.dot.ca.gov).

Page layouts are documented in docs/results/source_review.md. Fixtures for every
page type live in tests/fixtures/caltrans/.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup

_ALERT_RE = re.compile(r"alert\('((?:[^'\\]|\\.)*)'\)")
_MONEY_RE = re.compile(r"[$,\s]")


class ParseError(ValueError):
    """The page did not have the expected layout."""


@dataclass(frozen=True)
class BidRow:
    """One bid on one item, as listed on results.php."""

    row_id: int  # site row number (details.php?Num=...)
    item_code: str
    item_description: str
    unit: str
    district: str
    quantity: float
    unit_price: float
    total: float
    bid_open_date: date
    contract_number: str
    bid_rank: int

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ContractDetail:
    """Contract-level fields shown on details.php."""

    contract_number: str
    bid_open_date: date
    location: str  # County-Route-Postmile, e.g. "SON-101-22.8/32.8"
    county: str
    type_of_work: str

    def as_dict(self) -> dict:
        return asdict(self)


def site_error(html: str) -> str | None:
    """Return the site's error message if the page is an error page, else None.

    The site answers bad queries with HTTP 200 and a page titled "...: ERROR".
    """
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    if not title.upper().endswith("ERROR"):
        return None
    m = _ALERT_RE.search(html)
    if m:
        return m.group(1).replace("\\\\n", " ").replace("\\n", " ").strip()
    return "unknown site error"


def _money(text: str) -> float:
    cleaned = _MONEY_RE.sub("", text)
    if not cleaned:
        raise ParseError(f"empty number: {text!r}")
    return float(cleaned)


def _mdy(text: str) -> date:
    return datetime.strptime(text.strip(), "%m-%d-%Y").date()


_REQUIRED_HEADERS = (
    "Item No. / Description",
    "Unit",
    "Dist",
    "Qty",
    "UnitPrice",
    "Total",
    "Bid OpenDate",
    "ContractNo.",
    "Bid",
)


def _result_table(html: str) -> tuple[list[tuple[int, list[str]]], dict[str, int]]:
    """The bid rows of a results.php page as (row id, cell texts), and the column map."""
    if (msg := site_error(html)) is not None:
        raise ParseError(f"site error page: {msg}")
    soup = BeautifulSoup(html, "html.parser")
    header_row = next(
        (tr for tr in soup.find_all("tr") if tr.find("th") and "Qty" in tr.get_text()),
        None,
    )
    if header_row is None:
        raise ParseError("results table header not found")
    headers = [th.get_text(" ", strip=True).replace(" ", "") for th in header_row.find_all("th")]
    col = {h: i for i, h in enumerate(headers)}
    missing = [h for h in _REQUIRED_HEADERS if h.replace(" ", "") not in col]
    if missing:
        raise ParseError(f"results table missing columns: {missing}")
    rows = []
    for tr in soup.find_all("tr"):
        box = tr.find("input", attrs={"type": "checkbox"})
        if box is None or not str(box.get("name", "")).isdigit():
            continue
        rows.append((int(box["name"]), [td.get_text(" ", strip=True) for td in tr.find_all("td")]))
    return rows, col


def parse_results(html: str) -> list[BidRow]:
    """Parse a results.php page into bid rows. An empty result returns []."""
    table, col = _result_table(html)

    def c(cells: list[str], name: str) -> str:
        return cells[col[name.replace(" ", "")]]

    rows: list[BidRow] = []
    for row_id, cells in table:
        item = c(cells, "Item No. / Description")
        code, _, desc = item.partition(" - ")
        rows.append(
            BidRow(
                row_id=row_id,
                item_code=code.strip(),
                item_description=desc.strip(),
                unit=c(cells, "Unit"),
                district=c(cells, "Dist"),
                quantity=_money(c(cells, "Qty")),
                unit_price=_money(c(cells, "UnitPrice")),
                total=_money(c(cells, "Total")),
                bid_open_date=_mdy(c(cells, "Bid OpenDate")),
                contract_number=c(cells, "ContractNo."),
                bid_rank=int(c(cells, "Bid")),
            )
        )
    return rows


_INDEX_RE = re.compile(r"CURRENT 12-MO INDEX \(([^)]*\)?)\):\s*([\d.]+)")


@dataclass(frozen=True)
class AdjustedPrices:
    """The cost index line and the original vs adjusted price of every row (D-039)."""

    index_name: str  # e.g. "CHCCI (2020 Base)"
    current_index: float  # I(c), the current 12-month index
    rows: list[tuple[str, date, float, float]]  # contract, bid open date, unit price, adjusted


def parse_adjusted(html: str) -> AdjustedPrices:
    """Read the current index and the "Adj Price" column of a results.php page."""
    m = _INDEX_RE.search(html)
    if m is None:
        raise ParseError("current 12-month index line not found")
    table, col = _result_table(html)
    if "AdjPrice" not in col:
        raise ParseError("results table has no Adj Price column")
    rows = [
        (
            cells[col["ContractNo."]],
            _mdy(cells[col["BidOpenDate"]]),
            _money(cells[col["UnitPrice"]]),
            _money(cells[col["AdjPrice"]]),
        )
        for _, cells in table
    ]
    return AdjustedPrices(m.group(1), float(m.group(2)), rows)


def _field(text: str, label: str) -> str:
    m = re.search(rf"{re.escape(label)}\s*:?\s*(.+)", text)
    if not m:
        raise ParseError(f"field not found: {label}")
    return m.group(1).strip()


def _county(location: str) -> str:
    """County code from 'SON-101-22.8' or '04-SON-101-22.8' (some rows lead with the district)."""
    parts = location.split("-")
    if len(parts) > 1 and parts[0].isdigit():
        parts = parts[1:]
    return parts[0].strip().upper()


def parse_details(html: str) -> ContractDetail:
    """Parse a details.php page (one bid row) into its contract-level fields."""
    if (msg := site_error(html)) is not None:
        raise ParseError(f"site error page: {msg}")
    soup = BeautifulSoup(html, "html.parser")
    h2 = soup.find("h2", string=re.compile(r"Project Details For EA"))
    if h2 is None:
        raise ParseError("project details heading not found")
    contract = h2.get_text(strip=True).rsplit(" ", 1)[-1]
    text = soup.get_text("\n")
    location = _field(text, "District-County-Route-Postmile:")
    return ContractDetail(
        contract_number=contract,
        bid_open_date=_mdy(_field(text, "Bid Opening Date (mm-dd-yyyy):")),
        location=location,
        county=_county(location),
        type_of_work=_field(text, "Type of work:"),
    )
