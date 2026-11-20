"""Read Caltrans Bid Summary PDFs (decision D-021).

Layout notes are in docs/results/source_review.md (Source 3). Only market-level fields
are kept: no bidder names, addresses, phone numbers or IDs are stored.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

import pdfplumber

LOW_BIDDER_MARK = "Contract Proposal of Low Bidder"

_HEADER_FIELDS = {
    "contract_number": r"Contract Number:\s*(\S+)",
    "bid_open_date": r"Bid Opening Date:\s*(\d{2}/\d{2}/\d{4})",
    "project_id": r"Project ID:\s*(\S+)",
    "n_items": r"Number of Items:\s*(\d+)",
    "location": r"Location:\s*(\S+)",
    "proposals_issued": r"Proposals Issued:\s*(\d+)",
    "working_days": r"Total Number of Working Days:\s*([\d,]+)",
    "n_bidders_reported": r"Number of Bidders:\s*(\d+)",
    "engineers_estimate": r"Engineers Est:\s*\$([\d,]+\.\d{2})",
    "pct_over_under": r"% Over/Under Est:\s*(-?[\d,.]+)%",
}
_REQUIRED = ("contract_number", "bid_open_date", "engineers_estimate", "n_bidders_reported")

# "1 $6,368,565.50 VC..." or "1 Cost: $7,965,469.13 VC..." (rank missing on irregular bids)
_BID_RE = re.compile(r"^(\d{1,2})?\s*(?:Cost:\s*)?\$([\d,]+\.\d{2})\s+VC\w*", re.M)
_TIME_RE = re.compile(r"^Time:\s*([\d,]+)\s*Days\s*x\s*\$([\d,]+\.\d{2})", re.M)
_TOTAL_RE = re.compile(r"^Total:\s*\$([\d,]+\.\d{2})", re.M)
_ITEM_RE = re.compile(
    r"^(\d{4})\s+(?:([A-Z]{1,2})\s+)?(\d{6})\s+(.+?)\s+(\S+)\s+"
    r"(LUMP SUM|[\d,]+\.\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$"
)
_ITEM_START_RE = re.compile(r"^\d{4}\s")


class BidSummaryError(ValueError):
    """The file is not a readable Caltrans bid summary."""


def _num(text: str) -> float:
    return float(text.replace(",", ""))


@dataclass
class Bid:
    rank: int | None  # None: listed but unranked (most likely an irregular bid)
    cost: float
    time_days: int | None = None
    time_rate: float | None = None
    total: float | None = None  # A+B contracts: cost + time x rate

    @property
    def ranking_amount(self) -> float:
        return self.total if self.total is not None else self.cost


@dataclass
class ItemLine:
    item_no: str
    flag: str | None  # "F" = final pay item
    item_code: str
    description: str
    unit: str
    quantity: float | None  # None for LUMP SUM
    unit_price: float
    amount: float


@dataclass
class BidSummary:
    source_file: str
    contract_number: str
    bid_open_date: date
    project_id: str | None
    location: str | None
    district: str | None
    county: str | None
    n_items: int | None
    proposals_issued: int | None
    working_days: int | None
    n_bidders_reported: int
    engineers_estimate: float
    pct_over_under: float | None
    type_of_work: str | None
    is_a_plus_b: bool
    bids: list[Bid] = field(default_factory=list)
    low_items: list[ItemLine] = field(default_factory=list)
    unparsed_item_lines: list[str] = field(default_factory=list)

    @property
    def ranked_bids(self) -> list[Bid]:
        return sorted((b for b in self.bids if b.rank is not None), key=lambda b: b.rank)

    @property
    def low_bid(self) -> Bid | None:
        ranked = self.ranked_bids
        return ranked[0] if ranked else None

    @property
    def low_items_total(self) -> float:
        return round(sum(i.amount for i in self.low_items), 2)

    def checks(self) -> list[str]:
        """Consistency problems; an empty list means the file reads cleanly."""
        problems = []
        if self.low_bid is None:
            problems.append("no ranked bids")
        if self.n_items is not None and len(self.low_items) != self.n_items:
            problems.append(f"item rows {len(self.low_items)} != Number of Items {self.n_items}")
        if self.low_bid and abs(self.low_items_total - self.low_bid.cost) > 0.01:
            problems.append(
                f"item total {self.low_items_total:,.2f} != low bid cost {self.low_bid.cost:,.2f}"
            )
        if len(self.bids) != self.n_bidders_reported:
            problems.append(f"bids listed {len(self.bids)} != reported {self.n_bidders_reported}")
        if self.unparsed_item_lines:
            problems.append(f"{len(self.unparsed_item_lines)} item lines not parsed")
        return problems

    def contract_record(self) -> dict:
        low = self.low_bid
        second = self.ranked_bids[1] if len(self.ranked_bids) > 1 else None
        return {
            "contract_number": self.contract_number,
            "bid_open_date": self.bid_open_date,
            "project_id": self.project_id,
            "location": self.location,
            "district": self.district,
            "county": self.county,
            "type_of_work": self.type_of_work,
            "n_items": self.n_items,
            "proposals_issued": self.proposals_issued,
            "working_days": self.working_days,
            "n_bidders_reported": self.n_bidders_reported,
            "n_bidders_ranked": len(self.ranked_bids),
            "engineers_estimate": self.engineers_estimate,
            "pct_over_under_reported": self.pct_over_under,
            "is_a_plus_b": self.is_a_plus_b,
            "low_bid_cost": low.cost if low else None,
            "low_bid_total": low.ranking_amount if low else None,
            "second_bid_total": second.ranking_amount if second else None,
            "source_file": self.source_file,
        }

    def as_dict(self) -> dict:
        return asdict(self)


def _location_parts(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    parts = location.rstrip(",").split("-")
    district = parts[0] if parts and parts[0].isdigit() else None
    county = parts[1].upper() if len(parts) > 1 else None
    return district, county


def _type_of_work(page1: str) -> str | None:
    """The free-text line after 'Location: ... Number of Items:' on page 1."""
    lines = page1.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("Location:") and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if not re.match(r"^(NO GOAL|DBE|SBE|DVBE|Federal Aid|Proposals Issued)", nxt):
                return nxt
    return None


def parse_text(pages: list[str], source_file: str = "") -> BidSummary:
    """Parse the extracted text of each page."""
    if not pages or "Bid Summary" not in pages[0]:
        raise BidSummaryError("page 1 is not a Caltrans Bid Summary")
    page1 = pages[0]
    found: dict[str, str | None] = {}
    for key, pat in _HEADER_FIELDS.items():
        m = re.search(pat, page1)
        found[key] = m.group(1) if m else None
    missing = [k for k in _REQUIRED if not found[k]]
    if missing:
        raise BidSummaryError(f"missing header fields: {missing}")

    low_start = next((i for i, t in enumerate(pages) if LOW_BIDDER_MARK in t), len(pages))
    bid_text = "\n".join(pages[:low_start])
    if LOW_BIDDER_MARK in (pages[low_start] if low_start < len(pages) else ""):
        bid_text += "\n" + pages[low_start].split(LOW_BIDDER_MARK)[0]

    bids: list[Bid] = []
    lines = bid_text.splitlines()
    for i, line in enumerate(lines):
        m = _BID_RE.match(line.strip())
        if not m:
            continue
        bid = Bid(rank=int(m.group(1)) if m.group(1) else None, cost=_num(m.group(2)))
        for follow in lines[i + 1 : i + 6]:  # A+B detail lines follow the cost line
            if _BID_RE.match(follow.strip()):
                break
            if t := _TIME_RE.match(follow.strip()):
                bid.time_days, bid.time_rate = int(_num(t.group(1))), _num(t.group(2))
            if tot := _TOTAL_RE.match(follow.strip()):
                bid.total = _num(tot.group(1))
        bids.append(bid)

    items: list[ItemLine] = []
    unparsed: list[str] = []
    for text in pages[low_start:]:
        if LOW_BIDDER_MARK not in text:
            break
        for raw in text.splitlines():
            line = raw.strip()
            m = _ITEM_RE.match(line)
            if m:
                no, flag, code, desc, unit, qty, price, amount = m.groups()
                items.append(
                    ItemLine(
                        item_no=no,
                        flag=flag,
                        item_code=code,
                        description=desc.strip(),
                        unit=unit,
                        quantity=None if qty == "LUMP SUM" else _num(qty),
                        unit_price=_num(price),
                        amount=_num(amount),
                    )
                )
            elif _ITEM_START_RE.match(line):
                unparsed.append(line)

    district, county = _location_parts(found["location"])
    return BidSummary(
        source_file=source_file,
        contract_number=found["contract_number"],
        bid_open_date=datetime.strptime(found["bid_open_date"], "%m/%d/%Y").date(),
        project_id=found["project_id"],
        location=found["location"].rstrip(",") if found["location"] else None,
        district=district,
        county=county,
        n_items=int(found["n_items"]) if found["n_items"] else None,
        proposals_issued=int(found["proposals_issued"]) if found["proposals_issued"] else None,
        working_days=int(_num(found["working_days"])) if found["working_days"] else None,
        n_bidders_reported=int(found["n_bidders_reported"]),
        engineers_estimate=_num(found["engineers_estimate"]),
        pct_over_under=_num(found["pct_over_under"]) if found["pct_over_under"] else None,
        type_of_work=_type_of_work(page1),
        is_a_plus_b=any(b.total is not None for b in bids),
        bids=bids,
        low_items=items,
        unparsed_item_lines=unparsed,
    )


def read_bid_summary(path: Path) -> BidSummary:
    """Read one bid summary PDF."""
    path = Path(path)
    try:
        with pdfplumber.open(path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
    except Exception as exc:  # pdfminer raises many types for broken files
        raise BidSummaryError(f"cannot open PDF: {exc}") from exc
    return parse_text(pages, source_file=path.name)
