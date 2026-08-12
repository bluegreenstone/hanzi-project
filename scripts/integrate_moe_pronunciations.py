#!/usr/bin/env python3
"""Make exact Taiwan-MOE word pronunciations canonical in corpus records.

The MOE Concised Dictionary is joined only by an exact NFC Traditional
headword. MOE Pinyin and Zhuyin strings are copied verbatim (apart from the
reader's documented NFC/whitespace normalization) with their source entry IDs.
When existing CC-CEDICT/CNS readings disagree, those readings are retained as
explicit comparison evidence rather than silently discarded.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from moe_concised import load_moe_rows


MOE_SOURCE_ID = "moe-tw-concised-dictionary-2014-20260626"
MOE_REVISED_SOURCE_ID = "moe-tw-revised-dictionary-2015-20260625"
CC_CEDICT_SOURCE_ID = "cc-cedict-editor-2026-08-11"
CNS_SOURCE_ID = "cns11643-attributes-2026-08-05"
TAIWAN_GAP_FIELDS = {
    "pinyin.taiwan_verification",
    "zhuyin.taiwan_verification",
}
DUAL_SOURCE_GAP_DETAIL = (
    "The exact NFC Traditional headword is absent from both pinned Taiwan MOE "
    "downloads: the Concised Mandarin Dictionary (2014_20260626) and the "
    "Revised Mandarin Dictionary (2015_20260625). Existing CC-CEDICT/CNS "
    "pronunciation data is provisional until another Taiwanese lexical "
    "authority or a documented manual review confirms the word reading; "
    "dictionary absence is not evidence that the reading is invalid."
)
REVISED_ZHUYIN_FILL_IDS = {
    "moe1996-02681",  # 有時候
    "moe1996-03331",  # 謝謝
    "moe1996-05852",  # 山藥
    "moe1996-13698",  # 少不了
    "moe1996-14899",  # 指甲油
    "moe1996-17358",  # 不含糊
    "moe1996-19017",  # 豆腐皮
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--moe-xlsx",
        type=Path,
        required=True,
        help="Path to the pinned official MOE Concised Dictionary workbook.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Corpus repository root (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if applying the integration would change any record.",
    )
    return parser.parse_args()


def source_refs(item: dict[str, Any]) -> tuple[str, list[Any]]:
    if "source_entry_ids" in item:
        return "source_entry_ids", item["source_entry_ids"]
    return "source_entry_indices", item["source_entry_indices"]


def corpus_pinyin_values(record: dict[str, Any]) -> list[str]:
    return sorted({item["reading"] for item in record.get("pinyin") or []})


def corpus_zhuyin_values(record: dict[str, Any]) -> list[dict[str, str]]:
    return sorted(
        (
            {"pinyin": item["pinyin"], "reading": item["reading"]}
            for item in record.get("zhuyin") or []
        ),
        key=lambda item: (item["pinyin"], item["reading"]),
    )


def collect_refs(items: Iterable[dict[str, Any]]) -> tuple[str, list[Any]]:
    reference_types: dict[str, list[Any]] = defaultdict(list)
    for item in items:
        name, values = source_refs(item)
        reference_types[name].extend(values)
    if len(reference_types) != 1:
        raise ValueError(
            "comparison readings must use one source-entry reference type"
        )
    name = next(iter(reference_types))
    return name, sorted(set(reference_types[name]))


def moe_readings(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pinyin_ids: dict[str, list[str]] = defaultdict(list)
    pair_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        pinyin_ids[row["pinyin"]].append(row["entry_id"])
        pair_ids[(row["pinyin"], row["zhuyin"])].append(row["entry_id"])
    pinyin = [
        {
            "reading": reading,
            "context": "dictionary_entry",
            "source_entry_ids": sorted(set(entry_ids)),
        }
        for reading, entry_ids in sorted(pinyin_ids.items())
    ]
    zhuyin = [
        {
            "reading": reading,
            "pinyin": pinyin_value,
            "source_entry_ids": sorted(set(entry_ids)),
        }
        for (pinyin_value, reading), entry_ids in sorted(pair_ids.items())
    ]
    return pinyin, zhuyin


def conflict_value(
    value: Any,
    source_ids: list[str],
    reference_name: str,
    references: list[Any],
) -> dict[str, Any]:
    return {
        "value": value,
        "source_ids": source_ids,
        reference_name: references,
    }


def conflict_detail(field: str, source_label: str) -> str:
    if field == "pinyin":
        return (
            f"The exact {source_label} headword reading is canonical for this "
            "Traditional-first corpus. The differing CC-CEDICT reading set is "
            "retained as regional or lexical comparison evidence."
        )
    return (
        f"The {source_label} Zhuyin is canonical. The previous value was "
        "mechanically converted from CC-CEDICT Pinyin through the CNS syllable "
        "table and remains comparison evidence."
    )


def add_taiwan_gap(record: dict[str, Any], field: str) -> None:
    if any(item.get("field") == field for item in record["gaps"]):
        return
    record["gaps"].append(
        {
            "field": field,
            "reason": "not_attested",
            "detail": (
                "The exact Traditional headword is absent from the pinned Taiwan "
                "MOE Concised Dictionary. Existing CC-CEDICT/CNS pronunciation "
                "data is provisional until another Taiwanese lexical authority "
                "confirms the word reading; dictionary absence is not evidence "
                "that the reading is invalid."
            ),
        }
    )


def set_dual_source_gaps(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with exact gaps for absence from both MOE downloads."""
    result = json.loads(json.dumps(record, ensure_ascii=False))
    result["gaps"] = [
        item for item in result["gaps"] if item.get("field") not in TAIWAN_GAP_FIELDS
    ]
    for field in sorted(TAIWAN_GAP_FIELDS):
        result["gaps"].append(
            {
                "field": field,
                "reason": "not_attested",
                "detail": DUAL_SOURCE_GAP_DETAIL,
            }
        )
    result["gaps"].sort(key=lambda item: (item["field"], item["reason"]))
    return result


