"""Findings checked before they are shown to an estimator.

Plain rules, no model:
- A model summary is shown only if it stays close to its own quote: at least 75% of its
  content words, and every number and time unit it states, appear in the quote. Otherwise
  the quote itself is shown, so the fact stays visible but nothing unsupported is said.
- A model finding that repeats a value an addendum replaced (recorded by a pattern rule as
  "changed by addendum; was ...") is dropped.
- The same quote is shown once: a pattern finding first, else the topic whose search terms
  best match the quote.
"""

from __future__ import annotations

import re

import pandas as pd

STOP = {
    "the", "a", "an", "of", "to", "and", "or", "for", "in", "on", "is", "are", "be", "must",
    "by", "with", "at", "as", "that", "this", "it", "any", "each", "all",
}  # fmt: skip
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
UNIT = re.compile(r"\b(day|hour|minute|week|month|year)s?\b", re.I)
WAS = re.compile(r"\(changed by addendum; was ([^)]+?)\)")
SUPPORT_MIN = 0.75


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower())


def support(statement: str, evidence: str) -> float:
    """Share of the statement's content words that also appear in its own quote (0 to 1)."""
    w = {x for x in _words(statement) if x not in STOP}
    return len(w & set(_words(evidence))) / len(w) if w else 0.0


def _nums(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in NUM.findall(str(text))}


def _units(text: str) -> set[str]:
    return {u.lower() for u in UNIT.findall(str(text))}


def faithful(statement: str, evidence: str) -> bool:
    return (
        support(statement, evidence) >= SUPPORT_MIN
        and _nums(statement) <= _nums(evidence)
        and _units(statement) <= _units(evidence)
    )


def _superseded(items: pd.DataFrame) -> pd.Series:
    """Model findings that still state a value an addendum replaced."""
    old = [
        (m.group(1), r.statement)
        for r in items[items["source"] == "pattern"].itertuples()
        if (m := WAS.search(r.statement))
    ]
    out = pd.Series(False, index=items.index)
    for value, current in old:
        date = re.sub(r"\s+at\s+.*$", "", value).strip()  # "September 10, 2026"
        same_fact = items["statement"].map(lambda s, c=current: support(s, c) >= 0.5)
        out |= (
            (items["source"] != "pattern")
            & items["statement"].str.contains(re.escape(date), regex=True)
            & same_fact
        )
    return out


def _topic_fit(evidence: str, category: str) -> int:
    from bidlens.documents.extract import CATEGORIES

    terms = {c.key: set(_words(c.terms)) for c in CATEGORIES}.get(category, set())
    return len(terms & set(_words(evidence)))


def tidy(items: pd.DataFrame) -> pd.DataFrame:
    """Checked findings. Where a model summary fails the check, `statement` becomes the quote
    (the summary is kept in `model_summary`, its value is dropped) and `as_quoted` is True."""
    if items.empty:
        return items.assign(model_summary=[], as_quoted=[])
    f = items.copy()
    if "source" not in f:
        f["source"] = "model"
    f["source"] = f["source"].fillna("model")
    f = f[~_superseded(f)]
    f["_key"] = f["evidence"].map(lambda e: " ".join(_words(e)))
    f["_pattern"] = (f["source"] == "pattern").astype(int)
    f["_fit"] = [_topic_fit(e, c) for e, c in zip(f["evidence"], f["category"], strict=True)]
    f["_order"] = range(len(f))
    f = (
        f.sort_values(["_pattern", "_fit", "_order"], ascending=[False, False, True])
        .drop_duplicates("_key")
        .sort_values("_order")
    )
    f["as_quoted"] = [
        src != "pattern" and not faithful(s, e)
        for s, e, src in zip(f["statement"], f["evidence"], f["source"], strict=True)
    ]
    f["model_summary"] = f["statement"]
    f["statement"] = f["evidence"].where(f["as_quoted"], f["statement"])
    f["value"] = f["value"].where(~f["as_quoted"], "")
    return f.drop(columns=["_key", "_pattern", "_fit", "_order"])
