"""Step 2.4 test: Kumo Tabular wrapper (skipped when the weights are not cached locally)."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

pytest.importorskip("sdm")


def _cached() -> bool:
    from huggingface_hub import try_to_load_from_cache

    path = try_to_load_from_cache("nvidia/Kumo-Tabular", "small/regressor.pt", revision="v1.0.1")
    return isinstance(path, str) and os.path.exists(path)


SCRIPT = """
import numpy as np, pandas as pd
from bidlens.pricing import features as F
from bidlens.pricing.kumo import KumoPricer
rng = np.random.default_rng(0)
n = 600
X = pd.DataFrame({c: pd.Series(["a"] * n) for c in F.CATEGORICAL})
X["item_code"] = rng.choice(["390132", "120100"], n)
for c in F.NUMERIC:
    X[c] = rng.normal(size=n)
y = np.where(X["item_code"] == "390132", 5.0, 10.0) + 0.5 * X["log_quantity"]
pred = KumoPricer().predict(X[:500], y[:500], X[500:])
print(float(np.median(np.abs(pred - y[500:]))))
"""


@pytest.mark.skipif(not _cached(), reason="Kumo Tabular small weights not downloaded")
def test_kumo_pricer_learns_from_context():
    # Own process: PyTorch and XGBoost/LightGBM must not share one (see features.py).
    out = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, timeout=300, check=True
    )
    assert float(out.stdout.strip().splitlines()[-1]) < 0.3
