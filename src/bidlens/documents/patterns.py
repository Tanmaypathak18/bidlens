"""Plain pattern matching for simple facts: working days, dates and dollar amounts.

No language model. Each rule is a regular expression over the sentences of the special
provisions and addenda (the information handout is left out: its dates and amounts are
lab reports and emails). A finding quotes the sentence it comes from and cites that
sentence's chunk, exactly like a model finding, so it passes the same citation check.
When an addendum states a different value for the same rule (for example a moved prebid
meeting), the addendum's version is kept and the earlier one is noted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.? \d{1,2}, 20\d\d"
)
MONEY = r"\$\d[\d,]*(?:\.\d\d)?"
ABBREV = re.compile(r"\b(a\.m|p\.m|No|Nos|e\.g|i\.e|Ave|St|Blvd|Rd|Dr|U\.S|etc|Inc|Co|vs)\.")
MAX_QUOTE = 300


@dataclass(frozen=True)
class Rule:
    key: str
    topic: str
    pattern: str
    statement: str  # a template on the match's groups; "" uses the sentence itself


RULES = [
    Rule(
        "working_days",
        "time_damages",
        r"Complete the work within (?P<v>\d[\d,]*) working days",
        "Complete the work within {v} working days.",
    ),
    Rule(
        "start_days",
        "time_damages",
        r"Start job site activities within (?P<v>\d+) days after (?P<w>[^.;]+)",
        "Start job site activities within {v} days after {w}.",
    ),
    Rule(
        "bid_open",
        "bid_requirements",
        r"Bids (?:open|for this work will be opened on) (?P<v>(?:[A-Z][a-z]+day, )?" + MONTH + ")",
        "Bids open {v}.",
    ),
    Rule(
        "prebid",
        "bid_requirements",
        r"(?P<m>mandatory )?prebid meeting is scheduled on (?P<v>"
        + MONTH
        + r",? at [\d:]+ [ap]\.m)",
        "A {m}prebid meeting is scheduled on {v}.",
    ),
    Rule(
        "estimate",
        "scope",
        r"estimated cost of the project is (?P<v>" + MONEY + ")",
        "The engineer's estimated cost of the project is {v}.",
    ),
    Rule(
        "late_closure",
        "time_damages",
        r"1st half hour (?P<a>" + MONEY + r")/ ?10 minutes (?P<f>Mainline|Connector|Ramps) "
        r"(?P<r>[A-Z]+-[\d/]+) (?P<d>\w+bound) 2nd half hour (?P<b>" + MONEY + r")/ ?10 minutes "
        r"2nd hour and beyond (?P<v>" + MONEY + r")/ ?10 minutes",
        "Late closure reopening, {f} {r} {d}: liquidated damages of {a} per 10 minutes for the "
        "1st half hour, {b} for the 2nd half hour and {v} from the 2nd hour on.",
    ),
    Rule(
        "price_firm",
        "payment",
        r"firm for orders placed on or before (?P<v>" + MONTH + ")",
        "",
    ),
    Rule(
        "money_rate",
        "payment",
        r"(?P<v>" + MONEY + r") (?:per|for each|a) (?:day|hour|meeting|month|cubic yard|ton|"
        r"engine|occurrence|interval|10-minute|working day|DR[AB])",
        "",
    ),
    Rule(
        "money_terms",
        "payment",
        r"(?:withhold|penalty|price quoted|liquidated damages|more than|limit of)[^.$]{0,80}"
        r"(?P<v>" + MONEY + ")",
        "",
    ),
    Rule(
        "money_penalty",
        "payment",
        r"(?P<v>" + MONEY + r") (?:penalty|performance failure withhold|withhold)",
        "",
    ),
]

TIME_WORDS = re.compile(r"\b(liquidated damages|late|pickup|reopen\w*)\b", re.I)
TABLE_RULES = {"late_closure"}  # matched on the whole chunk: table rows are not sentences


def sentences(text: str) -> list[str]:
    """Split a chunk into sentences, joining lines and words hyphenated across a line."""
    t = re.sub(r"-\n(?=\w)", "-", text)
    t = re.sub(r"\s+", " ", t).strip()
    t = ABBREV.sub(lambda m: m.group(0).replace(".", "§"), t)
    parts = re.split(r"(?<=[.;:])\s+(?=[A-Z(\"“$])|\s+(?=\d{1,2}\. [A-Z$])", t)
    return [p.replace("§", ".").strip() for p in parts if p.strip()]


def _quote(sentence: str, start: int, end: int) -> str:
    """The sentence, or a whole-word window around the match when it is too long."""
    if len(sentence) <= MAX_QUOTE:
        return sentence
    pad = max(0, (MAX_QUOTE - (end - start)) // 2)
    a, b = max(0, start - pad), min(len(sentence), end + pad)
    a = sentence.rfind(" ", 0, a) + 1 if a > 0 else 0
    b2 = sentence.find(" ", b)
    b = len(sentence) if b2 == -1 else b2
    return sentence[a:b].strip()


def match(chunks: pd.DataFrame) -> list[dict]:
    """Raw pattern findings in the extraction item format (topic, statement, value,
    evidence, chunk id), before the citation check."""
    pool = chunks[chunks["kind"].isin(["special_provisions", "addendum"])]
    found: list[dict] = []
    for r in pool.itertuples():
        whole = re.sub(r"\s+", " ", re.sub(r"-\n(?=\w)", "-", r.text))
        units = [(s, False) for s in sentences(r.text)] + [(whole, True)]
        for s, is_whole in units:
            for rule in RULES:
                if (rule.key in TABLE_RULES) != is_whole:
                    continue
                for m in re.finditer(rule.pattern, s):
                    g = {k: (v or "") for k, v in m.groupdict().items()}
                    topic = rule.topic
                    if rule.key.startswith("money") and TIME_WORDS.search(s):
                        topic = "time_damages"
                    quote = m.group(0) if is_whole else _quote(s, m.start(), m.end())
                    g = {k: re.sub(r"\b([ap])\.m$", r"\1.m.", v) for k, v in g.items()}
                    stmt = rule.statement.format(**g) if rule.statement else quote
                    stmt = stmt.replace("m..", "m.")
                    found.append(
                        {
                            "rule": rule.key,
                            "topic": topic,
                            "statement": re.sub(r"\s+", " ", stmt).strip()[:300],
                            "value": g.get("v", ""),
                            "evidence": quote,
                            "chunk_id": r.chunk_id,
                            "kind": r.kind,
                        }
                    )
    return resolve(found)


def resolve(found: list[dict]) -> list[dict]:
    """One finding per rule and sentence; for the single-valued rules (bid opening,
    prebid meeting, working days, start), an addendum's value replaces the special
    provisions' value."""
    out, seen = [], set()
    single = {"working_days", "start_days", "bid_open", "prebid"}
    by_rule: dict[str, list[dict]] = {}
    for f in found:
        # One finding per sentence, whichever money rule matched it first.
        key = ("s", f["evidence"]) if f["rule"] not in single else (f["rule"], f["value"])
        if key in seen:
            continue
        seen.add(key)
        if f["rule"] in single:
            by_rule.setdefault(f["rule"], []).append(f)
        else:
            out.append(f)
    for fs in by_rule.values():
        add = [f for f in fs if f["kind"] == "addendum"]
        base = [f for f in fs if f["kind"] != "addendum"]
        if add and base and {f["value"] for f in add} != {f["value"] for f in base}:
            f = dict(add[0])
            was = ", ".join(sorted({b["value"] for b in base}))
            st = f["statement"]
            core = st if st.endswith(("a.m.", "p.m.")) else st.rstrip(".")
            f["statement"] = f"{core} (changed by addendum; was {was})."
            out.append(f)
        else:
            out.append((add or base)[0])
    return out
