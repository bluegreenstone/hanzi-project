#!/usr/bin/env python3
"""Acquire all exact-radical glyph images from CODH 偏類六書通 TE00008–21."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "source-data" / "codh-liushutong-series-2026-08-11"
INDEX = SOURCE_ROOT / "radical-candidates-series.json"
PAGES = SOURCE_ROOT / "pages"
LOG = SOURCE_ROOT / "original-acquisition-log.json"
REGISTRY = ROOT / "sources.json"
ASSET_MANIFEST = ROOT / "assets" / "manifest.json"
SOURCE_ID = "codh-henrui-liushutong-te00008-21-series-2026-08-11"
USER_AGENT = "hanzi-project/1.0 (licensed Liushutong series glyph acquisition)"
IMAGE_RE = re.compile(
    r'<a href="([^"]+)" title="([^"]+)"><img src="([^"]+)"></a>',
    re.DOTALL,
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def jpeg_dimensions(payload: bytes) -> tuple[int, int]:
    if not payload.startswith(b"\xff\xd8"):
        raise RuntimeError("source image is not a JPEG")
    offset = 2
    while offset + 9 < len(payload):
        if payload[offset] != 0xFF:
            offset += 1
            continue
        marker = payload[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(payload):
            break
        length = int.from_bytes(payload[offset : offset + 2], "big")
        if length < 2 or offset + length > len(payload):
            break
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(payload[offset + 3 : offset + 5], "big")
            width = int.from_bytes(payload[offset + 5 : offset + 7], "big")
            return width, height
        offset += length
    raise RuntimeError("JPEG dimensions were not found")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum new image downloads after all required character pages are pinned.",
    )
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    source = registry["sources"].get(SOURCE_ID)
    if (
        not source
        or source.get("status") != "approved"
        or source.get("license", {}).get("id") != "CC-BY-SA-4.0"
        or not source.get("license", {}).get("verified")
        or not source.get("acquisition", {}).get("candidate_sha256")
    ):
        raise RuntimeError(
            "CODH Liushutong series license and pinned indexes must be approved "
            "before image acquisition"
        )
    if sha256_bytes(INDEX.read_bytes()) != source["acquisition"]["candidate_sha256"]:
        raise RuntimeError("CODH Liushutong series index fails the registry SHA-256")

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    if LOG.exists():
        prior = json.loads(LOG.read_text(encoding="utf-8"))
    else:
        manifest = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
        prior = {
            "entries": [
                entry
                for key in ("assets", "provenance_alias_assets")
                for entry in manifest.get(key, [])
                if entry.get("source_id") == SOURCE_ID and entry.get("original_url")
            ]
        }
        if len(prior["entries"]) != 3338:
            raise RuntimeError(
                "missing series log and manifest does not preserve all 3,338 entries"
            )
    entry_by_url = {entry["original_url"]: entry for entry in prior.get("entries", [])}
    failures_by_url = {
        failure["original_url"]: failure for failure in prior.get("failures", [])
    }
    last_request_started: float | None = None

    def fetch(url: str, accept: str) -> tuple[bytes, str]:
        nonlocal last_request_started
        if last_request_started is not None:
            delay = 1.1 - (time.monotonic() - last_request_started)
            if delay > 0:
                time.sleep(delay)
        last_request_started = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": accept},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read(), response.headers.get_content_type()

    unique_pages = {
        candidate["codepoint"]: candidate["source_character_page"]
        for candidate in index["radical_candidates"]
    }
    page_raw_by_codepoint: dict[str, bytes] = {}
    page_snapshots: list[dict[str, Any]] = []
    for position, (codepoint, url) in enumerate(sorted(unique_pages.items()), start=1):
        page_path = PAGES / f"{codepoint}.html"
        if page_path.exists():
            raw = page_path.read_bytes()
        else:
            raw, content_type = fetch(url, "text/html")
            if content_type != "text/html":
                raise RuntimeError(
                    f"unexpected page content type for {codepoint}: {content_type}"
                )
            page_path.parent.mkdir(parents=True, exist_ok=True)
            page_path.write_bytes(raw)
        page_raw_by_codepoint[codepoint] = raw
        page_snapshots.append(
            {
                "codepoint": codepoint,
                "path": str(page_path.relative_to(ROOT)),
                "sha256": sha256_bytes(raw),
                "bytes": len(raw),
                "url": url,
            }
        )
        if position % 20 == 0 or position == len(unique_pages):
            print(
                f"series character pages {position}/{len(unique_pages)}",
                flush=True,
            )

    image_candidates: list[dict[str, Any]] = []
    for radical in index["radical_candidates"]:
        volume_id = radical["volume_id"]
        section_re = re.compile(
            rf'<h2 id="{re.escape(volume_id)}">.*?</h2>(.*?)(?=<h2 id=|<h3>)',
            re.DOTALL,
        )
        text = page_raw_by_codepoint[radical["codepoint"]].decode("utf-8")
        section_match = section_re.search(text)
        if section_match is None:
            raise RuntimeError(
                f"{volume_id} section absent for radical {radical['kangxi_number']}"
            )
        section_candidates = []
        for variant_index, match in enumerate(
            IMAGE_RE.finditer(section_match.group(1)), start=1
        ):
            section_candidates.append(
                {
                    "volume_id": volume_id,
                    "kangxi_number": radical["kangxi_number"],
                    "primary": radical["primary"],
                    "codepoint": radical["codepoint"],
                    "variant_index": variant_index,
                    "source_character_page": radical["source_character_page"],
                    "viewer_url": urllib.parse.urljoin(
                        radical["source_character_page"], html.unescape(match.group(1))
                    ),
                    "source_title": html.unescape(match.group(2)),
                    "original_url": urllib.parse.urljoin(
                        radical["source_character_page"], html.unescape(match.group(3))
                    ),
                }
            )
        if len(section_candidates) != radical["source_glyph_count"]:
            raise RuntimeError(
                f"{volume_id} radical {radical['kangxi_number']}: parsed "
                f"{len(section_candidates)} images, index declares "
                f"{radical['source_glyph_count']}"
            )
        image_candidates.extend(section_candidates)

    image_candidates.sort(
        key=lambda item: (
            item["volume_id"],
            item["kangxi_number"],
            item["variant_index"],
        )
    )
    if len({item["original_url"] for item in image_candidates}) != len(
        image_candidates
    ):
        raise RuntimeError("series image candidates contain duplicate original URLs")

    def write_log() -> None:
        entries = sorted(
            entry_by_url.values(),
            key=lambda item: (
                item["volume_id"],
                item["kangxi_number"],
                item["variant_index"],
            ),
        )
        failures = sorted(
            failures_by_url.values(),
            key=lambda item: (
                item["volume_id"],
                item["kangxi_number"],
                item["variant_index"],
            ),
        )
        payload = {
            "updated_at": utc_now(),
            "source_id": SOURCE_ID,
            "license_id": "CC-BY-SA-4.0",
            "required_attribution": source["required_attribution"],
            "request_policy": (
                "Sequential same-host requests with at least 1.1 seconds between "
                "starts; source-published JPEG bytes are preserved unchanged."
            ),
            "selection_policy": (
                "Every glyph image from TE00008–TE00009 and TE00011–TE00021 "
                "for every exact Traditional-primary Kangxi radical codepoint in "
                "the pinned book indexes."
            ),
            "index_path": str(INDEX.relative_to(ROOT)),
            "index_sha256": sha256_bytes(INDEX.read_bytes()),
            "page_snapshots": page_snapshots,
            "expected_count": len(image_candidates),
            "completed_count": len(entries),
            "failure_count": len(failures),
            "entries": entries,
            "failures": failures,
        }
        LOG.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    downloads = 0
    for index_number, candidate in enumerate(image_candidates, start=1):
        original_url = candidate["original_url"]
        volume_id = candidate["volume_id"]
        codepoint = candidate["codepoint"]
        variant_index = candidate["variant_index"]
        asset_id = (
            f"codh-liushutong-{volume_id}-{codepoint}-{variant_index:03d}"
        )
        target = ROOT / "assets" / "liushutong" / codepoint / f"{asset_id}.jpg"
        prior_entry = entry_by_url.get(original_url)
        if target.exists():
            payload = target.read_bytes()
            if prior_entry and sha256_bytes(payload) != prior_entry["sha256"]:
                raise RuntimeError(f"existing CODH target fails logged SHA-256: {target}")
            retrieved_at = prior_entry.get("retrieved_at") if prior_entry else utc_now()
        else:
            if args.limit is not None and downloads >= args.limit:
                break
            try:
                payload, content_type = fetch(original_url, "image/jpeg")
                if content_type != "image/jpeg":
                    raise RuntimeError(f"unexpected image content type: {content_type}")
                jpeg_dimensions(payload)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                retrieved_at = utc_now()
                downloads += 1
            except Exception as exc:
                failures_by_url[original_url] = {
                    **candidate,
                    "error_type": type(exc).__name__,
                    "detail": str(exc),
                }
                write_log()
                print(f"FAILED {candidate['source_title']}: {exc}", flush=True)
                continue
        width, height = jpeg_dimensions(payload)
        entry_by_url[original_url] = {
            "asset_id": asset_id,
            "source_id": SOURCE_ID,
            "volume_id": volume_id,
            "source_file": candidate["source_title"],
            "source_character_page": candidate["source_character_page"],
            "viewer_url": candidate["viewer_url"],
            "original_url": original_url,
            "local_path": str(target.relative_to(ROOT)),
            "retrieved_at": retrieved_at,
            "sha256": sha256_bytes(payload),
            "bytes": len(payload),
            "mime_type": "image/jpeg",
            "width": width,
            "height": height,
            "license_id": "CC-BY-SA-4.0",
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "required_attribution": source["required_attribution"],
            "kangxi_number": candidate["kangxi_number"],
            "primary": candidate["primary"],
            "historical_form": "liushutong_六書通",
            "edition": f"偏類六書通 {volume_id}",
            "variant_index": variant_index,
            "mapping_method": (
                "exact_traditional_primary_unicode_index_and_"
                f"{volume_id}_anchor"
            ),
            "transformations": [],
            "representation_note": (
                "Unchanged source-published CODH glyph JPEG extracted by the source "
                "dataset from 偏類六書通; no local crop, resize, or re-encoding."
            ),
        }
        failures_by_url.pop(original_url, None)
        if index_number % 25 == 0 or index_number == len(image_candidates):
            write_log()
        if index_number % 50 == 0 or index_number == len(image_candidates):
            print(
                f"series originals {index_number}/{len(image_candidates)}; "
                f"new downloads {downloads}",
                flush=True,
            )
    write_log()
    print(
        f"series acquisition state: {len(entry_by_url)}/{len(image_candidates)} "
        f"originals; {len(failures_by_url)} failures"
    )


if __name__ == "__main__":
    main()
