"""Price a bid item list live, step by step, from the data bundle.

Every step is real computation on bids opened before the job:

1. `load_items`: read the item list, attach item families, mark the top-100 items.
2. `price_items`: price the top-100 items with Kumo Tabular (in a worker process) or, where
   Kumo is not installed, LightGBM fit on every cleaned earlier low bid; price the rest
   from earlier bids for the same item (history tiers).
3. `build_ranges`: an 80% low to high range. Model items: from the errors of a model fit
   one year earlier on that last year's bids (split conformal, by time). Other items with
   at least 5 earlier prices: the 10th to 90th percentile of those prices.
4. `market_view`: a linear model on earlier contracts for the low bid against the
   engineer's estimate and the number of bidders, with 80% ranges.

The app runs the steps one at a time so the screen fills in as each finishes. A test
contract is priced from bids before its quarter (as in the track record); an uploaded
list from bids before its bid date.

Listed test contracts read their Kumo prices from the track record's own run, saved in the
bundle (`kumo_lines`), so their totals equal the published ones to the cent; everything
else (history tiers, ranges, market view) is still computed when the job is evaluated.
Uploaded lists run Kumo Tabular live in a worker process.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from bidlens.live.bundle import ROOT, Bundle
from bidlens.pricing import features as F
from bidlens.pricing.benchmarks import LinePricer, prepare_lines
from bidlens.pricing.escalate import CostIndex
from bidlens.pricing.setup import CUTOFF, TEST_END, escalate, use_cost_index

MODELS = {
    "kumo": "Kumo Tabular (NVIDIA), run live on this computer",
    "lightgbm": "LightGBM, fit live (the lighter online model)",
}
SAVED_LABEL = "Kumo Tabular (NVIDIA), from the track record's run (computed ahead on a laptop)"
MODEL_NAME = "LightGBM"
COVERAGE = (0.10, 0.90)
CAL_DAYS = 365
MIN_HISTORY_RANGE = 5
MAX_ROWS = 1000
SEED = 2026

TIER_TEXT = {
    0: "Pricing model",
    1: "Recent low bids for this item",
    2: "Earlier low bids for this item code",
    3: "Earlier low bids for the same special item description",
    4: "Typical price for this item family and unit (rough)",
    5: "No price history",
}
WORK_LABELS = {
    "wt_paving": "Paving",
    "wt_bridge": "Bridge",
    "wt_electrical": "Electrical and signals",
    "wt_drainage": "Drainage",
    "wt_safety": "Guardrail and barrier",
    "wt_landscape": "Landscape and erosion",
    "wt_concrete_pavement": "Concrete pavement",
    "wt_signs": "Signs",
    "wt_slope_storm": "Slope and storm repair",
    "wt_pedestrian": "Pedestrian and ADA",
}


# ----------------------------------------------------------------- the job


@dataclass
class Job:
    """What is being evaluated: an item list plus whatever is known about the job."""

    label: str
    bid_date: pd.Timestamp
    lines: pd.DataFrame  # item_no, item_code, description, unit, quantity
    district: str | None = None
    county: str | None = None
    type_of_work: str = ""
    engineers_estimate: float | None = None
    working_days: float | None = None
    plan_holders: float | None = None
    is_a_plus_b: bool = False
    contract_number: str | None = None
    your_prices: pd.Series | None = None  # by item_no; the bid to check
    check_label: str = "Your unit price"
    actual: dict = field(default_factory=dict)  # low bid, second bid, bidders (bid jobs)

    @property
    def cutoff(self) -> pd.Timestamp:
        """Bids before this date are used. Test contracts: the start of their quarter."""
        if self.contract_number:
            return self.bid_date.to_period("Q").start_time
        return self.bid_date


def default_model() -> str:
    """Kumo Tabular wherever it is installed; LightGBM otherwise.
    `BIDLENS_MODEL=lightgbm` forces the lighter model."""
    import importlib.util
    import os

    want = os.environ.get("BIDLENS_MODEL", "").lower()
    if want in MODELS:
        return want
    if importlib.util.find_spec("sdm") is None:
        return "lightgbm"
    return "kumo"


class Engine:
    """Holds the bundle and the fitted models (cached by cutoff date)."""

    def __init__(self, bundle: Bundle, model: str | None = None, use_saved: bool = True) -> None:
        self.b = bundle
        self.model_kind = model or default_model()
        self.use_saved = use_saved and bundle.kumo_lines is not None
        use_cost_index(CostIndex(bundle.cost_index))
        bids = bundle.bids
        self.clean = bids[
            ~bids["low_bidder_disagrees"] & ~bids["is_outlier"] & (bids["unit_price"] > 0)
        ]
        self.pricer = LinePricer(bids, self._history_lines(), bundle.scope)
        self._models: dict[pd.Timestamp, tuple] = {}
        self._finder = None

    def _history_lines(self) -> pd.DataFrame:
        return prepare_lines(self.b.lines, self.b.master[["item_code", "unit", "item_family"]])

    # --------------------------------------------------------------- jobs

    def test_contracts(self) -> pd.DataFrame:
        """Contracts bid in the test years (2024 to 2026) with a full item list."""
        c = self.b.contracts
        have = self.b.lines.groupby(["contract_number", "bid_open_date"]).size().rename("items")
        c = c.merge(have.reset_index(), on=["contract_number", "bid_open_date"], how="inner")
        d = c["bid_open_date"]
        c = c[(d >= pd.Timestamp(CUTOFF)) & (d <= pd.Timestamp(TEST_END))]
        c = c[~c["low_bidder_disagrees"]].copy()
        flags = F.work_type_flags(c["type_of_work"])
        c["work_types"] = [
            ", ".join(WORK_LABELS[k] for k in flags.columns if r[k]) for _, r in flags.iterrows()
        ]
        return c.sort_values(["bid_open_date", "contract_number"], ascending=[False, True])

    def contract_job(self, contract_number: str, bid_open_date=None) -> Job:
        c = self.b.contracts[self.b.contracts["contract_number"] == contract_number]
        if bid_open_date is not None:
            c = c[c["bid_open_date"] == pd.Timestamp(bid_open_date)]
        if c.empty:
            raise KeyError(contract_number)
        r = c.sort_values("bid_open_date").iloc[-1]
        lines = self.b.lines[
            (self.b.lines["contract_number"] == contract_number)
            & (self.b.lines["bid_open_date"] == r["bid_open_date"])
        ]
        lump = lines["quantity"].isna()
        # The actual low bid's unit prices, for the check only (lump sum: the line amount).
        actual_prices = pd.Series(
            np.where(lump, lines["amount"], lines["unit_price"]), index=lines["item_no"]
        )

        def num(x):
            return None if pd.isna(x) else float(x)

        return Job(
            label=f"Contract {contract_number}",
            bid_date=r["bid_open_date"],
            lines=lines[["item_no", "item_code", "description", "unit", "quantity"]].reset_index(
                drop=True
            ),
            district=str(r["district"]),
            county=None if pd.isna(r["county"]) else str(r["county"]),
            type_of_work="" if pd.isna(r["type_of_work"]) else str(r["type_of_work"]),
            engineers_estimate=num(r["engineers_estimate"]),
            working_days=num(r["working_days"]),
            plan_holders=num(r["proposals_issued"]),
            is_a_plus_b=bool(r["is_a_plus_b"]) if pd.notna(r["is_a_plus_b"]) else False,
            contract_number=contract_number,
            your_prices=actual_prices,
            check_label="Actual low bid",
            actual={
                "low_bid": num(r["low_bid_cost"]),
                "second_bid": num(r["second_bid_total"]),
                "low_bid_total": num(r["low_bid_total"]),
                "bidders": None if pd.isna(r["n_bidders"]) else int(r["n_bidders"]),
            },
        )

    # --------------------------------------------------------------- step 1

    def load_items(self, job: Job) -> pd.DataFrame:
        t0 = time.perf_counter()
        df = job.lines.copy()
        df["contract_number"] = job.contract_number or "upload"
        df["bid_open_date"] = job.bid_date
        df["unit_price"] = np.nan
        df["amount"] = np.nan
        items = prepare_lines(df, self.b.master[["item_code", "unit", "item_family"]])
        items["in_scope"] = [
            (c, u) in self.b.scope for c, u in zip(items["item_code"], items["unit"], strict=True)
        ]
        if job.your_prices is not None:
            items["check_price"] = items["item_no"].map(job.your_prices).astype(float)
        items.attrs["seconds"] = time.perf_counter() - t0
        items.attrs["earlier_bids"] = int((self.clean["bid_open_date"] < job.cutoff).sum())
        return items

    # --------------------------------------------------------------- step 2

    def saved_kumo(self, job: Job) -> pd.DataFrame | None:
        """The track record's Kumo prices for this listed contract (by item_no), if saved."""
        if not (self.use_saved and job.contract_number):
            return None
        k = self.b.kumo_lines
        k = k[(k["contract_number"] == job.contract_number) & (k["bid_open_date"] == job.bid_date)]
        quarter = str(job.bid_date.to_period("Q"))
        if k.empty or quarter not in (self.b.kumo_quarters or {}):
            return None
        return k.set_index("item_no")[["q50", "q10", "q90"]]

    def _fit(self, before: pd.Timestamp, after: pd.Timestamp | None = None):
        """LightGBM on cleaned bids opened before `before` (and on or after `after`)."""
        import lightgbm as lgb

        m = self.clean["bid_open_date"] < before
        if after is not None:
            m &= self.clean["bid_open_date"] >= after
        rows = self.clean[m]
        X = rows[F.FEATURES].copy()
        cats = {c: sorted(X[c].dropna().astype(str).unique()) for c in F.CATEGORICAL}
        X = F.as_categories(X, cats)
        cfg = self.b.meta["lightgbm"]
        params = {"objective": "regression", "verbose": -1, "seed": SEED, "num_threads": 2,
                  **cfg["params"]}  # fmt: skip
        model = lgb.train(params, lgb.Dataset(X, rows["y"].to_numpy()), cfg["trees"])
        return model, cats, len(rows)

    def model(self, cutoff: pd.Timestamp) -> dict:
        """The fitted pricing model and its one-year-earlier twin for ranges (cached)."""
        if self.model_kind == "kumo":
            raise RuntimeError("Kumo prices through price_items")
        if cutoff in self._models:
            return {**self._models[cutoff], "reused": True}
        t0 = time.perf_counter()
        main, cats, n = self._fit(cutoff)
        t1 = time.perf_counter()
        start = cutoff - pd.Timedelta(days=CAL_DAYS)
        cal, cal_cats, _ = self._fit(start)
        held = self.clean[
            (self.clean["bid_open_date"] >= start) & (self.clean["bid_open_date"] < cutoff)
        ]
        pred = cal.predict(F.as_categories(held[F.FEATURES].copy(), cal_cats))
        err = held["y"].to_numpy() - pred
        lump = (held["unit"] == "LS").to_numpy()
        spread = {
            ls: tuple(float(np.quantile(err[lump == ls], q)) for q in COVERAGE)
            for ls in (True, False)
            if (lump == ls).sum() >= 20
        }
        res = {
            "main": main,
            "cats": cats,
            "rows": n,
            "fit_seconds": t1 - t0,
            "cal_seconds": time.perf_counter() - t1,
            "cal_rows": len(held),
            "spread": spread,
        }
        self._models[cutoff] = res
        return {**res, "reused": False}

    def _kumo(self, job: Job, X: pd.DataFrame) -> tuple[np.ndarray, dict]:
        """Kumo in a worker process: (log q50, q10, q90 per row), run info."""
        import json
        import subprocess
        import sys
        import tempfile

        cached = self._models.get(("kumo", job.cutoff))
        quarter = str(job.bid_date.to_period("Q"))
        if cached is None and quarter in (self.b.kumo_quarters or {}):
            # The track record's widening for this quarter (calibrated on every earlier
            # priced bid), so uploads get the published range method without a second run.
            cached = {"adjustment": self.b.kumo_quarters[quarter], "cal_rows": 0,
                      "cal_seconds": 0.0, "saved_widening": True}  # fmt: skip
            self._models[("kumo", job.cutoff)] = cached
        with tempfile.TemporaryDirectory() as d:
            X.to_parquet(Path(d) / "query.parquet")
            (Path(d) / "request.json").write_text(json.dumps({
                "cutoff": job.cutoff.isoformat(), "calibrate": cached is None,
                "cal_days": CAL_DAYS,
            }))  # fmt: skip
            r = subprocess.run([sys.executable, "-m", "bidlens.live.kumo_worker", d],
                               capture_output=True, text=True, cwd=ROOT)  # fmt: skip
            if r.returncode:
                raise RuntimeError("Kumo worker failed: " + r.stderr[-800:])
            pred = pd.read_parquet(Path(d) / "result.parquet").to_numpy()
            info = json.loads((Path(d) / "result.json").read_text())
        if cached is None:
            cached = {"adjustment": info["adjustment"], "cal_rows": info["cal_rows"],
                      "cal_seconds": info["cal_seconds"]}  # fmt: skip
            self._models[("kumo", job.cutoff)] = cached
            info["reused"] = False
        else:
            info["reused"] = True
        return pred, {**info, **cached}

    def price_items(self, job: Job, items: pd.DataFrame) -> pd.DataFrame:
        t0 = time.perf_counter()
        priced = self.pricer.price_lines(items)
        priced["source"] = priced["tier"].map(TIER_TEXT)
        sel = priced[priced["in_scope"]].copy()
        if len(sel):
            sel["district"] = job.district
            sel["county"] = job.county
            sel["type_of_work"] = job.type_of_work
            sel["n_items"] = float(len(items))
            sel["working_days"] = job.working_days if job.working_days else np.nan
            sel["engineers_estimate"] = job.engineers_estimate if job.engineers_estimate else np.nan
            saved = self.saved_kumo(job)
            if saved is not None and not sel["item_no"].isin(saved.index).all():
                saved = None
            X = None if saved is not None else F.build(sel, self.b.bids)
            if saved is not None:
                q = saved.loc[sel["item_no"]]
                priced.loc[sel.index, "pred_unit_price"] = q["q50"].to_numpy()
                priced.loc[sel.index, "kumo_q10"] = q["q10"].to_numpy()
                priced.loc[sel.index, "kumo_q90"] = q["q90"].to_numpy()
                quarter = str(job.bid_date.to_period("Q"))
                m = {"rows": int((self.clean["bid_open_date"] < job.cutoff).sum()),
                     "fit_seconds": 0.0, "reused": False, "saved": True,
                     "adjustment": self.b.kumo_quarters[quarter]}  # fmt: skip
            elif self.model_kind == "kumo":
                pred, m = self._kumo(job, X)
                when = sel["bid_open_date"]
                priced.loc[sel.index, "pred_unit_price"] = F.from_ref(np.exp(pred[:, 0]), when)
                priced.loc[sel.index, "kumo_q10"] = F.from_ref(np.exp(pred[:, 1]), when)
                priced.loc[sel.index, "kumo_q90"] = F.from_ref(np.exp(pred[:, 2]), when)
            else:
                m = self.model(job.cutoff)
                log_ref = m["main"].predict(F.as_categories(X, m["cats"]))
                priced.loc[sel.index, "pred_unit_price"] = F.from_ref(
                    np.exp(log_ref), sel["bid_open_date"]
                )
            priced.loc[sel.index, "tier"] = 0
            priced.loc[sel.index, "source"] = TIER_TEXT[0]
        else:
            m = {"rows": int((self.clean["bid_open_date"] < job.cutoff).sum()),
                 "fit_seconds": 0.0, "reused": True}  # fmt: skip
        priced["pred_amount"] = priced["pred_unit_price"] * priced["quantity"]
        saved = bool(m.get("saved"))
        kind = "kumo" if saved else self.model_kind
        priced.attrs = {
            **items.attrs,
            "model": kind,
            "saved": saved,
            "model_label": SAVED_LABEL if saved else MODELS[kind],
            "kumo_adjustment": m.get("adjustment") if kind == "kumo" else None,
            "model_rows": m["rows"],
            "fit_seconds": m["fit_seconds"],
            "reused": m["reused"],
            "run": {k: v for k, v in m.items() if k not in ("main", "cats", "spread")},
            "seconds": time.perf_counter() - t0,
        }
        return priced

    # --------------------------------------------------------------- step 3

    def _history_range(self, row) -> tuple[float, float, int]:
        """10th and 90th percentile of earlier prices for the same item (bid-date dollars)."""
        if row.special:
            hist, key = self.pricer.tier3, (row.desc_key, row.unit)
        else:
            hist, key = self.pricer.tier2, (row.item_code, row.unit)
        grp = hist._groups.get(key)
        if grp is None:
            return np.nan, np.nan, 0
        dates, prices = grp
        on = np.datetime64(pd.Timestamp(row.bid_open_date).date(), "D")
        k = int(np.searchsorted(dates, on, side="left"))
        if k < MIN_HISTORY_RANGE:
            return np.nan, np.nan, k
        p = escalate(prices[:k], dates[:k], on)
        lo, hi = np.quantile(p, COVERAGE)
        return float(lo), float(hi), k

    def build_ranges(self, job: Job, priced: pd.DataFrame) -> pd.DataFrame:
        t0 = time.perf_counter()
        out = priced.copy()
        out["low"], out["high"], out["range_kind"] = np.nan, np.nan, ""
        model = out["tier"] == 0
        kumo = priced.attrs.get("model") == "kumo"
        if kumo:
            spread = priced.attrs.get("kumo_adjustment") or {}
            for ls in (True, False):
                sel = model & ((out["unit"] == "LS") == ls)
                a = spread.get("LS" if ls else "unit")
                if a is not None and sel.any():
                    out.loc[sel, "low"] = out.loc[sel, "kumo_q10"] * np.exp(-a)
                    out.loc[sel, "high"] = out.loc[sel, "kumo_q90"] * np.exp(a)
                    out.loc[sel, "range_kind"] = "model"
        else:
            spread = self.model(job.cutoff)["spread"] if model.any() else {}
        for ls in (True, False) if not kumo else ():
            sel = model & ((out["unit"] == "LS") == ls)
            if ls in spread and sel.any():
                lo, hi = spread[ls]
                out.loc[sel, "low"] = out.loc[sel, "pred_unit_price"] * np.exp(lo)
                out.loc[sel, "high"] = out.loc[sel, "pred_unit_price"] * np.exp(hi)
                out.loc[sel, "range_kind"] = "model"
        for i, r in out[~model & out["tier"].isin([1, 2, 3])].iterrows():
            lo, hi, _ = self._history_range(r)
            if pd.notna(lo):
                out.loc[i, ["low", "high", "range_kind"]] = [lo, hi, "history"]
        out["low_amount"] = out["low"] * out["quantity"]
        out["high_amount"] = out["high"] * out["quantity"]
        out["range_dollars"] = out["high_amount"] - out["low_amount"]
        if "check_price" in out:
            out["check"] = check(out)
        out.attrs = {**priced.attrs, "spread": spread, "ranges_seconds": time.perf_counter() - t0}
        return out

    # --------------------------------------------------------------- step 4

    def market_view(self, job: Job, draft_total: float) -> dict:
        from bidlens.market.context import NUMERIC as MKT
        from bidlens.market.context import features, linear

        t0 = time.perf_counter()
        c = self.b.contracts
        c = c[
            c["has_bid_summary"]
            & (c["engineers_estimate"] > 0)
            & (c["low_bid_cost"] > 0)
            & c["n_bidders"].notna()
            & (c["bid_open_date"] < job.bid_date)
        ].copy()
        c["spread"] = (c["low_bid_cost"] - c["engineers_estimate"]) / c["engineers_estimate"]
        c["bidders"] = c["n_bidders"].astype(float)
        has_ee = bool(job.engineers_estimate)
        target = pd.DataFrame([{
            "contract_id": "job", "bid_open_date": job.bid_date,
            "district": job.district or "04", "county": job.county,
            "type_of_work": job.type_of_work, "n_items": float(len(job.lines)),
            "working_days": job.working_days or np.nan,
            "proposals_issued": job.plan_holders or np.nan,
            "is_a_plus_b": job.is_a_plus_b,
            "engineers_estimate": job.engineers_estimate if has_ee else draft_total,
            "spread": np.nan, "bidders": np.nan,
        }])  # fmt: skip
        df = pd.concat([c, target], ignore_index=True)
        X = features(df)
        cutoff, start = job.cutoff, job.cutoff - pd.Timedelta(days=CAL_DAYS)
        d = df["bid_open_date"]
        fit = (d < cutoff) & df["spread"].notna()
        old, held = (d < start) & fit, (d >= start) & fit
        q = df.index[-1:]
        res = {"contracts": int(fit.sum()), "has_ee": has_ee}
        for t in ("spread", "bidders"):
            if t == "spread" and not has_ee:
                continue
            p = float(linear(X[fit], df.loc[fit, t], X.loc[q], MKT)[0])
            e = df.loc[held, t].to_numpy() - linear(X[old], df.loc[old, t], X[held], MKT)
            lo, hi = np.quantile(e, COVERAGE) if len(e) >= 10 else (np.nan, np.nan)
            res[t] = {"likely": p, "low": p + lo, "high": p + hi}
        if "bidders" in res:
            b = res["bidders"]
            b["likely"], b["low"], b["high"] = (
                max(1.0, round(b[k])) for k in ("likely", "low", "high")
            )
        if has_ee:
            ee = job.engineers_estimate
            s = res["spread"]
            res["low_bid"] = {k: ee * (1 + s[k]) for k in ("likely", "low", "high")}
        # Recent market, for context: last 12 months before the job.
        recent = c[c["bid_open_date"] >= job.bid_date - pd.Timedelta(days=365)]
        res["recent"] = {
            "contracts": len(recent),
            "median_spread": float(recent["spread"].median()) if len(recent) else None,
            "median_bidders": float(recent["bidders"].median()) if len(recent) else None,
        }
        res["seconds"] = time.perf_counter() - t0
        return res

    # --------------------------------------------------------------- comparables

    def comparables(self, job: Job, row) -> pd.DataFrame:
        from bidlens.pricing.comparables import ComparableFinder

        if self._finder is None:
            self._finder = ComparableFinder(self.clean)
        return self._finder.find(
            row.item_code, row.unit, job.cutoff, row.quantity, job.district or "04",
            job.engineers_estimate,
        )  # fmt: skip

    def price_history(self, job: Job, row) -> pd.DataFrame:
        """Earlier low bids for the item, in bid-date dollars: the cleaned top-100 bids, else
        the low bidders' lines in earlier bid summaries (same code, or same description for
        special items)."""
        h = self.clean[
            (self.clean["item_code"] == row.item_code)
            & (self.clean["unit"] == row.unit)
            & (self.clean["bid_open_date"] < job.cutoff)
        ]
        if len(h):
            dates, qty, prices = (
                h["bid_open_date"].to_numpy(),
                h["quantity"].to_numpy(),
                h["unit_price"].to_numpy(float),
            )
        else:
            src = (self.pricer.tier3, (row.desc_key, row.unit)) if row.special else (
                self.pricer.tier2, (row.item_code, row.unit))  # fmt: skip
            grp = src[0]._groups.get(src[1])
            if grp is None:
                return pd.DataFrame(columns=["bid_open_date", "quantity", "unit_price"])
            on = np.datetime64(job.cutoff.date(), "D")
            k = int(np.searchsorted(grp[0], on, side="left"))
            dates, prices, qty = grp[0][:k], grp[1][:k], np.full(k, np.nan)
        return pd.DataFrame({
            "bid_open_date": pd.to_datetime(dates),
            "quantity": qty,
            "unit_price": escalate(prices, dates, job.bid_date),
        })  # fmt: skip

    def evaluate(self, job: Job) -> tuple[pd.DataFrame, dict]:
        """All steps at once (for scripts and tests)."""
        items = self.load_items(job)
        est = self.build_ranges(job, self.price_items(job, items))
        return est, self.market_view(job, float(est["pred_amount"].sum()))


