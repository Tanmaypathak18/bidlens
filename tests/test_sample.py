"""D-069: the committed app sample, and the fallback that lets a fresh clone use it."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from bidlens.sample import app_dir, docs_dir

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample" / "app" / "04-0W0504"
CONTACT = re.compile(r"@[A-Za-z0-9.-]+\.[a-z]{2,}|\(?\d{3}\)?[ .-]\d{3}-\d{4}")


def test_built_files_win_and_the_sample_is_the_fallback(tmp_path):
    sample = tmp_path / "data" / "sample" / "app" / "X"
    sample.mkdir(parents=True)
    (sample / "summary.json").write_text("{}")
    assert app_dir("X", tmp_path) == sample
    assert docs_dir("X", tmp_path) == sample

    built = tmp_path / "data" / "interim" / "app" / "X"
    built.mkdir(parents=True)
    (built / "summary.json").write_text("{}")
    (tmp_path / "data" / "interim" / "docs" / "X").mkdir(parents=True)
    assert app_dir("X", tmp_path) == built
    assert docs_dir("X", tmp_path) == tmp_path / "data" / "interim" / "docs" / "X"


def test_committed_sample_is_complete_and_holds_no_contacts():
    names = {p.name for p in SAMPLE.iterdir()}
    assert {
        "summary.json",
        "estimate.parquet",
        "charts.parquet",
        "extraction_combined.json",
    } <= names
    assert sum(p.stat().st_size for p in SAMPLE.iterdir()) < 5e6
    assert not CONTACT.search((SAMPLE / "extraction_combined.json").read_text())
    charts = pd.read_parquet(SAMPLE / "charts.parquet")
    assert not charts.astype(str).apply(lambda c: c.str.contains(CONTACT)).any().any()
