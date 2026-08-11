#!/usr/bin/env python3
"""Acquire the unchanged numbered 540-radical composite as a local fallback asset."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA_PATH = ROOT / "source-data" / "wikimedia-2026-08-10"
METADATA_PATH = SOURCE_DATA_PATH / "commons-shuowen-540-numbered-composite-metadata.json"
MANIFEST_PATH = ROOT / "assets" / "manifest.json"
RADICALS_PATH = ROOT / "radicals"
LOCAL_PATH = ROOT / "assets" / "shuowen_seal" / "_library" / "shuowen-540-numbered.svg"
SOURCE_ID = "commons-shuowen-540-numbered-composite-2026-08-10"
SOURCE_FILE = "The 540 Shuowen Seal Radicals - numbered.svg"
WAYBACK_CAPTURE = "20210507100504"
WAYBACK_URL = (
    "https://web.archive.org/web/20210507100504id_/"
    "https://upload.wikimedia.org/wikipedia/commons/0/06/"
    "The_540_Shuowen_Seal_Radicals_-_numbered.svg"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Safari/537.36 hanzi-project/1.0"
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def request_bytes(url: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def acquire_metadata() -> None:
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "imageinfo",
            "titles": f"File:{SOURCE_FILE}",
            "iiprop": "url|size|mime|sha1|timestamp|mediatype|extmetadata",
            "format": "json",
            "formatversion": "2",
        }
    )
    url = f"https://commons.wikimedia.org/w/api.php?{query}"
    raw = request_bytes(url, "application/json")
    result = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "request_url": url,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "response": json.loads(raw),
    }
    SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote numbered-composite Commons metadata")


def metadata_value(metadata: dict, name: str) -> str:
    return str(metadata.get(name, {}).get("value", "")).strip()


def acquire_original() -> None:
    metadata_payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    page = metadata_payload["response"]["query"]["pages"][0]
    imageinfo = page["imageinfo"][0]
    metadata = imageinfo["extmetadata"]
    license_id = metadata_value(metadata, "License")
    if license_id != "cc-by-sa-4.0":
        raise RuntimeError(f"unexpected composite license: {license_id!r}")
    if imageinfo["mime"] != "image/svg+xml":
        raise RuntimeError("composite original is not SVG")
    acquisition_route = {
        "source_id": SOURCE_ID,
        "url": imageinfo["url"],
    }
    try:
        raw = request_bytes(imageinfo["url"], "image/svg+xml")
    except HTTPError as exc:
        if exc.code != 429:
            raise
        raw = request_bytes(WAYBACK_URL, "image/svg+xml")
        acquisition_route = {
            "source_id": "internet-archive-wayback-commons-mirror-2026-08-10",
            "url": WAYBACK_URL,
            "capture_timestamp": WAYBACK_CAPTURE,
            "integrity_requirement": "Byte-for-byte match to Commons imageinfo SHA-1",
        }
    if hashlib.sha1(raw).hexdigest() != imageinfo["sha1"]:
        raise RuntimeError("composite differs from Commons original SHA-1")
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_PATH.write_bytes(raw)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    preferred_sources = {
        "commons-shuowen-540-svg-series-2026-08-10",
        "commons-shuowen-seal-files-2026-08-10",
    }
    acquired_numbers = {
        asset["kangxi_number"]
        for asset in manifest["assets"]
        if asset.get("source_id") in preferred_sources
    }
    manifest["assets"] = [
        asset for asset in manifest["assets"] if asset.get("source_id") != SOURCE_ID
    ]
    common = {
        "source_id": SOURCE_ID,
        "source_file": SOURCE_FILE,
        "source_file_page": imageinfo["descriptionurl"],
        "original_url": imageinfo["url"],
        "local_path": str(LOCAL_PATH.relative_to(ROOT)),
        "retrieved_at": utc_now(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "mime_type": imageinfo["mime"],
        "media_type": imageinfo.get("mediatype"),
        "width": imageinfo["width"],
        "height": imageinfo["height"],
        "commons_sha1": imageinfo["sha1"],
        "commons_timestamp": imageinfo["timestamp"],
        "license_id": license_id,
        "license_url": metadata_value(metadata, "LicenseUrl") or None,
        "usage_terms": metadata_value(metadata, "UsageTerms") or None,
        "artist": metadata_value(metadata, "Artist") or None,
        "credit": metadata_value(metadata, "Credit") or None,
        "attribution_required": metadata_value(metadata, "AttributionRequired") or None,
        "acquisition_route": acquisition_route,
        "transformations": [],
        "representation_note": "Unchanged numbered composite; the locator identifies a Shuowen radical without cropping the stored original.",
    }
    created = 0
    for number in range(1, 215):
        record = json.loads((RADICALS_PATH / f"{number}.json").read_text(encoding="utf-8"))
        shuowen = record.get("shuowen")
        if shuowen is None or number in acquired_numbers:
            continue
        manifest["assets"].append(
            {
                **common,
                "asset_id": f"shuowen-composite-{record['primary']['codepoint']}",
                "kangxi_number": number,
                "shuowen_radical_number": shuowen["radical_number"],
                "locator": {
                    "kind": "shuowen_radical_number",
                    "value": shuowen["radical_number"],
                },
            }
        )
        created += 1
    manifest["assets"] = sorted(
        manifest["assets"], key=lambda asset: (asset["kangxi_number"], asset["asset_id"])
    )
    manifest["generated_at"] = utc_now()
    manifest["shuowen_540_composite_metadata"] = {
        "local_path": str(METADATA_PATH.relative_to(ROOT)),
        "sha256": hashlib.sha256(METADATA_PATH.read_bytes()).hexdigest(),
        "retrieved_at": metadata_payload["retrieved_at"],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"acquired unchanged composite ({len(raw)} bytes); created {created} fallback locators")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("metadata", "download"))
    args = parser.parse_args()
    if args.command == "metadata":
        acquire_metadata()
    else:
        acquire_original()


if __name__ == "__main__":
    main()
