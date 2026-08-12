#!/usr/bin/env python3
"""Add exact Taiwan-MOE Revised Dictionary evidence to uncovered words.

The Concised Dictionary remains the first lexical authority.  This pass only
touches exact NFC Traditional headwords that the Concised Dictionary does not
contain.  Exact Revised Dictionary Pinyin, Zhuyin, and entry IDs become
canonical; displaced CC-CEDICT/CNS values remain in explicit conflicts.  A
word absent from both official downloads keeps its earlier readings together
with an explicit two-source Taiwan-verification gap.
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
from integrate_moe_pronunciations import (  # noqa: E402
    DUAL_SOURCE_GAP_DETAIL,
    REVISED_ZHUYIN_FILL_IDS,
    TAIWAN_GAP_FIELDS,
    integrate_record,
    set_dual_source_gaps,
)
from moe_concised import load_moe_rows  # noqa: E402


CONCISED_XLSX = Path(
    "source-data/moe-concised-2014-20260626/"
    "dict_concised_2014_20260626.xlsx"
)
REVISED_XLSX = Path(
    "source-data/moe-revised-2015-20260625/"
    "dict_revised_2015_20260625.xlsx"
)
EXPECTED_COUNTS = {
    "word_record_count": 13_368,
    "concised_covered_count": 10_640,
    "revised_additional_covered_count": 1_251,
    "revised_additional_conflict_count": 81,
    "revised_additional_zhuyin_fill_count": 7,
    "dual_source_gap_count": 1_477,
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
        "--check",
        action="store_true",
        help="Exit nonzero if records, registry metadata, or manifest are stale.",
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


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def updated_revised_source(registry: dict[str, Any]) -> dict[str, Any]:
    source = json.loads(
        json.dumps(registry["sources"][phase4.MOE_REVISED_ID], ensure_ascii=False)
    )
    source["coverage"] = unique(
        [
            *source.get("coverage", []),
            (
                "1,251 exact Traditional word headwords absent from the "
                "Concised Dictionary"
            ),
            "word-headword Pinyin, Zhuyin, and dictionary entry IDs",
        ]
    )
    source["schema_fields"] = unique(
        [
            *source.get("schema_fields", []),
            "words.*.pinyin",
            "words.*.zhuyin",
            "words.*.conflicts",
        ]
    )
    source["constraints"] = unique(
        [
            *source.get("constraints", []),
            (
                "For word records, use only an exact NFC Traditional-headword "
                "match after confirming the Concised Dictionary has no entry."
            ),
            (
                "A headword absent from both official downloads remains an "
                "explicit verification gap rather than an inferred match."
            ),
        ]
    )
    return source


def manifest_updates(
    records: list[dict[str, Any]],
    revised_source: dict[str, Any],
) -> dict[str, Any]:
    concised_count = sum(
        record["sources"].get("pinyin") == [phase4.MOE_CONCISED_ID]
        and record["sources"].get("zhuyin") == [phase4.MOE_CONCISED_ID]
        for record in records
    )
    revised_count = sum(
        record["sources"].get("pinyin") == [phase4.MOE_REVISED_ID]
        and record["sources"].get("zhuyin") == [phase4.MOE_REVISED_ID]
        for record in records
    )
    revised_conflicts = sum(
        record["sources"].get("pinyin") == [phase4.MOE_REVISED_ID]
        and has_taiwan_conflict(record)
        for record in records
    )
    gap_count = sum(
        any(
            gap.get("field") == "pinyin.taiwan_verification"
            for gap in record["gaps"]
        )
        for record in records
    )
    return {
        "word_record_digest_sha256": phase3.deterministic_record_digest(records),
        "word_records_with_conflicts": sum(
            bool(record["conflicts"]) for record in records
        ),
        "moe_pronunciation_covered_count": concised_count,
        "moe_pronunciation_conflict_count": sum(
            has_taiwan_conflict(record) for record in records
        ),
        "taiwan_pronunciation_verification_gap_count": gap_count,
        "word_gap_count": sum(len(record["gaps"]) for record in records),
        "moe_revised_additional_word_covered_count": revised_count,
        "moe_revised_additional_conflict_count": revised_conflicts,
        "moe_revised_additional_zhuyin_fill_count": len(
            REVISED_ZHUYIN_FILL_IDS
        ),
        "taiwan_word_pronunciation_covered_count": concised_count + revised_count,
        "unresolved_word_pronunciation_count": gap_count,
        "source_acquisitions": {
            phase4.MOE_REVISED_ID: revised_source["acquisition"],
        },
    }


def assert_expected_counts(counts: dict[str, int]) -> None:
    differences = {
        key: (counts.get(key), value)
        for key, value in EXPECTED_COUNTS.items()
        if counts.get(key) != value
    }
    if differences:
        raise RuntimeError(f"unexpected Taiwan-MOE coverage split: {differences}")


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    concised = load_moe_rows(root / CONCISED_XLSX)
    revised = load_moe_rows(root / REVISED_XLSX)

    records: list[dict[str, Any]] = []
    changed_records = 0
    counts = {
        "word_record_count": 0,
        "concised_covered_count": 0,
        "revised_additional_covered_count": 0,
        "revised_additional_conflict_count": 0,
        "revised_additional_zhuyin_fill_count": 0,
        "dual_source_gap_count": 0,
    }
    for path in sorted((root / "words").glob("moe1996-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        counts["word_record_count"] += 1
        term = record["traditional"]
        if concised.get(term):
            counts["concised_covered_count"] += 1
            updated = record
        elif revised.get(term):
            counts["revised_additional_covered_count"] += 1
            updated = integrate_record(
                record,
                revised[term],
                source_id=phase4.MOE_REVISED_ID,
                source_label="Taiwan MOE Revised Dictionary",
            )
            counts["revised_additional_conflict_count"] += has_taiwan_conflict(
                updated
            )
            if record["id"] in REVISED_ZHUYIN_FILL_IDS:
                before_is_expected = (
                    record.get("zhuyin") is None
                    and record.get("pinyin")
                    and record["sources"].get("pinyin")
                    != [phase4.MOE_REVISED_ID]
                )
                after_is_expected = (
                    record["sources"].get("pinyin") == [phase4.MOE_REVISED_ID]
                    and record["sources"].get("zhuyin")
                    == [phase4.MOE_REVISED_ID]
                )
                if not before_is_expected and not after_is_expected:
                    raise RuntimeError(
                        f"unexpected Revised Zhuyin-fill state: {record['id']}"
                    )
                counts["revised_additional_zhuyin_fill_count"] += 1
        else:
            counts["dual_source_gap_count"] += 1
            updated = set_dual_source_gaps(record)
        if updated != record:
            changed_records += 1
            if not args.check:
                path.write_text(
                    json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        records.append(updated)
    assert_expected_counts(counts)

    registry_path = root / "sources.json"
    current_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry = json.loads(json.dumps(current_registry, ensure_ascii=False))
    revised_source = updated_revised_source(registry)
    registry["sources"][phase4.MOE_REVISED_ID] = revised_source
    changed_registry = registry != current_registry

    manifest_path = root / "metadata" / "manifests" / "phase4.json"
    current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = json.loads(json.dumps(current_manifest, ensure_ascii=False))
    updates = manifest_updates(records, revised_source)
    revised_acquisition = updates.pop("source_acquisitions")[phase4.MOE_REVISED_ID]
    changed_manifest = any(manifest.get(key) != value for key, value in updates.items())
    changed_manifest = changed_manifest or (
        manifest["source_acquisitions"].get(phase4.MOE_REVISED_ID)
        != revised_acquisition
    )
    if not args.check:
        if changed_registry:
            registry_path.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if changed_manifest:
            manifest.update(updates)
            manifest["source_acquisitions"][phase4.MOE_REVISED_ID] = (
                revised_acquisition
            )
            manifest["generated_at"] = utc_now()
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    result = {
        **counts,
        "taiwan_word_pronunciation_covered_count": (
            counts["concised_covered_count"]
            + counts["revised_additional_covered_count"]
        ),
        "changed_records": changed_records,
        "changed_registry": changed_registry,
        "changed_manifest": changed_manifest,
        "mode": "check" if args.check else "write",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.check and (changed_records or changed_registry or changed_manifest):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
