#!/usr/bin/env python3
"""Acquire admitted Oracle, bronze, and Liushutong originals sequentially."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = ROOT / "source-data" / "wikimedia-2026-08-10"
CANDIDATES = ROOT / "metadata" / "audits" / "phase2-historical-asset-candidates.json"
METADATA = SOURCE_DATA / "commons-acc-historical-file-metadata.json"
LOG_PATH = SOURCE_DATA / "commons-acc-historical-original-acquisition-log.json"
MANIFEST = ROOT / "assets" / "manifest.json"
SOURCE_ID = "commons-ancient-chinese-historical-form-files-2026-08-10"
USER_AGENT = "hanzi-project/1.0 (sequential historical radical acquisition)"
KIND_SLUG = {
    "oracle_bone_甲骨文": "oracle",
    "bronze_金文": "bronze",
    "liushutong_六書通": "liushutong",
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def metadata_value(metadata: dict[str, Any], name: str) -> str:
    return str(metadata.get(name, {}).get("value", "")).strip()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request_bytes(
    url: str, *, rate_limit_retries: int, rate_limit_backoff: float
) -> tuple[bytes, str]:
    retries = 0
    while True:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read(), response.geturl()
        except HTTPError as exc:
            if exc.code != 429 or retries >= rate_limit_retries:
                raise
            retries += 1
            print(
                f"Commons rate limit; retry {retries}/{rate_limit_retries} "
                f"after {rate_limit_backoff:.1f}s",
                flush=True,
            )
            time.sleep(rate_limit_backoff)


def local_target(decision: dict[str, Any]) -> tuple[str, Path]:
    slug = KIND_SLUG[decision["kind"]]
    codepoint = f"U+{ord(decision['primary']):04X}"
    asset_id = f"{slug}-{codepoint}-commons-index"
    return asset_id, ROOT / "assets" / slug / codepoint / f"{asset_id}.svg"


def build_asset(
    decision: dict[str, Any],
    page: dict[str, Any],
    payload: bytes,
    retrieved_at: str,
    acquisition_route: str | dict[str, Any],
) -> dict[str, Any]:
    imageinfo = page["imageinfo"][0]
    extmetadata = imageinfo.get("extmetadata", {})
    asset_id, target = local_target(decision)
    return {
        "asset_id": asset_id,
        "source_id": SOURCE_ID,
        "source_index_id": decision["source_id"],
        "source_file": decision["source_file"],
        "source_file_page": imageinfo["descriptionurl"],
        "original_url": imageinfo["url"],
        "local_path": str(target.relative_to(ROOT)),
        "retrieved_at": retrieved_at,
        "sha256": sha256_bytes(payload),
        "bytes": len(payload),
        "mime_type": imageinfo["mime"],
        "media_type": imageinfo.get("mediatype"),
        "width": imageinfo["width"],
        "height": imageinfo["height"],
        "commons_sha1": imageinfo["sha1"],
        "commons_timestamp": imageinfo["timestamp"],
        "license_id": metadata_value(extmetadata, "License"),
        "license_short_name": metadata_value(extmetadata, "LicenseShortName"),
        "license_url": metadata_value(extmetadata, "LicenseUrl") or None,
        "usage_terms": metadata_value(extmetadata, "UsageTerms") or None,
        "artist": metadata_value(extmetadata, "Artist") or None,
        "credit": metadata_value(extmetadata, "Credit") or None,
        "attribution_required": metadata_value(extmetadata, "AttributionRequired") or None,
        "image_description": metadata_value(extmetadata, "ImageDescription") or None,
        "categories": sorted(category["title"] for category in page.get("categories", [])),
        "kangxi_number": decision["kangxi_number"],
        "primary": decision["primary"],
        "historical_form": decision["kind"],
        "mapping_method": decision["mapping_method"],
        "source_page": decision["source_page"],
        "source_revision_id": decision["source_revision_id"],
        "acquisition_route": acquisition_route,
        "transformations": [],
        "representation_note": (
            "Unchanged Commons original SVG: a modern vector transcription of the "
            "historical glyph identified in the file metadata, not a cropped rubbing."
        ),
    }


def write_log(entries: list[dict[str, Any]], failures: list[dict[str, Any]]) -> None:
    payload = {
        "updated_at": utc_now(),
        "source_id": SOURCE_ID,
        "request_policy": (
            "Sequential original-file requests with at least 1.1 seconds between "
            "requests to the Wikimedia upload host."
        ),
        "completed_count": len(entries),
        "failure_count": len(failures),
        "entries": entries,
        "failures": failures,
    }
    LOG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--kind",
        choices=("oracle_bone_甲骨文", "bronze_金文", "liushutong_六書通"),
        default=None,
    )
    parser.add_argument(
        "--numbers",
        help="Optional comma-separated Kangxi radical numbers to attempt.",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=1.1,
        help="Seconds between original-file requests; values below 1.1 are rejected.",
    )
    parser.add_argument("--rate-limit-retries", type=int, default=0)
    parser.add_argument("--rate-limit-backoff", type=float, default=15.0)
    args = parser.parse_args()
    if args.request_delay < 1.1:
        parser.error("--request-delay must be at least 1.1 seconds")
    if args.rate_limit_retries < 0:
        parser.error("--rate-limit-retries cannot be negative")
    selected_numbers = (
        {int(value) for value in args.numbers.split(",") if value.strip()}
        if args.numbers
        else None
    )
    candidate_payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    decisions = sorted(
        (
            decision
            for decision in candidate_payload["decisions"]
            if decision["decision"] == "admitted"
            and (args.kind is None or decision["kind"] == args.kind)
            and (
                selected_numbers is None
                or decision["kangxi_number"] in selected_numbers
            )
        ),
        key=lambda item: (item["kangxi_number"], item["kind"]),
    )
    metadata_payload = json.loads(METADATA.read_text(encoding="utf-8"))
    pages = {
        page["title"].removeprefix("File:"): page for page in metadata_payload["pages"]
    }
    prior_log = json.loads(LOG_PATH.read_text(encoding="utf-8")) if LOG_PATH.exists() else {}
    log_by_file = {entry["source_file"]: entry for entry in prior_log.get("entries", [])}
    failures_by_file = {
        failure["source_file"]: failure for failure in prior_log.get("failures", [])
    }
    assets: list[dict[str, Any]] = []
    attempted_downloads = 0
    for index, decision in enumerate(decisions, start=1):
        page = pages[decision["source_file"]]
        imageinfo = page["imageinfo"][0]
        asset_id, target = local_target(decision)
        retrieved_at: str
        route: str
        if target.exists():
            payload = target.read_bytes()
            previous = log_by_file.get(decision["source_file"], {})
            expected_existing_sha1 = previous.get("commons_sha1", imageinfo["sha1"])
            if hashlib.sha1(payload).hexdigest() != expected_existing_sha1:
                raise RuntimeError(f"existing target has wrong Commons SHA-1: {target}")
            retrieved_at = previous.get("retrieved_at") or (
                datetime.fromtimestamp(target.stat().st_mtime, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            route = previous.get("acquisition_route", "existing_exact_original")
        else:
            if args.limit is not None and attempted_downloads >= args.limit:
                break
            attempted_downloads += 1
            try:
                payload, resolved_url = request_bytes(
                    imageinfo["url"],
                    rate_limit_retries=args.rate_limit_retries,
                    rate_limit_backoff=max(args.rate_limit_backoff, 1.1),
                )
                if hashlib.sha1(payload).hexdigest() != imageinfo["sha1"]:
                    raise RuntimeError(
                        f"downloaded bytes fail Commons SHA-1 for {decision['source_file']}"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                retrieved_at = utc_now()
                route = "direct_commons_original"
            except Exception as exc:  # Preserve the exact per-file transport failure.
                failures_by_file[decision["source_file"]] = {
                    "source_file": decision["source_file"],
                    "kangxi_number": decision["kangxi_number"],
                    "kind": decision["kind"],
                    "url": imageinfo["url"],
                    "error_type": type(exc).__name__,
                    "detail": str(exc),
                    "route_attempted": "direct_commons_original",
                }
                entries = sorted(
                    log_by_file.values(),
                    key=lambda item: (item["kangxi_number"], item["kind"]),
                )
                failures = sorted(
                    failures_by_file.values(),
                    key=lambda item: (item["kangxi_number"], item["kind"]),
                )
                write_log(entries, failures)
                print(
                    f"FAILED {index}/{len(decisions)} {decision['source_file']}: {exc}",
                    flush=True,
                )
                if isinstance(exc, HTTPError) and exc.code == 429:
                    print("stopping after Commons rate limit", flush=True)
                    break
                if isinstance(exc, URLError) and "Connection refused" in str(exc):
                    print("stopping after Commons transport refusal", flush=True)
                    break
                time.sleep(args.request_delay)
                continue
            log_by_file[decision["source_file"]] = {
                "asset_id": asset_id,
                "source_file": decision["source_file"],
                "kangxi_number": decision["kangxi_number"],
                "kind": decision["kind"],
                "local_path": str(target.relative_to(ROOT)),
                "retrieved_at": retrieved_at,
                "acquisition_route": route,
                "request_url": imageinfo["url"],
                "resolved_url": resolved_url,
                "commons_sha1": imageinfo["sha1"],
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
            }
            failures_by_file.pop(decision["source_file"], None)
            time.sleep(args.request_delay)
        asset = build_asset(decision, page, payload, retrieved_at, route)
        assets.append(asset)
        entries = sorted(
            log_by_file.values(),
            key=lambda item: (item["kangxi_number"], item["kind"]),
        )
        failures = sorted(
            failures_by_file.values(),
            key=lambda item: (item["kangxi_number"], item["kind"]),
        )
        write_log(entries, failures)
        if index % 20 == 0 or index == len(decisions):
            print(f"originals {index}/{len(decisions)}", flush=True)
    entries = sorted(
        log_by_file.values(), key=lambda item: (item["kangxi_number"], item["kind"])
    )
    failures = sorted(
        failures_by_file.values(), key=lambda item: (item["kangxi_number"], item["kind"])
    )
    complete = (
        args.kind is None
        and selected_numbers is None
        and len(assets) == len(decisions)
        and not failures
    )
    if not complete:
        print(
            f"partial acquisition: {len(assets)}/{len(decisions)} exact originals, "
            f"{len(failures)} failures"
        )
        return
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["assets"] = [
        asset for asset in manifest["assets"] if asset.get("source_id") != SOURCE_ID
    ] + assets
    manifest["assets"] = sorted(
        manifest["assets"],
        key=lambda asset: (
            asset.get("kangxi_number", 999),
            asset.get("historical_form", "shuowen_seal_說文解字"),
            asset["asset_id"],
        ),
    )
    manifest["historical_asset_candidates"] = {
        "local_path": str(CANDIDATES.relative_to(ROOT)),
        "sha256": sha256_path(CANDIDATES),
        "admitted_count": len(decisions),
    }
    manifest["historical_file_metadata"] = {
        "local_path": str(METADATA.relative_to(ROOT)),
        "sha256": sha256_path(METADATA),
        "retrieved_at": metadata_payload["retrieved_at"],
    }
    manifest["historical_original_acquisition_log"] = {
        "local_path": str(LOG_PATH.relative_to(ROOT)),
        "sha256": sha256_path(LOG_PATH),
        "completed_count": len(entries),
    }
    manifest["historical_source_gaps"] = [
        {
            "kangxi_number": decision["kangxi_number"],
            "primary": decision["primary"],
            "historical_form": decision["kind"],
            "reason": decision["reason"],
            "historical_status": decision["historical_status"],
            "source_page": decision["source_page"],
            "source_revision_id": decision["source_revision_id"],
        }
        for decision in candidate_payload["decisions"]
        if decision["decision"] == "not_acquired"
    ]
    manifest["generated_at"] = utc_now()
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"manifest now records {len(assets)} historical originals")


if __name__ == "__main__":
    main()
