"""Step 3.1: manifest of the sample bid package.

Usage:
    uv run python -m bidlens.documents.manifest 04-0W0504

The documents themselves stay in data/raw/bid_package/<contract>/ (git-ignored, downloaded
by hand). Only this manifest is committed: file name, kind, size, pages, SHA-256 and the
Caltrans page it came from.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import zipfile
from pathlib import Path

import pdfplumber

ROOT = Path(".")
PACKAGES = ROOT / "data" / "raw" / "bid_package"
MANIFEST = ROOT / "data" / "bid_package_manifest.csv"
OUT = ROOT / "outputs" / "16_bid_package"
SOURCE = "https://ppmoe.dot.ca.gov/cc?id=cc_advertisement_details&ad_id={contract}"

# File-name suffix after the contract number -> what the file is, and whether BidLens reads it.
KINDS = {
    "sp": ("Notice to Bidders and Special Provisions (includes the bid item list)", True),
    "formsforbid": ("Forms for bid", True),
    "IH": ("Information Handout (materials and site reports)", True),
    "fw": ("Project plans (drawings)", False),
    "ad3fw": ("Project plans revised by Addendum 3 (drawings)", False),
    "supplemental_info": ("Supplemental information (cross sections)", False),
    "": ("Bid summary (bid results; holds bidder names, never an input or output)", False),
}


def kind_of(contract: str, name: str) -> tuple[str, bool]:
    stem = name.split(".")[0].removeprefix(contract)
    if stem.startswith("ad") and stem[2:].isdigit():
        return f"Addendum No. {stem[2:]}", True
    return KINDS.get(stem, ("Other", False))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pages(path: Path) -> int | str:
    if path.suffix.lower() == ".pdf":
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            return f"{sum(1 for i in z.infolist() if not i.is_dir())} files"
    return ""


def build(contract: str) -> list[dict]:
    folder = PACKAGES / contract
    rows = []
    for f in sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")):
        kind, used = kind_of(contract, f.name)
        rows.append(
            {
                "contract": contract,
                "file": f.name,
                "kind": kind,
                "read_by_bidlens": used,
                "bytes": f.stat().st_size,
                "pages": pages(f),
                "sha256": sha256(f),
                "source": SOURCE.format(contract=contract),
                "obtained": "Downloaded by hand by the maintainer; not scripted",
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    rows = build(ap.parse_args(argv).contract)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_outputs(rows)
    for r in rows:
        print(f"{r['file']:32s} {r['pages']!s:>10} {r['kind']}")
    return 0


def write_outputs(rows: list[dict]) -> None:
    from datetime import date

    from bidlens.outputs import write_index

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.csv").write_text(MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")
    c = rows[0]["contract"]
    lines = ["| File | What it is | Pages | Read by BidLens |", "| --- | --- | ---: | --- |"]
    for r in rows:
        lines.append(
            f"| `{r['file']}` | {r['kind']} | {r['pages']} | "
            f"{'yes' if r['read_by_bidlens'] else 'no'} |"
        )
    body = f"""
The sample bid package BidLens reads in Phase 3: Caltrans contract {c} (step 3.1).

## Which project and why

Contract {c}: highway work in Alameda and Contra Costa counties (trash capture devices,
maintenance vehicle pullouts, guardrail, erosion control and lighting), engineer's estimate
$22.7 million, 120 bid items, bids opened 17 September 2026. Bids are already open, so the
draft estimate BidLens builds from these documents can be checked against the real bids.
It has three addenda and an information handout.

## The files

{chr(10).join(lines)}

The documents are not in this repository: Caltrans serves them from a site that does not
allow automated downloads, so they were downloaded by hand from the contract's page
({rows[0]["source"]}) into `data/raw/bid_package/{c}/`. `manifest.csv` lists each file's
size and SHA-256 fingerprint, so anyone can check they have the same files. The plans are
drawings without a text layer and are not read in v1. The bid summary is the bid result,
not part of the package; it names bidders and is never used here.

## How it was produced

`uv run python -m bidlens.documents.manifest {c}`. Generated {date.today().isoformat()}.
"""
    (OUT / "README.md").write_text("# 16 Bid package\n\n" + body.strip() + "\n", encoding="utf-8")
    write_index()


if __name__ == "__main__":
    raise SystemExit(main())
