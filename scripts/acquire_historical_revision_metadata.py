#!/usr/bin/env python3
"""Pin Commons file-history evidence for exact SVGs found in a transport mirror."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = ROOT / "source-data" / "wikimedia-2026-08-10"
MIRROR_LOG = (
    ROOT
    / "source-data"
    / "github-analects-data-2026-08-10"
    / "mirror-acquisition-log.json"
)
OUTPUT = SOURCE_DATA / "commons-acc-historical-file-revisions.json"
API = "https://commons.wikimedia.org/w/api.php"
SOURCE_ID = "commons-ancient-chinese-historical-form-files-2026-08-10"
USER_AGENT = "hanzi-project/1.0 (historical Commons revision integrity audit)"
BATCH_SIZE = 25


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def request_json(params: dict[str, str]) -> dict[str, Any]:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def main() -> None:
    mirror = json.loads(MIRROR_LOG.read_text(encoding="utf-8"))
    mismatches = mirror["mismatches"]
    mismatch_by_file = {item["source_file"]: item for item in mismatches}
    histories: dict[str, list[dict[str, Any]]] = {}
    request_count = 0
    for offset in range(0, len(mismatches), BATCH_SIZE):
        batch = mismatches[offset : offset + BATCH_SIZE]
        continuation: dict[str, str] = {}
        while True:
            params = {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "imageinfo",
                "titles": "|".join(f"File:{item['source_file']}" for item in batch),
                "iiprop": "timestamp|user|url|size|sha1|mime|mediatype",
                "iilimit": "max",
                "maxlag": "5",
                **continuation,
            }
            if request_count:
                time.sleep(1.1)
            response = request_json(params)
            request_count += 1
            if "error" in response:
                raise RuntimeError(response["error"])
            for page in response.get("query", {}).get("pages", []):
                source_file = page["title"].removeprefix("File:")
                histories.setdefault(source_file, []).extend(page.get("imageinfo", []))
            next_values = response.get("continue")
            if not next_values:
                break
            continuation = {
                str(key): str(value)
                for key, value in next_values.items()
                if key != "continue"
            }
        print(
            f"revision metadata {min(offset + BATCH_SIZE, len(mismatches))}/"
            f"{len(mismatches)}",
            flush=True,
        )

    matches: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for source_file, mismatch in sorted(mismatch_by_file.items()):
        wanted = mismatch["mirror_sha1"]
        matching = [info for info in histories.get(source_file, []) if info["sha1"] == wanted]
        if len(matching) == 1:
            info = matching[0]
            matches.append(
                {
                    "source_file": source_file,
                    "kangxi_number": mismatch["kangxi_number"],
                    "kind": mismatch["kind"],
                    "mirror_sha1": wanted,
                    "current_commons_sha1": mismatch["commons_sha1"],
                    "matched_revision": info,
                    "mapping_method": "exact_content_sha1_to_commons_file_history",
                }
            )
        else:
            unresolved.append(
                {
                    **mismatch,
                    "matching_revision_count": len(matching),
                    "history_revision_count": len(histories.get(source_file, [])),
                }
            )
    payload = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "api": API,
        "request_policy": (
            "MediaWiki imageinfo history queries in batches of 25, with at least "
            "1.1 seconds between same-host requests."
        ),
        "request_count": request_count,
        "queried_file_count": len(mismatches),
        "matched_historical_revision_count": len(matches),
        "unresolved_count": len(unresolved),
        "integrity_policy": (
            "A mirror file is eligible only when its content SHA-1 appears exactly "
            "once in the Commons file's pinned revision history."
        ),
        "matches": matches,
        "unresolved": unresolved,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"matched historical revisions {len(matches)}/{len(mismatches)}; "
        f"unresolved {len(unresolved)}; output sha256 "
        f"{hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}"
    )


if __name__ == "__main__":
    main()
