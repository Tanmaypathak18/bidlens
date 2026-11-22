"""Parser, cache and fetcher tests for the sv08data scraper (step 1.2)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import httpx
import pytest

from bidlens.ingest.cache import RawCache, cache_key
from bidlens.ingest.caltrans import (
    Fetcher,
    Scope,
    contract_list,
    plan_bids,
    plan_contract_list,
    results_params,
    write_parquet,
)
from bidlens.ingest.parse_sv08 import (
    ParseError,
    parse_details,
    parse_results,
    site_error,
)

FIX = Path(__file__).parent / "fixtures" / "caltrans"


def fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8", errors="replace")


# ----------------------------------------------------------------- parsers


def test_parse_results_all_bidders() -> None:
    rows = parse_results(fixture("results_item_district_year.html"))
    assert len(rows) == 68
    first = rows[0]
    assert first.item_code == "390132"
    assert first.item_description == "HOT MIX ASPHALT (TYPE A)"
    assert first.unit == "TON"
    assert first.district == "05"
    assert first.contract_number == "05-1R2904"
    assert first.bid_open_date == date(2025, 2, 19)
    assert first.bid_rank == 1
    assert first.quantity * first.unit_price == pytest.approx(first.total)
    assert all(r.district == "05" and r.bid_open_date.year == 2025 for r in rows)
    assert len({r.row_id for r in rows}) == len(rows)


def test_parse_results_awarded_list() -> None:
    rows = parse_results(fixture("results_awarded_contract_list.html"))
    assert len(rows) == 16
    assert {r.item_code for r in rows} == {"999990"}
    assert len(contract_list(rows)) == 16


def test_parse_details() -> None:
    d = parse_details(fixture("contract_item_details.html"))
    assert d.contract_number == "04-1Q7004"
    assert d.bid_open_date == date(2025, 1, 7)
    assert d.location == "SON-101-22.8/32.8"
    assert d.county == "SON"
    assert d.type_of_work.startswith("REPLACE BRIDGE RAILING")


def test_site_error_detected_on_http_200_page() -> None:
    html = fixture("results_error_invalid_year.html")
    assert site_error(html) == "Invalid year(s) specified!"
    with pytest.raises(ParseError):
        parse_results(html)


def test_normal_pages_are_not_errors() -> None:
    for name in ("search_form.html", "results_item_district_year.html", "code_search.html"):
        assert site_error(fixture(name)) is None


def test_parse_results_rejects_unrelated_page() -> None:
    with pytest.raises(ParseError):
        parse_results(fixture("code_search.html"))


# ----------------------------------------------------------------- scope and plan


def test_scope_and_plan(tmp_path: Path) -> None:
    p = tmp_path / "scope.yaml"
    p.write_text(
        "districts: [4, 5]\nyears: [2024, 2025]\n"
        "contract_list_items: ['999990']\nitems: [{code: '390132'}, '120100']\n"
    )
    scope = Scope.load(p)
    assert scope.districts == ["04", "05"]
    assert len(list(plan_contract_list(scope))) == 2
    assert len(list(plan_bids(scope))) == 2 * 2 * 2
    params = results_params("390132", ["04"], [2025], ob=0)
    assert ("Year[]", "y2025") in params  # the site needs the y prefix


def test_scope_rejects_fast_rate(tmp_path: Path) -> None:
    p = tmp_path / "scope.yaml"
    p.write_text(
        "districts: [4]\nyears: [2025]\ncontract_list_items: []\nitems: []\nmin_interval_s: 0.5\n"
    )
    with pytest.raises(ValueError):
        Scope.load(p)


def test_project_scope_file_loads() -> None:
    scope = Scope.load(Path(__file__).parents[1] / "config" / "scope.yaml")
    assert scope.districts == ["04", "05"]
    assert len(scope.items) == 100
    assert scope.min_interval_s >= 1.0


# ----------------------------------------------------------------- cache


def test_cache_round_trip_and_resume(tmp_path: Path) -> None:
    params = results_params("390132", ["04"], [2025], ob=0)
    cache = RawCache(tmp_path)
    cache.record("results.php", params, status="ok", http_status=200, body="<html>x</html>")
    reopened = RawCache(tmp_path)
    entry = reopened.entry("results.php", params)
    assert entry is not None and entry.status == "ok"
    assert reopened.read(entry) == "<html>x</html>"
    assert entry.key == cache_key("results.php", list(reversed(params)))  # order-independent


# ----------------------------------------------------------------- fetcher


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def make_fetcher(tmp_path: Path, handler, **kw) -> tuple[Fetcher, FakeClock]:
    fc = FakeClock()
    client = httpx.Client(
        base_url="https://sv08data.dot.ca.gov/", transport=httpx.MockTransport(handler)
    )
    f = Fetcher(
        RawCache(tmp_path), client=client, sleep=fc.sleep, clock=fc.clock, min_interval_s=2.0, **kw
    )
    return f, fc


def test_fetcher_caches_and_spaces_requests(tmp_path: Path) -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(200, text=fixture("results_awarded_contract_list.html"))

    f, fc = make_fetcher(tmp_path, handler)
    a = results_params("999990", ["05"], [2026], ob=1)
    b = results_params("120100", ["05"], [2026], ob=1)
    assert f.get("results.php", a) is not None
    assert f.get("results.php", b) is not None
    assert f.get("results.php", a) is not None  # served from cache
    assert len(calls) == 2
    assert fc.sleeps == [2.0]  # second request waited the minimum gap


def test_fetcher_retries_5xx_then_succeeds(tmp_path: Path) -> None:
    responses = iter(
        [
            httpx.Response(500),
            httpx.Response(503),
            httpx.Response(200, text=fixture("contract_item_details.html")),
        ]
    )
    f, fc = make_fetcher(tmp_path, lambda req: next(responses))
    body = f.get("details.php", [("Num", "5014594")])
    assert body is not None and "04-1Q7004" in body
    assert 60.0 in fc.sleeps and 120.0 in fc.sleeps
    assert f.cache.entry("details.php", [("Num", "5014594")]).status == "ok"


def test_fetcher_gives_up_and_records_http_error(tmp_path: Path) -> None:
    f, fc = make_fetcher(tmp_path, lambda req: httpx.Response(500))
    assert f.get("details.php", [("Num", "1")]) is None
    assert f.requests_made == 4
    assert f.cache.entry("details.php", [("Num", "1")]).status == "http_error"


def test_fetcher_reconnects_quickly_after_dropped_connection(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("Server disconnected", request=req)
        return httpx.Response(200, text=fixture("contract_item_details.html"))

    f, fc = make_fetcher(tmp_path, handler)
    assert f.get("details.php", [("Num", "5014594")]) is not None
    assert f.requests_made == 2
    assert max(fc.sleeps) <= 2.0  # no 60 s backoff


def test_fetcher_backs_off_after_repeated_drops(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("Server disconnected", request=req)

    f, fc = make_fetcher(tmp_path, handler)
    assert f.get("details.php", [("Num", "1")]) is None
    assert f.requests_made == 5  # one quick retry + 4 backoff attempts
    assert 60.0 in fc.sleeps


def test_fetcher_no_retry_on_404(tmp_path: Path) -> None:
    f, _ = make_fetcher(tmp_path, lambda req: httpx.Response(404))
    assert f.get("nope.php", []) is None
    assert f.requests_made == 1


def test_fetcher_records_site_error_without_retry(tmp_path: Path) -> None:
    html = fixture("results_error_invalid_year.html")
    f, _ = make_fetcher(tmp_path, lambda req: httpx.Response(200, text=html))
    params = [("item", "390132"), ("Year[]", "2025")]
    assert f.get("results.php", params) is None
    assert f.get("results.php", params) is None  # not re-fetched
    assert f.requests_made == 1
    entry = f.cache.entry("results.php", params)
    assert entry.status == "site_error" and entry.message == "Invalid year(s) specified!"


def test_fetcher_refuses_disallowed_host(tmp_path: Path) -> None:
    client = httpx.Client(base_url="https://ppmoe.dot.ca.gov/")
    with pytest.raises(ValueError):
        Fetcher(RawCache(tmp_path), client=client)


# ----------------------------------------------------------------- output


def test_write_parquet_dedupes(tmp_path: Path) -> None:
    rows = [r.as_dict() for r in parse_results(fixture("results_item_district_year.html"))]
    from bidlens.ingest.caltrans import _BID_SCHEMA

    out = tmp_path / "bids.parquet"
    assert write_parquet(rows + rows, _BID_SCHEMA, out) == 68
    con = duckdb.connect()
    n = con.execute(f"SELECT count(DISTINCT contract_number) FROM '{out}'").fetchone()[0]
    con.close()
    assert n > 1


def test_county_with_district_prefix() -> None:
    from bidlens.ingest.parse_sv08 import _county

    assert _county("SON-101-22.8/32.8") == "SON"
    assert _county("04-ALA-880-20.9/20.9") == "ALA"
    assert _county("05-SB-101,217-Var") == "SB"
