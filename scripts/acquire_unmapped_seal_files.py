#!/usr/bin/env python3
"""Acquire exact-character seal SVGs for Kangxi radicals without Shuowen headings."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA_PATH = ROOT / "source-data" / "wikimedia-2026-08-10"
METADATA_PATH = SOURCE_DATA_PATH / "commons-unmapped-kangxi-seal-metadata.json"
MANIFEST_PATH = ROOT / "assets" / "manifest.json"
ASSET_ROOT = ROOT / "assets" / "shuowen_seal"
SOURCE_ID = "commons-ancient-chinese-character-seal-files-2026-08-10"
GITHUB_MIRROR_SOURCE_ID = "github-hanzi-etymology-commons-mirror-2026-08-10"
GITHUB_MIRROR_REPOSITORY = "lbm364dl/hanzi-etymology-dict"
GITHUB_MIRROR_COMMIT = "caada9c8ec6f51e59158e9633598230d9e23a9c8"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Safari/537.36 hanzi-project/1.0"
)
UNMAPPED = {
    8: "亠",
    15: "冫",
    55: "廾",
    56: "弋",
    71: "无",
    88: "父",
    90: "爿",
    138: "艮",
    170: "阜",
    174: "靑",
}


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
        headers={"User-Agent": USER_AGENT, "Accept": "image/svg+xml,application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def wayback_original(
    original_url: str, revisions: list[dict[str, Any]]
) -> tuple[bytes, dict[str, str], dict[str, Any]]:
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
    by_sha1 = {revision["sha1"]: revision for revision in revisions}
    for row in reversed(rows[1:]):
        timestamp = row[1]
        captured_origin = row[2].replace("http://", "https://", 1)
        capture_url = f"https://web.archive.org/web/{timestamp}id_/{captured_origin}"
        raw = request_bytes(capture_url)
        actual_sha1 = hashlib.sha1(raw).hexdigest()
        if actual_sha1 in by_sha1:
            revision = by_sha1[actual_sha1]
            return raw, {
                "source_id": "internet-archive-wayback-commons-mirror-2026-08-10",
                "url": capture_url,
                "capture_timestamp": timestamp,
                "integrity_requirement": "Byte-for-byte match to Commons imageinfo SHA-1",
                "commons_revision_timestamp": revision["timestamp"],
            }, revision
        time.sleep(1.1)
    raise RuntimeError("no Wayback capture matches the Commons original SHA-1")


def github_original(
    source_file: str, original_url: str, revisions: list[dict[str, Any]]
) -> tuple[bytes, dict[str, str], dict[str, Any]]:
    """Fetch a pinned repository copy only when it exactly matches Commons."""
    current_name = urllib.parse.unquote(
        urllib.parse.urlparse(original_url).path.rsplit("/", 1)[-1]
    )
    candidate_names = list(dict.fromkeys((current_name, source_file)))
    by_sha1 = {revision["sha1"]: revision for revision in revisions}
    for candidate_name in candidate_names:
        encoded_path = urllib.parse.quote(
            f"docs/glyphs/wikimedia_seal/{candidate_name}", safe="/"
        )
        mirror_url = (
            "https://raw.githubusercontent.com/"
            f"{GITHUB_MIRROR_REPOSITORY}/{GITHUB_MIRROR_COMMIT}/{encoded_path}"
        )
        try:
            raw = request_bytes(mirror_url)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            time.sleep(1.1)
            continue
        actual_sha1 = hashlib.sha1(raw).hexdigest()
        if actual_sha1 in by_sha1:
            revision = by_sha1[actual_sha1]
            return raw, {
                "source_id": GITHUB_MIRROR_SOURCE_ID,
                "url": mirror_url,
                "repository": GITHUB_MIRROR_REPOSITORY,
                "commit": GITHUB_MIRROR_COMMIT,
                "integrity_requirement": "Byte-for-byte match to Commons imageinfo SHA-1",
                "commons_revision_timestamp": revision["timestamp"],
            }, revision
        time.sleep(1.1)
    raise RuntimeError("no pinned GitHub mirror file matches a Commons original SHA-1")


def acquire_metadata() -> None:
    titles = [f"File:{character}-seal.svg" for character in UNMAPPED.values()]
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "imageinfo",
            "titles": "|".join(titles),
            "iiprop": "url|size|mime|sha1|timestamp|mediatype|extmetadata",
            "iilimit": "max",
            "format": "json",
            "formatversion": "2",
        }
    )
    url = f"https://commons.wikimedia.org/w/api.php?{query}"
    raw = request_bytes(url)
    payload = json.loads(raw)
    result = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "request_url": url,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "mappings": [
            {
                "kangxi_number": number,
                "primary": character,
                "codepoint": f"U+{ord(character):04X}",
                "source_file": f"{character}-seal.svg",
            }
            for number, character in UNMAPPED.items()
        ],
        "pages": payload.get("query", {}).get("pages", []),
    }
    SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote exact-character metadata for {len(result['pages'])} pages")


def metadata_value(metadata: dict[str, Any], name: str) -> str:
    return str(metadata.get(name, {}).get("value", "")).strip()


def normalized_license(imageinfo: dict[str, Any]) -> str:
    metadata = imageinfo.get("extmetadata", {})
    return metadata_value(metadata, "License") or metadata_value(metadata, "LicenseShortName")


def license_allowed(license_id: str) -> bool:
    normalized = license_id.casefold().replace("_", "-").replace(" ", "-")
    return normalized == "pd" or normalized.startswith(
        ("pd-", "pdm", "cc0", "cc-by-", "cc-by-sa-", "public-domain")
    )


def download_one(kangxi_number: int) -> None:
    mapping = next(
        (item for item in json.loads(METADATA_PATH.read_text(encoding="utf-8"))["mappings"] if item["kangxi_number"] == kangxi_number),
        None,
    )
    if mapping is None:
        raise RuntimeError(f"radical {kangxi_number} is not in the unmapped set")
    payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    page = next(
        (page for page in payload["pages"] if page.get("title") == f"File:{mapping['source_file']}"),
        None,
    )
    if page is None or page.get("missing") or not page.get("imageinfo"):
        raise RuntimeError(f"exact-character source file is missing: {mapping['source_file']}")
    revisions = page["imageinfo"]
    imageinfo = revisions[0]
    license_id = normalized_license(imageinfo)
    if not license_allowed(license_id):
        raise RuntimeError(f"license is not allowlisted: {license_id!r}")
    if imageinfo.get("mime") != "image/svg+xml":
        raise RuntimeError(f"source is not SVG: {imageinfo.get('mime')!r}")
    acquisition_route = {"source_id": SOURCE_ID, "url": imageinfo["url"]}
    try:
        raw = request_bytes(imageinfo["url"])
    except HTTPError as exc:
        if exc.code != 429:
            raise
        try:
            raw, acquisition_route, matched_revision = wayback_original(
                imageinfo["url"], revisions
            )
        except RuntimeError:
            raw, acquisition_route, matched_revision = github_original(
                mapping["source_file"], imageinfo["url"], revisions
            )
        current_metadata = imageinfo["extmetadata"]
        imageinfo = {**matched_revision, "descriptionurl": imageinfo["descriptionurl"]}
        imageinfo["extmetadata"] = current_metadata
    if hashlib.sha1(raw).hexdigest() != imageinfo["sha1"]:
        raise RuntimeError(f"Commons SHA-1 mismatch for {mapping['source_file']}")

    asset_id = f"character-seal-{mapping['codepoint']}"
    directory = ASSET_ROOT / mapping["codepoint"]
    directory.mkdir(parents=True, exist_ok=True)
    local_path = directory / f"{asset_id}.svg"
    local_path.write_bytes(raw)
    metadata = imageinfo["extmetadata"]
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
        "license_url": metadata_value(metadata, "LicenseUrl") or None,
        "usage_terms": metadata_value(metadata, "UsageTerms") or None,
        "artist": metadata_value(metadata, "Artist") or None,
        "credit": metadata_value(metadata, "Credit") or None,
        "attribution_required": metadata_value(metadata, "AttributionRequired") or None,
        "acquisition_route": acquisition_route,
        "kangxi_number": mapping["kangxi_number"],
        "transformations": [],
        "representation_note": "Exact-character seal-script SVG; this does not assert that the character is one of Shuowen's 540 section headings.",
    }
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["assets"] = [
        item for item in manifest["assets"] if item["asset_id"] != asset_id
    ] + [asset]
    manifest["assets"] = sorted(
        manifest["assets"], key=lambda item: (item["kangxi_number"], item["asset_id"])
    )
    manifest["generated_at"] = utc_now()
    manifest["unmapped_seal_metadata"] = {
        "local_path": str(METADATA_PATH.relative_to(ROOT)),
        "sha256": hashlib.sha256(METADATA_PATH.read_bytes()).hexdigest(),
        "retrieved_at": payload["retrieved_at"],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"acquired exact-character seal for radical {kangxi_number}: {mapping['source_file']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("metadata")
    one = subparsers.add_parser("download-one")
    one.add_argument("--kangxi", type=int, required=True)
    args = parser.parse_args()
    if args.command == "metadata":
        acquire_metadata()
    else:
        download_one(args.kangxi)


if __name__ == "__main__":
    main()