def check(est: pd.DataFrame) -> pd.Series:
    """below / inside / above the range, or "no range" / "no price"."""
    p = est["check_price"]
    out = np.where(
        p.isna() | (p <= 0),
        "no price",
        np.where(
            est["low"].isna(),
            "no range",
            np.where(p < est["low"], "below", np.where(p > est["high"], "above", "inside")),
        ),
    )
    return pd.Series(out, index=est.index)


# ----------------------------------------------------------------- uploads

ALIASES = {
    "item_code": ["itemcode", "code", "item", "itemnumber", "itemno", "bditemcode",
                  "contractitemcode"],
    "description": ["description", "itemdescription", "desc", "name"],
    "unit": ["unit", "units", "uom", "unitofmeasure", "payunit"],
    "quantity": ["quantity", "qty", "estimatedquantity", "quantities"],
    "your_unit_price": ["yourunitprice", "unitprice", "price", "myunitprice", "bidunitprice",
                        "estimatorunitprice"],
}  # fmt: skip


class UploadError(ValueError):
    pass


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def read_upload(name: str, data: bytes) -> pd.DataFrame:
    """A CSV or Excel bid item list -> item_no, item_code, description, unit, quantity and,
    when given, your_unit_price. Raises UploadError with a plain message."""
    import io

    if len(data) > 2_000_000:
        raise UploadError("The file is larger than 2 MB.")
    try:
        if name.lower().endswith((".xlsx", ".xlsm", ".xls")):
            raw = pd.read_excel(io.BytesIO(data), dtype=str)
        else:
            head = data[:2000].decode("utf-8", "ignore").splitlines()[0] if data else ""
            sep = max([",", ";", "\t", "|"], key=head.count) if head else ","
            raw = pd.read_csv(io.BytesIO(data), dtype=str, sep=sep)
    except Exception as e:  # noqa: BLE001 - shown to the user as a plain message
        raise UploadError(f"Could not read the file: {e}") from e
    cols = {}
    for c in raw.columns:
        k = _key(c)
        for target, names in ALIASES.items():
            if target not in cols and k in names:
                cols[target] = c
    if "item_code" not in cols:
        raise UploadError("No item code column found. Name it 'Item code'.")
    if len(raw) > MAX_ROWS:
        raise UploadError(f"The file has {len(raw):,} rows; the limit is {MAX_ROWS:,}.")
    df = pd.DataFrame({t: raw[c] for t, c in cols.items()})
    df["item_code"] = df["item_code"].fillna("").str.strip().str.replace(r"\.0$", "", regex=True)
    df = df[df["item_code"] != ""].copy()
    df["item_code"] = df["item_code"].str.zfill(6)
    if df.empty:
        raise UploadError("No rows with an item code.")

    def number(s):
        return pd.to_numeric(s.astype(str).str.replace(r"[$,\s]", "", regex=True), errors="coerce")

    df["quantity"] = number(df["quantity"]) if "quantity" in df else np.nan
    if "your_unit_price" in df:
        df["your_unit_price"] = number(df["your_unit_price"])
    for c in ("description", "unit"):
        df[c] = df[c].fillna("").str.strip().str.upper() if c in df else ""
    df["unit"] = df["unit"].replace("", None)
    df["description"] = df["description"].replace("", None)
    df.loc[df["unit"] == "LS", "quantity"] = np.nan  # lump sum: one unit
    df["item_no"] = [f"{i:04d}" for i in range(1, len(df) + 1)]
    return df.reset_index(drop=True)


