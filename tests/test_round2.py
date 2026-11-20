"""Extraction round 2 tests: closure charts from word positions (D-060), pattern rules
(D-062) and the combined merge (D-063). Synthetic text only."""

from __future__ import annotations

import pandas as pd

from bidlens.documents.charts import compact, describe, parse_page
from bidlens.documents.extract import _overlap
from bidlens.documents.patterns import match, sentences


class FakePage:
    def __init__(self, words):
        self.words = words

    def extract_words(self):
        return self.words


def _w(text, x0, top, width=7.0):
    return {"text": text, "x0": x0, "x1": x0 + width, "top": top}


def _chart_page():
    ws = [_w("Chart", 50, 10, 20), _w("No.", 75, 10, 10), _w("J9", 90, 10, 10)]
    ws += [_w("Complete", 50, 20, 30), _w("Ramp", 85, 20, 20), _w("Closure", 110, 20, 25)]
    ws += [_w("County:", 50, 30, 25), _w("ALA", 80, 30, 15), _w("Route/Direction:", 100, 30, 50)]
    ws += [_w("80/EB", 155, 30, 20), _w("Post", 180, 30, 15), _w("Mile:", 200, 30, 15)]
    ws += [_w("7.0", 220, 30, 10)]
    ws += [_w("Hour", 50, 40, 20)]
    # Hour headers 00..24, 18 points apart starting at x=88.
    ws += [_w(f"{h:02d}", 88 + 18 * h, 40, 11) for h in range(25)]
    # Mon-Thu: closed hours 0, 1 and 23. Cells sit between two header centers.
    ws += [_w("Mon–Thu", 45, 52, 40)] + [_w("C", 99 + 18 * h, 52) for h in (0, 1, 23)]
    # Fri: label wrapped onto two lines, closed at hour 2 only.
    ws += [_w("Fri", 60, 64, 12), _w("C", 99 + 18 * 2, 64)]
    ws += [_w("Sun", 60, 76, 12)]  # no closure at all
    ws += [_w("Legend:", 50, 88, 30), _w("C", 55, 100), _w("Ramp", 80, 100, 20)]
    ws += [_w("may", 105, 100, 15), _w("be", 125, 100, 10), _w("closed", 140, 100, 25)]
    ws += [_w("completely.", 170, 100, 40)]
    ws += [_w("R", 50, 112, 5), _w("EMARKS:", 56, 112, 30), _w("Location", 90, 112, 30)]
    ws += [_w("3", 125, 112, 5)]
    return FakePage(ws)


def test_chart_symbols_go_to_their_hour_columns():
    (c,) = parse_page(_chart_page(), 80, "sp.pdf")
    assert c["chart"] == "J9" and c["route"] == "80/EB" and c["remarks"] == "Location 3"
    assert c["rows"] == {"Mon–Thu": {0: "C", 1: "C", 23: "C"}, "Fri": {2: "C"}, "Sun": {}}
    assert c["problems"] == []
    text = describe(c)
    assert "Mon–Thu: ramp may be closed completely: 00:00 to 02:00, 23:00 to 24:00." in text
    assert "Sun: no closure allowed at any hour." in text
    assert compact(c).endswith("Mon–Thu 00 to 02, 23 to 24; Fri 02 to 03; Sun none.")


def test_sentences_keep_abbreviations_and_join_hyphenated_words():
    s = sentences("Meet at 10:00 a.m. at the site.\nUse Bridge No. 33-\n0285 only.")
    assert s == ["Meet at 10:00 a.m. at the site.", "Use Bridge No. 33-0285 only."]


def _chunks(rows):
    return pd.DataFrame([{"chunk_id": cid, "kind": kind, "text": text} for cid, kind, text in rows])


def test_patterns_take_the_addendum_value_and_skip_the_handout():
    c = _chunks(
        [
            (
                "sp:p1:c1",
                "special_provisions",
                "Complete the work within 120 working days. "
                "A mandatory prebid meeting is scheduled on May 4, 2026 at 9:00 a.m. today.",
            ),
            (
                "ad1:p1:c1",
                "addendum",
                "A mandatory prebid meeting is scheduled on May 6, 2026, at 9:00 a.m. instead.",
            ),
            ("ih:p9:c1", "information_handout", "Complete the work within 999 working days."),
        ]
    )
    got = {f["rule"]: f for f in match(c)}
    assert got["working_days"]["statement"] == "Complete the work within 120 working days."
    assert got["prebid"]["chunk_id"] == "ad1:p1:c1"
    assert "was May 4, 2026 at 9:00 a.m" in got["prebid"]["statement"]
    assert all(f["chunk_id"] != "ih:p9:c1" for f in got.values())


def test_overlap_finds_the_same_fact_by_quote_or_by_statement_words():
    a = {
        "category": "t",
        "chunk_id": "x",
        "statement": "Work 600 days.",
        "evidence": "Complete the work within 600 working days.",
    }
    b = {
        "category": "t",
        "chunk_id": "x",
        "statement": "Contract time is 600.",
        "evidence": "within 600 working days",
    }
    c = {
        "category": "t",
        "chunk_id": "y",
        "statement": "Complete the work in 600 days.",
        "evidence": "other",
    }
    d = {
        "category": "t",
        "chunk_id": "z",
        "statement": "Complete the work in 600 days!",
        "evidence": "different",
    }
    assert _overlap(a, b)
    assert not _overlap(a, c)
    assert _overlap(c, d)
    assert not _overlap({**c, "category": "u"}, d)
