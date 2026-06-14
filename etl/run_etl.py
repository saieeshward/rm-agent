#!/usr/bin/env python3
"""
Phase 1 — ETL orchestrator: scrape -> transform -> load -> proofs.

Usage:
  python -m etl.run_etl                 # fresh scrape, then load (use on submit day)
  python -m etl.run_etl --use-cache     # reuse etl/.cache/raw.json (dev loop)
  python -m etl.run_etl --manifest-only # just (re)write SCRAPE_MANIFEST.json from cache

After loading, run scripts/compute_load_fingerprint.py to emit etl/LOAD_PROOF.json
and reconcile both proofs against the data site /verify page on the scrape day.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
from pathlib import Path

ETL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ETL_DIR))

from transform import load_raw, transform  # noqa: E402
from load import load  # noqa: E402

MANIFEST_PATH = ETL_DIR / "SCRAPE_MANIFEST.json"
PAGE_SIZE = 100


def write_scrape_manifest(raw: dict) -> dict:
    ids = sorted({d["reservation_id"] for d in raw["details"]})
    ids_sha = hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()
    manifest = {
        "anchor_date": raw["verify"].get("anchor_date"),
        "dataset_revision": raw["verify"].get("dataset_revision"),
        "pages_scraped": math.ceil(len(ids) / PAGE_SIZE),
        "reservation_ids_count": len(ids),
        "reservation_ids_sha256": ids_sha,
        "source_url": raw.get("base_url"),
        "notes": "reservation_ids_sha256 = sha256 of sorted distinct reservation_id lines; "
                 "must match count(distinct reservation_id) in DB and total_reservations on /verify.",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-cache", action="store_true", help="reuse etl/.cache/raw.json")
    parser.add_argument("--manifest-only", action="store_true", help="only rewrite SCRAPE_MANIFEST.json")
    args = parser.parse_args()

    if not args.use_cache and not args.manifest_only:
        import scrape  # noqa: E402
        asyncio.run(scrape.main())

    raw = load_raw()

    manifest = write_scrape_manifest(raw)
    print(f"wrote {MANIFEST_PATH.name}: {manifest['reservation_ids_count']} ids, "
          f"{manifest['pages_scraped']} pages, anchor {manifest['anchor_date']}")

    if args.manifest_only:
        return

    data = transform(raw)
    result = load(
        data,
        dataset_revision=raw["verify"]["dataset_revision"],
        source_url=raw["base_url"],
        scraped_at=raw["verify"].get("anchor_date"),
    )
    print(f"loaded {result['fact_rows']} fact rows; row_hash={result['row_hash']}")
    print("next: python scripts/compute_load_fingerprint.py --manifest etl/SCRAPE_MANIFEST.json "
          "--output etl/LOAD_PROOF.json  (then reconcile with /verify)")


if __name__ == "__main__":
    main()
