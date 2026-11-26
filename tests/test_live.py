"""The live engine: real pricing on the committed bundle, uploads and the bid check."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from bidlens.live.bundle import BUNDLE, load
from bidlens.live.engine import Engine, Job, UploadError, check, read_upload, upload_job

pytestmark = pytest.mark.skipif(not (BUNDLE / "meta.json").exists(), reason="no bundle")


@pytest.fixture(scope="module")
def eng():
    return Engine(load(), model="lightgbm", use_saved=False)


def test_bundle_is_small_and_has_no_bidder_names():
    size = sum(p.stat().st_size for p in BUNDLE.iterdir())
    assert size < 5e6
    b = load()
    cols = {c.lower() for df in (b.bids, b.lines, b.contracts) for c in df.columns}
    assert not any("bidder_name" in c or "phone" in c or "address" in c for c in cols)


def test_test_contracts_cover_2024_to_2026(eng):
    tc = eng.test_contracts()
    assert len(tc) > 150
    assert tc["bid_open_date"].min() >= pd.Timestamp("2024-01-01")
    assert "04-0W0504" in set(tc["contract_number"])


def test_contract_is_priced_only_from_earlier_bids(eng):
    job = eng.contract_job("04-0W0504")
    items = eng.load_items(job)
    assert items.attrs["earlier_bids"] == int((eng.clean["bid_open_date"] < job.cutoff).sum())
    est, mk = eng.evaluate(job)
    assert est.attrs["model_rows"] == items.attrs["earlier_bids"]
    assert (est["pred_unit_price"] > 0).all()
    total = est["pred_amount"].sum()
    assert 0.7 < total / job.actual["low_bid"] < 1.4
    model = est["tier"] == 0
    assert (est.loc[model, "low"] < est.loc[model, "pred_unit_price"]).all()
    assert (est.loc[model, "high"] > est.loc[model, "pred_unit_price"]).all()
    assert set(est["check"]) <= {"inside", "above", "below", "no range", "no price"}
    assert mk["bidders"]["low"] <= mk["bidders"]["likely"] <= mk["bidders"]["high"]
    assert mk["low_bid"]["low"] < mk["low_bid"]["high"]


def test_check_labels():
    est = pd.DataFrame(
        {
            "check_price": [5, 15, 25, 10, np.nan],
            "low": [10, 10, 10, np.nan, 10],
            "high": [20, 20, 20, np.nan, 20],
        }
    )
    assert check(est).tolist() == ["below", "inside", "above", "no range", "no price"]


def test_upload_matches_columns_loosely_and_fills_units(eng):
    csv = "Item No,Desc,Qty,Your Unit Price\n999990,,,250000\n390132,HMA,1200,$140.50\n"
    df = read_upload("bid.csv", csv.encode())
    assert df["item_code"].tolist() == ["999990", "390132"]
    assert df["your_unit_price"].tolist() == [250000, 140.5]
    job = upload_job(eng, df, {"bid_date": "2026-11-20", "district": "04"})
    assert job.lines["unit"].tolist() == ["LS", "TON"]  # from the Caltrans item list
    est, mk = eng.evaluate(job)
    assert set(est["check"]) <= {"inside", "above", "below", "no range"}
    assert "low_bid" not in mk and mk["bidders"]["likely"] >= 1  # no estimate given


def test_upload_with_every_column(eng):
    csv = (
        "Item code,Description,Unit,Quantity,Your unit price\n"
        "999990,MOBILIZATION,LS,,400000\n390132,HOT MIX ASPHALT (TYPE A),TON,4200,155\n"
    )
    job = upload_job(eng, read_upload("b.csv", csv.encode()), {"engineers_estimate": 2e6})
    est, mk = eng.evaluate(job)
    assert len(est) == 2 and "low_bid" in mk


def test_upload_from_excel(eng):
    buf = io.BytesIO()
    pd.DataFrame({"Code": ["390132"], "Unit": ["TON"], "Quantity": [500]}).to_excel(
        buf, index=False
    )
    df = read_upload("bid.xlsx", buf.getvalue())
    assert df.loc[0, "quantity"] == 500


def test_upload_errors_are_plain():
    with pytest.raises(UploadError, match="item code"):
        read_upload("x.csv", b"foo,bar\n1,2\n")
    with pytest.raises(UploadError, match="limit"):
        read_upload("x.csv", ("code\n" + "390132\n" * 1001).encode())


def test_upload_needs_quantity(eng):
    df = read_upload("x.csv", b"code,unit\n390132,TON\n")
    with pytest.raises(UploadError, match="unit and quantity"):
        upload_job(eng, df, {})


def test_job_cutoff():
    j = Job(
        label="x", bid_date=pd.Timestamp("2025-05-20"), lines=pd.DataFrame(), contract_number="04-X"
    )
    assert j.cutoff == pd.Timestamp("2025-04-01")
    j.contract_number = None
    assert j.cutoff == pd.Timestamp("2025-05-20")


def test_listed_jobs_match_the_track_record_exactly():
    """Listed jobs read the track record's saved Kumo prices: every draft total equals the
    published production total."""
    from bidlens.live.bundle import ROOT

    path = ROOT / "outputs" / "13_model_comparison" / "contract_totals_refreshed.csv"
    totals = pd.read_csv(path, parse_dates=["bid_open_date"])
    saved = Engine(load(), model="lightgbm")  # model only used for uploads here
    tc = saved.test_contracts()
    assert len(tc) == len(totals)
    for r in totals.itertuples():
        job = saved.contract_job(r.contract_number, r.bid_open_date)
        est = saved.build_ranges(job, saved.price_items(job, saved.load_items(job)))
        assert est.attrs["saved"] and est.attrs["model"] == "kumo"
        assert est["pred_amount"].sum() == pytest.approx(r.production_total, rel=1e-9)
        model = est[est["tier"] == 0]
        assert (model["range_kind"] == "model").all()
        assert (model["low"] <= model["pred_unit_price"]).all()
