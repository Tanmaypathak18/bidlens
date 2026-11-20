"""Read Caltrans Bid Summary PDFs (decision D-021).

Layout notes are in docs/results/source_review.md (Source 3). Only market-level fields
are kept: no bidder names, addresses, phone numbers or IDs are stored.
"""

from __future__ import annotations

import re
from dataclasses import asdict, astuple, dataclass, field
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
    "engineers_estimate": r"Engineers Est:\s*\$?([\d,]+\.\d{2})",
    "pct_over_under": r"% Over/Under Est:\s*(-?[\d,.]+)%",
}
_REQUIRED = ("contract_number", "bid_open_date", "engineers_estimate", "n_bidders_reported")

# "1 $6,368,565.50 VC..." or "1 Cost: $7,965,469.13 VC..." (rank missing on irregular bids)
_BID_RE = re.compile(r"^(?:(\d{1,2})\s+)?(?:Cost:\s*|A\)\s*)?\$([\d,]+\.\d{2})\s+VC\w*", re.M)
_TIME_RE = re.compile(r"^(?:Time:|B\))\s*([\d,]+)\s*Days\s*[x*]\s*\$?([\d,]+(?:\.\d{2})?)", re.M)
_TOTAL_RE = re.compile(r"^(?:Total:|A\+B\))\s*\$([\d,]+\.\d{2})", re.M)
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

    duplicate_item_lines: int = 0

    def __post_init__(self) -> None:
        """Drop item rows repeated verbatim (seen at some page breaks)."""
        seen: set[tuple] = set()
        kept: list[ItemLine] = []
        for item in self.low_items:
            key = astuple(item)
            if key in seen:
                self.duplicate_item_lines += 1
                continue
            seen.add(key)
            kept.append(item)
        self.low_items = kept

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
    """Parse the extracted text of each page (either layout)."""
    pages = [p.replace("(cid:13)", "") for p in pages]
    if pages and _LEGACY_MARK in pages[0]:
        return parse_legacy_text(pages, source_file)
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


# --------------------------------------------------------------------------- legacy layout
# Older summaries (roughly before 2023) are a fixed-width mainframe report ("BID211").

_LEGACY_MARK = "B I D S U M M A R Y"
_LEGACY_LOW_MARK = "C O N T R A C T P R O P O S A L O F L O W B I D D E R"
_LEGACY_STOP_MARKS = ("L I S T O F S U B", "S U M M A R Y O F R E M A I N I N G", _LEGACY_LOW_MARK)
_LEGACY_HEADER = {
    "contract_number": r"CONTRACT NUMBER\s+(\d{2}-[0-9A-Z]{6})",
    "bid_open_date": r"BID OPENING DATE\s+(\d{2}/\d{2}/\d{2})",
    "n_items": r"(\d+)\s+CONTRACT ITEMS",
    "location": r"LOCATION\s+(\S+)",
    "proposals_issued": r"PROPOSALS ISSUED\s+(\d+)",
    "working_days": r"TOTAL NUMBER OF WORKING DAYS\s+([\d,]+)",
    "n_bidders_reported": r"NUMBER OF BIDDERS\s+(\d+)",
    "engineers_estimate": r"ENGINEERS EST\s+([\d,]+\.\d{2})",
}
_LEGACY_PCT = re.compile(r"PERCENT (OVER|UNDER) EST\s+([\d.]+)")
_LEGACY_BID = re.compile(r"^(?:(\d{1,2})\s+)?(?:A\)\s*)?([\d,]+\.\d{2})\s+\d{1,3}\s+\S")
_LEGACY_TIME = re.compile(r"^B\)\s*([\d,]+)\s*DAYS\s*X\s*([\d,.]+)")
_LEGACY_TOTAL = re.compile(r"^A\+B\)\s*([\d,]+\.\d{2})")
_LEGACY_ITEM_START = re.compile(r"^\d{1,4}\s+(?:\(?F\)?\s+)?\d{6}\s")
_LEGACY_ITEM = re.compile(
    r"^(\d{1,4})\s+(?:\(?(F)\)?\s+)?(\d{6})\s+(.*?)\s+(\S+)\s+"
    r"(LUMP SUM|[\d,]*\.?\d+)\s+([\d,]*\.\d{2})\s+([\d,]*\.\d{2})(?:\s+(.*))?$"
)
_LEGACY_PAGE_HEADER = re.compile(
    r"(BID211|PAGE \d+$|^\d{2}/\d{2}/\d{2}\s+\d{2}/\d{2}/\d{2}$|^-{10,}|^ITEM\s+ITEM|^NO\.\s+CODE)"
)


