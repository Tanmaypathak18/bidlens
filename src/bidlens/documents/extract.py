"""Step 3.3: extract scope, risks and requirements with page citations (decision D-052).

Usage (local is the default; documents never leave this machine, no paid service):
    uv run python -m bidlens.documents.extract 04-0W0504                  # qwen3:8b
    uv run python -m bidlens.documents.extract 04-0W0504 --model llama3.1:8b
    uv run python -m bidlens.documents.extract 04-0W0504 --mode combined  # both + patterns
    uv run python -m bidlens.documents.extract 04-0W0504 --mode patterns  # rules only

The default is the second round (D-060 to D-063): rebuilt closure charts, a question
checklist per topic, and the closure tables; `--round1` reproduces step 3.5's settings.

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
import contextlib
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
NUM_CTX = 32768  # D-054
NUM_PREDICT = 4096  # D-056: stop a looping model
RETRIES, RETRY_WAIT = 6, 30
MAX_QUOTE = 400
MAX_ITEMS = 25  # D-058

HOSTED_MODEL = os.environ.get("BIDLENS_HOSTED_MODEL", "claude-opus-5-5")
LOCAL_MODEL = os.environ.get("BIDLENS_LOCAL_MODEL", "qwen3:8b")
# The run the app shows (D-059, D-063), then fallbacks if it has not been run.
DEFAULT_RUN = "local_qwen3-8b_v2"
RUN_FALLBACKS = ("combined", "local_qwen3-8b_v2", "local_qwen3-8b", "patterns")


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

# D-061: specific questions an estimator asks on each topic, written for any Caltrans
# contract (not for the sample one).
CHECKLIST: dict[str, list[str]] = {
    "scope": [
        "What is the general work description?",
        "Which counties, routes and locations does the work cover?",
        "What are the main types of work (the largest parts of the job)?",
        "What is the engineer's estimated cost?",
        "Do the addenda add, delete or change bid items or work?",
        "Is any work to be done by others, or excluded from the contract?",
    ],
    "time_damages": [
        "How many working days are allowed to complete the work?",
        "When may or must job site activities start, and what must be done first?",
        "What are the liquidated damages per day for late completion?",
        "What damages apply for reopening a lane or ramp closure late?",
        "Are there interim milestones, or separate time limits for parts of the work?",
        "How is time-related overhead bid and paid?",
        "What notices are required before starting work?",
        "What other penalties or withholds are tied to time or performance?",
    ],
    "traffic": [
        "During which hours are lane, ramp or connector closures allowed?",
        "How many lanes must be kept open, and where?",
        "What limits apply to the length, number or spacing of closures?",
        "When must all lanes be open (holidays, special days)?",
        "Are moving closures or one-way traffic control allowed, and with what limits?",
        "What protective devices are required (attenuator vehicles, mobile barriers, signs)?",
        "Is a work zone speed limit reduction required?",
        "Which closures depend on others (ramps that can't close at the same time)?",
        "What traffic plans or contingency plans must be submitted?",
    ],
    "environmental": [
        "Which protected species or habitats are in or near the project?",
        "What seasonal work restrictions apply (for example bird nesting season)?",
        "What surveys, biologist work or training are required before work, and when?",
        "What buffers or stop-work distances apply if wildlife or nests are found?",
        "What materials or practices are prohibited?",
        "What permits or approvals are needed, including for areas outside the job site?",
        "What daily site protection is required (covering holes, inspections)?",
    ],
    "hazardous": [
        "What hazardous or regulated materials are present (for example aerially deposited lead)?",
        "What lead concentrations or classifications are reported, and at what depths?",
        "How must regulated material be handled, stockpiled, transported and disposed of?",
        "Which quantities or bid items cover hazardous material?",
        "What plans and documentation are required, and when are they due?",
        "Who pays for extra sampling, testing or disposal costs?",
        "What rules apply to local or imported material?",
    ],
    "geotechnical": [
        "What soil, rock or groundwater conditions are reported?",
        "How do site conditions affect excavation, posts or foundations?",
        "How are changes in excavation, embankment or borrow quantities paid?",
        "Are there excavation limits or methods required at specific locations?",
        "What site investigation reports or test results are in the information handout?",
        "Are there other site conditions that affect methods or cost?",
    ],
    "utilities": [
        "Which utilities must be protected, relocated or worked around?",
        "Which other contracts or agencies work at or near the job site, and what "
        "coordination is required?",
        "Is a railroad within or next to the project, and what applies?",
        "What notice is needed before working on existing electrical or utility systems?",
        "Who performs utility work, and when?",
        "Are there third-party permits or agreements the contractor must follow?",
    ],
    "bid_requirements": [
        "When do bids open, and how are they submitted?",
        "Is there a prebid meeting, is it mandatory, and when is it?",
        "What bidder's security is required?",
        "What contractor license is required?",
        "What small business, DVBE or DBE goals or reporting apply?",
        "What wage requirements apply (prevailing and federal minimum wages)?",
        "Is the project federal-aid, and what federal requirements follow (training, Buy America)?",
        "What do the addenda change for bidders?",
        "What supplemental information is provided for bidding?",
    ],
    "submittals": [
        "What safety submittals are required, and when?",
        "What submittals are required for traffic safety devices (crash cushions, "
        "barriers, terminals), and when?",
        "What equipment or emissions submittals are required, and when?",
        "What material test results or mix designs must be submitted, and when?",
        "What payroll, payment or labor reports must be submitted, and how often?",
        "What requests or notices must be submitted before storing materials or starting work?",
        "What test results must be submitted after testing, and how soon?",
    ],
    "payment": [
        "Are there quoted prices or rental costs given for any equipment or material?",
        "How are major or unusual items measured and paid (by day, month, length)?",
        "When must subcontractors and suppliers be paid?",
        "What are the dispute resolution rates the contractor shares?",
        "What thresholds apply to payment for materials on hand?",
        "What withholds or penalties can reduce payment?",
        "Which items are paid as change order work rather than bid items?",
        "Are there payment terms for mobilization, move-in or move-out?",
    ],
}

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "maxItems": MAX_ITEMS,  # D-058
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string", "maxLength": 300},
                    "value": {"type": "string", "maxLength": 120},
                    "evidence": {"type": "string", "maxLength": 300},
                    "chunk_id": {"type": "string", "maxLength": 40},
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

Return the distinct facts in the passages that an estimator needs on that topic, as JSON \
items: at most 25, most important first, and never the same fact twice. For each item:
- statement: one plain-English sentence an estimator would understand.
- value: the key number or limit (an amount, a duration, hours, a date), or "" if none.
- evidence: a short exact quote copied character for character from one chunk that \
supports the statement (at most 300 characters; do not paraphrase or join text from \
different chunks).
- chunk_id: the id of that chunk.

Use only the passages. If an addendum changes something, report the addendum's version. \
If the passages say nothing on the topic, return an empty list."""