def upload_job(engine: Engine, df: pd.DataFrame, info: dict) -> Job:
    master = engine.b.master.drop_duplicates("item_code").set_index("item_code")
    df = df.copy()
    # Missing units and descriptions come from the Caltrans item list.
    df["unit"] = df["unit"].fillna(df["item_code"].map(master["unit"]))
    df["description"] = df["description"].fillna(df["item_code"].map(master["description"]))
    df["description"] = df["description"].fillna("(no description)")
    bad = df["unit"].isna() | (df["quantity"].isna() & (df["unit"] != "LS"))
    if bad.any():
        miss = ", ".join(df.loc[bad, "item_code"].head(5))
        raise UploadError(f"{int(bad.sum())} rows need a unit and quantity (for example {miss}).")
    prices = None
    if "your_unit_price" in df and df["your_unit_price"].notna().any():
        prices = df.set_index("item_no")["your_unit_price"]
    bid = pd.Timestamp(info.get("bid_date") or date.today())
    return Job(
        label=info.get("label") or "Your bid item list",
        bid_date=bid,
        lines=df[["item_no", "item_code", "description", "unit", "quantity"]],
        district=info.get("district") or "04",
        county=info.get("county") or None,
        type_of_work=info.get("type_of_work") or "",
        engineers_estimate=info.get("engineers_estimate") or None,
        working_days=info.get("working_days") or None,
        your_prices=prices,
    )
