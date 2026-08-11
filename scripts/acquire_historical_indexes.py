#!/usr/bin/env python3
"""Acquire pinned Commons project indexes for radical historical forms."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "source-data"
    / "wikimedia-2026-08-10"
    / "commons-acc-radical-historical-indexes.json"
)
SOURCE_ID = "commons-acc-radical-historical-indexes-2026-08-10"
TITLES = [
    "Commons:Ancient Chinese characters/oracle",
    "Commons:Ancient Chinese characters/bronze",
    "Commons:Ancient Chinese characters/bigseal",
]
USER_AGENT = "hanzi-project/1.0 (historical radical source audit)"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def main() -> None:
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "revisions",
            "titles": "|".join(TITLES),
            "rvprop": "ids|timestamp|content",
            "rvslots": "main",
            "format": "json",
            "formatversion": "2",
        }
    )
    request_url = f"https://commons.wikimedia.org/w/api.php?{query}"
    request = urllib.request.Request(
        request_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    api_payload = json.loads(raw)
    pages = api_payload.get("query", {}).get("pages", [])
    if {page.get("title") for page in pages} != set(TITLES):
        raise RuntimeError("Commons response did not resolve all three project pages")
    rendered_pages = []
    for page in sorted(pages, key=lambda item: item["title"]):
        time.sleep(1.1)
        revision_id = page["revisions"][0]["revid"]
        parse_query = urllib.parse.urlencode(
            {
                "action": "parse",
                "oldid": revision_id,
                "prop": "text|images|templates",
                "format": "json",
                "formatversion": "2",
            }
        )
        parse_url = f"https://commons.wikimedia.org/w/api.php?{parse_query}"
        parse_request = urllib.request.Request(
            parse_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(parse_request, timeout=60) as response:
            parse_raw = response.read()
        rendered_pages.append(
            {
                "title": page["title"],
                "page_id": page["pageid"],
                "revision_id": revision_id,
                "request_url": parse_url,
                "response_sha256": hashlib.sha256(parse_raw).hexdigest(),
                "response_bytes": len(parse_raw),
                "parse": json.loads(parse_raw).get("parse", {}),
            }
        )
    payload = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "request_url": request_url,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "response_bytes": len(raw),
        "pages": pages,
        "rendered_pages": rendered_pages,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for page in sorted(pages, key=lambda item: item["title"]):
        revision = page["revisions"][0]
        print(
            f"{page['title']}: page {page['pageid']}, revision {revision['revid']}, "
            f"{revision['timestamp']}"
        )


if __name__ == "__main__":
    main()