CHECKLIST_SCHEMA = json.loads(json.dumps(SCHEMA))
_props = CHECKLIST_SCHEMA["properties"]["items"]["items"]
_props["properties"] = {"question": {"type": "string", "maxLength": 10}, **_props["properties"]}
_props["required"] = ["question", *_props["required"]]

CHECKLIST_SYSTEM = """You read Caltrans highway construction bid documents for a contractor's \
estimator. You are given numbered passages ("chunks") from one contract's Notice to \
Bidders and Special Provisions, addenda and information handout, one topic and a \
checklist of questions on that topic.

Answer the checklist from the passages, as JSON items, at most 25 in all. For each \
question the passages answer, give one item per distinct fact (usually one); skip \
questions the passages do not answer, and never state the same fact twice. After the \
questions, add at most 5 other facts on the topic that an estimator must price or plan \
around, with question "other". For each item:
- question: the question id (q1, q2, ...) or "other".
- statement: one plain-English sentence that answers it, with its conditions.
- value: the key number or limit (an amount, a duration, hours, a date), or "" if none.
- evidence: a short exact quote copied character for character from one chunk that \
supports the statement (at most 300 characters; do not paraphrase or join text from \
different chunks).
- chunk_id: the id of that chunk.

Use only the passages. If an addendum changes something, report the addendum's version."""


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


RAW_GRID = re.compile(r"Hour 00 01 02 03")


