#!/usr/bin/env python3
"""Verify every word against the two pinned Taiwan-MOE dictionaries.

The audit uses exact NFC Traditional headwords.  Concised Dictionary evidence
has first priority; the Revised Dictionary is consulted only when the first
source has no entry.  Words absent from both remain an explicit unresolved
queue and are never treated as verified merely because an older source has a
plausible reading.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase3 as phase3  # noqa: E402
import build_phase4 as phase4  # noqa: E402
import integrate_moe_revised_word_pronunciations as revised_words  # noqa: E402
from moe_concised import load_moe_rows  # noqa: E402


OUTPUT = Path("metadata/audits/word-pronunciation-taiwan-moe.json")
EXPECTED = {
    "word_record_count": 13_368,
    "concised_exact_count": 10_640,
    "revised_additional_exact_count": 1_251,
    "dual_source_unresolved_count": 1_477,
    "concised_conflict_record_count": 814,
    "revised_conflict_record_count": 81,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Corpus repository root (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Report path, relative to the corpus root by default.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if verification fails or the report is stale.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def has_taiwan_conflict(record: dict[str, Any]) -> bool:
    return any(
        item.get("resolution") == "taiwan_moe_canonical"
        for item in record["conflicts"]
    )


def expected_conflict_values(
    pinyin: list[dict[str, Any]], zhuyin: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "pinyin": phase4.moe_pronunciations.corpus_pinyin_values(
            {"pinyin": pinyin}
        ),
        "zhuyin": phase4.moe_pronunciations.corpus_zhuyin_values(
            {"zhuyin": zhuyin}
        ),
    }


def validate_official_record(
    record: dict[str, Any],
    rows: list[dict[str, str]],
    source_id: str,
) -> list[str]:
    errors: list[str] = []
    expected_pinyin, expected_zhuyin = phase4.moe_pronunciations.moe_readings(rows)
    if record.get("pinyin") != expected_pinyin:
        errors.append("Pinyin or exact source entry IDs differ")
    if record.get("zhuyin") != expected_zhuyin:
        errors.append("Zhuyin/Pinyin pairs or exact source entry IDs differ")
    if record["sources"].get("pinyin") != [source_id]:
        errors.append("Pinyin provenance is not the selected official source")
    if record["sources"].get("zhuyin") != [source_id]:
        errors.append("Zhuyin provenance is not the selected official source")
    official_gap_fields = {
        gap["field"]
        for gap in record["gaps"]
        if gap.get("field") in phase4.moe_pronunciations.TAIWAN_GAP_FIELDS
    }
    if official_gap_fields:
        errors.append(
            "officially covered record retains Taiwan-verification gaps: "
            + ", ".join(sorted(official_gap_fields))
        )

    expected_values = expected_conflict_values(expected_pinyin, expected_zhuyin)
    for conflict in record["conflicts"]:
        if conflict.get("resolution") != "taiwan_moe_canonical":
            continue
        field = conflict.get("field")
        if field not in expected_values:
            errors.append(f"unexpected Taiwan-MOE conflict field {field!r}")
            continue
        official_values = [
            value
            for value in conflict["values"]
            if source_id in value.get("source_ids", [])
        ]
        if len(official_values) != 1:
            errors.append(f"{field} conflict lacks one official value")
        elif official_values[0].get("value") != expected_values[field]:
            errors.append(f"{field} conflict official value differs")
    return errors


def build_report(root: Path) -> dict[str, Any]:
    registry = phase3.load_registry()
    concised_path = phase3.acquired_path(registry, phase4.MOE_CONCISED_ID)
    revised_path = phase3.acquired_path(registry, phase4.MOE_REVISED_ID)
    concised = load_moe_rows(concised_path)
    revised = load_moe_rows(revised_path)

    counts = {
        "word_record_count": 0,
        "concised_exact_count": 0,
        "revised_additional_exact_count": 0,
        "dual_source_unresolved_count": 0,
        "concised_conflict_record_count": 0,
        "revised_conflict_record_count": 0,
        "revised_zhuyin_fill_count": 0,
    }
    errors: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    revised_fills: list[dict[str, Any]] = []

    for path in sorted((root / "words").glob("moe1996-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        counts["word_record_count"] += 1
        term = record["traditional"]
        source_id: str | None = None
        rows: list[dict[str, str]] = []
        count_key: str | None = None
        conflict_key: str | None = None
        if concised.get(term):
            source_id = phase4.MOE_CONCISED_ID
            rows = concised[term]
            count_key = "concised_exact_count"
            conflict_key = "concised_conflict_record_count"
        elif revised.get(term):
            source_id = phase4.MOE_REVISED_ID
            rows = revised[term]
            count_key = "revised_additional_exact_count"
            conflict_key = "revised_conflict_record_count"
        else:
            counts["dual_source_unresolved_count"] += 1
            gap_by_field = {
                gap["field"]: gap
                for gap in record["gaps"]
                if gap.get("field")
                in phase4.moe_pronunciations.TAIWAN_GAP_FIELDS
            }
            record_errors: list[str] = []
            for field in sorted(phase4.moe_pronunciations.TAIWAN_GAP_FIELDS):
                gap = gap_by_field.get(field)
                if gap is None:
                    record_errors.append(f"missing {field} gap")
                elif (
                    gap.get("reason") != "not_attested"
                    or gap.get("detail") != revised_words.DUAL_SOURCE_GAP_DETAIL
                ):
                    record_errors.append(f"noncanonical {field} gap evidence")
            if has_taiwan_conflict(record):
                record_errors.append("uncovered record has a canonical MOE conflict")
            unresolved.append(
                {
                    "id": record["id"],
                    "traditional": term,
                    "frequency_rank": record["frequency"]["rank"],
                    "current_pinyin": [
                        item["reading"] for item in record.get("pinyin") or []
                    ],
                    "status": "requires_another_taiwan_authority_or_manual_review",
                }
            )
            if record_errors:
                errors.append(
                    {
                        "id": record["id"],
                        "traditional": term,
                        "errors": record_errors,
                    }
                )
            continue

        record_errors = validate_official_record(record, rows, source_id)
        if record_errors:
            errors.append(
                {
                    "id": record["id"],
                    "traditional": term,
                    "errors": record_errors,
                }
            )
        else:
            counts[count_key] += 1
        if has_taiwan_conflict(record):
            counts[conflict_key] += 1
        if record["id"] in revised_words.REVISED_ZHUYIN_FILL_IDS:
            if source_id != phase4.MOE_REVISED_ID:
                errors.append(
                    {
                        "id": record["id"],
                        "traditional": term,
                        "errors": ["declared Revised Zhuyin fill uses another source"],
                    }
                )
            counts["revised_zhuyin_fill_count"] += 1
            revised_fills.append(
                {
                    "id": record["id"],
                    "traditional": term,
                    "official_pinyin": [
                        item["reading"] for item in record.get("pinyin") or []
                    ],
                    "official_zhuyin": [
                        item["reading"] for item in record.get("zhuyin") or []
                    ],
                    "baseline_issue": (
                        "Pinyin already agreed; prior CNS conversion supplied no "
                        "word-level Zhuyin."
                    ),
                }
            )

    for key, expected in EXPECTED.items():
        if counts[key] != expected:
            errors.append(
                {
                    "id": "<corpus>",
                    "errors": [f"{key} is {counts[key]}, expected {expected}"],
                }
            )
    if counts["revised_zhuyin_fill_count"] != len(
        revised_words.REVISED_ZHUYIN_FILL_IDS
    ):
        errors.append(
            {
                "id": "<corpus>",
                "errors": ["Revised Zhuyin fill exception set is incomplete"],
            }
        )

    covered = counts["concised_exact_count"] + counts[
        "revised_additional_exact_count"
    ]
    total = counts["word_record_count"]
    unresolved_count = counts["dual_source_unresolved_count"]
    source_summaries = []
    for source_id, path, indexed_terms, priority in (
        (phase4.MOE_CONCISED_ID, concised_path, len(concised), 1),
        (phase4.MOE_REVISED_ID, revised_path, len(revised), 2),
    ):
        source = registry["sources"][source_id]
        source_summaries.append(
            {
                "priority": priority,
                "source_id": source_id,
                "full_name": source["full_name"],
                "version": source["version"],
                "url": source["url"],
                "license_id": source["license"]["id"],
                "workbook_path": str(path.relative_to(root)),
                "workbook_sha256": phase3.sha256_path(path),
                "workbook_bytes": path.stat().st_size,
                "indexed_exact_headwords": indexed_terms,
            }
        )

    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now(),
        "dataset": {
            "name": "Traditional-first common-word corpus pronunciations",
            "grain": "one record per selected MOE-1996 frequency-row ID",
            "record_count": total,
            "intended_use": (
                "Taiwan-oriented word-level Pinyin and Zhuyin with exact, "
                "inspectable source provenance"
            ),
        },
        "method": {
            "join": "exact NFC Traditional headword only",
            "priority": [phase4.MOE_CONCISED_ID, phase4.MOE_REVISED_ID],
            "no_match_policy": (
                "Retain earlier readings as provisional and record two explicit "
                "Taiwan-verification gaps; never infer a fuzzy or converted match."
            ),
            "checks": [
                "source workbook SHA-256 and byte length",
                "Pinyin/Zhuyin values",
                "per-reading dictionary entry IDs",
                "source-map identity",
                "official conflict-value preservation",
                "dual-source gap completeness",
            ],
        },
        "sources": source_summaries,
        "summary": {
            **counts,
            "officially_verified_count": covered,
            "officially_verified_rate": round(covered / total, 6),
            "dual_source_unresolved_rate": round(unresolved_count / total, 6),
            "official_conflict_record_count": (
                counts["concised_conflict_record_count"]
                + counts["revised_conflict_record_count"]
            ),
            "verification_error_count": len(errors),
            "status": "PASS_WITH_EXPLICIT_GAPS" if not errors else "FAIL",
        },
        "findings": [
            {
                "severity": "high",
                "confidence": "high",
                "finding": (
                    f"{covered:,} of {total:,} word records ({covered / total:.2%}) "
                    "reproduce an exact prioritized Taiwan-MOE entry."
                ),
                "impact": (
                    "These records are safe to use as Taiwan-oriented lexical "
                    "pronunciation data under the stated exact-headword policy."
                ),
            },
            {
                "severity": "high",
                "confidence": "high",
                "finding": (
                    f"{unresolved_count:,} records ({unresolved_count / total:.2%}) "
                    "are absent from both pinned official downloads."
                ),
                "impact": (
                    "Their current CC-CEDICT/CNS readings must not be represented "
                    "as Taiwan-MOE-verified."
                ),
                "remediation": (
                    "Cross-check the queue against another Taiwanese lexical "
                    "authority or perform documented entry-level review."
                ),
            },
        ],
        "revised_zhuyin_fills": revised_fills,
        "unresolved_records": unresolved,
        "verification_errors": errors,
        "reproducible_with": "scripts/audit_moe_word_pronunciations.py",
    }


def comparable(report: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(report, ensure_ascii=False))
    result.pop("generated_at", None)
    return result


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output
    if not output.is_absolute():
        output = root / output
    report = build_report(root)
    stale = True
    if output.is_file():
        current = json.loads(output.read_text(encoding="utf-8"))
        stale = comparable(current) != comparable(report)
    if not args.check:
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                **report["summary"],
                "report_stale": stale,
                "mode": "check" if args.check else "write",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if report["verification_errors"] or (args.check and stale):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
