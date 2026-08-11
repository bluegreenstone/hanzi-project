#!/usr/bin/env python3
"""Acquire exact Commons historical SVG originals from latest Wayback captures."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from acquire_historical_assets import local_target


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = ROOT / "source-data" / "wikimedia-2026-08-10"
CANDIDATES = ROOT / "phase2-historical-asset-candidates.json"
METADATA = SOURCE_DATA / "commons-acc-historical-file-metadata.json"
COMMON_LOG = SOURCE_DATA / "commons-acc-historical-original-acquisition-log.json"
WAYBACK_LOG = SOURCE_DATA / "commons-acc-historical-wayback-acquisition-log.json"
WAYBACK_SOURCE_ID = "internet-archive-wayback-commons-mirror-2026-08-10"
USER_AGENT = "hanzi-project/1.0 (exact-hash Wayback historical glyph recovery)"
CAPTURE_RE = re.compile(r"/web/(\d{14})id_/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_logs(
    entries: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    wayback_entries: list[dict[str, Any]],
) -> None:
    common = {
        "updated_at": utc_now(),
        "source_id": "commons-ancient-chinese-historical-form-files-2026-08-10",
        "request_policy": (
            "Direct Commons originals or sequential Wayback replay requests; all "
            "admitted bytes must match the pinned Commons SHA-1 exactly."
        ),
        "completed_count": len(entries),
        "failure_count": len(failures),
        "entries": entries,
        "failures": failures,
    }
    COMMON_LOG.write_text(
        json.dumps(common, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    wayback = {
        "updated_at": utc_now(),
        "source_id": WAYBACK_SOURCE_ID,
        "request_policy": (
            "Latest-capture timegate lookup followed by capture replay, with at least "
            "1.1 seconds between every request to web.archive.org."
        ),
        "integrity_policy": "Byte-for-byte SHA-1 match to pinned Commons imageinfo.",
        "completed_count": len(wayback_entries),
        "failure_count": len(failures),
        "entries": wayback_entries,
        "failures": failures,
    }
    WAYBACK_LOG.write_text(
        json.dumps(wayback, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
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
    args = parser.parse_args()
    selected_numbers = (
        {int(value) for value in args.numbers.split(",") if value.strip()}
        if args.numbers
        else None
    )
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    decisions = sorted(
        (
            decision
            for decision in candidates["decisions"]
            if decision["decision"] == "admitted"
            and (args.kind is None or decision["kind"] == args.kind)
            and (
                selected_numbers is None
                or decision["kangxi_number"] in selected_numbers
            )
        ),
        key=lambda item: (item["kangxi_number"], item["kind"]),
    )
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    pages = {
        page["title"].removeprefix("File:"): page for page in metadata["pages"]
    }
    common = json.loads(COMMON_LOG.read_text(encoding="utf-8")) if COMMON_LOG.exists() else {}
    entry_by_file = {entry["source_file"]: entry for entry in common.get("entries", [])}
    failures_by_file = {
        failure["source_file"]: failure for failure in common.get("failures", [])
    }
    wayback = json.loads(WAYBACK_LOG.read_text(encoding="utf-8")) if WAYBACK_LOG.exists() else {}
    wayback_by_file = {
        entry["source_file"]: entry for entry in wayback.get("entries", [])
    }
    no_redirect = urllib.request.build_opener(NoRedirect)
    normal = urllib.request.build_opener()
    last_request_started: float | None = None

    def rate_limited_open(opener, request):  # type: ignore[no-untyped-def]
        nonlocal last_request_started
        if last_request_started is not None:
            delay = 1.1 - (time.monotonic() - last_request_started)
            if delay > 0:
                time.sleep(delay)
        last_request_started = time.monotonic()
        return opener.open(request, timeout=90)

    attempted = 0
    for index_number, decision in enumerate(decisions, start=1):
        source_file = decision["source_file"]
        asset_id, target = local_target(decision)
        imageinfo = pages[source_file]["imageinfo"][0]
        if target.exists():
            payload = target.read_bytes()
            logged = entry_by_file.get(source_file)
            expected_existing_sha1 = (
                logged.get("commons_sha1") if logged else imageinfo["sha1"]
            )
            if hashlib.sha1(payload).hexdigest() != expected_existing_sha1:
                raise RuntimeError(f"existing target has wrong SHA-1: {target}")
            if logged is None:
                raise RuntimeError(f"existing target has no acquisition log: {target}")
            continue
        if args.limit is not None and attempted >= args.limit:
            break
        original_url = urllib.parse.urlsplit(imageinfo["url"])._replace(query="").geturl()
        timegate_url = f"https://web.archive.org/web/2id_/{original_url}"
        timegate_request = urllib.request.Request(
            timegate_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
        )
        attempted += 1
        stop_transport = False
        try:
            try:
                with rate_limited_open(no_redirect, timegate_request) as response:
                    status = response.status
                    capture_url = response.headers.get("Location")
            except HTTPError as exc:
                status = exc.code
                capture_url = exc.headers.get("Location")
            if status not in (301, 302, 303, 307, 308) or not capture_url:
                raise RuntimeError(f"Wayback timegate returned {status} without capture")
            capture_request = urllib.request.Request(
                capture_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "image/svg+xml",
                    "Accept-Encoding": "identity",
                },
            )
            with rate_limited_open(normal, capture_request) as response:
                replay_url = response.geturl()
                content_type = response.headers.get_content_type()
                content_encoding = response.headers.get("Content-Encoding", "")
                payload = response.read()
            if content_encoding.casefold() == "gzip" or payload.startswith(b"\x1f\x8b"):
                payload = gzip.decompress(payload)
            if content_type != "image/svg+xml":
                raise RuntimeError(f"capture content type is {content_type!r}")
            actual_sha1 = hashlib.sha1(payload).hexdigest()
            if actual_sha1 != imageinfo["sha1"]:
                raise RuntimeError(
                    f"capture SHA-1 {actual_sha1} != Commons {imageinfo['sha1']}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            capture_match = CAPTURE_RE.search(capture_url)
            capture_timestamp = capture_match.group(1) if capture_match else None
            route = {
                "source_id": WAYBACK_SOURCE_ID,
                "timegate_url": timegate_url,
                "url": capture_url,
                "replay_url": replay_url,
                "capture_timestamp": capture_timestamp,
                "integrity_requirement": "Byte-for-byte match to Commons imageinfo SHA-1",
            }
            entry = {
                "asset_id": asset_id,
                "source_file": source_file,
                "kangxi_number": decision["kangxi_number"],
                "kind": decision["kind"],
                "local_path": str(target.relative_to(ROOT)),
                "retrieved_at": utc_now(),
                "acquisition_route": route,
                "request_url": imageinfo["url"],
                "resolved_url": capture_url,
                "commons_sha1": imageinfo["sha1"],
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
            }
            entry_by_file[source_file] = entry
            wayback_by_file[source_file] = entry
            failures_by_file.pop(source_file, None)
        except Exception as exc:
            stop_transport = (
                isinstance(exc, URLError) and not isinstance(exc, HTTPError)
            ) or (
                isinstance(exc, HTTPError) and exc.code == 429
            ) or "Connection refused" in str(exc) or "returned 429" in str(exc)
            failures_by_file[source_file] = {
                "source_file": source_file,
                "kangxi_number": decision["kangxi_number"],
                "kind": decision["kind"],
                "url": imageinfo["url"],
                "error_type": type(exc).__name__,
                "detail": str(exc),
                "route_attempted": "wayback_latest_capture",
            }
            print(f"FAILED {source_file}: {exc}", flush=True)
        entries = sorted(
            entry_by_file.values(), key=lambda item: (item["kangxi_number"], item["kind"])
        )
        failures = sorted(
            failures_by_file.values(), key=lambda item: (item["kangxi_number"], item["kind"])
        )
        wayback_entries = sorted(
            wayback_by_file.values(), key=lambda item: (item["kangxi_number"], item["kind"])
        )
        write_logs(entries, failures, wayback_entries)
        if stop_transport:
            print("stopping after Wayback transport refusal or rate limit", flush=True)
            break
        if attempted % 10 == 0:
            print(
                f"Wayback attempts {attempted}; total originals {len(entries)}/511; "
                f"failures {len(failures)}",
                flush=True,
            )
    print(
        f"Wayback pass ended: total originals {len(entry_by_file)}/511; "
        f"failures {len(failures_by_file)}"
    )


if __name__ == "__main__":
    main()