def integrate_record(
    record: dict[str, Any],
    rows: list[dict[str, str]],
    source_id: str = MOE_SOURCE_ID,
    source_label: str = "Taiwan MOE Concised Dictionary",
) -> dict[str, Any]:
    """Return a pronunciation-integrated copy of one word record."""
    result = json.loads(json.dumps(record, ensure_ascii=False))
    existing_pronunciation_conflicts = {
        item["field"]: item
        for item in result["conflicts"]
        if item.get("field") in {"pinyin", "zhuyin"}
        and item.get("resolution") == "taiwan_moe_canonical"
    }
    result["gaps"] = [
        item
        for item in result["gaps"]
        if item.get("field") not in TAIWAN_GAP_FIELDS
    ]
    result["conflicts"] = [
        item
        for item in result["conflicts"]
        if not (
            item.get("field") in {"pinyin", "zhuyin"}
            and item.get("resolution") == "taiwan_moe_canonical"
        )
    ]

    if not rows:
        add_taiwan_gap(result, "pinyin.taiwan_verification")
        add_taiwan_gap(result, "zhuyin.taiwan_verification")
        result["gaps"].sort(key=lambda item: (item["field"], item["reason"]))
        return result

    old_pinyin_rows = result.get("pinyin") or []
    old_zhuyin_rows = result.get("zhuyin") or []
    old_pinyin = corpus_pinyin_values(result)
    old_zhuyin = corpus_zhuyin_values(result)
    pinyin, zhuyin = moe_readings(rows)
    new_pinyin = corpus_pinyin_values({"pinyin": pinyin})
    new_zhuyin = corpus_zhuyin_values({"zhuyin": zhuyin})

    result["pinyin"] = pinyin
    result["zhuyin"] = zhuyin
    result["sources"]["pinyin"] = [source_id]
    result["sources"]["zhuyin"] = [source_id]
    result["gaps"] = [
        item
        for item in result["gaps"]
        if item.get("field")
        not in {"pinyin", "pinyin.partial", "zhuyin", "zhuyin.partial"}
    ]

    if old_pinyin and old_pinyin != new_pinyin:
        old_ref_name, old_refs = collect_refs(old_pinyin_rows)
        new_ref_name, new_refs = collect_refs(pinyin)
        result["conflicts"].append(
            {
                "field": "pinyin",
                "resolution": "taiwan_moe_canonical",
                "values": [
                    conflict_value(
                        new_pinyin, [source_id], new_ref_name, new_refs
                    ),
                    conflict_value(
                        old_pinyin,
                        [CC_CEDICT_SOURCE_ID],
                        old_ref_name,
                        old_refs,
                    ),
                ],
                "detail": conflict_detail("pinyin", source_label),
            }
        )
    elif "pinyin" in existing_pronunciation_conflicts:
        conflict = json.loads(
            json.dumps(
                existing_pronunciation_conflicts["pinyin"], ensure_ascii=False
            )
        )
        conflict["detail"] = conflict_detail("pinyin", source_label)
        result["conflicts"].append(conflict)
    if old_zhuyin and old_zhuyin != new_zhuyin:
        old_ref_name, old_refs = collect_refs(old_zhuyin_rows)
        new_ref_name, new_refs = collect_refs(zhuyin)
        result["conflicts"].append(
            {
                "field": "zhuyin",
                "resolution": "taiwan_moe_canonical",
                "values": [
                    conflict_value(
                        new_zhuyin, [source_id], new_ref_name, new_refs
                    ),
                    conflict_value(
                        old_zhuyin,
                        [CC_CEDICT_SOURCE_ID, CNS_SOURCE_ID],
                        old_ref_name,
                        old_refs,
                    ),
                ],
                "detail": conflict_detail("zhuyin", source_label),
            }
        )
    elif "zhuyin" in existing_pronunciation_conflicts:
        conflict = json.loads(
            json.dumps(
                existing_pronunciation_conflicts["zhuyin"], ensure_ascii=False
            )
        )
        conflict["detail"] = conflict_detail("zhuyin", source_label)
        result["conflicts"].append(conflict)
    result["conflicts"].sort(
        key=lambda item: (item["field"], item["resolution"], item["detail"])
    )
    result["gaps"].sort(key=lambda item: (item["field"], item["reason"]))
    return result


