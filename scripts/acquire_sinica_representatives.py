#!/usr/bin/env python3
"""Acquire one highest-size 小學堂 original per covered radical and form."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "source-data" / "sinica-xiaoxuetang-2026-08-10"
INDEX = SOURCE_ROOT / "radical-historical-glyph-index.json"
LOG_PATH = SOURCE_ROOT / "representative-original-acquisition-log.json"
ASSET_MANIFEST = ROOT / "assets" / "manifest.json"
SOURCE_ID = "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10"
USER_AGENT = "hanzi-project/1.0 (Sinica radical glyph acquisition)"
KIND_SLUG = {
    "oracle_bone_甲骨文": "oracle",
    "bronze_金文": "bronze",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def png_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 24 or not payload.startswith(PNG_SIGNATURE):
        raise ValueError("source response is not a PNG")
    if payload[12:16] != b"IHDR":
        raise ValueError("PNG has no leading IHDR chunk")
    return struct.unpack(">II", payload[16:24])


def target_for(record: dict[str, Any]) -> tuple[str, Path]:
    slug = KIND_SLUG[record["kind"]]
    codepoint = f"U+{ord(record['primary']):04X}"
    asset_id = f"sinica-{slug}-{codepoint}-representative"
    path = ROOT / "assets" / slug / codepoint / f"{asset_id}.png"
    return asset_id, path


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "image/png"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        content_type = response.headers.get_content_type()
        payload = response.read()
    if content_type != "image/png":
        raise ValueError(f"unexpected source content type {content_type!r}")
    png_dimensions(payload)
    return payload


def write_log(entries: list[dict[str, Any]], expected_count: int) -> None:
    payload = {
        "updated_at": utc_now(),
        "source_id": SOURCE_ID,
        "index_path": str(INDEX.relative_to(ROOT)),
        "index_sha256": sha256_bytes(INDEX.read_bytes()),
        "selection_policy": (
            "For each radical and historical form with one or more exact-character "
            "results, acquire the first glyph in the source's returned order. The full "
            "candidate list remains preserved in the index."
        ),
        "image_policy": (
            "Official 300-point, 96-dpi PNG response, the highest size exposed by the "
            "source interface; no local resize, crop, or re-encoding."
        ),
        "request_policy": (
            "Sequential requests with at least 1.1 seconds between starts to "
            "xiaoxue.iis.sinica.edu.tw."
        ),
        "expected_count": expected_count,
        "completed_count": len(entries),
        "entries": entries,
    }
    LOG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for record in index["records"]:
        grouped.setdefault((record["kangxi_number"], record["kind"]), []).append(record)
    representatives = [
        sorted(records, key=lambda record: record["variant_index"])[0]
        for records in grouped.values()
    ]
    representatives.sort(key=lambda record: (record["kangxi_number"], record["kind"]))
    candidate_counts = {key: len(records) for key, records in grouped.items()}
    if LOG_PATH.exists():
        prior = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    else:
        manifest = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
        prior = {
            "entries": [
                entry
                for entry in manifest.get("assets", [])
                if entry.get("source_id") == SOURCE_ID
                and entry.get("historical_form") in KIND_SLUG
            ]
        }
        if len(prior["entries"]) != 325:
            raise RuntimeError(
                "missing Sinica representative log and manifest does not preserve all 325 entries"
            )
    prior_by_asset = {entry["asset_id"]: entry for entry in prior.get("entries", [])}
    payload_by_url: dict[str, bytes] = {}
    entries: list[dict[str, Any]] = []
    downloads = 0
    last_request_started: float | None = None
    for index_number, record in enumerate(representatives, start=1):
        asset_id, target = target_for(record)
        if target.exists():
            payload = target.read_bytes()
            width, height = png_dimensions(payload)
            retrieved_at = prior_by_asset.get(asset_id, {}).get("retrieved_at") or (
                datetime.fromtimestamp(target.stat().st_mtime, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
        else:
            url = record["source_image_url_300"]
            payload = payload_by_url.get(url)
            if payload is None:
                if args.limit is not None and downloads >= args.limit:
                    break
                if last_request_started is not None:
                    delay = 1.1 - (time.monotonic() - last_request_started)
                    if delay > 0:
                        time.sleep(delay)
                last_request_started = time.monotonic()
                payload = request_bytes(url)
                payload_by_url[url] = payload
                downloads += 1
            width, height = png_dimensions(payload)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            retrieved_at = utc_now()
        entry = {
            "asset_id": asset_id,
            "source_id": SOURCE_ID,
            "source_glyph_code": record["glyph_code"],
            "source_page": record["source_page"],
            "original_url": record["source_image_url_300"],
            "local_path": str(target.relative_to(ROOT)),
            "retrieved_at": retrieved_at,
            "sha256": sha256_bytes(payload),
            "bytes": len(payload),
            "mime_type": "image/png",
            "width": width,
            "height": height,
            "license_id": "CC0-1.0",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "attribution_required": "false",
            "kangxi_number": record["kangxi_number"],
            "primary": record["primary"],
            "historical_form": record["kind"],
            "source_reference": record["source_reference"],
            "source_candidate_count": candidate_counts[
                (record["kangxi_number"], record["kind"])
            ],
            "variant_index": record["variant_index"],
            "mapping_method": record["mapping_method"],
            "transformations": [],
            "representation_note": (
                "Unchanged official maximum-size 小學堂 query image generated from "
                "the database's palaeographic glyph font; not a cropped rubbing."
            ),
        }
        entries.append(entry)
        write_log(entries, len(representatives))
        if index_number % 20 == 0 or index_number == len(representatives):
            print(
                f"representatives {index_number}/{len(representatives)}; "
                f"network downloads {downloads}",
                flush=True,
            )
    if len(entries) != len(representatives):
        print(
            f"partial acquisition: {len(entries)}/{len(representatives)} representatives"
        )
        return
    print(f"wrote {LOG_PATH.relative_to(ROOT)} with {len(entries)} originals")


if __name__ == "__main__":
    main()
