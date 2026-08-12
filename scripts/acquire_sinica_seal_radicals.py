#!/usr/bin/env python3
"""Acquire exact-character 小學堂 small-seal glyphs for 214 radicals."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import struct
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "source-data" / "sinica-xiaoxuetang-seal-2026-08-11"
PAGE_ROOT = SOURCE_ROOT / "character-pages"
LOG_PATH = SOURCE_ROOT / "radical-seal-acquisition-log.json"
SOURCE_ID = "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10"
HOST = "https://xiaoxue.iis.sinica.edu.tw"
USER_AGENT = "hanzi-project/1.0 (Taiwan scholarly seal-glyph verification)"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SEAL_RE = re.compile(
    r'<td(?=[^>]*\bclass="VariantList[AB]")[^>]*>\s*'
    r'<img src="(?P<src>[^"]+)" alt="&(?P<code>27\.[A-F0-9]+);"'
    r'\s+class="charValue"[^>]*/>\s*<br\s*/>(?P<reference>[^<]+)'
)
QUERY_URL = f"{HOST}/xiaozhuan/PageResult/PageResult"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Corpus repository root (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Acquire at most this many new radical page/image pairs.",
    )
    return parser.parse_args()


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


def request_bytes(url: str, accept: str, data: bytes | None = None) -> bytes:
    delays = (0, 2, 5, 10, 20)
    last_error: Exception | None = None
    for attempt, delay in enumerate(delays, start=1):
        if delay:
            time.sleep(delay)
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": accept,
                "Connection": "close",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except (HTTPError, URLError) as exc:
            last_error = exc
            print(
                f"request attempt {attempt}/{len(delays)} failed for {url}: {exc}",
                flush=True,
            )
    assert last_error is not None
    raise last_error


def image_url_300(src: str) -> str:
    parsed = urllib.parse.urlparse(urllib.parse.urljoin(HOST, html.unescape(src)))
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["size"] = ["300"]
    query["resolution"] = ["96"]
    return urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(query, doseq=True))
    )


def query_body(primary: str) -> bytes:
    return urllib.parse.urlencode(
        {
            "ZiOrder": "",
            "EudcFontChar": primary,
            "PageNo": "",
            "PaginalZiNum": "1000",
            "ImageSize": "36",
        }
    ).encode("utf-8")


def parse_page(payload: bytes, primary: str) -> dict[str, Any] | None:
    document = payload.decode("utf-8")
    matches = list(SEAL_RE.finditer(document))
    if not matches:
        return None
    match = matches[0]
    reference = html.unescape(match.group("reference")).strip()
    if not reference.startswith("說文‧"):
        raise RuntimeError(f"unexpected 小學堂 source reference: {reference!r}")
    image_url = image_url_300(match.group("src"))
    image_query = urllib.parse.parse_qs(urllib.parse.urlparse(image_url).query)
    if image_query.get("font") != ["北師大說文小篆"]:
        raise RuntimeError("small-seal image font identity differs")
    return {
        "glyph_code": match.group("code"),
        "source_reference": reference,
        "image_url": image_url,
        "source_candidate_count": len(matches),
        "queried_primary": primary,
    }


def write_log(
    entries: list[dict[str, Any]], gaps: list[dict[str, Any]]
) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": utc_now(),
        "source_id": SOURCE_ID,
        "selection_policy": (
            "POST the exact Traditional-primary radical to the official 小篆 "
            "query endpoint and select the first source-ordered result. Each "
            "result must expose a 27.* glyph code, a 說文 source reference, and "
            "the official 北師大說文小篆 image-font endpoint. The query response "
            "and complete returned-candidate count are preserved."
        ),
        "image_policy": (
            "Official 300-point, 96-dpi PNG response; no local crop, resize, "
            "re-encoding, tracing, or other transformation."
        ),
        "request_spacing_seconds": 1.1,
        "expected_count": 214,
        "completed_count": len(entries),
        "gap_count": len(gaps),
        "query_accounted_count": len(entries) + len(gaps),
        "entries": entries,
        "gaps": gaps,
    }
    LOG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    source_root = root / "source-data" / "sinica-xiaoxuetang-seal-2026-08-11"
    page_root = source_root / "character-pages"
    log_path = source_root / "radical-seal-acquisition-log.json"
    page_root.mkdir(parents=True, exist_ok=True)
    prior = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    prior_by_number = {
        entry["kangxi_number"]: entry for entry in prior.get("entries", [])
    }
    entries: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    new_pairs = 0
    last_request_started: float | None = None

    def spaced_request(
        url: str, accept: str, data: bytes | None = None
    ) -> bytes:
        nonlocal last_request_started
        if last_request_started is not None:
            delay = 1.1 - (time.monotonic() - last_request_started)
            if delay > 0:
                time.sleep(delay)
        last_request_started = time.monotonic()
        return request_bytes(url, accept, data)

    for number in range(1, 215):
        record = json.loads(
            (root / "radicals" / f"{number}.json").read_text(encoding="utf-8")
        )
        primary = record["primary"]["char"]
        codepoint = record["primary"]["codepoint"]
        page_path = page_root / f"{number:03d}-{codepoint}-query.html"
        target = (
            root
            / "assets"
            / "shuowen_seal"
            / codepoint
            / f"sinica-shuowen-seal-{codepoint}.png"
        )
        parsed: dict[str, Any] | None
        if not page_path.is_file():
            if args.limit is not None and new_pairs >= args.limit:
                continue
            page_payload = spaced_request(
                QUERY_URL, "text/html", query_body(primary)
            )
            page_path.write_bytes(page_payload)
            parsed = parse_page(page_payload, primary)
            new_pairs += 1
        else:
            page_payload = page_path.read_bytes()
            parsed = parse_page(page_payload, primary)
        if parsed is None:
            gaps.append(
                {
                    "kangxi_number": number,
                    "primary": primary,
                    "codepoint": codepoint,
                    "reason": "not_attested_in_exact_small_seal_query",
                    "source_query_url": QUERY_URL,
                    "source_query_method": "POST",
                    "source_query_form": urllib.parse.parse_qs(
                        query_body(primary).decode("utf-8")
                    ),
                    "source_query_response": str(page_path.relative_to(root)),
                    "source_query_response_sha256": sha256_bytes(page_payload),
                    "source_query_response_bytes": len(page_payload),
                }
            )
            write_log(entries, gaps)
            continue
        if not target.is_file():
            image_payload = spaced_request(parsed["image_url"], "image/png")
            png_dimensions(image_payload)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(image_payload)
        else:
            image_payload = target.read_bytes()
        width, height = png_dimensions(image_payload)
        retrieved_at = prior_by_number.get(number, {}).get("retrieved_at") or utc_now()
        entries.append(
            {
                "asset_id": f"sinica-shuowen-seal-{codepoint}",
                "source_id": SOURCE_ID,
                "source_glyph_code": parsed["glyph_code"],
                "source_page": f"{HOST}/char?fontcode={parsed['glyph_code']}",
                "source_query_url": QUERY_URL,
                "source_query_method": "POST",
                "source_query_form": urllib.parse.parse_qs(
                    query_body(primary).decode("utf-8")
                ),
                "source_page_local_path": str(page_path.relative_to(root)),
                "source_page_sha256": sha256_bytes(page_payload),
                "source_page_bytes": len(page_payload),
                "source_reference": parsed["source_reference"],
                "source_candidate_count": parsed["source_candidate_count"],
                "original_url": parsed["image_url"],
                "local_path": str(target.relative_to(root)),
                "retrieved_at": retrieved_at,
                "sha256": sha256_bytes(image_payload),
                "bytes": len(image_payload),
                "mime_type": "image/png",
                "width": width,
                "height": height,
                "license_id": "CC0-1.0",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "attribution_required": "false",
                "kangxi_number": number,
                "primary": primary,
                "historical_form": "shuowen_seal_說文解字",
                "mapping_method": "exact_traditional_primary_small_seal_character_page",
                "transformations": [],
                "representation_note": (
                    "Unchanged official maximum-size 小學堂 北師大說文小篆 "
                    "glyph-font response for the exact Traditional primary "
                    "character; not a locally traced Commons vector."
                ),
                "source_file": parsed["glyph_code"],
                "source_file_page": f"{HOST}/char?fontcode={parsed['glyph_code']}",
            }
        )
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_log(entries, gaps)
        if number % 10 == 0 or number == 214:
            print(
                f"seal radicals {number}/214; complete {len(entries)}; "
                f"new pairs {new_pairs}",
                flush=True,
            )
    accounted = len(entries) + len(gaps)
    if accounted != 214:
        print(
            f"partial acquisition: {len(entries)} assets + {len(gaps)} gaps "
            f"= {accounted}/214 accounted"
        )
        return
    print(
        f"wrote {log_path.relative_to(root)} with {len(entries)} exact seal "
        f"assets and {len(gaps)} source gaps"
    )


if __name__ == "__main__":
    main()
