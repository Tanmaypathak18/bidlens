"""Collect Caltrans item bids from the Contract Cost Data site (sv08data.dot.ca.gov).

Decisions: D-012 (method), D-013 (rate), D-015 (contract list), D-017 (cache),
D-018 (retries). Never point this at ppmoe.dot.ca.gov (robots.txt disallows it).

Usage:
    uv run python -m bidlens.ingest.caltrans all --scope config/scope.yaml
    uv run python -m bidlens.ingest.caltrans bids --limit 5      # smoke run
    uv run python -m bidlens.ingest.caltrans all --dry-run        # count requests only
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import httpx
import yaml

from bidlens.ingest.cache import Params, RawCache
from bidlens.ingest.parse_sv08 import (
    BidRow,
    ContractDetail,
    ParseError,
    parse_details,
    parse_results,
    site_error,
)

log = logging.getLogger("bidlens.ingest")

BASE_URL = "https://sv08data.dot.ca.gov/"
USER_AGENT = "BidLens-research/0.1 (public-data study)"
FORBIDDEN_HOSTS = ("ppmoe.dot.ca.gov",)
RETRY_WAITS = (60.0, 120.0, 240.0)  # D-018: 4 attempts in total


# --------------------------------------------------------------------------- scope


@dataclass
class Scope:
    districts: list[str]
    years: list[int]
    items: list[str]
    contract_list_items: list[str]
    min_interval_s: float = 2.0
    notes: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Scope:
        raw = yaml.safe_load(Path(path).read_text())
        scope = cls(
            districts=[f"{int(d):02d}" for d in raw["districts"]],
            years=[int(y) for y in raw["years"]],
            items=[str(i["code"]) if isinstance(i, dict) else str(i) for i in raw["items"]],
            contract_list_items=[str(i) for i in raw["contract_list_items"]],
            min_interval_s=float(raw.get("min_interval_s", 2.0)),
        )
        if scope.min_interval_s < 1.0:
            raise ValueError("min_interval_s must be at least 1 second (project rule)")
        return scope


def results_params(item: str, districts: list[str], years: list[int], ob: int) -> Params:
    p: Params = [("item", item), ("ob", str(ob))]
    p += [("DISTRICT[]", d) for d in districts]
    p += [("Year[]", f"y{y}") for y in years]
    p += [("unit", "none"), ("start", "Search")]
    return p


# --------------------------------------------------------------------------- fetching


class Fetcher:
    """One request at a time, a minimum gap between requests, cached, with retries."""

    def __init__(
        self,
        cache: RawCache,
        *,
        min_interval_s: float = 2.0,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        retry_errors: bool = False,
    ) -> None:
        self.cache = cache
        self.min_interval_s = min_interval_s
        self.client = client or httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(120.0, connect=20.0),
            follow_redirects=True,
        )
        if any(h in str(self.client.base_url) for h in FORBIDDEN_HOSTS):
            raise ValueError("automated requests to this host are not allowed (D-013)")
        self.sleep = sleep
        self.clock = clock
        self.retry_errors = retry_errors
        self._last_request: float | None = None
        self.requests_made = 0

    def _wait_turn(self) -> None:
        if self._last_request is not None:
            gap = self.clock() - self._last_request
            if gap < self.min_interval_s:
                self.sleep(self.min_interval_s - gap)
        self._last_request = self.clock()

    def get(self, endpoint: str, params: Params) -> str | None:
        """Return the page body (cached or fetched), or None on a site or HTTP error."""
        entry = self.cache.entry(endpoint, params)
        if entry is not None and (entry.status == "ok" or not self.retry_errors):
            return self.cache.read(entry) if entry.status == "ok" else None

        last_error = ""
        quick_retry_used = False
        attempt = 0
        while attempt <= len(RETRY_WAITS):
            self._wait_turn()
            self.requests_made += 1
            try:
                resp = self.client.get(endpoint, params=params)
            except httpx.RemoteProtocolError as exc:
                last_error, status = f"{type(exc).__name__}: {exc}", None
                if not quick_retry_used:
                    # D-020: a dropped keep-alive connection; reconnect after the normal gap.
                    quick_retry_used = True
                    log.info("connection dropped for %s; reconnecting", endpoint)
                    continue
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error, status = f"{type(exc).__name__}: {exc}", None
            else:
                status = resp.status_code
                if status == 200:
                    body = resp.text
                    msg = site_error(body)
                    kind = "ok" if msg is None else "site_error"
                    self.cache.record(
                        endpoint, params, status=kind, http_status=200, body=body, message=msg
                    )
                    if msg:
                        log.warning("site error for %s %s: %s", endpoint, params, msg)
                        return None
                    return body
                last_error = f"HTTP {status}"
                if status != 429 and status < 500:
                    break  # other 4xx: retrying will not help
            if attempt < len(RETRY_WAITS):
                wait = RETRY_WAITS[attempt]
                log.warning("%s for %s; retrying in %.0f s", last_error, endpoint, wait)
                self.sleep(wait)
            attempt += 1
        self.cache.record(
            endpoint, params, status="http_error", http_status=status, message=last_error
        )
        log.error("giving up on %s %s: %s", endpoint, params, last_error)
        return None


# --------------------------------------------------------------------------- stages


def plan_contract_list(scope: Scope) -> Iterator[Params]:
    for item in scope.contract_list_items:
        for d in scope.districts:
            yield results_params(item, [d], scope.years, ob=1)


def plan_bids(scope: Scope) -> Iterator[Params]:
    for item in scope.items:
        for d in scope.districts:
            for y in scope.years:
                yield results_params(item, [d], [y], ob=0)


def collect_results(fetcher: Fetcher, plan: Iterator[Params], limit: int | None) -> list[BidRow]:
    rows: list[BidRow] = []
    for i, params in enumerate(plan):
        if limit is not None and i >= limit:
            break
        body = fetcher.get("results.php", params)
        if body is None:
            continue
        try:
            rows.extend(parse_results(body))
        except ParseError as exc:
            log.error("parse failed for %s: %s", params, exc)
    return rows


def contract_list(rows: list[BidRow]) -> dict[tuple[str, str], BidRow]:
    """One representative row per (contract number, bid open date)."""
    out: dict[tuple[str, str], BidRow] = {}
    for r in sorted(rows, key=lambda r: r.row_id):
        out.setdefault((r.contract_number, r.bid_open_date.isoformat()), r)
    return out


def collect_details(
    fetcher: Fetcher, contracts: dict[tuple[str, str], BidRow], limit: int | None
) -> list[ContractDetail]:
    details: list[ContractDetail] = []
    for i, row in enumerate(contracts.values()):
        if limit is not None and i >= limit:
            break
        body = fetcher.get("details.php", [("Num", str(row.row_id))])
        if body is None:
            continue
        try:
            details.append(parse_details(body))
        except ParseError as exc:
            log.error("details parse failed for %s: %s", row.contract_number, exc)
    return details


# --------------------------------------------------------------------------- output


_BID_SCHEMA = """
    row_id BIGINT, item_code VARCHAR, item_description VARCHAR, unit VARCHAR,
    district VARCHAR, quantity DOUBLE, unit_price DOUBLE, total DOUBLE,
    bid_open_date DATE, contract_number VARCHAR, bid_rank INTEGER
