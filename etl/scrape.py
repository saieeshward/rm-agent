#!/usr/bin/env python3
"""
Phase 1 — EXTRACT.

Scrapes the live (client-rendered, Next.js RSC) data site with Playwright and
writes a single raw snapshot to etl/.cache/raw.json. No transformation or DB
work happens here — see transform.py / load.py.

The site is forward-looking from "today" (the anchor date) and regenerates
daily, so the snapshot is only valid for the anchor recorded inside it.

Strategy (see ARCHITECTURE.md):
  - one browser context, images/css/fonts/media blocked for speed
  - /verify  -> Raw JSON reconciliation targets
  - /reference -> 5 lookup tables (tabbed)
  - /reservations -> paginated list (100/page), collect reservation ids
  - /reservations/<id> -> <dl> field block + per-night stay-rows table,
    fetched concurrently (bounded) since this is the bulk of the work
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

BASE = "https://otel-hackathon-data-site.vercel.app"
CACHE = Path(__file__).resolve().parent / ".cache"
# Parallel detail fetches. Override with DETAIL_CONCURRENCY=1 on environments where
# Chromium's new headless mode (Playwright 1.40+) crashes under concurrent new_page
# (seen on macOS Darwin 25.x): set it to 1 to scrape serially.
DETAIL_CONCURRENCY = int(os.environ.get("DETAIL_CONCURRENCY", "6"))
BLOCK = {"image", "media", "font", "stylesheet"}


async def _block_assets(context: BrowserContext) -> None:
    async def route(r):
        if r.request.resource_type in BLOCK:
            await r.abort()
        else:
            await r.continue_()

    await context.route("**/*", route)


async def scrape_verify(page: Page) -> dict:
    await page.goto(f"{BASE}/verify", wait_until="networkidle")
    await page.wait_for_selector("text=reservation_stay_status_sha256", timeout=30_000)
    raw = await page.evaluate(
        """() => {
            const pre = document.querySelector('details pre, details code, pre, code');
            return pre ? pre.textContent : null;
        }"""
    )
    if not raw:
        raise RuntimeError("could not read /verify Raw JSON")
    return json.loads(raw)


async def scrape_reference(page: Page) -> dict:
    await page.goto(f"{BASE}/reference", wait_until="networkidle")
    await page.wait_for_selector("table tbody tr", timeout=30_000)
    return await page.evaluate(
        """async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const read = () => {
              const tbl = document.querySelector('table');
              if (!tbl) return null;
              const headers = [...tbl.querySelectorAll('thead th, thead td')].map(t => t.textContent.trim());
              const rows = [...tbl.querySelectorAll('tbody tr')]
                .map(tr => [...tr.querySelectorAll('td,th')].map(c => c.textContent.trim()));
              return { headers, rows };
            };
            const out = {};
            const tabs = { room_types: 'Room types', markets: 'Markets',
                           channels: 'Channels', rate_plans: 'Rate plans', macro_history: 'Macro history' };
            for (const [key, label] of Object.entries(tabs)) {
              const btn = [...document.querySelectorAll('button,[role=tab],a')]
                .find(b => b.textContent.trim() === label);
              if (btn) { btn.click(); await sleep(250); }
              out[key] = read();
            }
            return out;
        }"""
    )


async def scrape_list(page: Page) -> list[dict]:
    """Page through the list (100/page) and collect every row's cells + id."""
    await page.goto(f"{BASE}/reservations", wait_until="networkidle")
    await page.wait_for_selector("table tbody tr", timeout=30_000)
    rows: list[dict] = []
    seen_pages: set[str] = set()
    while True:
        page_info = await page.evaluate(
            """() => {
                const t = document.body.innerText;
                const m = t.match(/Page\\s+(\\d+)\\s+of\\s+(\\d+)/i);
                const tbl = document.querySelector('table');
                const headers = [...tbl.querySelectorAll('thead th,thead td')].map(c=>c.textContent.trim());
                const data = [...tbl.querySelectorAll('tbody tr')].map(tr => {
                  const cells = [...tr.querySelectorAll('td,th')].map(c=>c.textContent.trim());
                  const a = tr.querySelector('a[href*="/reservations/"]');
                  return { cells, href: a ? a.getAttribute('href') : null };
                });
                return { cur: m ? m[1] : '1', total: m ? m[2] : '1', headers, data };
            }"""
        )
        key = page_info["cur"]
        if key in seen_pages:
            break
        seen_pages.add(key)
        headers = page_info["headers"]
        for r in page_info["data"]:
            rec = dict(zip(headers, r["cells"]))
            rec["_href"] = r["href"]
            rec["reservation_id"] = (r["href"] or "").rsplit("/", 1)[-1]
            rows.append(rec)
        if page_info["cur"] == page_info["total"]:
            break
        # advance
        await page.click("text=Next →")
        await page.wait_for_function(
            "(prev) => { const m=document.body.innerText.match(/Page\\s+(\\d+)\\s+of/i); return m && m[1] !== prev; }",
            arg=key,
            timeout=30_000,
        )
    return rows


