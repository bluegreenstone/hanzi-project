#!/usr/bin/env python3
"""Verify the Taiwan-MOE character-pronunciation integration end to end."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import build_phase3 as phase3
from integrate_moe_character_pronunciations import (
    LEGACY_READING_SOURCES,
    REVISED_ID,
    REVISED_XLSX,
    VARIANTS_ID,
    VARIANTS_LOG,
)
from moe_concised import load_moe_rows


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("metadata/audits/character-pronunciation-taiwan-moe.json"),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if verification fails or the report is stale.",
    )
    return parser.parse_args()


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def conflict_value(
    record: dict[str, Any], field: str, source_id: str
) -> list[str] | None:
    for conflict in record["conflicts"]:
        if (
            conflict.get("field") == field
            and conflict.get("resolution") == "taiwan_moe_canonical"
        ):
            for value in conflict["values"]:
                if source_id in value["source_ids"]:
                    return value["value"]
    return None


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    registry = phase3.load_registry()
    revised_path = phase3.acquired_path(registry, REVISED_ID)
    variants_path = phase3.acquired_path(registry, VARIANTS_ID)
    revised = load_moe_rows(revised_path)
    variants_log = json.loads(variants_path.read_text(encoding="utf-8"))
    if (
        variants_log.get("target_count") != 36
        or variants_log.get("completed_count") != 36
        or variants_log.get("gap_count") != 0
    ):
        raise RuntimeError("targeted Variant Dictionary acquisition is incomplete")
    variants = {
        entry["codepoint"]: entry for entry in variants_log["entries"]
    }
    errors: list[dict[str, Any]] = []
    revised_exact = 0
    variants_exact = 0
    retired_pinyin: list[dict[str, str]] = []
    added_pinyin: list[dict[str, str]] = []
    targeted_conflict_records = 0

    for path in sorted((root / "characters").glob("U+*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        codepoint = record["codepoint"]
        corpus_pinyin = [item["reading"] for item in record["readings"]["pinyin"]]
        corpus_zhuyin = list(record["readings"]["zhuyin"])
        variant = variants.get(codepoint)
        if variant is None:
            rows = revised.get(record["traditional"], [])
            expected_pinyin = unique([row["pinyin"] for row in rows])
            expected_zhuyin = unique([row["zhuyin"] for row in rows])
            if set(corpus_pinyin) != set(expected_pinyin) or set(corpus_zhuyin) != set(expected_zhuyin):
                errors.append(
                    {
                        "codepoint": codepoint,
                        "error": "revised_dictionary_value_mismatch",
                    }
                )
                continue
            for item in record["readings"]["pinyin"]:
                expected_ids = unique(
                    [
                        row["entry_id"]
                        for row in rows
                        if row["pinyin"] == item["reading"]
                    ]
                )
                if (
                    item.get("standard") != "TW-MOE-Revised-2015"
                    or item.get("source_entry_ids") != expected_ids
                ):
                    errors.append(
                        {
                            "codepoint": codepoint,
                            "error": "revised_dictionary_citation_mismatch",
                            "reading": item["reading"],
                        }
                    )
            if REVISED_ID not in record["sources"].get("readings.pinyin", []):
                errors.append(
                    {"codepoint": codepoint, "error": "revised_source_missing"}
                )
            revised_exact += 1
            continue

        if (
            set(corpus_pinyin) != set(variant["pinyin"])
            or set(corpus_zhuyin) != set(variant["zhuyin"])
        ):
            errors.append(
                {"codepoint": codepoint, "error": "variant_dictionary_value_mismatch"}
            )
            continue
        if any(
            item.get("standard") != "TW-MOE-Variants-2024"
            or item.get("source_entry_ids") != [variant["dictionary_serial"]]
            for item in record["readings"]["pinyin"]
        ):
            errors.append(
                {"codepoint": codepoint, "error": "variant_dictionary_citation_mismatch"}
            )
        if record["sources"].get("readings.pinyin") != [VARIANTS_ID]:
            errors.append(
                {"codepoint": codepoint, "error": "variant_source_mismatch"}
            )
        legacy = next(
            (
                conflict_value(record, "readings.pinyin", source_id)
                for source_id in LEGACY_READING_SOURCES
                if conflict_value(record, "readings.pinyin", source_id) is not None
            ),
            None,
        )
        if legacy is None:
            errors.append(
                {"codepoint": codepoint, "error": "legacy_conflict_evidence_missing"}
            )
        else:
            targeted_conflict_records += 1
            for reading in sorted(set(legacy) - set(variant["pinyin"])):
                retired_pinyin.append(
                    {
                        "codepoint": codepoint,
                        "traditional": record["traditional"],
                        "reading": reading,
                    }
                )
            for reading in sorted(set(variant["pinyin"]) - set(legacy)):
                added_pinyin.append(
                    {
                        "codepoint": codepoint,
                        "traditional": record["traditional"],
                        "reading": reading,
                    }
                )
        variants_exact += 1

    summary = {
        "character_count": revised_exact + variants_exact,
        "revised_dictionary_exact_count": revised_exact,
        "variant_dictionary_exact_count": variants_exact,
        "targeted_conflict_record_count": targeted_conflict_records,
        "retired_unverified_pinyin_count": len(retired_pinyin),
        "added_official_pinyin_count": len(added_pinyin),
        "unresolved_count": len(errors),
    }
    report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "scope": (
            "All 2,000 character Pinyin/Zhuyin records, using the downloadable "
            "Taiwan MOE Revised Dictionary first and exact-codepoint MOE "
            "Dictionary of Variants entries for the 36 lexical discrepancies."
        ),
        "precedence": (
            "For a character record, exact-codepoint 正字 readings from the "
            "Dictionary of Variants take precedence over the Revised Dictionary's "
            "lexical headword inventory. Conflicting evidence is preserved."
        ),
        "summary": summary,
        "retired_unverified_pinyin": retired_pinyin,
        "added_official_pinyin": added_pinyin,
        "errors": errors,
    }
    comparable = json.loads(json.dumps(report, ensure_ascii=False))
    comparable.pop("generated_at", None)
    stale = True
    if output.is_file():
        current = json.loads(output.read_text(encoding="utf-8"))
        current.pop("generated_at", None)
        stale = current != comparable
    if not args.check:
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {**summary, "report_stale": stale, "mode": "check" if args.check else "write"},
            ensure_ascii=False,
        )
    )
    if errors or (args.check and stale):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
