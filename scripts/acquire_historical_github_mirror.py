#!/usr/bin/env python3
"""Recover Commons historical SVG originals from a pinned GitHub mirror.

The repository is transport only.  A member is written to the asset library only
when its content SHA-1 equals the already-pinned current Commons imageinfo SHA-1.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acquire_historical_assets import local_target


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = ROOT / "source-data" / "wikimedia-2026-08-10"
MIRROR_DATA = ROOT / "source-data" / "github-analects-data-2026-08-10"
CANDIDATES = ROOT / "phase2-historical-asset-candidates.json"
METADATA = SOURCE_DATA / "commons-acc-historical-file-metadata.json"
REVISION_METADATA = SOURCE_DATA / "commons-acc-historical-file-revisions.json"
COMMON_LOG = SOURCE_DATA / "commons-acc-historical-original-acquisition-log.json"
MIRROR_LOG = MIRROR_DATA / "mirror-acquisition-log.json"
TREE_SNAPSHOT = MIRROR_DATA / "tree.json"
SOURCE_ID = "github-analects-data-commons-mirror-2026-08-10"
CONTENT_SOURCE_ID = "commons-ancient-chinese-historical-form-files-2026-08-10"
OWNER = "plexus"
REPOSITORY = "analects-data"
COMMIT = "c1efa0bbd30d3a74acad756efe401977edc501ce"
TREE_URL = (
    f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/git/trees/"
    f"{COMMIT}?recursive=1"
)
ARCHIVE_URL = f"https://codeload.github.com/{OWNER}/{REPOSITORY}/tar.gz/{COMMIT}"
USER_AGENT = "hanzi-project/1.0 (exact-hash historical glyph mirror audit)"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch(url: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def write_common_log(
    entries: list[dict[str, Any]], failures: list[dict[str, Any]]
) -> None:
    payload = {
        "updated_at": utc_now(),
        "source_id": CONTENT_SOURCE_ID,
        "request_policy": (
            "Direct Commons originals or registered transport mirrors; every "
            "admitted SVG must match the pinned Commons SHA-1 exactly."
        ),
        "completed_count": len(entries),
        "failure_count": len(failures),
        "entries": entries,
        "failures": failures,
    }
    COMMON_LOG.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    decisions = sorted(
        (
            decision
            for decision in candidates["decisions"]
            if decision["decision"] == "admitted"
        ),
        key=lambda item: (item["kangxi_number"], item["kind"]),
    )
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    pages = {
        page["title"].removeprefix("File:"): page for page in metadata["pages"]
    }
    revision_metadata = (
        json.loads(REVISION_METADATA.read_text(encoding="utf-8"))
        if REVISION_METADATA.exists()
        else {"matches": []}
    )
    historical_revision_by_file = {
        item["source_file"]: item for item in revision_metadata["matches"]
    }
    common = json.loads(COMMON_LOG.read_text(encoding="utf-8")) if COMMON_LOG.exists() else {}
    entry_by_file = {entry["source_file"]: entry for entry in common.get("entries", [])}
    failure_by_file = {
        failure["source_file"]: failure for failure in common.get("failures", [])
    }

    tree_raw = fetch(TREE_URL, "application/vnd.github+json")
    tree = json.loads(tree_raw)
    if tree.get("truncated"):
        raise RuntimeError("pinned GitHub tree response is truncated")
    MIRROR_DATA.mkdir(parents=True, exist_ok=True)
    TREE_SNAPSHOT.write_bytes(tree_raw)
    time.sleep(1.1)
    archive = fetch(ARCHIVE_URL, "application/gzip")

    member_by_file: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as stream:
        for member in stream.getmembers():
            marker = "/commons_ancient_characters/"
            if not member.isfile() or marker not in member.name:
                continue
            source_file = member.name.split(marker, 1)[1]
            if "/" in source_file:
                continue
            extracted = stream.extractfile(member)
            if extracted is not None:
                member_by_file[source_file] = extracted.read()

    matched: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    preserved_newer: list[dict[str, Any]] = []
    already_present = 0
    recovered = 0
    for decision in decisions:
        source_file = decision["source_file"]
        imageinfo = pages[source_file]["imageinfo"][0]
        expected_sha1 = imageinfo["sha1"]
        payload = member_by_file.get(source_file)
        if payload is None:
            missing.append(
                {
                    "source_file": source_file,
                    "kangxi_number": decision["kangxi_number"],
                    "kind": decision["kind"],
                }
            )
            continue
        actual_sha1 = hashlib.sha1(payload).hexdigest()
        revision_kind = "current"
        selected_info = imageinfo
        if actual_sha1 != expected_sha1:
            historical = historical_revision_by_file.get(source_file)
            historical_info = historical.get("matched_revision") if historical else None
            if historical_info and historical_info["sha1"] == actual_sha1:
                revision_kind = "historical"
                selected_info = historical_info
            else:
                mismatches.append(
                    {
                        "source_file": source_file,
                        "kangxi_number": decision["kangxi_number"],
                        "kind": decision["kind"],
                        "mirror_sha1": actual_sha1,
                        "commons_sha1": expected_sha1,
                        "bytes": len(payload),
                        "reason": "mirror SHA-1 is absent from the pinned Commons file history",
                    }
                )
                continue
        selected_sha1 = selected_info["sha1"]
        asset_id, target = local_target(decision)
        if target.exists():
            existing = target.read_bytes()
            existing_sha1 = hashlib.sha1(existing).hexdigest()
            if existing_sha1 != selected_sha1:
                prior = entry_by_file.get(source_file)
                prior_sha1 = prior.get("commons_sha1") if prior else None
                if revision_kind == "historical" and existing_sha1 == expected_sha1:
                    preserved_newer.append(
                        {
                            "source_file": source_file,
                            "kangxi_number": decision["kangxi_number"],
                            "kind": decision["kind"],
                            "mirror_historical_sha1": selected_sha1,
                            "preserved_current_sha1": existing_sha1,
                            "reason": "a verified current Commons original was already acquired",
                        }
                    )
                    failure_by_file.pop(source_file, None)
                    continue
                if prior_sha1 == existing_sha1:
                    raise RuntimeError(
                        f"existing target revision conflicts with selected mirror revision: {target}"
                    )
                raise RuntimeError(f"existing target has wrong Commons SHA-1: {target}")
            already_present += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            recovered += 1
        raw_url = (
            f"https://raw.githubusercontent.com/{OWNER}/{REPOSITORY}/{COMMIT}/"
            f"commons_ancient_characters/{urllib.parse.quote(source_file)}"
        )
        route = {
            "source_id": SOURCE_ID,
            "repository": f"{OWNER}/{REPOSITORY}",
            "commit": COMMIT,
            "path": f"commons_ancient_characters/{source_file}",
            "url": raw_url,
            "archive_url": ARCHIVE_URL,
            "integrity_requirement": "Byte-for-byte match to Commons imageinfo SHA-1",
            "commons_revision": revision_kind,
            "commons_revision_timestamp": selected_info["timestamp"],
        }
        prior = entry_by_file.get(source_file)
        prior_route = prior.get("acquisition_route") if prior else None
        prior_route_source = (
            prior_route.get("source_id") if isinstance(prior_route, dict) else None
        )
        if prior is None or prior_route_source == SOURCE_ID:
            entry_by_file[source_file] = {
                "asset_id": asset_id,
                "source_file": source_file,
                "kangxi_number": decision["kangxi_number"],
                "kind": decision["kind"],
                "local_path": str(target.relative_to(ROOT)),
                "retrieved_at": prior.get("retrieved_at") if prior else utc_now(),
                "acquisition_route": route,
                "request_url": selected_info["url"],
                "resolved_url": raw_url,
                "commons_sha1": selected_sha1,
                "commons_timestamp": selected_info["timestamp"],
                "commons_original_url": selected_info["url"],
                "commons_revision": revision_kind,
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
            }
        failure_by_file.pop(source_file, None)
        matched.append(
            {
                "source_file": source_file,
                "kangxi_number": decision["kangxi_number"],
                "kind": decision["kind"],
                "commons_sha1": selected_sha1,
                "commons_timestamp": selected_info["timestamp"],
                "commons_original_url": selected_info["url"],
                "commons_revision": revision_kind,
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
                "local_path": str(target.relative_to(ROOT)),
                "acquisition_route": route,
            }
        )

    entries = sorted(
        entry_by_file.values(), key=lambda item: (item["kangxi_number"], item["kind"])
    )
    failures = sorted(
        failure_by_file.values(), key=lambda item: (item["kangxi_number"], item["kind"])
    )
    write_common_log(entries, failures)
    log = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "repository": f"{OWNER}/{REPOSITORY}",
        "commit": COMMIT,
        "tree_url": TREE_URL,
        "tree_path": str(TREE_SNAPSHOT.relative_to(ROOT)),
        "tree_sha256": sha256_bytes(tree_raw),
        "archive_url": ARCHIVE_URL,
        "archive_sha256": sha256_bytes(archive),
        "archive_bytes": len(archive),
        "archive_retained": False,
        "archive_retention_note": (
            "Processed in memory so unmapped repository media with unverified per-file "
            "licenses were not written to disk."
        ),
        "candidate_count": len(decisions),
        "mirror_svg_count": len(member_by_file),
        "matched_count": len(matched),
        "recovered_count": recovered,
        "already_present_count": already_present,
        "mismatch_count": len(mismatches),
        "missing_count": len(missing),
        "preserved_newer_count": len(preserved_newer),
        "integrity_policy": (
            "Exact match to either the pinned current Commons content SHA-1 or a "
            "unique SHA-1 in the pinned Commons file revision history."
        ),
        "matched": matched,
        "mismatches": mismatches,
        "missing": missing,
        "preserved_newer": preserved_newer,
    }
    MIRROR_LOG.write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"mirror matched {len(matched)}/{len(decisions)}; recovered {recovered}; "
        f"revision mismatches {len(mismatches)}; missing {len(missing)}; "
        f"preserved newer {len(preserved_newer)}; "
        f"total exact originals {len(entries)}/{len(decisions)}"
    )


if __name__ == "__main__":
    # Imported lazily above only for URL encoding, keeping the file-level constants tidy.
    import urllib.parse

    main()
