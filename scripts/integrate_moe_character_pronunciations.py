#!/usr/bin/env python3
"""Make Taiwan MOE evidence canonical for all 2,000 character readings.

The downloadable Revised Dictionary verifies 1,964 records exactly. The 36
remaining codepoint-level discrepancies are resolved with exact 正字 pages from
the MOE Dictionary of Character Variants, whose character-level reading set is
preferred over lexical headword coverage. Superseded CNS/Unihan values remain
in explicit conflict evidence rather than disappearing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase3 as phase3  # noqa: E402
import build_phase4 as phase4  # noqa: E402
import validate_phase4 as validate4  # noqa: E402
from moe_concised import load_moe_rows  # noqa: E402


REVISED_ID = "moe-tw-revised-dictionary-2015-20260625"
VARIANTS_ID = "moe-tw-dictionary-variants-2024-targeted-readings"
REVISED_ROOT = Path("source-data/moe-revised-2015-20260625")
REVISED_XLSX = REVISED_ROOT / "dict_revised_2015_20260625.xlsx"
REVISED_ZIP = REVISED_ROOT / "dict_revised_2015_20260625.zip"
REVISED_PAGE = REVISED_ROOT / "download-page.html"
REVISED_LICENSE_PAGE = REVISED_ROOT / "public-license-index.html"
VARIANTS_ROOT = Path("source-data/moe-variants-2024-targeted")
VARIANTS_LOG = VARIANTS_ROOT / "character-reading-acquisition-log.json"
VARIANTS_HOME = VARIANTS_ROOT / "home.html"
LEGACY_READING_SOURCES = [
    "cns11643-attributes-2026-08-05",
    "unicode-unihan-17.0.0",
]
TARGETED_COUNT = 36


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Corpus repository root (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if records, source registry, or manifests are stale.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pointer(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    return {
        "path": str(relative),
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
    }


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def legacy_value(record: dict[str, Any], field: str) -> list[str]:
    for conflict in record["conflicts"]:
        if (
            conflict.get("field") == field
            and conflict.get("resolution") == "taiwan_moe_canonical"
        ):
            for value in conflict["values"]:
                if any(source in LEGACY_READING_SOURCES for source in value["source_ids"]):
                    return list(value["value"])
    if field == "readings.pinyin":
        return [item["reading"] for item in record["readings"]["pinyin"]]
    return list(record["readings"]["zhuyin"])


def merge_conflict_values(
    candidates: list[tuple[list[str], list[str]]]
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for value, source_ids in candidates:
        prior = next((item for item in merged if item["value"] == value), None)
        if prior is None:
            merged.append({"value": value, "source_ids": unique(source_ids)})
        else:
            prior["source_ids"] = unique([*prior["source_ids"], *source_ids])
    return merged


def reading_conflict(
    field: str,
    legacy: list[str],
    revised: list[str],
    variants: list[str],
) -> dict[str, Any] | None:
    values = merge_conflict_values(
        [
            (legacy, LEGACY_READING_SOURCES),
            (revised, [REVISED_ID]),
            (variants, [VARIANTS_ID]),
        ]
    )
    if len(values) < 2:
        return None
    return {
        "field": field,
        "resolution": "taiwan_moe_canonical",
        "values": values,
        "detail": (
            "For a character-level record, the exact-codepoint 正字 reading set "
            "from the Taiwan MOE Dictionary of Character Variants is canonical. "
            "The downloadable Revised Dictionary lexical set and earlier "
            "CNS/Unihan evidence remain here for transparent cross-reference."
        ),
    }


def ordered_variant_pinyin(
    record: dict[str, Any], official: list[str]
) -> list[str]:
    current = [item["reading"] for item in record["readings"]["pinyin"]]
    primary = next(
        (
            item["reading"]
            for item in record["readings"]["pinyin"]
            if item["context"] == "primary" and item["reading"] in official
        ),
        None,
    )
    result: list[str] = []
    if primary:
        result.append(primary)
    result.extend(value for value in current if value in official and value not in result)
    result.extend(value for value in official if value not in result)
    return result


def update_targeted_record(
    record: dict[str, Any],
    revised_rows: list[dict[str, str]],
    variant: dict[str, Any],
) -> dict[str, Any]:
    result = json.loads(json.dumps(record, ensure_ascii=False))
    legacy_pinyin = legacy_value(record, "readings.pinyin")
    legacy_zhuyin = legacy_value(record, "readings.zhuyin")
    revised_pinyin = unique([row["pinyin"] for row in revised_rows])
    revised_zhuyin = unique([row["zhuyin"] for row in revised_rows])
    variant_pinyin = list(variant["pinyin"])
    variant_zhuyin = list(variant["zhuyin"])
    if len(variant_pinyin) != len(variant_zhuyin):
        raise RuntimeError(f"unpaired Variant Dictionary readings: {record['codepoint']}")
    zhuyin_by_pinyin = dict(zip(variant_pinyin, variant_zhuyin))
    pinyin = ordered_variant_pinyin(result, variant_pinyin)
    result["readings"]["pinyin"] = [
        {
            "reading": reading,
            "context": "primary" if index == 0 else "additional",
            "region": "TW",
            "standard": "TW-MOE-Variants-2024",
            "source_entry_ids": [variant["dictionary_serial"]],
        }
        for index, reading in enumerate(pinyin)
    ]
    result["readings"]["zhuyin"] = [zhuyin_by_pinyin[reading] for reading in pinyin]
    result["sources"]["readings.pinyin"] = [VARIANTS_ID]
    result["sources"]["readings.zhuyin"] = [VARIANTS_ID]
    result["conflicts"] = [
        conflict
        for conflict in result["conflicts"]
        if not (
            conflict.get("field") in {"readings.pinyin", "readings.zhuyin"}
            and conflict.get("resolution") == "taiwan_moe_canonical"
        )
    ]
    for conflict in (
        reading_conflict(
            "readings.pinyin", legacy_pinyin, revised_pinyin, variant_pinyin
        ),
        reading_conflict(
            "readings.zhuyin", legacy_zhuyin, revised_zhuyin, variant_zhuyin
        ),
    ):
        if conflict is not None:
            result["conflicts"].append(conflict)
    result["conflicts"].sort(
        key=lambda item: (item["field"], item["resolution"], item["detail"])
    )
    return result


def update_revised_record(
    record: dict[str, Any], rows: list[dict[str, str]]
) -> dict[str, Any]:
    result = json.loads(json.dumps(record, ensure_ascii=False))
    by_pinyin: dict[str, list[str]] = defaultdict(list)
    by_zhuyin: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row["entry_id"] not in by_pinyin[row["pinyin"]]:
            by_pinyin[row["pinyin"]].append(row["entry_id"])
        if row["entry_id"] not in by_zhuyin[row["zhuyin"]]:
            by_zhuyin[row["zhuyin"]].append(row["entry_id"])
    corpus_pinyin = [item["reading"] for item in result["readings"]["pinyin"]]
    corpus_zhuyin = list(result["readings"]["zhuyin"])
    if set(corpus_pinyin) != set(by_pinyin) or set(corpus_zhuyin) != set(by_zhuyin):
        raise RuntimeError(
            f"non-targeted Revised reading mismatch: {record['codepoint']}"
        )
    for item in result["readings"]["pinyin"]:
        item["standard"] = "TW-MOE-Revised-2015"
        item["source_entry_ids"] = by_pinyin[item["reading"]]
    result["sources"]["readings.pinyin"] = unique(
        [REVISED_ID, *result["sources"].get("readings.pinyin", [])]
    )
    result["sources"]["readings.zhuyin"] = unique(
        [REVISED_ID, *result["sources"].get("readings.zhuyin", [])]
    )
    return result


def registry_sources(root: Path, log: dict[str, Any]) -> dict[str, dict[str, Any]]:
    revised_xlsx = pointer(root, REVISED_XLSX)
    revised_zip = pointer(root, REVISED_ZIP)
    revised_page = pointer(root, REVISED_PAGE)
    revised_license = pointer(root, REVISED_LICENSE_PAGE)
    variants_log = pointer(root, VARIANTS_LOG)
    variants_home = pointer(root, VARIANTS_HOME)
    return {
        REVISED_ID: {
            "id": REVISED_ID,
            "full_name": "Taiwan Ministry of Education Revised Mandarin Dictionary",
            "url": "https://dict.revised.moe.edu.tw/",
            "documentation_url": "https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/respub/reviseddict_10312.pdf",
            "access_date": "2026-08-11",
            "version": "2015_20260625",
            "acquisition": {
                "retrieved_at": "2026-08-12T00:05:26Z",
                "local_path": revised_xlsx["path"],
                "sha256": revised_xlsx["sha256"],
                "expected_bytes": revised_xlsx["bytes"],
                "download_url": "https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/respub/download/dict_revised_2015_20260625.zip",
                "container_path": revised_zip["path"],
                "container_sha256": revised_zip["sha256"],
                "container_bytes": revised_zip["bytes"],
                "archive_member": "dict_revised_2015_20260625.xlsx",
                "download_page": revised_page,
                "public_license_index": revised_license,
            },
            "status": "approved",
            "license": {
                "id": "CC-BY-ND-3.0-TW",
                "name": "Creative Commons Attribution-NoDerivatives 3.0 Taiwan",
                "url": "https://creativecommons.org/licenses/by-nd/3.0/tw/",
                "verified": True,
            },
            "redistribution": (
                "Verbatim redistribution is permitted with attribution. The "
                "corpus copies exact pronunciation strings and decoded XLSX "
                "definition-cell strings with entry IDs without editorial alteration."
            ),
            "coverage": [
                "all 2,000 selected Traditional character headwords",
                "character-headword Pinyin and Zhuyin cross-check",
                (
                    "1,251 exact Traditional word headwords absent from the "
                    "Concised Dictionary"
                ),
                "word-headword Pinyin, Zhuyin, and dictionary entry IDs",
            ],
            "schema_fields": [
                "characters.*.readings.pinyin",
                "characters.*.readings.zhuyin",
                "characters.*.definitions_zh_TW",
                "characters.*.conflicts",
                "words.*.pinyin",
                "words.*.zhuyin",
                "words.*.definitions_zh_TW",
                "words.*.conflicts",
            ],
            "constraints": [
                "Match exact NFC Traditional headwords only.",
                "Do not alter MOE pronunciation strings.",
                "Do not summarize, split, reorder, normalize compatibility ideographs, or otherwise adapt definition strings after standards-compliant OOXML character-escape decoding.",
                "Prefer exact-codepoint Dictionary of Variants evidence when lexical and character-level inventories differ.",
                (
                    "For word records, use only an exact NFC Traditional-headword "
                    "match after confirming the Concised Dictionary has no entry."
                ),
                (
                    "A headword absent from both official downloads remains an "
                    "explicit verification gap rather than an inferred match."
                ),
            ],
        },
        VARIANTS_ID: {
            "id": VARIANTS_ID,
            "full_name": "教育部《異體字字典》臺灣學術網路十四版（正式七版）2024 — targeted 正字 reading verification",
            "url": "https://dict.variants.moe.edu.tw/",
            "documentation_url": "https://dict.variants.moe.edu.tw/page.jsp?ID=7",
            "access_date": "2026-08-11",
            "version": "臺灣學術網路十四版（正式七版）2024",
            "acquisition": {
                "retrieved_at": log["updated_at"],
                "local_path": variants_log["path"],
                "sha256": variants_log["sha256"],
                "expected_bytes": variants_log["bytes"],
                "home_snapshot": variants_home,
                "target_count": log["target_count"],
                "completed_count": log["completed_count"],
                "gap_count": log["gap_count"],
                "per_entry_response_hashes": True,
            },
            "status": "approved",
            "license": {
                "id": "MOE-site-copyright-factual-citation-only",
                "name": "MOE site copyright; approval limited to citation of factual pronunciation data",
                "url": "https://dict.variants.moe.edu.tw/",
                "verified": True,
            },
            "redistribution": (
                "Raw response pages are audit-only source data and excluded from "
                "the release. Character records retain only short factual reading "
                "strings, exact codepoints, and dictionary serial citations."
            ),
            "coverage": [
                "36 exact-codepoint 正字 entries targeted from the Revised Dictionary discrepancy queue",
                "displayed Pinyin, Zhuyin, and stable dictionary serial",
            ],
            "schema_fields": [
                "characters.*.readings.pinyin",
                "characters.*.readings.zhuyin",
                "characters.*.conflicts",
            ],
            "constraints": [
                "Accept only an exact data-ucs codepoint match marked 正字.",
                "Preserve the exact search and detail response hashes outside the release payload.",
                "Do not redistribute definitions, page imagery, or raw HTML in the corpus release.",
            ],
        },
    }


def update_manifests(
    root: Path,
    records: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
) -> None:
    phase3_path = root / "metadata" / "manifests" / "phase3.json"
    manifest3 = json.loads(phase3_path.read_text(encoding="utf-8"))
    phase3_records = [phase4.phase3_projection(record) for record in records]
    manifest3.update(
        {
            "generated_at": utc_now(),
            "record_digest_sha256": phase3.deterministic_record_digest(
                phase3_records
            ),
            "records_with_conflicts": sum(
                bool(record["conflicts"]) for record in phase3_records
            ),
            "conflict_count": sum(
                len(record["conflicts"]) for record in phase3_records
            ),
            "gap_count": sum(len(record["gaps"]) for record in phase3_records),
            "moe_revised_exact_character_count": 1964,
            "moe_variants_canonical_character_count": TARGETED_COUNT,
            "unresolved_character_pronunciation_count": 0,
        }
    )
    for source_id, source in sources.items():
        manifest3["source_acquisitions"][source_id] = source["acquisition"]
    phase3_path.write_text(
        json.dumps(manifest3, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    phase4_path = root / "metadata" / "manifests" / "phase4.json"
    manifest4 = json.loads(phase4_path.read_text(encoding="utf-8"))
    manifest4.update(
        {
            "generated_at": utc_now(),
            "character_record_digest_sha256": phase3.deterministic_record_digest(
                [validate4.phase4_projection(record) for record in records]
            ),
            "phase3_base_record_digest_sha256": manifest3[
                "record_digest_sha256"
            ],
            "moe_revised_exact_character_count": 1964,
            "moe_variants_canonical_character_count": TARGETED_COUNT,
            "unresolved_character_pronunciation_count": 0,
        }
    )
    for source_id, source in sources.items():
        manifest4["source_acquisitions"][source_id] = source["acquisition"]
    phase4_path.write_text(
        json.dumps(manifest4, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    phase5_path = root / "metadata" / "manifests" / "phase5.json"
    manifest5 = json.loads(phase5_path.read_text(encoding="utf-8"))
    manifest5.update(
        {
            "generated_at": utc_now(),
            "character_record_digest_sha256": phase3.deterministic_record_digest(
                records
            ),
            "phase4_base_character_digest_sha256": manifest4[
                "character_record_digest_sha256"
            ],
        }
    )
    phase5_path.write_text(
        json.dumps(manifest5, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def manifests_stale(
    root: Path,
    records: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
) -> bool:
    manifest3 = json.loads(
        (root / "metadata" / "manifests" / "phase3.json").read_text(encoding="utf-8")
    )
    phase3_records = [phase4.phase3_projection(record) for record in records]
    expected3 = {
        "record_digest_sha256": phase3.deterministic_record_digest(phase3_records),
        "records_with_conflicts": sum(
            bool(record["conflicts"]) for record in phase3_records
        ),
        "conflict_count": sum(
            len(record["conflicts"]) for record in phase3_records
        ),
        "gap_count": sum(len(record["gaps"]) for record in phase3_records),
        "moe_revised_exact_character_count": 1964,
        "moe_variants_canonical_character_count": TARGETED_COUNT,
        "unresolved_character_pronunciation_count": 0,
    }
    if any(manifest3.get(key) != value for key, value in expected3.items()):
        return True
    if any(
        manifest3["source_acquisitions"].get(source_id)
        != source["acquisition"]
        for source_id, source in sources.items()
    ):
        return True

    manifest4 = json.loads(
        (root / "metadata" / "manifests" / "phase4.json").read_text(encoding="utf-8")
    )
    expected4 = {
        "character_record_digest_sha256": phase3.deterministic_record_digest(
            [validate4.phase4_projection(record) for record in records]
        ),
        "phase3_base_record_digest_sha256": expected3["record_digest_sha256"],
        "moe_revised_exact_character_count": 1964,
        "moe_variants_canonical_character_count": TARGETED_COUNT,
        "unresolved_character_pronunciation_count": 0,
    }
    if any(manifest4.get(key) != value for key, value in expected4.items()):
        return True
    if any(
        manifest4["source_acquisitions"].get(source_id)
        != source["acquisition"]
        for source_id, source in sources.items()
    ):
        return True

    manifest5 = json.loads(
        (root / "metadata" / "manifests" / "phase5.json").read_text(encoding="utf-8")
    )
    expected5 = {
        "character_record_digest_sha256": phase3.deterministic_record_digest(records),
        "phase4_base_character_digest_sha256": expected4[
            "character_record_digest_sha256"
        ],
    }
    return any(manifest5.get(key) != value for key, value in expected5.items())


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    revised = load_moe_rows(root / REVISED_XLSX)
    log = json.loads((root / VARIANTS_LOG).read_text(encoding="utf-8"))
    if (
        log.get("target_count") != TARGETED_COUNT
        or log.get("completed_count") != TARGETED_COUNT
        or log.get("gap_count") != 0
        or len(log.get("entries", [])) != TARGETED_COUNT
    ):
        raise RuntimeError("targeted MOE Variant Dictionary acquisition is incomplete")
    variants = {entry["codepoint"]: entry for entry in log["entries"]}
    if len(variants) != TARGETED_COUNT:
        raise RuntimeError("targeted MOE Variant Dictionary codepoints are not unique")

    records: list[dict[str, Any]] = []
    changed_records = 0
    revised_exact_count = 0
    for path in sorted((root / "characters").glob("U+*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        rows = revised.get(record["traditional"], [])
        if not rows:
            raise RuntimeError(f"Revised Dictionary has no {record['codepoint']}")
        variant = variants.get(record["codepoint"])
        if variant is None:
            updated = update_revised_record(record, rows)
            revised_exact_count += 1
        else:
            if variant["traditional"] != record["traditional"]:
                raise RuntimeError(
                    f"Variant Dictionary character mismatch: {record['codepoint']}"
                )
            updated = update_targeted_record(record, rows, variant)
        if updated != record:
            changed_records += 1
            if not args.check:
                path.write_text(
                    json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        records.append(updated)
    if revised_exact_count != 1964 or len(records) != 2000:
        raise RuntimeError(
            f"unexpected character split: {revised_exact_count}/" f"{len(variants)}"
        )
    # Phase 3-5 digests are defined over MOE selection-rank order, not filename
    # (codepoint) order.  Keep the post-integration manifests on that same grain.
    records.sort(key=lambda item: item["frequency"]["selection_rank"])

    new_sources = registry_sources(root, log)
    registry_path = root / "sources.json"
    current_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry = json.loads(json.dumps(current_registry, ensure_ascii=False))
    registry["sources"].update(new_sources)
    changed_registry = registry != current_registry
    changed_manifests = manifests_stale(root, records, new_sources)
    print(
        json.dumps(
            {
                "characters": len(records),
                "revised_exact": revised_exact_count,
                "variants_canonical": len(variants),
                "changed_records": changed_records,
                "changed_registry": changed_registry,
                "changed_manifests": changed_manifests,
                "mode": "check" if args.check else "write",
            }
        )
    )
    if args.check:
        if changed_records or changed_registry or changed_manifests:
            raise SystemExit(1)
        return
    if changed_registry:
        registry_path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if changed_manifests:
        update_manifests(root, records, new_sources)


if __name__ == "__main__":
    main()