def integrate_prioritized_record(
    record: dict[str, Any],
    concised_rows: list[dict[str, str]],
    revised_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Apply the exact-headword Concised-then-Revised Taiwan policy."""
    if concised_rows:
        return integrate_record(record, concised_rows)
    if revised_rows:
        return integrate_record(
            record,
            revised_rows,
            source_id=MOE_REVISED_SOURCE_ID,
            source_label="Taiwan MOE Revised Dictionary",
        )
    return set_dual_source_gaps(integrate_record(record, []))


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    source = load_moe_rows(args.moe_xlsx.resolve())
    changed = 0
    covered = 0
    for path in sorted((root / "words").glob("moe1996-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        rows = source.get(record["traditional"], [])
        covered += bool(rows)
        has_revised_layer = (
            not rows
            and record.get("sources", {}).get("pinyin")
            == [MOE_REVISED_SOURCE_ID]
            and record.get("sources", {}).get("zhuyin")
            == [MOE_REVISED_SOURCE_ID]
        )
        has_dual_source_gap = not rows and any(
            gap.get("field") in TAIWAN_GAP_FIELDS
            and "absent from both pinned Taiwan MOE downloads"
            in gap.get("detail", "")
            for gap in record.get("gaps", [])
        )
        # A later Taiwan-MOE layer is intentionally authoritative for records
        # outside this source.  Preserve it so rerunning the first-stage check
        # cannot erase Revised Dictionary conflicts or two-source gap evidence.
        updated = (
            record
            if has_revised_layer or has_dual_source_gap
            else integrate_record(record, rows)
        )
        payload = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
        if payload == path.read_text(encoding="utf-8"):
            continue
        changed += 1
        if not args.check:
            path.write_text(payload, encoding="utf-8")
    print(
        json.dumps(
            {
                "records": 13_368,
                "moe_covered": covered,
                "changed": changed,
                "mode": "check" if args.check else "write",
            }
        )
    )
    if args.check and changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
