#!/usr/bin/env python3
"""Acquire the numbered Commons SVG series for mapped Shuowen radicals."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RADICALS_PATH = ROOT / "radicals"
SOURCE_DATA_PATH = ROOT / "source-data" / "wikimedia-2026-08-10"
METADATA_PATH = SOURCE_DATA_PATH / "commons-shuowen-540-series-metadata.json"
MANIFEST_PATH = ROOT / "assets" / "manifest.json"
ASSET_ROOT = ROOT / "assets" / "shuowen_seal"
SOURCE_ID = "commons-shuowen-540-svg-series-2026-08-10"
COMPOSITE_SOURCE_ID = "commons-shuowen-540-numbered-composite-2026-08-10"
GITHUB_MIRROR_SOURCE_ID = "github-hanzi-etymology-commons-mirror-2026-08-10"
GITHUB_MIRROR_REPOSITORY = "lbm364dl/hanzi-etymology-dict"
GITHUB_MIRROR_COMMIT = "caada9c8ec6f51e59158e9633598230d9e23a9c8"
API_URL = "https://commons.wikimedia.org/w/api.php"
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


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/svg+xml,application/json;q=0.9,*/*;q=0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def wayback_original(original_url: str, expected_sha1: str) -> tuple[bytes, dict[str, str]]:
    origin = original_url.split("?", 1)[0]
    query = urllib.parse.urlencode(
        {
            "url": origin,
            "output": "json",
            "filter": "statuscode:200",
            "collapse": "digest",
        }
    )
    cdx_url = f"https://web.archive.org/cdx/search/cdx?{query}"
    rows = json.loads(request_bytes(cdx_url))
    time.sleep(1.1)
    for row in reversed(rows[1:]):
        timestamp = row[1]
        captured_origin = row[2].replace("http://", "https://", 1)
        capture_url = f"https://web.archive.org/web/{timestamp}id_/{captured_origin}"
        raw = request_bytes(capture_url)
        if hashlib.sha1(raw).hexdigest() == expected_sha1:
            return raw, {
                "source_id": "internet-archive-wayback-commons-mirror-2026-08-10",
                "url": capture_url,
                "capture_timestamp": timestamp,
                "integrity_requirement": "Byte-for-byte match to Commons imageinfo SHA-1",
            }
        time.sleep(1.1)
    raise RuntimeError("no Wayback capture matches the Commons original SHA-1")


def github_original(source_file: str, expected_sha1: str) -> tuple[bytes, dict[str, str]]:
    encoded_path = urllib.parse.quote(
        f"docs/glyphs/wikimedia_seal/{source_file}", safe="/"
    )
    mirror_url = (
        "https://raw.githubusercontent.com/"
        f"{GITHUB_MIRROR_REPOSITORY}/{GITHUB_MIRROR_COMMIT}/{encoded_path}"
    )
    raw = request_bytes(mirror_url)
    if hashlib.sha1(raw).hexdigest() != expected_sha1:
        raise RuntimeError("pinned GitHub mirror differs from the Commons SHA-1")
    return raw, {
        "source_id": GITHUB_MIRROR_SOURCE_ID,
        "url": mirror_url,
        "repository": GITHUB_MIRROR_REPOSITORY,
        "commit": GITHUB_MIRROR_COMMIT,
        "integrity_requirement": "Byte-for-byte match to Commons imageinfo SHA-1",
    }


def preserve_composite_library_asset(manifest: dict[str, Any]) -> None:
    library_id = "shuowen-540-numbered-composite-library"
    library_assets = manifest.setdefault("library_assets", [])
    if any(asset.get("asset_id") == library_id for asset in library_assets):
        return
    composite = next(
        (
            asset
            for asset in manifest.get("assets", [])
            if asset.get("source_id") == COMPOSITE_SOURCE_ID
        ),
        None,
    )
    if composite is None:
        raise RuntimeError("cannot preserve the composite: no logical locator remains")
    library_asset = {
        key: value
        for key, value in composite.items()
        if key not in {"asset_id", "kangxi_number", "shuowen_radical_number", "locator"}
    }
    library_asset["asset_id"] = library_id
    library_asset["representation_note"] = (
        "Unchanged supplemental numbered composite of all 540 Shuowen seal radicals; "
        "individual record references use separately acquired numbered originals."
    )
    library_assets.append(library_asset)


def mapped_radicals() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for number in range(1, 215):
        record = json.loads((RADICALS_PATH / f"{number}.json").read_text(encoding="utf-8"))
        shuowen = record.get("shuowen")
        if shuowen is None:
            continue
        result.append(
            {
                "kangxi_number": number,
                "primary": record["primary"]["char"],
                "codepoint": record["primary"]["codepoint"],
                "shuowen_radical_number": shuowen["radical_number"],
                "source_file": f"Shuowen Seal Radical {shuowen['radical_number']:03d}.svg",
            }
        )
    return result


def acquire_metadata() -> None:
    mappings = mapped_radicals()
    batches: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for offset in range(0, len(mappings), 25):
        titles = [f"File:{item['source_file']}" for item in mappings[offset : offset + 25]]
        query = urllib.parse.urlencode(
            {
                "action": "query",
                "prop": "imageinfo",
                "titles": "|".join(titles),
                "iiprop": "url|size|mime|sha1|timestamp|mediatype|extmetadata",
                "format": "json",
                "formatversion": "2",
            }
        )
        url = f"{API_URL}?{query}"
        raw = request_bytes(url)
        payload = json.loads(raw)
        batches.append(
            {
                "offset": offset,
                "request_url": url,
                "response_sha256": hashlib.sha256(raw).hexdigest(),
                "response_bytes": len(raw),
            }
        )
        pages.extend(payload.get("query", {}).get("pages", []))
        if offset + 25 < len(mappings):
            time.sleep(1.1)
    result = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "requested_file_count": len(mappings),
        "mappings": mappings,
        "batches": batches,
        "pages": pages,
    }
    SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote metadata for {len(pages)} numbered Shuowen SVG pages")


def metadata_value(metadata: dict[str, Any], name: str) -> str:
    return str(metadata.get(name, {}).get("value", "")).strip()


def page_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        page.get("title", "").removeprefix("File:"): page
        for page in payload["pages"]
    }


def normalized_license(imageinfo: dict[str, Any]) -> str:
    metadata = imageinfo.get("extmetadata", {})
    return metadata_value(metadata, "License") or metadata_value(metadata, "LicenseShortName")


def license_allowed(license_id: str) -> bool:
    normalized = license_id.casefold().replace("_", "-").replace(" ", "-")
    return normalized.startswith(("cc-by-", "cc-by-sa-", "cc0", "pdm", "pd-")) or normalized == "pd"


def download_one(kangxi_number: int, mirror_first: bool = False) -> None:
    payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    mapping = next(
        (item for item in payload["mappings"] if item["kangxi_number"] == kangxi_number),
        None,
    )
    if mapping is None:
        raise RuntimeError(f"radical {kangxi_number} has no admitted Shuowen mapping")
    page = page_map(payload).get(mapping["source_file"])
    if page is None or page.get("missing") or not page.get("imageinfo"):
        raise RuntimeError(f"Commons file is missing: {mapping['source_file']}")
    imageinfo = page["imageinfo"][0]
    license_id = normalized_license(imageinfo)
    if not license_allowed(license_id):
        raise RuntimeError(f"license is not allowlisted: {license_id!r}")
    if imageinfo.get("mime") != "image/svg+xml":
        raise RuntimeError(f"numbered source is not SVG: {imageinfo.get('mime')!r}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    preserve_composite_library_asset(manifest)
    asset_id = f"shuowen-540-{mapping['codepoint']}"
    if any(asset["asset_id"] == asset_id for asset in manifest.get("assets", [])):
        print(f"already acquired {asset_id}")
        return

    if mirror_first:
        raw, acquisition_route = github_original(
            mapping["source_file"], imageinfo["sha1"]
        )
    else:
        acquisition_route = {"source_id": SOURCE_ID, "url": imageinfo["url"]}
        try:
            raw = request_bytes(imageinfo["url"])
        except HTTPError as exc:
            if exc.code != 429:
                raise
            try:
                raw, acquisition_route = github_original(
                    mapping["source_file"], imageinfo["sha1"]
                )
            except (HTTPError, RuntimeError):
                raw, acquisition_route = wayback_original(
                    imageinfo["url"], imageinfo["sha1"]
                )
    if hashlib.sha1(raw).hexdigest() != imageinfo["sha1"]:
        raise RuntimeError(f"Commons SHA-1 mismatch for {mapping['source_file']}")
    directory = ASSET_ROOT / mapping["codepoint"]
    directory.mkdir(parents=True, exist_ok=True)
    local_path = directory / f"{asset_id}.svg"
    local_path.write_bytes(raw)
    extmetadata = imageinfo["extmetadata"]
    asset = {
        "asset_id": asset_id,
        "source_id": SOURCE_ID,
        "source_file": mapping["source_file"],
        "source_file_page": imageinfo["descriptionurl"],
        "original_url": imageinfo["url"],
        "local_path": str(local_path.relative_to(ROOT)),
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
        "license_url": metadata_value(extmetadata, "LicenseUrl") or None,
        "usage_terms": metadata_value(extmetadata, "UsageTerms") or None,
        "artist": metadata_value(extmetadata, "Artist") or None,
        "credit": metadata_value(extmetadata, "Credit") or None,
        "attribution_required": metadata_value(extmetadata, "AttributionRequired") or None,
        "acquisition_route": acquisition_route,
        "kangxi_number": mapping["kangxi_number"],
        "shuowen_radical_number": mapping["shuowen_radical_number"],
        "transformations": [],
        "representation_note": "Modern vector rendering of the numbered Shuowen seal radical.",
    }
    manifest["assets"] = [
        item
        for item in manifest["assets"]
        if not (
            item.get("kangxi_number") == mapping["kangxi_number"]
            and item.get("source_id")
            == COMPOSITE_SOURCE_ID
        )
    ]
    manifest["assets"].append(asset)
    manifest["assets"] = sorted(
        manifest["assets"], key=lambda item: (item["kangxi_number"], item["asset_id"])
    )
    manifest["generated_at"] = utc_now()
    manifest["shuowen_540_series_metadata"] = {
        "local_path": str(METADATA_PATH.relative_to(ROOT)),
        "sha256": hashlib.sha256(METADATA_PATH.read_bytes()).hexdigest(),
        "retrieved_at": payload["retrieved_at"],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"acquired radical {kangxi_number}: {mapping['source_file']} ({len(raw)} bytes)")


def download_missing(delay: float, mirror_first: bool) -> None:
    if delay < 1.0:
        raise RuntimeError("per-host rate limit requires --delay >= 1.0")
    mappings = mapped_radicals()
    completed = 0
    for mapping in mappings:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if any(
            asset.get("kangxi_number") == mapping["kangxi_number"]
            and asset.get("source_id")
            in {SOURCE_ID, "commons-shuowen-seal-files-2026-08-10"}
            for asset in manifest.get("assets", [])
        ):
            continue
        try:
            download_one(mapping["kangxi_number"], mirror_first=mirror_first)
        except HTTPError as exc:
            if exc.code == 429:
                print(
                    f"stopped cleanly at radical {mapping['kangxi_number']}: Commons returned HTTP 429; rerun later to resume",
                    flush=True,
                )
                return
            raise
        completed += 1
        if completed % 10 == 0:
            print(f"progress: acquired {completed} files in this run", flush=True)
        time.sleep(delay)
    print(f"queue complete; acquired {completed} files in this run", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("metadata")
    one = subparsers.add_parser("download-one")
    one.add_argument("--kangxi", type=int, required=True)
    one.add_argument("--mirror-first", action="store_true")
    missing = subparsers.add_parser("download-missing")
    missing.add_argument("--delay", type=float, default=1.1)
    missing.add_argument("--mirror-first", action="store_true")
    args = parser.parse_args()
    if args.command == "metadata":
        acquire_metadata()
    elif args.command == "download-one":
        download_one(args.kangxi, mirror_first=args.mirror_first)
    else:
        download_missing(args.delay, mirror_first=args.mirror_first)


if __name__ == "__main__":
    main()
