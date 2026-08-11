#!/usr/bin/env python3
"""Acquire pinned hanzi_origin Commons filename discovery manifests."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "source-data" / "github-hanzi-origin-2026-08-10"
COMMIT = "309ccc3c6349357e6ece0181228e3fb2ad28b5cd"
SOURCE_ID = "github-hanzi-origin-commons-discovery-2026-08-10"
FILES = ["data/oracle_manifest.json", "data/oracle_manifest_extra.json"]
USER_AGENT = "hanzi-project/1.0 (pinned historical filename discovery)"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def main() -> None:
    acquisitions = []
    for index, relative in enumerate(FILES):
        url = f"https://raw.githubusercontent.com/vtsen/hanzi_origin/{COMMIT}/{relative}"
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        json.loads(raw)
        target = OUTPUT_ROOT / Path(relative).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        acquisitions.append(
            {
                "url": url,
                "path": str(target.relative_to(ROOT)),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
        )
        if index + 1 < len(FILES):
            time.sleep(1.1)
    payload = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "commit": COMMIT,
        "files": acquisitions,
    }
    audit = OUTPUT_ROOT / "acquisition.json"
    audit.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
