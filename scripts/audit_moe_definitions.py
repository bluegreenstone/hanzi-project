#!/usr/bin/env python3
"""Audit verbatim Taiwan-MOE definition coverage and exact reproduction."""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase3 as phase3  # noqa: E402
import build_phase4 as phase4  # noqa: E402


OUTPUT_PATH = ROOT / "metadata" / "audits" / "definition-taiwan-moe.json"


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
        help="Exit nonzero if the saved audit differs from a fresh audit.",
    )
    return parser.parse_args()


def load_records(root: Path, directory: str, sort_key: str) -> list[dict[str, Any]]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (root / directory).glob("*.json")
    ]
    if sort_key == "selection_rank":
        records.sort(key=lambda item: item["frequency"][sort_key])
    else:
        records.sort(key=lambda item: item["frequency"][sort_key])
    return records


def expected_definitions(
    rows: list[dict[str, str]], source_id: str
) -> list[dict[str, Any]]:
    return phase3.build_taiwan_definitions(rows, source_id)


def audit(root: Path) -> dict[str, Any]:
    registry_path = root / "sources.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    concised_path = phase3.acquired_path(registry, phase4.MOE_CONCISED_ID)
    revised_path = phase3.acquired_path(registry, phase4.MOE_REVISED_ID)
    concised = phase4.load_moe_rows(concised_path)
    revised = phase4.load_moe_rows(revised_path)
    characters = load_records(root, "characters", "selection_rank")
    words = load_records(root, "words", "rank")

    errors: list[str] = []
    character_source_counts: Counter[str] = Counter()
    word_source_counts: Counter[str] = Counter()
    character_definition_entries = 0
    word_definition_entries = 0
    verbatim_non_nfc_records: list[str] = []

    for record in characters:
        term = record["traditional"]
        rows = concised.get(term, [])
        expected = expected_definitions(rows, phase4.MOE_CONCISED_ID)
        if record.get("definitions_zh_TW") != expected:
            errors.append(f"{record['codepoint']}: definition payload differs")
        if record["sources"].get("definitions_zh_TW") != [
            phase4.MOE_CONCISED_ID
        ]:
            errors.append(f"{record['codepoint']}: definition source differs")
        if not expected:
            errors.append(f"{record['codepoint']}: no exact Concised definition")
        character_source_counts[phase4.MOE_CONCISED_ID] += bool(expected)
        character_definition_entries += len(expected)
        if any(
            not unicodedata.is_normalized("NFC", item["text"])
            for item in expected
        ):
            verbatim_non_nfc_records.append(record["codepoint"])

    for record in words:
        term = record["traditional"]
        concised_rows = concised.get(term, [])
        revised_rows = revised.get(term, [])
        rows = concised_rows or revised_rows
        source_id = (
            phase4.MOE_CONCISED_ID
            if concised_rows
            else phase4.MOE_REVISED_ID
        )
        expected = expected_definitions(rows, source_id) if rows else None
        if record.get("definitions_zh_TW") != expected:
            errors.append(f"{record['id']}: definition payload differs")
        if expected is not None:
            if record["sources"].get("definitions_zh_TW") != [source_id]:
                errors.append(f"{record['id']}: definition source differs")
            word_source_counts[source_id] += 1
            word_definition_entries += len(expected)
            if any(
                not unicodedata.is_normalized("NFC", item["text"])
                for item in expected
            ):
                verbatim_non_nfc_records.append(record["id"])
        else:
            word_source_counts["dual_source_gap"] += 1
            matching_gaps = [
                gap
                for gap in record["gaps"]
                if gap["field"] == "definitions_zh_TW"
                and gap["reason"] == "not_attested"
            ]
            if len(matching_gaps) != 1:
                errors.append(f"{record['id']}: exact dual-source gap differs")

    concised_source = registry["sources"][phase4.MOE_CONCISED_ID]
    revised_source = registry["sources"][phase4.MOE_REVISED_ID]
    covered_words = (
        word_source_counts[phase4.MOE_CONCISED_ID]
        + word_source_counts[phase4.MOE_REVISED_ID]
    )
    payload = {
        "schema_version": "1.0.0",
        "generated_at": phase3.utc_now(),
        "scope": (
            "All 2,000 character records and 13,368 word records; exact NFC "
            "Traditional-headword joins to the pinned Taiwan MOE Concised "
            "Dictionary first and Revised Dictionary second."
        ),
        "policy": {
            "copy_mode": "verbatim_decoded_xlsx_cell",
            "allowed_transform": (
                "Decode standards-defined OOXML _xHHHH_ character escapes; "
                "make no editorial, whitespace, Unicode-compatibility, sense, "
                "ordering, or wording changes to the resulting cell string."
            ),
            "entry_identity": "Retain the source workbook entry ID on every definition.",
            "no_match": (
                "Keep definitions_zh_TW null with an exact not_attested gap; "
                "never use script conversion, substring, or fuzzy matching."
            ),
        },
        "sources": [
            {
                "source_id": phase4.MOE_CONCISED_ID,
                "version": concised_source["version"],
                "workbook_sha256": concised_source["acquisition"]["sha256"],
                "workbook_bytes": concised_source["acquisition"]["expected_bytes"],
                "indexed_exact_headwords_with_readings": len(concised),
                "license_id": concised_source["license"]["id"],
            },
            {
                "source_id": phase4.MOE_REVISED_ID,
                "version": revised_source["version"],
                "workbook_sha256": revised_source["acquisition"]["sha256"],
                "workbook_bytes": revised_source["acquisition"]["expected_bytes"],
                "indexed_exact_headwords_with_readings": len(revised),
                "license_id": revised_source["license"]["id"],
            },
        ],
        "summary": {
            "character_record_count": len(characters),
            "character_exact_concised_count": character_source_counts[
                phase4.MOE_CONCISED_ID
            ],
            "character_definition_entry_count": character_definition_entries,
            "word_record_count": len(words),
            "word_exact_concised_count": word_source_counts[
                phase4.MOE_CONCISED_ID
            ],
            "word_exact_revised_additional_count": word_source_counts[
                phase4.MOE_REVISED_ID
            ],
            "word_exact_definition_covered_count": covered_words,
            "word_exact_definition_coverage_rate": round(
                covered_words / len(words), 6
            ),
            "word_dual_source_gap_count": word_source_counts["dual_source_gap"],
            "word_definition_entry_count": word_definition_entries,
            "verbatim_non_nfc_record_count": len(verbatim_non_nfc_records),
            "verbatim_non_nfc_records": verbatim_non_nfc_records,
            "verification_error_count": len(errors),
            "status": (
                "PASS_WITH_EXPLICIT_GAPS" if not errors else "FAIL"
            ),
        },
        "errors": errors,
    }
    return payload


def comparable(payload: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(payload, ensure_ascii=False))
    result.pop("generated_at", None)
    return result


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    payload = audit(root)
    output_path = root / OUTPUT_PATH.relative_to(ROOT)
    if args.check:
        if not output_path.is_file():
            raise SystemExit("definition audit is missing")
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if comparable(existing) != comparable(payload):
            raise SystemExit("definition audit differs from a fresh source comparison")
        if payload["errors"]:
            raise SystemExit(f"definition audit has {len(payload['errors'])} error(s)")
        print(
            "Taiwan MOE definition audit: PASS "
            f"({payload['summary']['word_exact_definition_covered_count']} words; "
            f"{payload['summary']['word_dual_source_gap_count']} explicit gaps)"
        )
        return

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {output_path.name}: {payload['summary']['status']}; "
        f"{payload['summary']['verification_error_count']} error(s)"
    )
    if payload["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
