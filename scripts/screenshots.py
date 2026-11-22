"""Screenshot every app page with headless Chromium.

Usage:
    uv run python scripts/screenshots.py            # starts the app on port 8599
    uv run python scripts/screenshots.py --out DIR  # default outputs/21_app/screenshots

Saves one full-page PNG per page, plus a phone-width Home page.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8599
PAGES = [("01_overview", ""), ("02_package", "Package"), ("03_prices", "Prices"),
         ("04_market", "Market"), ("05_export", "Export")]  # fmt: skip


def wait_up(url: str, seconds: int = 60) -> None:
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            urllib.request.urlopen(url + "/_stcore/health", timeout=2)
            return
        except OSError:
            time.sleep(1)
    raise SystemExit("the app did not start")


def settle(page) -> None:
    """Wait until Streamlit has finished running the script and charts are drawn."""
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=60000)
    page.wait_for_timeout(1500)
    for _ in range(60):
        if page.locator('[data-testid="stStatusWidget"]').count() == 0:
            break
        page.wait_for_timeout(500)
    page.wait_for_timeout(2500)


def shoot(page, path: Path, width: int) -> None:
    """Streamlit scrolls inside its own container, so grow the window to fit the page."""
    h = page.evaluate(
        '() => Math.max(...[...document.querySelectorAll(\'[data-testid="stMain"], '
        '[data-testid="stAppViewContainer"], section.main\')].map(e => e.scrollHeight), 800)'
    )
    page.set_viewport_size({"width": width, "height": int(h) + 40})
    page.wait_for_timeout(1500)
    page.screenshot(path=str(path), full_page=True)


def main(argv: list[str] | None = None) -> int:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "21_app" / "screenshots"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    url = f"http://localhost:{PORT}"
    app = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app/Home.py", "--server.port", str(PORT),
         "--server.headless", "true"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        wait_up(url)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1)
            for name, path in PAGES:
                page.set_viewport_size({"width": 1400, "height": 900})
                page.goto(f"{url}/{path}")
                settle(page)
                shoot(page, out / f"{name}.png", 1400)
                print(out / f"{name}.png")
            phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            phone.goto(url)
            settle(phone)
            shoot(phone, out / "06_overview_phone.png", 390)
            print(out / "06_overview_phone.png")
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