def retrieve(
    chunks: pd.DataFrame, cat: Category, k: int = TOP_K, charts: pd.DataFrame | None = None
) -> pd.DataFrame:
    """The top-k chunks for a category, plus every addendum chunk. With `charts` (D-060),
    the traffic topic gets one rebuilt line per closure chart in place of the raw grids."""
    pool = chunks if cat.handout else chunks[chunks["kind"] != "information_handout"]
    pool = pool.reset_index(drop=True)
    s = BM25(pool["text"].tolist()).scores(cat.terms + " " + cat.ask)
    top = pool.assign(score=s).sort_values("score", ascending=False).head(k)
    add = chunks[chunks["kind"] == "addendum"]
    ctx = pd.concat([top, add[~add["chunk_id"].isin(top["chunk_id"])]], ignore_index=True)
    if charts is not None and len(charts) and cat.key == "traffic":
        ctx = ctx[~ctx["text"].str.contains(RAW_GRID)]
        ctx = pd.concat([ctx, charts], ignore_index=True)
    return ctx


def prompt(cat: Category, ctx: pd.DataFrame, checklist: bool = False) -> str:
    parts = [
        f'<chunk id="{r.chunk_id}" document="{r.title}" page="{r.page}" '
        f'section="{r.section}">\n{r.text}\n</chunk>'
        for r in ctx.itertuples()
    ]
    tail = f"\n\nTopic: {cat.name}. {cat.ask}"
    if checklist:
        qs = "\n".join(f"q{i}. {q}" for i, q in enumerate(CHECKLIST[cat.key], start=1))
        tail += f"\n\nChecklist:\n{qs}"
    return "\n\n".join(parts) + tail


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
        import httpx

        payload = {
            "model": self.model,
            "stream": True,  # D-057: keep what was written if the reply is aborted
            "format": schema,
            "think": False,  # D-054: qwen3's reasoning mode off, same as llama3.1
            "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # The Ollama desktop app can restart itself (e.g. to apply an update); wait for it.
        for attempt in range(RETRIES + 1):
            try:
                text, last = self._stream(payload)
                break
            except (httpx.TransportError, httpx.HTTPStatusError, OllamaError) as e:
                if attempt == RETRIES:
                    raise
                print(f"Ollama call failed ({e!r}); retrying in {RETRY_WAIT} s", flush=True)
                time.sleep(RETRY_WAIT)
        if (last.get("prompt_eval_count") or 0) >= NUM_CTX - 1024:
            raise RuntimeError("prompt filled the context window; Ollama may have cut it")
        self.last_usage = {
            "input_tokens": last.get("prompt_eval_count"),
            "output_tokens": last.get("eval_count"),
            "model": self.model,
            "truncated": last.get("done_reason") in ("length", "repeat"),
        }
        return salvage(text)

    def _stream(self, payload: dict) -> tuple[str, dict]:
        """Read a streamed reply. A repeat-limit abort ends it like a cut-off (D-057)."""
        parts: list[str] = []
        with self.http.stream("POST", "/api/chat", json=payload) as r:
            for line in r.iter_lines():
                if not line.strip():
                    continue
                msg = json.loads(line)
                if "error" in msg:
                    if "repeat" in msg["error"]:
                        print(f"model looped, keeping items so far: {msg['error']}", flush=True)
                        return "".join(parts), {"done_reason": "repeat"}
                    raise OllamaError(msg["error"])
                parts.append(msg.get("message", {}).get("content", ""))
                if msg.get("done"):
                    return "".join(parts), msg
            if r.status_code >= 400:
                r.raise_for_status()
        raise OllamaError("stream ended without a final message")

    def close(self) -> None:
        """Unload the model so only one is in memory at a time (D-054)."""
        import httpx

        # If the server is already gone, nothing is loaded.
        with contextlib.suppress(httpx.TransportError):
            self.http.post("/api/generate", json={"model": self.model, "keep_alive": 0})


class OllamaError(RuntimeError):
    """An error message from the Ollama server (retried, D-054)."""


def salvage(text: str) -> dict:
    """Parse the model's JSON; if it was cut off (D-056), keep the complete items."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    cut = text.rfind("}")
    while cut > 0:
        try:
            return json.loads(text[: cut + 1] + "]}")
        except json.JSONDecodeError:
            cut = text.rfind("}", 0, cut)
    return {"items": []}


def slug(model: str) -> str:
    """qwen3:8b -> qwen3-8b, for file names."""
    return re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")


# ----------------------------------------------------------------- citations


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def words(text: str) -> str:
    """Letters and digits only, space separated, with spaces at both ends (D-056)."""
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def found(quote: str, text: str) -> bool:
    """The quote's words appear as one unbroken run in the text's words."""
    q = words(quote)
    return q.strip() != "" and q in words(text)


def cite(items: list[dict], ctx: pd.DataFrame, cat: Category) -> tuple[list[dict], list[dict]]:
    """Keep items whose quote is found in their chunk; attach the chunk's citation."""
    by_id = ctx.set_index("chunk_id")
    kept, rejected = [], []
    for it in items:
        cid, quote = it.get("chunk_id", ""), it.get("evidence", "")
        ok = (
            cid in by_id.index
            and 0 < len(quote) <= MAX_QUOTE
            and found(quote, by_id.at[cid, "text"])
        )
        if not ok:
            # The quote may be from another provided chunk than the one named.
            hits = [c for c in by_id.index if found(quote, by_id.at[c, "text"])]
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
                "question": it.get("question", ""),
                "source": it.get("source", "model"),
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


TABLES = ("quantities", "closure_hours", "closure_damages")  # read by code, not scored


def run(
    contract: str,
    backend,
    categories=CATEGORIES,
    partial: Path | None = None,
    v2: bool = False,
) -> dict:
    """Extract every category. With `partial`, finished categories are saved after each
    call and skipped on a rerun, so an interrupted run resumes where it stopped. `v2`
    is the second round: rebuilt closure charts (D-060) and the checklist (D-061)."""
    from bidlens.documents.charts import chart_chunks

    chunks = pd.read_parquet(CACHE / contract / "chunks.parquet")
    charts = chart_chunks(contract) if v2 else None
    system, schema = (CHECKLIST_SYSTEM, CHECKLIST_SCHEMA) if v2 else (SYSTEM, SCHEMA)
    done = json.loads(partial.read_text()) if partial and partial.exists() else {}
    for cat in categories:
        if cat.key in done:
            continue
        ctx = retrieve(chunks, cat, charts=charts)
        t0 = time.perf_counter()
        raw = backend.complete(system, prompt(cat, ctx, checklist=v2), schema).get("items", [])
        kept, rej = cite(raw, ctx, cat)
        done[cat.key] = {
            "items": kept,
            "rejected": rej,
            "call": {
                "category": cat.key,
                "chunks": len(ctx),
                "returned": len(raw),
                "kept": len(kept),
                "seconds": round(time.perf_counter() - t0, 1),
                **getattr(backend, "last_usage", {}),
            },
        }
        print(f"{cat.key}: {len(kept)} kept of {len(raw)}", flush=True)
        if partial:
            partial.write_text(json.dumps(done), encoding="utf-8")
    keys = [c.key for c in categories]
    return {
        "contract": contract,
        "mode": backend.name + ("_v2" if v2 else ""),
        "model": getattr(backend, "model", ""),
        "items": quantities(contract)
        + (tables(contract) if v2 else [])
        + [i for k in keys for i in done[k]["items"]],
        "rejected": [i for k in keys for i in done[k]["rejected"]],
        "calls": [done[k]["call"] for k in keys],
    }


def tables(contract: str) -> list[dict]:
    """Closure hours (D-060) and late closure damages (D-062), read by code."""
    from bidlens.documents import patterns as pt

    out = []
    path = CACHE / contract / "charts.parquet"
    cs = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    for r in cs.itertuples():
        out.append(
            {
                "category": "closure_hours",
                "category_name": "Closure hours (closure charts)",
                "question": "",
                "source": "table",
                "statement": r.text,
                "value": r.compact.split(": ", 1)[-1],
                "evidence": f"Chart No. {r.chart}",
                "chunk_id": f"{r.file}:p{r.page}:{r.chart}",
                "document": "Special Provisions",
                "file": r.file,
                "page": int(r.page),
                "printed_page": "",
                "section": "12-4.02C(3) Closure charts",
                "section_number": "12-4.02C(3)",
            }
        )
    chunks = pd.read_parquet(CACHE / contract / "chunks.parquet")
    rows = [f for f in pt.match(chunks) if f["rule"] in pt.TABLE_RULES]
    kept, _ = cite(rows, chunks, _cat("time_damages"))
    for k in kept:
        k.update(category="closure_damages", category_name="Late closure damages", source="table")
    return out + kept


def _cat(key: str) -> Category:
    return next(c for c in CATEGORIES if c.key == key)


def pattern_run(contract: str) -> dict:
    """The pattern rules alone (D-062), checked and cited like model findings."""
    from bidlens.documents import patterns as pt

    chunks = pd.read_parquet(CACHE / contract / "chunks.parquet")
    t0 = time.perf_counter()
    raw = [f for f in pt.match(chunks) if f["rule"] not in pt.TABLE_RULES]
    items, rejected = [], []
    for cat in CATEGORIES:
        mine = [
            {**f, "source": "pattern", "question": f["rule"]} for f in raw if f["topic"] == cat.key
        ]
        kept, rej = cite(mine, chunks, cat)
        items += kept
        rejected += rej
    return {
        "contract": contract,
        "mode": "patterns",
        "model": "pattern rules (no model)",
        "items": quantities(contract) + tables(contract) + items,
        "rejected": rejected,
        "calls": [
            {
                "category": "all",
                "returned": len(raw),
                "kept": len(items),
                "seconds": round(time.perf_counter() - t0, 1),
            }
        ],
    }


def _overlap(a: dict, b: dict) -> bool:
    """D-063: the same fact twice, by quote containment in one chunk or statement words."""
    if a["category"] != b["category"]:
        return False
    if a["chunk_id"] == b["chunk_id"]:
        qa, qb = words(a["evidence"]), words(b["evidence"])
        if qa in qb or qb in qa:
            return True
    wa, wb = set(tokens(a["statement"])), set(tokens(b["statement"]))
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.7


def merge(contract: str, runs: list[dict], name: str) -> dict:
    """Merge kept findings in priority order (first run wins), dropping duplicates."""
    kept: list[dict] = []
    for res in runs:
        for it in res["items"]:
            if it["category"] in TABLES:
                continue
            if not any(_overlap(it, k) for k in kept):
                kept.append({**it, "run": res["mode"]})
    return {
        "contract": contract,
        "mode": name,
        "model": " + ".join(r.get("model", r["mode"]) for r in runs),
        "items": quantities(contract) + tables(contract) + kept,
        "rejected": [i for r in runs for i in r["rejected"]],
        "calls": [c for r in runs for c in r["calls"]],
        "merged_from": [r["mode"] for r in runs],
    }


def save(result: dict) -> Path:
    path = CACHE / result["contract"] / f"extraction_{result['mode']}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path


def load(contract: str, mode: str) -> dict:
    return json.loads((CACHE / contract / f"extraction_{mode}.json").read_text())


def model_run(contract: str, mode: str, model: str, v2: bool) -> dict:
    backend = HostedBackend(model or HOSTED_MODEL) if mode == "hosted" else LocalBackend(model)
    name = backend.name + ("_v2" if v2 else "")
    partial = CACHE / contract / f"extraction_{name}.partial.json"
    try:
        result = run(contract, backend, partial=partial, v2=v2)
    finally:
        if hasattr(backend, "close"):
            backend.close()
    save(result)
    partial.unlink(missing_ok=True)
    print(json.dumps(result["calls"], indent=2))
    return result


COMBINED_MODELS = ("qwen3:8b", "llama3.1:8b")  # priority order (D-063)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    ap.add_argument("--mode", choices=["local", "hosted", "combined", "patterns"], default="local")
    ap.add_argument("--model", help=f"Ollama model for local mode (default {LOCAL_MODEL})")
    ap.add_argument(
        "--round1",
        action="store_true",
        help="step 3.5 settings: open lists, raw chart text, no tables (for comparison)",
    )
    ap.add_argument(
        "--reuse", action="store_true", help="combined: merge saved runs instead of rerunning"
    )
    args = ap.parse_args(argv)
    c, v2 = args.contract, not args.round1
    if args.mode == "patterns":
        result = pattern_run(c)
    elif args.mode == "combined":
        runs = []
        for m in COMBINED_MODELS:
            name = f"local_{slug(m)}_v2"
            have = (CACHE / c / f"extraction_{name}.json").exists()
            runs.append(load(c, name) if args.reuse and have else model_run(c, "local", m, True))
        pat = pattern_run(c)
        save(pat)
        result = merge(c, [pat, *runs], "combined")
    else:
        model = args.model or (LOCAL_MODEL if args.mode == "local" else "")
        result = model_run(c, args.mode, model, v2)
    path = save(result)
    print(f"{len(result['items'])} items, {len(result['rejected'])} rejected -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
