"""Step 3.3: extract scope, risks and requirements with page citations (decision D-052).

Usage (local is the default; documents never leave this machine, no paid service):
    uv run python -m bidlens.documents.extract 04-0W0504 --model qwen3:8b
    uv run python -m bidlens.documents.extract 04-0W0504 --model llama3.1:8b

Optional, for users with their own Anthropic API key (sends the document passages to the
Claude API, which is a paid service): set ANTHROPIC_API_KEY and add `--mode hosted`.

Needs the chunks from step 3.2. For each category, the most relevant chunks are retrieved
(BM25, plus every addendum chunk), and the model returns items as JSON, each with a
verbatim quote and the id of the chunk it came from. BidLens then checks every quote
against its chunk and takes the citation (file, page, section) from the chunk, never from
the model. Quantities come from the parsed bid item list, not from the model.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(".")
CACHE = ROOT / "data" / "interim" / "docs"
TOP_K = 25
MAX_QUOTE = 400

HOSTED_MODEL = os.environ.get("BIDLENS_HOSTED_MODEL", "claude-opus-5-5")
LOCAL_MODEL = os.environ.get("BIDLENS_LOCAL_MODEL", "qwen3:8b")


@dataclass(frozen=True)
class Category:
    key: str
    name: str
    ask: str
    terms: str
    handout: bool = False


CATEGORIES = [
    Category(
        "scope",
        "Scope of work",
        "What work the contract covers, where (counties, routes, locations) and its main parts.",
        "construction work location route county description scope consists "
        "install construct modify",
    ),
    Category(
        "time_damages",
        "Working days and liquidated damages",
        "Contract time (working days), liquidated damages per day, interim milestones, "
        "and when work may or must start.",
        "working days liquidated damages per day complete milestone start contract time",
    ),
    Category(
        "traffic",
        "Traffic control and lane closures",
        "Allowed hours for lane, ramp and shoulder closures, night work, closure charts, "
        "and traffic control requirements that affect cost or schedule.",
        "lane closure ramp closure night hours traffic control chart work hours shoulder detour",
    ),
    Category(
        "environmental",
        "Environmental windows and permits",
        "Seasonal or daily work limits for nesting birds, wildlife or water, permits, "
        "and environmental protection requirements.",
        "nesting bird season environmental permit wildlife water quality biological "
        "monitor sensitive area",
    ),
    Category(
        "hazardous",
        "Hazardous materials",
        "Lead (aerially deposited lead, lead paint), contaminated soil, handling and "
        "disposal requirements.",
        "lead aerially deposited hazardous contaminated disposal soil waste",
        True,
    ),
    Category(
        "geotechnical",
        "Geotechnical and site conditions",
        "Soil, groundwater and site conditions reported in the documents that affect "
        "excavation, foundations or methods.",
        "soil groundwater boring geotechnical excavation rock foundation site conditions",
        True,
    ),
    Category(
        "utilities",
        "Utilities and third parties",
        "Utilities to protect or relocate, coordination with other agencies, railroads "
        "or adjacent contractors.",
        "utility utilities relocate coordinate agency railroad owner adjacent contractor",
    ),
    Category(
        "bid_requirements",
        "Bid requirements",
        "Prebid meetings, small business and DVBE goals, bid forms and other conditions "
        "of bidding.",
        "bid prebid meeting dvbe small business goal bidder forms submit bid mandatory",
    ),
    Category(
        "submittals",
        "Submittals",
        "Required submittals (plans, schedules, certificates) and when they are due.",
        "submit submittal days before plan schedule certificate working drawings within days",
    ),
    Category(
        "payment",
        "Payment and price terms",
        "Payment terms that affect price: price adjustments, partial payments, "
        "retention, payment for specific items.",
        "payment paid price adjustment partial payment compensation bid item full compensation",
    ),
]

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "value": {"type": "string"},
                    "evidence": {"type": "string"},
                    "chunk_id": {"type": "string"},
                },
                "required": ["statement", "value", "evidence", "chunk_id"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

SYSTEM = """You read Caltrans highway construction bid documents for a contractor's \
estimator. You are given numbered passages ("chunks") from one contract's Notice to \
Bidders and Special Provisions, addenda and information handout, and one topic.

