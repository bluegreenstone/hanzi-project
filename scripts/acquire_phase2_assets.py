#!/usr/bin/env python3
"""Acquire and integrity-pin Commons assets admitted by the Phase 2 license gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_PATH = ROOT / "phase2-asset-candidates.json"
SOURCE_DATA_PATH = ROOT / "source-data" / "wikimedia-2026-08-10"
METADATA_PATH = SOURCE_DATA_PATH / "commons-shuowen-seal-metadata.json"
ASSET_ROOT = ROOT / "assets" / "shuowen_seal"
MANIFEST_PATH = ROOT / "assets" / "manifest.json"
SOURCE_ID = "commons-shuowen-seal-files-2026-08-10"
API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "hanzi-project/1.0 (Phase 2 source audit)"

FREE_LICENSE_PREFIXES = (
    "cc-by-",
    "cc-by-sa-",
    "cc0",
    "pdm",
    "pd-",
    "public domain",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def request_bytes(url: str) -> bytes:
    for attempt in range(4):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = min(float(retry_after), 30.0) if retry_after else 8.0 * (attempt + 1)
            time.sleep(delay)
    raise RuntimeError("unreachable retry state")


def source_file_map() -> dict[str, dict[str, Any]]:
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    return {candidate["source_file"]: candidate for candidate in payload["candidates"]}


def acquire_metadata() -> None:
    files = sorted(source_file_map())
    batches: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for offset in range(0, len(files), 25):
        titles = [f"File:{title}" for title in files[offset : offset + 25]]
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
        if offset + 25 < len(files):
            time.sleep(2.1)
    result = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "requested_file_count": len(files),
        "batches": batches,
        "pages": pages,
    }
    SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote metadata for {len(pages)} Commons pages")


def metadata_value(metadata: dict[str, Any], name: str) -> str:
    value = metadata.get(name, {}).get("value", "")
    return str(value).strip()


def normalized_license(imageinfo: dict[str, Any]) -> str:
    metadata = imageinfo.get("extmetadata", {})
    short = metadata_value(metadata, "LicenseShortName")
    code = metadata_value(metadata, "License")
    return code or short


def license_allowed(license_id: str, usage_terms: str) -> bool:
    normalized = license_id.casefold().replace("_", "-").replace(" ", "-").strip()
    terms = usage_terms.casefold().strip()
    if any(marker in normalized or marker in terms for marker in ("noncommercial", "no derivatives", "fair use")):
        return False
    return normalized == "pd" or normalized.startswith(FREE_LICENSE_PREFIXES)


def extension_for(source_file: str, mime: str) -> str:
    suffix = Path(source_file).suffix.lower()
    if suffix:
        return suffix
    return mimetypes.guess_extension(mime) or ".bin"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def admit_existing(kangxi_number: int) -> None:
    """Recover an exact original left on disk by an interrupted batch."""
    metadata_payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    candidates = source_file_map()
    matches = [
        candidate
        for candidate in candidates.values()
        if candidate["kangxi_number"] == kangxi_number
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one embedded candidate for radical {kangxi_number}")
    candidate = matches[0]
    source_file = candidate["source_file"]
    page = next(
        (
            page
            for page in metadata_payload["pages"]
            if page.get("title") == f"File:{source_file}"
        ),
        None,
    )
    if page is None or page.get("missing") or not page.get("imageinfo"):
        raise RuntimeError(f"Commons metadata is incomplete for {source_file}")
    imageinfo = page["imageinfo"][0]
    extmetadata = imageinfo["extmetadata"]
    license_id = normalized_license(imageinfo)
    usage_terms = metadata_value(extmetadata, "UsageTerms")
    if not license_allowed(license_id, usage_terms):
        raise RuntimeError(f"license is not allowlisted for {source_file}: {license_id}")
    extension = extension_for(source_file, imageinfo["mime"])
    codepoint = f"U+{ord(candidate['primary']):04X}"
    asset_id = f"shuowen-seal-{codepoint}"
    local_path = ASSET_ROOT / codepoint / f"{asset_id}{extension}"
    if not local_path.is_file():
        raise RuntimeError(f"interrupted-batch original is absent: {local_path}")
    payload = local_path.read_bytes()
    if hashlib.sha1(payload).hexdigest() != imageinfo["sha1"]:
        raise RuntimeError(f"Commons SHA-1 mismatch for recovered {source_file}")
    retrieved_at = (
        datetime.fromtimestamp(local_path.stat().st_mtime, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    asset = {
        "asset_id": asset_id,
        "source_id": SOURCE_ID,
        "source_file": source_file,
        "source_file_page": imageinfo["descriptionurl"],
        "original_url": imageinfo["url"],
        "local_path": str(local_path.relative_to(ROOT)),
        "retrieved_at": retrieved_at,
        "sha256": sha256_bytes(payload),
        "bytes": len(payload),
        "mime_type": imageinfo["mime"],
        "media_type": imageinfo.get("mediatype"),
        "width": imageinfo["width"],
        "height": imageinfo["height"],
        "commons_sha1": imageinfo["sha1"],
        "commons_timestamp": imageinfo["timestamp"],
        "license_id": license_id,
        "license_url": metadata_value(extmetadata, "LicenseUrl") or None,
        "usage_terms": usage_terms or None,
        "artist": metadata_value(extmetadata, "Artist") or None,
        "credit": metadata_value(extmetadata, "Credit") or None,
        "attribution_required": metadata_value(extmetadata, "AttributionRequired") or None,
        "kangxi_number": kangxi_number,
        "source_page": candidate["source_page"],
        "source_revision_id": candidate["revision_id"],
        "transformations": [],
        "recovery_note": "Exact Commons original recovered from an interrupted direct-download batch before manifest commit.",
    }
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["assets"] = [
        existing
        for existing in manifest["assets"]
        if existing.get("kangxi_number") != kangxi_number
    ] + [asset]
    manifest["assets"] = sorted(
        manifest["assets"], key=lambda existing: existing["kangxi_number"]
    )
    manifest["unacquired"] = [
        item
        for item in manifest.get("unacquired", [])
        if item.get("source_file") != source_file
    ]
    manifest["generated_at"] = utc_now()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"admitted recovered original for radical {kangxi_number}: {source_file}")


def download_assets(start: int, count: int) -> None:
    metadata_payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    candidates = source_file_map()
    pages = sorted(metadata_payload["pages"], key=lambda page: page.get("title", ""))
    admitted: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for page in pages:
        source_file = page.get("title", "").removeprefix("File:")
        imageinfos = page.get("imageinfo", [])
        if page.get("missing") or not imageinfos or source_file not in candidates:
            rejected.append({"source_file": source_file, "reason": "missing_or_metadata_incomplete"})
            continue
        imageinfo = imageinfos[0]
        extmetadata = imageinfo.get("extmetadata", {})
        license_id = normalized_license(imageinfo)
        usage_terms = metadata_value(extmetadata, "UsageTerms")
        if not license_allowed(license_id, usage_terms):
            rejected.append(
                {
                    "source_file": source_file,
                    "reason": "license_not_allowlisted",
                    "license_id": license_id,
                    "usage_terms": usage_terms,
                }
            )
            continue
        admitted.append((page, imageinfo, candidates[source_file]))

    if MANIFEST_PATH.is_file():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    else:
        manifest = {"schema_version": "1.0.0", "generated_at": utc_now(), "assets": [], "rejected": []}
    existing = {asset["asset_id"]: asset for asset in manifest["assets"]}

    selected = admitted[start : start + count]
    for index, (page, imageinfo, candidate) in enumerate(selected):
        source_file = page["title"].removeprefix("File:")
        extmetadata = imageinfo["extmetadata"]
        payload = request_bytes(imageinfo["url"])
        if hashlib.sha1(payload).hexdigest() != imageinfo["sha1"]:
            raise RuntimeError(f"Commons SHA-1 mismatch for {source_file}")
        extension = extension_for(source_file, imageinfo["mime"])
        asset_id = f"shuowen-seal-U+{ord(candidate['primary']):04X}"
        directory = ASSET_ROOT / f"U+{ord(candidate['primary']):04X}"
        directory.mkdir(parents=True, exist_ok=True)
        local_path = directory / f"{asset_id}{extension}"
        local_path.write_bytes(payload)
        expected_mime = imageinfo["mime"]
        asset = {
            "asset_id": asset_id,
            "source_id": SOURCE_ID,
            "source_file": source_file,
            "source_file_page": imageinfo["descriptionurl"],
            "original_url": imageinfo["url"],
            "local_path": str(local_path.relative_to(ROOT)),
            "retrieved_at": utc_now(),
            "sha256": sha256_bytes(payload),
            "bytes": len(payload),
            "mime_type": expected_mime,
            "media_type": imageinfo.get("mediatype"),
            "width": imageinfo["width"],
            "height": imageinfo["height"],
            "commons_sha1": imageinfo["sha1"],
            "commons_timestamp": imageinfo["timestamp"],
            "license_id": normalized_license(imageinfo),
            "license_url": metadata_value(extmetadata, "LicenseUrl") or None,
            "usage_terms": metadata_value(extmetadata, "UsageTerms") or None,
            "artist": metadata_value(extmetadata, "Artist") or None,
            "credit": metadata_value(extmetadata, "Credit") or None,
            "attribution_required": metadata_value(extmetadata, "AttributionRequired") or None,
            "kangxi_number": candidate["kangxi_number"],
            "source_page": candidate["source_page"],
            "source_revision_id": candidate["revision_id"],
            "transformations": [],
        }
        existing[asset_id] = asset
        if index + 1 < len(selected):
            time.sleep(2.1)

    manifest["generated_at"] = utc_now()
    manifest["metadata_acquisition"] = {
        "local_path": str(METADATA_PATH.relative_to(ROOT)),
        "sha256": hashlib.sha256(METADATA_PATH.read_bytes()).hexdigest(),
        "retrieved_at": metadata_payload["retrieved_at"],
    }
    manifest["assets"] = sorted(existing.values(), key=lambda asset: asset["kangxi_number"])
    manifest["rejected"] = rejected
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"admitted {len(admitted)}, rejected {len(rejected)}, "
        f"downloaded batch {start}:{start + len(selected)}, manifest assets {len(existing)}"
    )


def finalize_access_failure() -> None:
    metadata_payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    candidates = source_file_map()
    if not MANIFEST_PATH.is_file():
        raise RuntimeError("no asset manifest exists to finalize")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    acquired_files = {asset["source_file"] for asset in manifest.get("assets", [])}
    unacquired = [
        {
            "source_file": source_file,
            "kangxi_number": candidate["kangxi_number"],
            "reason": "source_access_failed",
            "detail": "Wikimedia upload host returned HTTP 429 after bounded, rate-limited retries and directed bulk clients to thumbnails; project policy requires the original file, so no thumbnail substitute was acquired.",
        }
        for source_file, candidate in sorted(candidates.items())
        if source_file not in acquired_files
    ]
    manifest["generated_at"] = utc_now()
    manifest["metadata_acquisition"] = {
        "local_path": str(METADATA_PATH.relative_to(ROOT)),
        "sha256": hashlib.sha256(METADATA_PATH.read_bytes()).hexdigest(),
        "retrieved_at": metadata_payload["retrieved_at"],
    }
    manifest["rejected"] = []
    manifest["unacquired"] = unacquired
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"retained {len(acquired_files)} acquired asset; marked {len(unacquired)} source-access failures")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("metadata")
    subparsers.add_parser("finalize-access-failure")
    recover = subparsers.add_parser("admit-existing")
    recover.add_argument("--kangxi", type=int, required=True)
    download = subparsers.add_parser("download")
    download.add_argument("--start", type=int, default=0)
    download.add_argument("--count", type=int, default=40)
    args = parser.parse_args()
    if args.command == "metadata":
        acquire_metadata()
    elif args.command == "finalize-access-failure":
        finalize_access_failure()
    elif args.command == "admit-existing":
        admit_existing(args.kangxi)
    else:
        download_assets(args.start, args.count)


if __name__ == "__main__":
    main()
