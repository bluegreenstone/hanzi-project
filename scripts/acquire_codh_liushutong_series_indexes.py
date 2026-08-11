#!/usr/bin/env python3
"""Acquire and parse licensed CODH 偏類六書通 indexes beyond TE00010."""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "source-data" / "codh-liushutong-series-2026-08-11"
OUTPUT = OUTPUT_ROOT / "radical-candidates-series.json"
CATALOG_URL = "https://codh.rois.ac.jp/tensho/book/"
VOLUME_IDS = [
    *(f"TE{number:05d}" for number in range(8, 10)),
    *(f"TE{number:05d}" for number in range(11, 22)),
]
SOURCE_ID = "codh-henrui-liushutong-te00008-21-series-2026-08-11"
USER_AGENT = "hanzi-project/1.0 (licensed Liushutong series index acquisition)"
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


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    catalog_path = OUTPUT_ROOT / "book-list.html"
    if catalog_path.exists():
        catalog_raw = catalog_path.read_bytes()
    else:
        catalog_raw = fetch(CATALOG_URL)
        catalog_path.write_bytes(catalog_raw)
        time.sleep(1.1)
    catalog_text = catalog_raw.decode("utf-8")
    for volume_id in VOLUME_IDS:
        if volume_id not in catalog_text or "CC BY-SA" not in catalog_text:
            raise RuntimeError(f"catalog lacks expected license row for {volume_id}")

    radicals = {
        number: json.loads(
            (ROOT / "radicals" / f"{number}.json").read_text(encoding="utf-8")
        )["primary"]["char"]
        for number in range(1, 215)
    }
    volume_snapshots: list[dict[str, object]] = []
    radical_candidates: list[dict[str, object]] = []
    radical_missing: list[dict[str, object]] = []
    indexed_character_total = 0

    for position, volume_id in enumerate(VOLUME_IDS, start=1):
        url = f"https://codh.rois.ac.jp/tensho/book/{volume_id}/index.html.ja"
        path = OUTPUT_ROOT / f"{volume_id}-index.html"
        if path.exists():
            raw = path.read_bytes()
        else:
            raw = fetch(url)
            path.write_bytes(raw)
            time.sleep(1.1)
        text = raw.decode("utf-8")
        if "CC BY-SA" not in text or "10.20676/00000390" not in text:
            raise RuntimeError(f"{volume_id} page lacks expected license/DOI evidence")

        entries_by_cp: dict[int, dict[str, object]] = {}
        for match in ENTRY_RE.finditer(text):
            cp = int(match.group(1), 16)
            entry = {
                "codepoint": f"U+{cp:04X}",
                "char": html.unescape(match.group(3)),
                "source_character_page": (
                    "https://codh.rois.ac.jp" + match.group(2).split("#", 1)[0]
                ),
                "source_anchor": volume_id,
                "source_glyph_count": int(match.group(4)),
                "mapping_method": (
                    "exact_unicode_codepoint_in_pinned_"
                    f"{volume_id}_index"
                ),
            }
            prior = entries_by_cp.get(cp)
            if prior is not None and prior != entry:
                raise RuntimeError(
                    f"conflicting duplicate {volume_id} entries for U+{cp:04X}"
                )
            entries_by_cp[cp] = entry
        indexed_character_total += len(entries_by_cp)

        exact_count = 0
        for number, primary in radicals.items():
            cp = ord(primary)
            entry = entries_by_cp.get(cp)
            if entry is None:
                radical_missing.append(
                    {
                        "volume_id": volume_id,
                        "kangxi_number": number,
                        "primary": primary,
                        "codepoint": f"U+{cp:04X}",
                        "reason": (
                            "exact Traditional-primary codepoint absent from "
                            f"{volume_id} index"
                        ),
                    }
                )
                continue
            if entry["char"] != primary:
                raise RuntimeError(
                    f"{volume_id} character mismatch at radical {number}: "
                    f"{entry['char']} != {primary}"
                )
            radical_candidates.append(
                {
                    "volume_id": volume_id,
                    "kangxi_number": number,
                    "primary": primary,
                    **entry,
                }
            )
            exact_count += 1

        volume_snapshots.append(
            {
                "volume_id": volume_id,
                "url": url,
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256_bytes(raw),
                "bytes": len(raw),
                "indexed_character_count": len(entries_by_cp),
                "exact_radical_count": exact_count,
            }
        )
        print(
            f"{volume_id} indexes {len(entries_by_cp)} characters; "
            f"exact radicals {exact_count}/214 ({position}/{len(VOLUME_IDS)})",
            flush=True,
        )

    payload = {
        "retrieved_at": utc_now(),
        "source_id": SOURCE_ID,
        "catalog": {
            "url": CATALOG_URL,
            "path": str(catalog_path.relative_to(ROOT)),
            "sha256": sha256_bytes(catalog_raw),
            "bytes": len(catalog_raw),
        },
        "license_id": "CC-BY-SA-4.0",
        "license_evidence": {
            "catalog_contains": [
                "TE00008 through TE00021 偏類六書通",
                "CC BY-SA",
            ],
            "volume_pages_contain": ["CC BY-SA", "doi:10.20676/00000390"],
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        },
        "request_spacing_seconds": 1.1,
        "volume_ids": VOLUME_IDS,
        "volume_snapshots": volume_snapshots,
        "indexed_character_total": indexed_character_total,
        "radical_candidate_count": len(radical_candidates),
        "radical_missing_count": len(radical_missing),
        "radical_candidates": radical_candidates,
        "radical_missing": radical_missing,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    covered = len({item["kangxi_number"] for item in radical_candidates})
    images = sum(int(item["source_glyph_count"]) for item in radical_candidates)
    print(
        f"series candidates {len(radical_candidates)} across {covered}/214 radicals; "
        f"declared glyph images {images}"
    )


if __name__ == "__main__":
    main()