Return every distinct fact in the passages that an estimator needs on that topic, as JSON \
items. For each item:
- statement: one plain-English sentence an estimator would understand.
- value: the key number or limit (an amount, a duration, hours, a date), or "" if none.
- evidence: a short exact quote copied character for character from one chunk that \
supports the statement (at most 300 characters; do not paraphrase or join text from \
different chunks).
- chunk_id: the id of that chunk.

Use only the passages. If an addendum changes something, report the addendum's version. \
If the passages say nothing on the topic, return an empty list."""


# ----------------------------------------------------------------- retrieval


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.tf = [Counter(tokens(d)) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / max(len(self.len), 1)
        df = Counter(w for t in self.tf for w in t)
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        q = tokens(query)
        out = []
        for tf, ln in zip(self.tf, self.len, strict=True):
            s = 0.0
            for w in q:
                f = tf.get(w, 0)
                if f:
                    s += (
                        self.idf[w]
                        * f
                        * (self.k1 + 1)
                        / (f + self.k1 * (1 - self.b + self.b * ln / self.avg))
                    )
            out.append(s)
        return out


def retrieve(chunks: pd.DataFrame, cat: Category, k: int = TOP_K) -> pd.DataFrame:
    """The top-k chunks for a category, plus every addendum chunk."""
    pool = chunks if cat.handout else chunks[chunks["kind"] != "information_handout"]
    pool = pool.reset_index(drop=True)
    s = BM25(pool["text"].tolist()).scores(cat.terms + " " + cat.ask)
    top = pool.assign(score=s).sort_values("score", ascending=False).head(k)
    add = chunks[chunks["kind"] == "addendum"]
    return pd.concat([top, add[~add["chunk_id"].isin(top["chunk_id"])]], ignore_index=True)


def prompt(cat: Category, ctx: pd.DataFrame) -> str:
    parts = [
        f'<chunk id="{r.chunk_id}" document="{r.title}" page="{r.page}" '
        f'section="{r.section}">\n{r.text}\n</chunk>'
        for r in ctx.itertuples()
    ]
    return "\n\n".join(parts) + f"\n\nTopic: {cat.name}. {cat.ask}"


# ----------------------------------------------------------------- backends


class HostedBackend:
    """Optional, off by default: Claude API with structured JSON output.

    Only for users who bring their own ANTHROPIC_API_KEY; it sends the retrieved passages
    to Anthropic and is billed per token (D-053). BidLens itself never needs it.
    """

    name = "hosted"

    def __init__(self, model: str = HOSTED_MODEL, effort: str = "high") -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.model, self.effort = model, effort

    def complete(self, system: str, user: str, schema: dict) -> dict:
        r = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if r.stop_reason == "refusal":
            raise RuntimeError(f"model declined: {r.stop_details}")
        if r.stop_reason == "max_tokens":
            raise RuntimeError("output hit max_tokens")
        text = next(b.text for b in r.content if b.type == "text")
        self.last_usage = {
            "input_tokens": r.usage.input_tokens,
            "output_tokens": r.usage.output_tokens,
            "model": r.model,
        }
        return json.loads(text)


class LocalBackend:
    """Ollama on this machine, structured JSON output; documents never leave it."""

    name = "local"

    def __init__(self, model: str = LOCAL_MODEL) -> None:
        import httpx

        self.model = model
        self.name = f"local_{slug(model)}"
        self.http = httpx.Client(
            base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"), timeout=1800
        )

    def complete(self, system: str, user: str, schema: dict) -> dict:
        r = self.http.post(
            "/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": schema,
                "think": False,  # D-054: qwen3's reasoning mode off, same as llama3.1
                "options": {"temperature": 0, "num_ctx": 32768},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        r.raise_for_status()
        body = r.json()
        self.last_usage = {
            "input_tokens": body.get("prompt_eval_count"),
            "output_tokens": body.get("eval_count"),
            "model": self.model,
        }
        return json.loads(body["message"]["content"])

    def close(self) -> None:
        """Unload the model so only one is in memory at a time (D-054)."""
        self.http.post("/api/generate", json={"model": self.model, "keep_alive": 0})


def slug(model: str) -> str:
    """qwen3:8b -> qwen3-8b, for file names."""
    return re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")


# ----------------------------------------------------------------- citations


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def cite(items: list[dict], ctx: pd.DataFrame, cat: Category) -> tuple[list[dict], list[dict]]:
    """Keep items whose quote is found in their chunk; attach the chunk's citation."""
    by_id = ctx.set_index("chunk_id")
    kept, rejected = [], []
    for it in items:
        cid, quote = it.get("chunk_id", ""), it.get("evidence", "")
        ok = (
            cid in by_id.index
            and 0 < len(quote) <= MAX_QUOTE
            and norm(quote) in norm(by_id.at[cid, "text"])
        )
        if not ok:
            # The quote may be from another provided chunk than the one named.
            hits = [c for c in by_id.index if quote and norm(quote) in norm(by_id.at[c, "text"])]
            if len(quote) <= MAX_QUOTE and len(hits) == 1:
                cid, ok = hits[0], True
        if not ok:
            rejected.append({**it, "category": cat.key, "reason": "quote not found in chunk"})
            continue
        c = by_id.loc[cid]
        kept.append(
            {
                "category": cat.key,
                "category_name": cat.name,
                "statement": it["statement"].strip(),
                "value": it.get("value", "").strip(),
                "evidence": quote.strip(),
                "chunk_id": cid,
                "document": c["title"],
                "file": c["file"],
                "page": int(c["page"]),
                "printed_page": c["printed_page"],
                "section": c["section"],
                "section_number": c["subsection"],
            }
        )
    # Drop exact duplicate statements within a category.
    seen, out = set(), []
    for k in kept:
        key = norm(k["statement"])
        if key not in seen:
            seen.add(key)
            out.append(k)
    return out, rejected


def quantities(contract: str) -> list[dict]:
    items = pd.read_parquet(CACHE / contract / "bid_items.parquet")
    out = []
    for r in items.itertuples():
        file, page = r.source.rsplit(" p", 1)
        qty = "lump sum" if pd.isna(r.quantity) else f"{r.quantity:,.10g} {r.unit}"
        out.append(
            {
                "category": "quantities",
                "category_name": "Bid items and quantities",
                "statement": f"Item {r.item_no}: {r.description} ({r.item_code}), {qty}.",
                "value": qty,
                "evidence": f"{r.item_no} {r.item_code}",
                "chunk_id": "",
                "document": "Addendum" if r.changed_by else "Bid Item List",
                "file": file,
                "page": int(page),
                "printed_page": "",
                "section": "Bid Item List",
                "section_number": "",
            }
        )
    return out


def run(contract: str, backend, categories=CATEGORIES) -> dict:
    chunks = pd.read_parquet(CACHE / contract / "chunks.parquet")
    items, rejected, calls = quantities(contract), [], []
    for cat in categories:
        ctx = retrieve(chunks, cat)
        t0 = time.perf_counter()
        raw = backend.complete(SYSTEM, prompt(cat, ctx), SCHEMA).get("items", [])
        kept, rej = cite(raw, ctx, cat)
        items += kept
        rejected += rej
        calls.append(
            {
                "category": cat.key,
                "chunks": len(ctx),
                "returned": len(raw),
                "kept": len(kept),
                "seconds": round(time.perf_counter() - t0, 1),
                **getattr(backend, "last_usage", {}),
            }
        )
    return {
        "contract": contract,
        "mode": backend.name,
        "model": getattr(backend, "model", ""),
        "items": items,
        "rejected": rejected,
        "calls": calls,
    }


def save(result: dict) -> Path:
    path = CACHE / result["contract"] / f"extraction_{result['mode']}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    ap.add_argument("--mode", choices=["local", "hosted"], default="local")
    ap.add_argument("--model", help=f"Ollama model for local mode (default {LOCAL_MODEL})")
    args = ap.parse_args(argv)
    if args.mode == "hosted":
        backend = HostedBackend(args.model or HOSTED_MODEL)
    else:
        backend = LocalBackend(args.model or LOCAL_MODEL)
    try:
        result = run(args.contract, backend)
    finally:
        if hasattr(backend, "close"):
            backend.close()
    path = save(result)
    from bidlens.documents.report import write_extraction_report

    write_extraction_report(args.contract)
    print(json.dumps(result["calls"], indent=2))
    print(f"{len(result['items'])} items, {len(result['rejected'])} rejected -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
