"""Step 3.3 tests: retrieval, citation checking and the run loop, with a fake model."""

from __future__ import annotations

import pandas as pd

from bidlens.documents.extract import BM25, CATEGORIES, cite, norm, retrieve, slug


def _chunks():
    return pd.DataFrame(
        [
            {
                "chunk_id": "sp.pdf:p40:c1",
                "file": "sp.pdf",
                "kind": "special_provisions",
                "title": "Special Provisions",
                "page": 40,
                "printed_page": "28",
                "section": "8 Prosecution And Progress",
                "subsection": "8-1.10",
                "text": "Liquidated damages are $4,100 per day.\n"
                "Complete the work in 600 working days.",
            },
            {
                "chunk_id": "sp.pdf:p50:c1",
                "file": "sp.pdf",
                "kind": "special_provisions",
                "title": "Special Provisions",
                "page": 50,
                "printed_page": "38",
                "section": "12 Temporary Traffic Control",
                "subsection": "12-4.02",
                "text": "Lane closures are allowed from 9 p.m. to 5 a.m. Mon-Thu.",
            },
            {
                "chunk_id": "ad1.pdf:p1:c1",
                "file": "ad1.pdf",
                "kind": "addendum",
                "title": "Addendum No. 1",
                "page": 1,
                "printed_page": "",
                "section": "Addendum No. 1",
                "subsection": "",
                "text": "A mandatory prebid meeting is scheduled on September 2, 2026.",
            },
            {
                "chunk_id": "ih.pdf:p9:c1",
                "file": "ih.pdf",
                "kind": "information_handout",
                "title": "Information Handout",
                "page": 9,
                "printed_page": "",
                "section": "Information Handout",
                "subsection": "",
                "text": "Groundwater was encountered at 12 feet in boring B-3.",
            },
        ]
    )


def _cat(key):
    return next(c for c in CATEGORIES if c.key == key)


def test_bm25_ranks_the_matching_chunk_first():
    s = BM25(_chunks()["text"].tolist()).scores("liquidated damages per day")
    assert max(range(len(s)), key=s.__getitem__) == 0


def test_retrieve_adds_addenda_and_keeps_handout_out_unless_asked():
    c = _chunks()
    traffic = retrieve(c, _cat("traffic"), k=1)
    assert "ad1.pdf:p1:c1" in set(traffic["chunk_id"])
    assert "ih.pdf:p9:c1" not in set(traffic["chunk_id"])
    geo = retrieve(c, _cat("geotechnical"), k=4)
    assert "ih.pdf:p9:c1" in set(geo["chunk_id"])


def test_cite_keeps_true_quotes_and_takes_the_page_from_the_chunk():
    ctx = _chunks()
    items = [
        {
            "statement": "Damages are $4,100 a day.",
            "value": "$4,100 per day",
            "evidence": "Liquidated damages are  $4,100 per day.",
            "chunk_id": "sp.pdf:p40:c1",
        },
        {
            "statement": "Made up.",
            "value": "",
            "evidence": "Damages are $9,999 per day.",
            "chunk_id": "sp.pdf:p40:c1",
        },
        # Right quote, wrong chunk id: repaired to the only chunk that holds it.
        {
            "statement": "Night closures.",
            "value": "9 p.m. to 5 a.m.",
            "evidence": "allowed from 9 p.m. to 5 a.m.",
            "chunk_id": "sp.pdf:p40:c1",
        },
        {
            "statement": "Damages are $4,100 a day.",
            "value": "",
            "evidence": "Liquidated damages are $4,100 per day.",
            "chunk_id": "sp.pdf:p40:c1",
        },  # duplicate
    ]
    kept, rejected = cite(items, ctx, _cat("time_damages"))
    assert [k["page"] for k in kept] == [40, 50]
    assert kept[0]["section_number"] == "8-1.10" and kept[0]["printed_page"] == "28"
    assert kept[1]["chunk_id"] == "sp.pdf:p50:c1"
    assert len(rejected) == 1 and rejected[0]["statement"] == "Made up."


def test_norm_ignores_whitespace_and_case():
    assert norm(" A\n b  C ") == "a b c"


def test_slug_names_one_results_file_per_local_model():
    assert slug("qwen3:8b") == "qwen3-8b"
    assert slug("llama3.1:8b") == "llama3.1-8b"
