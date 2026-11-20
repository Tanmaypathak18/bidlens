"""Rebuild the lane and ramp closure charts from PDF word positions (decision D-060).

The special provisions print each closure chart as a grid: one column per hour (00 to 24)
and one row per day group (Mon-Thu, Fri, Sat, Sun). Empty cells have no text, so the PDF
text layer squeezes each row into a run like `C C C C C` and the hour of every symbol is
lost. Here every symbol is put back in its hour column by its x position on the page,
using the hour header of the same chart. Plain code, no language model.

Usage:
    uv run python -m bidlens.documents.charts 04-0W0504
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(".")
PACKAGES = ROOT / "data" / "raw" / "bid_package"
CACHE = ROOT / "data" / "interim" / "docs"

FOOTER = re.compile(r"^Contract No\. \d{2}-[0-9A-Z]{6}$")
CHART_NO = re.compile(r"^Chart No\. ?([A-Z]+\d+)$")
DAYS = ("Mon–Thu", "Mon-Thu", "Mon–Fri", "Fri", "Sat", "Sun", "Holiday")
KIND = {
    "G": "freeway lane closure",
    "I": "connector closure",
    "J": "ramp closure",
}


def _lines(page) -> list[list[dict]]:
    """Words grouped into lines by their top position, left to right."""
    words = sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"]))
    lines: list[list[dict]] = []
    for w in words:
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 2.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(ln, key=lambda w: w["x0"]) for ln in lines]


def _text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line)


def _hour_of(x: float, centers: list[float]) -> int | None:
    """The hour whose column (between header h and header h+1) holds x."""
    for h in range(24):
        if centers[h] <= x < centers[h + 1]:
            return h
    return None


def parse_page(page, page_no: int, file: str) -> list[dict]:
    """Every chart on one page, with its symbols placed by hour."""
    charts: list[dict] = []
    cur: dict | None = None
    centers: list[float] | None = None
    label_pending = ""
    for line in _lines(page):
        t = _text(line)
        m = CHART_NO.match(t)
        if m:
            cur = {
                "file": file,
                "page": page_no,
                "chart": m.group(1),
                "title": "",
                "county": "",
                "route": "",
                "post_mile": "",
                "limits": "",
                "remarks": "",
                "legend": {},
                "rows": {},
                "problems": [],
                "after_remarks": False,
            }
            charts.append(cur)
            centers, label_pending = None, ""
            continue
        if cur is None:
            continue
        if not cur["title"]:
            cur["title"] = t
            continue
        if t.startswith("County:"):
            m2 = re.match(r"County: ?(\S+) Route/Direction: ?(\S+) Post Mile: ?(.*)$", t)
            if m2:
                cur["county"], cur["route"], cur["post_mile"] = m2.groups()
            continue
        if t.startswith("Closure limits:"):
            cur["limits"] = t.removeprefix("Closure limits:").strip()
            continue
        if t.startswith("Hour "):
            hdr = [w for w in line if re.fullmatch(r"\d{2}", w["text"])]
            if [int(w["text"]) for w in hdr] == list(range(25)):
                centers = [(w["x0"] + w["x1"]) / 2 for w in hdr]
            else:
                cur["problems"].append("hour header not 00 to 24")
            continue
        if t.startswith("Legend:"):
            centers = None
            continue
        # The text layer sometimes splits a first letter off ("R EMARKS", "S ee").
        t = re.sub(r"^([A-Z]) ([a-z]+|EMARKS:)", r"\1\2", t)
        if t.startswith("REMARKS:"):
            cur["remarks"] = t.removeprefix("REMARKS:").strip()
            cur["after_remarks"] = True
            continue
        if cur.get("after_remarks"):
            if t.startswith("Replace section") or re.match(r"^\d{1,2}-\d", t):
                cur["after_remarks"] = False
                cur = None  # section text after the last chart on the page
                continue
            if not (FOOTER.match(t) or re.fullmatch(r"\d{1,4}", t)):
                cur["remarks"] = f"{cur['remarks']}. {t}".strip(". ")
            continue
        if centers is None:
            # Legend lines: a one-character code, then its meaning.
            lm = re.match(r"^([0-9A-Z]) (.+)$", t)
            if lm and lm.group(1) not in cur["legend"]:
                cur["legend"][lm.group(1)] = lm.group(2)
            continue
        # A grid row: label words left of the first hour column, then symbols.
        label = " ".join(w["text"] for w in line if w["x1"] < centers[0])
        cells = [w for w in line if w["x1"] >= centers[0]]
        if label == "Thu" and not cells and label_pending:
            continue  # the second half of a wrapped "Mon– / Thu" label
        if label.endswith("–") or label.endswith("-"):
            label += "Thu"
            label_pending = label
        label = label.replace("-", "–")
        if not label:
            continue
        hours: dict[int, str] = {}
        for w in cells:
            h = _hour_of((w["x0"] + w["x1"]) / 2, centers)
            if h is None or h in hours or len(w["text"]) != 1:
                cur["problems"].append(f"{label}: cannot place {w['text']!r}")
                continue
            hours[h] = w["text"]
        cur["rows"][label] = hours
    return charts


def _ranges(hours: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for h in sorted(hours):
        if out and out[-1][1] == h:
            out[-1] = (out[-1][0], h + 1)
        else:
            out.append((h, h + 1))
    return out


def fmt(rs: list[tuple[int, int]]) -> str:
    return ", ".join(f"{a:02d}:00 to {b:02d}:00" for a, b in rs) or "none"


def short(meaning: str) -> str:
    """A legend meaning in a few words."""
    m = re.match(r"Provide at least (\d+) (?:adjacent )?through freeway lanes? open", meaning, re.I)
    if m:
        n = int(m.group(1))
        return f"lane closure allowed, keep at least {n} through lane{'s' if n > 1 else ''} open"
    m = re.match(r"Provide at least (\d+) ramp lanes?", meaning, re.I)
    if m:
        return f"ramp lane closure allowed, keep at least {m.group(1)} ramp lane open"
    if meaning.lower().startswith("shoulder closure is allowed"):
        return "shoulder closure only"
    m = re.match(r"(Ramp|Connector) may be closed completely", meaning)
    if m:
        return f"{m.group(1).lower()} may be closed completely"
    return meaning.rstrip(".")


def describe(c: dict) -> str:
    """The chart as plain sentences, one line per day group and code."""
    kind = KIND.get(re.sub(r"\d", "", c["chart"]), "closure")
    head = (
        f"Chart {c['chart']} ({c['title']}), {kind}: {c['county']} {c['route']}, "
        f"post mile {c['post_mile']}. {c['limits']}."
    )
    if c["remarks"]:
        head += f" {c['remarks']}."
    lines = [head]
    for day, hours in c["rows"].items():
        if not hours:
            lines.append(f"{day}: no closure allowed at any hour.")
            continue
        parts = []
        for code in sorted(set(hours.values())):
            meaning = short(c["legend"].get(code, f"code {code}"))
            hs = [h for h, v in hours.items() if v == code]
            parts.append(f"{meaning}: {fmt(_ranges(hs))}")
        lines.append(f"{day}: " + "; ".join(parts) + ".")
    return "\n".join(lines)


def compact(c: dict) -> str:
    """One line per chart: the hours when a lane, ramp or connector closure is allowed
    (shoulder-only hours left out). Used as model context in place of the broken grid."""
    kind = KIND.get(re.sub(r"\d", "", c["chart"]), "closure")
    days = []
    for day, hours in c["rows"].items():
        hs = [h for h, v in hours.items() if v != "S"]
        days.append(f"{day} {fmt(_ranges(hs)).replace(':00', '')}")
    where = f"{c['county']} {c['route']} {c['limits']}".strip()
    loc = f" ({c['remarks'].split('.')[0]})" if c["remarks"] else ""
    return f"Chart {c['chart']}, {kind} hours, {where}{loc}: " + "; ".join(days) + "."


def run(contract: str) -> pd.DataFrame:
    import pdfplumber

    file = f"{contract}sp.pdf"
    rows = []
    with pdfplumber.open(PACKAGES / contract / file) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            if "Chart No" not in (page.extract_text() or ""):
                continue
            for c in parse_page(page, i, file):
                rows.append(
                    {
                        **{k: c[k] for k in ("file", "page", "chart", "title", "county")},
                        "route": c["route"],
                        "post_mile": c["post_mile"],
                        "limits": c["limits"],
                        "remarks": c["remarks"],
                        "legend": "; ".join(f"{k} = {v}" for k, v in c["legend"].items()),
                        "grid": "; ".join(
                            f"{d}: " + " ".join(f"{h:02d}{v}" for h, v in sorted(hs.items()))
                            for d, hs in c["rows"].items()
                        ),
                        "text": describe(c),
                        "compact": compact(c),
                        "problems": "; ".join(c["problems"]),
                    }
                )
    df = pd.DataFrame(rows)
    df.to_parquet(CACHE / contract / "charts.parquet")
    return df


def chart_chunks(contract: str) -> pd.DataFrame:
    """One citable chunk per chart, in the same shape as the step 3.2 chunks."""
    path = CACHE / contract / "charts.parquet"
    if not path.exists():
        return pd.DataFrame()
    ch = pd.read_parquet(path)
    return pd.DataFrame(
        {
            "chunk_id": [f"{r.file}:p{r.page}:{r.chart}" for r in ch.itertuples()],
            "file": ch["file"],
            "kind": "closure_chart",
            "title": "Special Provisions (closure chart, rebuilt from the page layout)",
            "page": ch["page"],
            "printed_page": "",
            "section": "12-4.02C(3) Closure charts",
            "subsection": "12-4.02C(3)",
            "text": ch["compact"],
        }
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    args = ap.parse_args(argv)
    df = run(args.contract)
    print(df[["page", "chart", "grid"]].to_string(max_colwidth=90))
    bad = df[df["problems"] != ""]
    print(f"{len(df)} charts, {len(bad)} with problems")
    print(bad[["chart", "problems"]].to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
