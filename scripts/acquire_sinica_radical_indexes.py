#!/usr/bin/env python3
"""Acquire and parse exact-character 小學堂 Oracle and bronze query results."""

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
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "source-data" / "sinica-xiaoxuetang-2026-08-10"
SEARCH_ROOT = SOURCE_ROOT / "search"
OUTPUT = SOURCE_ROOT / "radical-historical-glyph-index.json"
SOURCE_ID = "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10"
HOST = "https://xiaoxue.iis.sinica.edu.tw"
USER_AGENT = "hanzi-project/1.0 (Traditional radical palaeography audit)"
KINDS = {
    "oracle_bone_甲骨文": "jiaguwen",
    "bronze_金文": "jinwen",
}
IMAGE_RE = re.compile(
    r'<td(?=[^>]*\bclass="VariantList[AB]")[^>]*>\s*'
    r'<img\s+src="(?P<src>[^"]+)"\s+alt="&(?P<code>\d+\.[A-F0-9]+);"'
    r'\s+class="charValue"[^>]*/>'
)
TAG_RE = re.compile(r"<[^>]+>")
BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def request(url: str, data: bytes | None = None) -> bytes:
    for attempt in range(5):
        request_object = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request_object, timeout=90) as response:
                return response.read()
        except (HTTPError, URLError):
            if attempt == 4:
                raise
            time.sleep(4.0 * (attempt + 1))
    raise RuntimeError("unreachable retry state")


def query_body(primary: str) -> bytes:
    return urllib.parse.urlencode(
        {
            "ZiOrder": "",
            "EudcFontChar": primary,
            "PageNo": "",
            "HeJiOrder": "",
            "Reference": "",
            "Category": "",
            "PaginalZiNum": "1000",
            "ImageSize": "36",
        }
    ).encode("utf-8")


def clean_reference(fragment: str) -> str | None:
    text = BREAK_RE.sub(" | ", fragment)
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    parts = [part.strip() for part in text.split("|") if part.strip()]
    return " | ".join(parts) or None


def image_url_300(src: str) -> str:
    decoded = html.unescape(src)
    parsed = urllib.parse.urlparse(urllib.parse.urljoin(HOST, decoded))
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["size"] = ["300"]
    query["resolution"] = ["96"]
    encoded = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=encoded))


def parse_records(
    raw: bytes,
    *,
    number: int,
    primary: str,
    kind: str,
    response_path: Path,
) -> list[dict[str, object]]:
    document = raw.decode("utf-8")
    matches = list(IMAGE_RE.finditer(document))
    records: list[dict[str, object]] = []
    for index, match in enumerate(matches, start=1):
        next_match_start = matches[index].start() if index < len(matches) else len(document)
        tail = document[match.end() : next_match_start]
        end_candidates = [position for marker in ("<td", "</tr>") if (position := tail.find(marker)) >= 0]
        reference_fragment = tail[: min(end_candidates)] if end_candidates else tail
        glyph_code = match.group("code")
        records.append(
            {
                "kangxi_number": number,
                "primary": primary,
                "kind": kind,
                "variant_index": index,
                "glyph_code": glyph_code,
                "source_reference": clean_reference(reference_fragment),
                "source_page": f"{HOST}/char?fontcode={glyph_code}",
                "source_image_url_300": image_url_300(match.group("src")),
                "source_query_response": str(response_path.relative_to(ROOT)),
                "source_query_response_sha256": sha256_bytes(raw),
                "mapping_method": "exact_traditional_primary_character_query",
                "source_id": SOURCE_ID,
            }
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    evidence = [
        ("license.html", f"{HOST}/License/License"),
        ("guide.html", f"{HOST}/guide/"),
    ]
    request_count = 0
    for filename, url in evidence:
        path = SOURCE_ROOT / filename
        if not path.exists():
            if args.limit is not None and request_count >= args.limit:
                break
            raw = request(url)
            path.write_bytes(raw)
            request_count += 1
            time.sleep(1.1)
    radicals = {
        number: json.loads((ROOT / "radicals" / f"{number}.json").read_text())
        for number in range(1, 215)
    }
    query_log: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    all_complete = all((SOURCE_ROOT / filename).exists() for filename, _ in evidence)
    for kind, endpoint in KINDS.items():
        target_dir = SEARCH_ROOT / endpoint
        target_dir.mkdir(parents=True, exist_ok=True)
        url = f"{HOST}/{endpoint}/PageResult/PageResult"
        for number in range(1, 215):
            primary = radicals[number]["primary"]["char"]
            path = target_dir / f"{number:03d}.html"
            if not path.exists():
                if args.limit is not None and request_count >= args.limit:
                    all_complete = False
                    continue
                raw = request(url, query_body(primary))
                path.write_bytes(raw)
                request_count += 1
                time.sleep(1.1)
            raw = path.read_bytes()
            parsed = parse_records(
                raw,
                number=number,
                primary=primary,
                kind=kind,
                response_path=path,
            )
            records.extend(parsed)
            query_log.append(
                {
                    "kangxi_number": number,
                    "primary": primary,
                    "kind": kind,
                    "request_url": url,
                    "request_method": "POST",
                    "request_form": urllib.parse.parse_qs(
                        query_body(primary).decode("utf-8")
                    ),
                    "response_path": str(path.relative_to(ROOT)),
                    "response_sha256": sha256_bytes(raw),
                    "response_bytes": len(raw),
                    "returned_glyph_count": len(parsed),
                }
            )
            if len(query_log) % 20 == 0:
                print(
                    f"searches {len(query_log)}/428; glyphs {len(records)}",
                    flush=True,
                )
    expected_paths = [
        SEARCH_ROOT / endpoint / f"{number:03d}.html"
        for endpoint in KINDS.values()
        for number in range(1, 215)
    ]
    all_complete = all_complete and all(path.exists() for path in expected_paths)
    if not all_complete:
        print(
            f"partial snapshot: {len(query_log)}/428 searches parsed; "
            f"{len(records)} glyph records"
        )
        return
    duplicate_codes: dict[str, list[dict[str, object]]] = {}
    for record in records:
        duplicate_codes.setdefault(str(record["glyph_code"]), []).append(record)
    duplicate_codes = {
        code: matches for code, matches in duplicate_codes.items() if len(matches) > 1
    }
    payload = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "license_evidence": [
            {
                "url": url,
                "path": str((SOURCE_ROOT / filename).relative_to(ROOT)),
                "sha256": sha256_bytes((SOURCE_ROOT / filename).read_bytes()),
                "bytes": (SOURCE_ROOT / filename).stat().st_size,
            }
            for filename, url in evidence
        ],
        "request_spacing_seconds": 1.1,
        "query_count": len(query_log),
        "glyph_count": len(records),
        "duplicate_glyph_codes": duplicate_codes,
        "queries": query_log,
        "records": records,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT.relative_to(ROOT)} with {len(records)} glyphs")


if __name__ == "__main__":
    main()
