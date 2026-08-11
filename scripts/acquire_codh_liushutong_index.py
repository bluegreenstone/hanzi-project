#!/usr/bin/env python3
"""Acquire and parse the licensed CODH 偏類六書通 TE00010 index."""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "source-data" / "codh-liushutong-2026-08-10"
INDEX_PATH = OUTPUT_ROOT / "TE00010-index.html"
OUTPUT = OUTPUT_ROOT / "radical-candidates.json"
URL = "https://codh.rois.ac.jp/tensho/book/TE00010/index.html.ja"
SOURCE_ID = "codh-henrui-liushutong-te00010-2026-08-10"
USER_AGENT = "hanzi-project/1.0 (licensed Liushutong radical index acquisition)"
ENTRY_RE = re.compile(
    r'<td id="U\+([0-9A-F]+)">.*?'
    r'<div class="unicode">U\+\1</div>.*?'
    r'<div class="glyph"><a href="([^"]+)">([^<]+)</a></div>.*?'
    r'<div class="count">(\d+)</div>',
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


def main() -> None:
    request = urllib.request.Request(
        URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
    text = raw.decode("utf-8")
    if "CC BY-SA" not in text or "10.20676/00000390" not in text:
        raise RuntimeError("TE00010 page lacks the expected license/DOI evidence")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_bytes(raw)

    entries_by_cp: dict[int, dict[str, object]] = {}
    for match in ENTRY_RE.finditer(text):
        cp = int(match.group(1), 16)
        entry = {
            "codepoint": f"U+{cp:04X}",
            "char": html.unescape(match.group(3)),
            "source_character_page": (
                "https://codh.rois.ac.jp" + match.group(2).split("#", 1)[0]
            ),
            "source_anchor": "TE00010",
            "source_glyph_count": int(match.group(4)),
            "mapping_method": "exact_unicode_codepoint_in_pinned_TE00010_index",
        }
        prior = entries_by_cp.get(cp)
        if prior is not None and prior != entry:
            raise RuntimeError(f"conflicting duplicate TE00010 entries for U+{cp:04X}")
        entries_by_cp[cp] = entry

    radical_candidates = []
    missing = []
    for number in range(1, 215):
        record = json.loads((ROOT / "radicals" / f"{number}.json").read_text(encoding="utf-8"))
        primary = record["primary"]["char"]
        cp = ord(primary)
        entry = entries_by_cp.get(cp)
        if entry is None:
            missing.append(
                {
                    "kangxi_number": number,
                    "primary": primary,
                    "codepoint": f"U+{cp:04X}",
                    "reason": "exact Traditional-primary codepoint absent from TE00010 index",
                }
            )
            continue
        if entry["char"] != primary:
            raise RuntimeError(
                f"TE00010 character mismatch at radical {number}: {entry['char']} != {primary}"
            )
        radical_candidates.append(
            {"kangxi_number": number, "primary": primary, **entry}
        )

    payload = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "source_url": URL,
        "index_path": str(INDEX_PATH.relative_to(ROOT)),
        "index_sha256": sha256_bytes(raw),
        "index_bytes": len(raw),
        "license_id": "CC-BY-SA-4.0",
        "license_evidence": {
            "page_contains": ["CC BY-SA", "doi:10.20676/00000390"],
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        },
        "indexed_character_count": len(entries_by_cp),
        "radical_candidate_count": len(radical_candidates),
        "radical_missing_count": len(missing),
        "radical_candidates": radical_candidates,
        "radical_missing": missing,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"TE00010 index has {len(entries_by_cp)} characters; exact radical "
        f"candidates {len(radical_candidates)}/214; absent {len(missing)}"
    )


if __name__ == "__main__":
    main()