"""
_DETAIL_SCHEMA = """
    contract_number VARCHAR, bid_open_date DATE, location VARCHAR,
    county VARCHAR, type_of_work VARCHAR
"""


def write_parquet(records: list[dict], schema: str, path: Path) -> int:
    """Write records to Parquet with DuckDB, de-duplicated. Returns the row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE t ({schema})")
    if records:
        cols = list(records[0].keys())
        placeholders = ", ".join("?" for _ in cols)
        con.executemany(
            f"INSERT INTO t ({', '.join(cols)}) VALUES ({placeholders})",
            [[r[c] for c in cols] for r in records],
        )
    con.execute(f"COPY (SELECT DISTINCT * FROM t ORDER BY ALL) TO '{path}' (FORMAT parquet)")
    n = con.execute(f"SELECT count(*) FROM '{path}'").fetchone()[0]
    con.close()
    return n


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("stage", choices=["contracts", "bids", "all"])
    ap.add_argument("--scope", type=Path, default=Path("config/scope.yaml"))
    ap.add_argument("--cache", type=Path, default=Path("data/raw/sv08data"))
    ap.add_argument("--out", type=Path, default=Path("data/interim"))
    ap.add_argument("--limit", type=int, help="max requests per stage (smoke runs)")
    ap.add_argument("--retry-errors", action="store_true", help="re-fetch recorded errors")
    ap.add_argument("--dry-run", action="store_true", help="count planned requests and exit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    scope = Scope.load(args.scope)
    if args.dry_run:
        n_list = len(list(plan_contract_list(scope)))
        n_bids = len(list(plan_bids(scope)))
        print(
            f"contract list: {n_list} requests; bids: {n_bids} requests; "
            f"details: one per contract found"
        )
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    cache = RawCache(args.cache)
    fetcher = Fetcher(cache, min_interval_s=scope.min_interval_s, retry_errors=args.retry_errors)
    counts: dict[str, int] = {}

    if args.stage in ("contracts", "all"):
        listed = collect_results(fetcher, plan_contract_list(scope), args.limit)
        contracts = contract_list(listed)
        counts["contract_list_rows"] = len(listed)
        counts["contracts"] = len(contracts)
        log.info("contract list: %d rows, %d contracts", len(listed), len(contracts))
        details = collect_details(fetcher, contracts, args.limit)
        counts["contract_details"] = write_parquet(
            [d.as_dict() for d in details], _DETAIL_SCHEMA, args.out / "sv08_contracts.parquet"
        )
    if args.stage in ("bids", "all"):
        bids = collect_results(fetcher, plan_bids(scope), args.limit)
        counts["bid_rows"] = write_parquet(
            [b.as_dict() for b in bids], _BID_SCHEMA, args.out / "sv08_bids.parquet"
        )

    statuses: dict[str, int] = {}
    for e in cache.entries():
        statuses[e.status] = statuses.get(e.status, 0) + 1
    counts["requests_this_run"] = fetcher.requests_made
    summary = {"counts": counts, "cache_status": statuses}
    (args.out / "ingest_log.json").write_text(json.dumps(summary, indent=2))
    log.info("done: %s", json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
