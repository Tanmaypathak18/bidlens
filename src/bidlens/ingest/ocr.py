"""OCR for bid summaries that have no usable text layer (decision D-025).

Pages are rendered with pypdfium2 and read with Apple Vision (macOS only). Recognized
words are regrouped into lines by vertical position so the regular parser can read them.
OCR text is cached so each file is read once.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
from collections.abc import Callable
from pathlib import Path

import pypdfium2 as pdfium

DPI = 300


def _vision_lines(png: Path) -> list[str]:
    import Vision  # macOS only; imported lazily
    from Foundation import NSURL

    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
        NSURL.fileURLWithPath_(str(png)), {}
    )
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(f"Vision OCR failed: {err}")
    words = []
    for obs in req.results() or []:
        box = obs.boundingBox()
        text = obs.topCandidates_(1)[0].string()
        y_mid = 1 - box.origin.y - box.size.height / 2  # top-down
        words.append((y_mid, box.origin.x, box.size.height, text))
    return group_lines(words)


def group_lines(words: list[tuple[float, float, float, str]]) -> list[str]:
    """Group (y, x, height, text) boxes into text lines, top to bottom, left to right."""
    lines: list[list] = []
    for y, x, h, text in sorted(words):
        if lines and abs(lines[-1][0] - y) < h * 0.5:
            lines[-1][1].append((x, text))
        else:
            lines.append([y, [(x, text)]])
    return [" ".join(t for _, t in sorted(parts)) for _, parts in lines]


def ocr_pages(
    pdf_path: Path,
    cache_dir: Path,
    *,
    stop: Callable[[list[str]], bool] | None = None,
) -> list[str]:
    """OCR a PDF page by page. `stop(pages_so_far)` can end early. Results are cached."""
    pdf_path = Path(pdf_path)
    digest = hashlib.sha1(pdf_path.read_bytes()).hexdigest()
    cache = Path(cache_dir) / f"{pdf_path.stem}_{digest[:12]}.json.gz"
    if cache.exists():
        return json.loads(gzip.decompress(cache.read_bytes()))
    doc = pdfium.PdfDocument(str(pdf_path))
    pages: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(len(doc)):
            png = Path(tmp) / f"p{i}.png"
            doc[i].render(scale=DPI / 72).to_pil().save(png)
            pages.append("\n".join(_vision_lines(png)))
            if stop and stop(pages):
                break
    doc.close()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(gzip.compress(json.dumps(pages).encode()))
    return pages
