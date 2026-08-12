#!/usr/bin/env python3
"""Acquire targeted readings from Taiwan MOE's Dictionary of Variants.

Only the character records still differing from the downloadable Revised
Dictionary are queried. Search and detail responses are retained byte-for-byte
with hashes so the cross-check remains inspectable and repeatable.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "moe-tw-dictionary-variants-2024-targeted-readings"
HOST = "https://dict.variants.moe.edu.tw"
SEARCH_URL = f"{HOST}/search.jsp"
SOURCE_ROOT = ROOT / "source-data" / "moe-variants-2024-targeted"
LOG_PATH = SOURCE_ROOT / "character-reading-acquisition-log.json"
USER_AGENT = "hanzi-project/1.0 (Taiwan MOE pronunciation verification)"
EXPECTED_TARGET_COUNT = 36
SEARCH_RESULT_RE = re.compile(
    r"<a href=['\"]/?dictView\.jsp\?ID=(?P<id>\d+)&amp;q=1['\"]"
    r"[^>]*data-tp=['\"]正['\"][^>]*data-ucs=['\"](?P<codepoint>U\+[0-9A-F]+)['\"]"
)
ROW_RE_TEMPLATE = r"<tr><th[^>]*>{label}</th>\s*<td>(?P<body>.*?)</td></tr>"
PHON_RE = re.compile(r"<phon>(?P<body>.*?)</phon>", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
PINYIN_RE = re.compile(
    r"[a-züāáǎàēéěèīíǐìōóǒòūúǔùńňǹḿê]+", re.IGNORECASE
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Corpus repository root (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("metadata/audits/pronunciation-moe-revised-20260625.json"),
        help="Revised-Dictionary audit whose character review queue is targeted.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Acquire at most this many new search/detail pairs.",
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


def strip_tags(value: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub("", value)).split())


def parse_detail(payload: bytes) -> tuple[list[str], list[str], str]:
    document = payload.decode("utf-8")
    zhuyin_match = re.search(
        ROW_RE_TEMPLATE.format(label="注　　音"), document, re.DOTALL
    )
    pinyin_match = re.search(
        ROW_RE_TEMPLATE.format(label="漢語拼音"), document, re.DOTALL
    )
    if not zhuyin_match or not pinyin_match or "ID Miss!!" in document:
        raise RuntimeError("MOE Variant Dictionary detail lacks reading rows")
    zhuyin = [
        strip_tags(match.group("body"))
        for match in PHON_RE.finditer(zhuyin_match.group("body"))
    ]
    pinyin = [
        value.casefold()
        for value in PINYIN_RE.findall(strip_tags(pinyin_match.group("body")))
    ]
    serial_match = re.search(r"<span class=viewH><code>([A-Z][0-9]+)</code>", document)
    if not serial_match:
        raise RuntimeError("MOE Variant Dictionary detail lacks a serial number")
    if not zhuyin or len(zhuyin) != len(pinyin):
        raise RuntimeError(
            f"MOE Variant Dictionary reading pairing differs: {zhuyin!r}/{pinyin!r}"
        )
    return pinyin, zhuyin, serial_match.group(1)


def build_opener() -> urllib.request.OpenerDirector:
    cookies = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))


def request_bytes(
    opener: urllib.request.OpenerDirector,
    url: str,
    referer: str | None = None,
) -> bytes:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    delays = (0, 2, 5, 10)
    last_error: Exception | None = None
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            with opener.open(request, timeout=90) as response:
                return response.read()
        except Exception as exc:  # bounded retries preserve the final exception
            last_error = exc
    assert last_error is not None
    raise last_error


def write_log(
    path: Path,
    targets: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": utc_now(),
        "source_id": SOURCE_ID,
        "source_version": "臺灣學術網路十四版（正式七版）2024",
        "source_url": HOST,
        "selection_policy": (
            "Exact quick-search query for the record's Traditional character; "
            "accept only the 正字 result whose data-ucs exactly equals the record "
            "codepoint. The matching session-bound detail page supplies the "
            "displayed 注音 and 漢語拼音 arrays."
        ),
        "request_spacing_seconds": 1.1,
        "target_count": len(targets),
        "completed_count": len(entries),
        "gap_count": len(gaps),
        "entries": sorted(entries, key=lambda item: item["frequency_rank"]),
        "gaps": sorted(gaps, key=lambda item: item["frequency_rank"]),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    audit_path = args.audit if args.audit.is_absolute() else root / args.audit
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit_targets = audit["characters"]["review_queue"]
    source_root = root / "source-data" / "moe-variants-2024-targeted"
    page_root = source_root / "pages"
    log_path = source_root / "character-reading-acquisition-log.json"
    page_root.mkdir(parents=True, exist_ok=True)
    prior = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    prior_entries = {entry["codepoint"]: entry for entry in prior.get("entries", [])}
    if (
        prior.get("target_count") == EXPECTED_TARGET_COUNT
        and prior.get("completed_count") == EXPECTED_TARGET_COUNT
        and prior.get("gap_count") == 0
    ):
        # The live corpus may already contain the Variant-Dictionary overlay,
        # making a post-integration Revised audit smaller than the original
        # discrepancy queue. Preserve the pinned acquisition target set rather
        # than silently dropping previously verified codepoints.
        targets = [
            {
                "codepoint": entry["codepoint"],
                "traditional": entry["traditional"],
                "frequency_rank": entry["frequency_rank"],
            }
            for entry in prior["entries"]
        ]
    else:
        targets = audit_targets
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise RuntimeError(
            f"Variant Dictionary target queue has {len(targets)} records; "
            f"expected the pinned pre-integration set of {EXPECTED_TARGET_COUNT}"
        )
    entries: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    opener = build_opener()
    new_pairs = 0
    last_request_started: float | None = None

    def spaced_request(url: str, referer: str | None = None) -> bytes:
        nonlocal last_request_started
        if last_request_started is not None:
            delay = 1.1 - (time.monotonic() - last_request_started)
            if delay > 0:
                time.sleep(delay)
        last_request_started = time.monotonic()
        return request_bytes(opener, url, referer)

    for target in targets:
        codepoint = target["codepoint"]
        traditional = target["traditional"]
        stem = codepoint.replace("+", "-")
        search_path = page_root / f"{stem}-search.html"
        detail_path = page_root / f"{stem}-detail.html"
        if detail_path.is_file() and search_path.is_file():
            search_payload = search_path.read_bytes()
            detail_payload = detail_path.read_bytes()
            match = next(
                (
                    item
                    for item in SEARCH_RESULT_RE.finditer(
                        search_payload.decode("utf-8")
                    )
                    if item.group("codepoint") == codepoint
                ),
                None,
            )
            if match is None:
                raise RuntimeError(f"cached search no longer parses for {codepoint}")
            entry_id = match.group("id")
        else:
            if args.limit is not None and new_pairs >= args.limit:
                continue
            query = urllib.parse.urlencode({"QTP": "0", "WORD": traditional})
            search_url = f"{SEARCH_URL}?{query}"
            search_payload = spaced_request(search_url)
            search_path.write_bytes(search_payload)
            match = next(
                (
                    item
                    for item in SEARCH_RESULT_RE.finditer(
                        search_payload.decode("utf-8")
                    )
                    if item.group("codepoint") == codepoint
                ),
                None,
            )
            if match is None:
                gaps.append(
                    {
                        "codepoint": codepoint,
                        "traditional": traditional,
                        "frequency_rank": target["frequency_rank"],
                        "reason": "no_exact_primary_result",
                        "search_url": search_url,
                        "search_local_path": str(search_path.relative_to(root)),
                        "search_sha256": sha256_bytes(search_payload),
                    }
                )
                write_log(log_path, targets, entries, gaps)
                continue
            entry_id = match.group("id")
            detail_url = f"{HOST}/dictView.jsp?ID={entry_id}&q=1"
            detail_payload = spaced_request(detail_url, search_url)
            detail_path.write_bytes(detail_payload)
            new_pairs += 1
        pinyin, zhuyin, serial = parse_detail(detail_payload)
        search_url = (
            f"{SEARCH_URL}?"
            + urllib.parse.urlencode({"QTP": "0", "WORD": traditional})
        )
        entry = {
            "codepoint": codepoint,
            "traditional": traditional,
            "frequency_rank": target["frequency_rank"],
            "dictionary_serial": serial,
            "internal_entry_id": entry_id,
            "pinyin": pinyin,
            "zhuyin": zhuyin,
            "search_url": search_url,
            "detail_url": f"{HOST}/dictView.jsp?ID={entry_id}&q=1",
            "search_local_path": str(search_path.relative_to(root)),
            "search_sha256": sha256_bytes(search_payload),
            "search_bytes": len(search_payload),
            "detail_local_path": str(detail_path.relative_to(root)),
            "detail_sha256": sha256_bytes(detail_payload),
            "detail_bytes": len(detail_payload),
            "retrieved_at": prior_entries.get(codepoint, {}).get("retrieved_at")
            or utc_now(),
        }
        entries.append(entry)
        write_log(log_path, targets, entries, gaps)
    write_log(log_path, targets, entries, gaps)
    print(
        json.dumps(
            {
                "target_count": len(targets),
                "completed_count": len(entries),
                "gap_count": len(gaps),
                "new_pairs": new_pairs,
                "log": str(log_path.relative_to(root)),
            }
        )
    )


if __name__ == "__main__":
    main()
