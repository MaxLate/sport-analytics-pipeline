"""Capture the three dashboard pages with Playwright (installed Chrome) and build a GIF.

Run against sample data only, never against the personal warehouse:

    WAREHOUSE_PATH=$PWD/0_data/database/demo.duckdb uv run uvicorn "2_analytics.api.main:app" --port 8000
    cd 2_analytics/dashboard && python3 -m http.server 5500 --bind 127.0.0.1
    uv run --with pillow --with playwright python docs/capture_dashboard.py docs/images
"""

import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5500"
OUT = Path(sys.argv[1])
PAGES = {"overview": "index.html", "sleep": "sleep.html", "training": "training.html"}
WIDTH = 1280

OUT.mkdir(parents=True, exist_ok=True)

shots = {}
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(
        viewport={"width": WIDTH, "height": 900},
        locale="en-US",
        timezone_id="Europe/Berlin",
        color_scheme="dark",
    )
    for name, page_file in PAGES.items():
        page = context.new_page()
        page.goto(f"{BASE}/{page_file}", wait_until="networkidle")
        page.wait_for_timeout(2500)  # let Chart.js entry animations finish
        path = OUT / f"dashboard-{name}.png"
        page.screenshot(path=str(path), full_page=True)
        shots[name] = Image.open(path).convert("RGB")
        print(name, shots[name].size)
        page.close()
    browser.close()

frames = []
for name in PAGES:
    frame = shots[name].crop((0, 0, WIDTH, 900)).resize((960, 675), Image.LANCZOS)
    frames.append(
        frame.quantize(
            colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        )
    )
frames[0].save(
    OUT / "dashboard-tour.gif",
    save_all=True,
    append_images=frames[1:],
    duration=2800,
    loop=0,
    optimize=True,
)
print("gif", (OUT / "dashboard-tour.gif").stat().st_size // 1024, "KB")