async def _extract_detail(page: Page, rid: str) -> dict:
    """Navigate `page` to one reservation detail and extract its fields + stay rows."""
    await page.goto(f"{BASE}/reservations/{rid}", wait_until="domcontentloaded")
    await page.wait_for_selector("dl dd", timeout=30_000)
    return await page.evaluate(
        """() => {
            const dl = document.querySelector('dl');
            const dts = [...dl.querySelectorAll('dt')], dds = [...dl.querySelectorAll('dd')];
            const fields = {};
            dts.forEach((dt,i)=>{ fields[dt.textContent.trim()] = dds[i] ? dds[i].textContent.trim() : null; });
            const tbl = document.querySelector('table');
            const headers = tbl ? [...tbl.querySelectorAll('thead th,thead td')].map(c=>c.textContent.trim()) : [];
            const stay_rows = tbl ? [...tbl.querySelectorAll('tbody tr')]
              .map(tr => [...tr.querySelectorAll('td,th')].map(c=>c.textContent.trim())) : [];
            return { reservation_id: location.pathname.split('/').pop(),
                     fields, stay_headers: headers, stay_rows };
        }"""
    )


async def scrape_details(context: BrowserContext, ids: list[str], workers: int) -> list[dict]:
    """
    Fetch every detail page with a fixed pool of `workers` REUSED pages.

    Pages are opened ONE AT A TIME up front (never two new_page() calls in flight)
    and each is reused for many reservations, so the context sees only `workers`
    page creations total and never a concurrent burst. Newer headless Chromium on
    macOS Darwin 25.x crashes on concurrent / high-volume page creation; this pattern
    sidesteps both. The caller keeps the list page open as a keepalive so the context
    is never at zero pages. Results come back in the original `ids` order.
    """
    queue: asyncio.Queue = asyncio.Queue()
    for idx, rid in enumerate(ids):
        queue.put_nowait((idx, rid))
    results: list = [None] * len(ids)

    async def worker(page: Page) -> None:
        while True:
            try:
                idx, rid = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            results[idx] = await _extract_detail(page, rid)

    # Sequential creation: the list comprehension awaits each new_page() before the
    # next, so two are never created at once.
    pages = [await context.new_page() for _ in range(max(1, min(workers, len(ids))))]
    try:
        await asyncio.gather(*[worker(p) for p in pages])
    finally:
        for p in pages:
            await p.close()
    return results


async def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        await _block_assets(context)
        page = await context.new_page()

        print("scraping /verify ...")
        verify = await scrape_verify(page)
        print(f"  anchor={verify.get('anchor_date')} rev={verify.get('dataset_revision')} "
              f"total_reservations={verify.get('total_reservations')} total_stay_rows={verify.get('total_stay_rows')}")

        print("scraping /reference ...")
        reference = await scrape_reference(page)

        print("scraping /reservations list ...")
        listing = await scrape_list(page)
        ids = [r["reservation_id"] for r in listing if r["reservation_id"]]
        print(f"  collected {len(ids)} reservation ids across list pages")

        # Keep the list page open through the detail phase: new headless Chromium can
        # quit when its last page closes, which would kill the context before the
        # worker pages open. Close it only after the details are gathered.
        print(f"scraping {len(ids)} detail pages ({DETAIL_CONCURRENCY} reused workers) ...")
        details = await scrape_details(context, ids, DETAIL_CONCURRENCY)

        await page.close()
        await browser.close()

    snapshot = {
        "base_url": BASE,
        "verify": verify,
        "reference": reference,
        "listing": listing,
        "details": details,
    }
    out = CACHE / "raw.json"
    out.write_text(json.dumps(snapshot, indent=2))
    print(f"\nwrote {out} ({out.stat().st_size:,} bytes)")

    # --- quick completeness + recon report ---
    total_stay_rows = sum(len(d["stay_rows"]) for d in details)
    rate_codes = sorted({d["fields"].get("rate_plan_code") for d in details})
    extra_labels = sorted({k for d in details for k in d["fields"]
                           if k not in _SCHEMA_FIELD_LABELS})
    print("\n--- recon ---")
    print(f"reservations scraped : {len(details)} (verify: {verify.get('total_reservations')})")
    print(f"total stay rows      : {total_stay_rows} (verify: {verify.get('total_stay_rows')})")
    print(f"distinct rate_plan_code ({len(rate_codes)}): {rate_codes}")
    print(f"extra (non-schema) detail field labels: {extra_labels}")
    ref_rate = reference.get("rate_plans", {}) or {}
    ref_codes = sorted({row[0] for row in ref_rate.get("rows", [])})
    print(f"rate_plan_lookup codes from /reference ({len(ref_codes)}): {ref_codes}")
    missing = sorted(set(rate_codes) - set(ref_codes))
    print(f"data rate codes NOT in /reference lookup: {missing}")


_SCHEMA_FIELD_LABELS = {
    "arrival_date", "departure_date", "nights", "reservation_status", "create_datetime",
    "cancellation_datetime", "guest_country", "is_block", "is_walk_in", "number_of_spaces",
    "space_type", "market_code", "channel_code", "source_name", "rate_plan_code",
    "adr_room", "lead_time", "company_name", "travel_agent_name",
}


if __name__ == "__main__":
    asyncio.run(main())