def _legacy_num(text: str) -> float:
    text = text.replace(",", "")
    return float(text) if text not in ("", ".") else 0.0


def parse_legacy_text(pages: list[str], source_file: str = "") -> BidSummary:
    page1 = pages[0]
    found = {
        k: (m.group(1) if (m := re.search(p, page1)) else None) for k, p in _LEGACY_HEADER.items()
    }
    missing = [k for k in _REQUIRED if not found[k]]
    if missing:
        raise BidSummaryError(f"missing header fields (older layout): {missing}")
    pct = None
    if m := _LEGACY_PCT.search(page1):
        pct = float(m.group(2)) * (1 if m.group(1) == "OVER" else -1)

    bids: list[Bid] = []
    for text in pages:
        head, stop = text, None
        for mark in _LEGACY_STOP_MARKS:
            if mark in head:
                head, stop = head.split(mark)[0], mark
        in_list = "BID RANK" in text or text is pages[0] or not bids
        if in_list or bids:
            for line in head.splitlines():
                line = line.strip()
                if bm := _LEGACY_BID.match(line):
                    rank = int(bm.group(1)) if bm.group(1) else None
                    bids.append(Bid(rank=rank, cost=_num(bm.group(2))))
                elif bids and (tm := _LEGACY_TIME.match(line)):
                    bids[-1].time_days = int(_num(tm.group(1)))
                    bids[-1].time_rate = _num(tm.group(2))
                elif bids and (am := _LEGACY_TOTAL.match(line)):
                    bids[-1].total = _num(am.group(1))
        if stop:
            break

    # Item lines: join wrapped description lines until the next item or TOTAL.
    body: list[str] = []
    started = False
    for text in pages:
        if _LEGACY_LOW_MARK in text:
            started = True
        elif started:
            break
        if not started:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line and not _LEGACY_PAGE_HEADER.search(line) and _LEGACY_LOW_MARK not in line:
                body.append(line)
    items: list[ItemLine] = []
    unparsed: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        joined = " ".join(current)
        m = _LEGACY_ITEM.match(current[0]) or _LEGACY_ITEM.match(joined)
        if m:
            no, flag, code, desc, unit, qty, price, amount, tail = m.groups()
            extra = " ".join(current[1:]) if _LEGACY_ITEM.match(current[0]) else (tail or "")
            items.append(
                ItemLine(
                    item_no=no.zfill(4),
                    flag=flag,
                    item_code=code,
                    description=" ".join(f"{desc} {extra}".split()),
                    unit=unit,
                    quantity=None if qty == "LUMP SUM" else _legacy_num(qty),
                    unit_price=_legacy_num(price),
                    amount=_legacy_num(amount),
                )
            )
        else:
            unparsed.append(joined[:120])
        current.clear()

    for line in body:
        if line.startswith("TOTAL"):
            flush()
            break
        if _LEGACY_ITEM_START.match(line):
            flush()
        if _LEGACY_ITEM_START.match(line) or current:
            current.append(line)
    flush()

    district, county = _location_parts(found["location"])
    return BidSummary(
        source_file=source_file,
        contract_number=found["contract_number"],
        bid_open_date=datetime.strptime(found["bid_open_date"], "%m/%d/%y").date(),
        project_id=None,
        location=found["location"].rstrip(",") if found["location"] else None,
        district=district,
        county=county,
        n_items=int(found["n_items"]) if found["n_items"] else None,
        proposals_issued=int(found["proposals_issued"]) if found["proposals_issued"] else None,
        working_days=int(_num(found["working_days"])) if found["working_days"] else None,
        n_bidders_reported=int(found["n_bidders_reported"]),
        engineers_estimate=_num(found["engineers_estimate"]),
        pct_over_under=pct,
        type_of_work=None,  # wrapped into the project description; taken from sv08data instead
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
