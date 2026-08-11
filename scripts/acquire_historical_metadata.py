#!/usr/bin/env python3
"""Acquire Commons metadata for mapped radical historical-form candidates."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = ROOT / "source-data" / "wikimedia-2026-08-10"
CANDIDATES = SOURCE_DATA / "commons-acc-radical-historical-candidates.json"
OUTPUT = SOURCE_DATA / "commons-acc-historical-file-metadata.json"
SOURCE_ID = "commons-ancient-chinese-historical-form-files-2026-08-10"
API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "hanzi-project/1.0 (historical radical file-license audit)"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def request_bytes(url: str) -> bytes:
    for attempt in range(4):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = min(float(retry_after), 30.0) if retry_after else 8.0 * (attempt + 1)
            time.sleep(delay)
    raise RuntimeError("unreachable retry state")


def main() -> None:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    files = sorted(
        record["source_file"]
        for record in candidates["records"]
        if record["status"] == "candidate"
    )
    if len(files) != len(set(files)):
        raise ValueError("historical candidate source filenames are not unique")
    batches: list[dict[str, object]] = []
    pages: list[dict[str, object]] = []
    for offset in range(0, len(files), 25):
        titles = [f"File:{filename}" for filename in files[offset : offset + 25]]
        query = urllib.parse.urlencode(
            {
                "action": "query",
                "prop": "imageinfo|categories",
                "titles": "|".join(titles),
                "iiprop": (
                    "timestamp|user|userid|url|size|sha1|mime|mediatype|extmetadata"
                ),
                "iilimit": "1",
                "cllimit": "max",
                "format": "json",
                "formatversion": "2",
            }
        )
        request_url = f"{API_URL}?{query}"
        raw = request_bytes(request_url)
        response = json.loads(raw)
        response_pages = response.get("query", {}).get("pages", [])
        batches.append(
            {
                "offset": offset,
                "requested_titles": titles,
                "request_url": request_url,
                "response_sha256": hashlib.sha256(raw).hexdigest(),
                "response_bytes": len(raw),
                "returned_page_count": len(response_pages),
            }
        )
        pages.extend(response_pages)
        print(f"metadata {min(offset + 25, len(files))}/{len(files)}", flush=True)
        if offset + 25 < len(files):
            time.sleep(1.1)
    by_title = {page.get("title"): page for page in pages}
    missing_titles = [f"File:{filename}" for filename in files if f"File:{filename}" not in by_title]
    if missing_titles:
        raise RuntimeError(f"Commons omitted requested pages: {missing_titles}")
    payload = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "candidate_source_id": candidates["source_id"],
        "candidate_path": str(CANDIDATES.relative_to(ROOT)),
        "candidate_sha256": hashlib.sha256(CANDIDATES.read_bytes()).hexdigest(),
        "requested_file_count": len(files),
        "request_spacing_seconds": 1.1,
        "batches": batches,
        "pages": sorted(pages, key=lambda page: page.get("title", "")),
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT.relative_to(ROOT)} with {len(pages)} pages")


if __name__ == "__main__":
    main()
