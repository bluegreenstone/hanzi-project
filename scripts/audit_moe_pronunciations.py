#!/usr/bin/env python3
"""Compare corpus pronunciations with a pinned Taiwan MOE dictionary.

The MOE workbook is used as verification evidence. This script does not copy
definitions or mutate corpus records. A mismatch is a review queue item, not an
automatic claim that either source is wrong: the Concised Dictionary may omit
rare or historical readings, while the Revised Dictionary may expose lexical
homographs that do not belong in a character-level inventory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from moe_concised import load_moe_rows, normalize


MOE_LICENSE = "CC-BY-ND-3.0-TW"
PROFILES = {
    "concised": {
        "source_id": "moe-tw-concised-dictionary-2014-20260626",
        "full_name": "Taiwan MOE Concised Mandarin Dictionary",
        "version": "2014_20260626",
        "download_url": (
            "https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/"
            "respub/download/dict_concised_2014_20260626.zip"
        ),
    },
    "revised": {
        "source_id": "moe-tw-revised-dictionary-2015-20260625",
        "full_name": "Taiwan MOE Revised Mandarin Dictionary",
        "version": "2015_20260625",
        "download_url": (
            "https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/"
            "respub/download/dict_revised_2015_20260625.zip"
        ),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--moe-xlsx",
        type=Path,
        required=True,
        help="Path to a supported official MOE dictionary workbook.",
    )
    parser.add_argument(
        "--profile",
        choices=["auto", *PROFILES],
        default="auto",
        help="Dictionary metadata profile; auto infers it from the filename.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Corpus repository root (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the complete JSON report here; stdout is used if omitted.",
    )
    return parser.parse_args()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def corpus_character_pairs(record: dict[str, Any]) -> tuple[set[str], set[str]]:
    readings = record.get("readings", {})
    pinyin = {
        normalize(item.get("reading"))
        for item in readings.get("pinyin", [])
        if normalize(item.get("reading"))
    }
    zhuyin = {
        normalize(item)
        for item in readings.get("zhuyin", [])
        if normalize(item)
    }
    return pinyin, zhuyin


def corpus_word_pairs(record: dict[str, Any]) -> set[tuple[str, str]]:
    zhuyin_by_pinyin: dict[str, set[str]] = defaultdict(set)
    for item in record.get("zhuyin") or []:
        pinyin = normalize(item.get("pinyin"))
        zhuyin = normalize(item.get("reading"))
        if pinyin and zhuyin:
            zhuyin_by_pinyin[pinyin].add(zhuyin)

    result: set[tuple[str, str]] = set()
    for item in record.get("pinyin") or []:
        pinyin = normalize(item.get("reading"))
        if not pinyin:
            continue
        matches = zhuyin_by_pinyin.get(pinyin)
        if matches:
            result.update((pinyin, value) for value in matches)
        else:
            result.add((pinyin, ""))
    return result


def moe_pairs(rows: Iterable[dict[str, str]]) -> set[tuple[str, str]]:
    return {(row["pinyin"], row["zhuyin"]) for row in rows}


def mismatch_classification(extra: set[Any], missing: set[Any]) -> str:
    if extra and missing:
        return "corpus_and_moe_disagree"
    if extra:
        return "corpus_has_additional_reading"
    return "corpus_missing_moe_reading"


def audit_characters(
    root: Path, source: dict[str, list[dict[str, str]]]
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    summary = {
        "total_records": 0,
        "moe_covered": 0,
        "exact_matches": 0,
        "review_required": 0,
        "not_in_source": 0,
    }
    reviews: list[dict[str, Any]] = []
    for path in sorted((root / "characters").glob("U+*.json")):
        record = read_json(path)
        summary["total_records"] += 1
        term = record["traditional"]
        rows = source.get(term)
        if not rows:
            summary["not_in_source"] += 1
            continue
        summary["moe_covered"] += 1
        corpus_pinyin, corpus_zhuyin = corpus_character_pairs(record)
        pairs = moe_pairs(rows)
        source_pinyin = {pair[0] for pair in pairs}
        source_zhuyin = {pair[1] for pair in pairs}
        extra_pinyin = corpus_pinyin - source_pinyin
        missing_pinyin = source_pinyin - corpus_pinyin
        extra_zhuyin = corpus_zhuyin - source_zhuyin
        missing_zhuyin = source_zhuyin - corpus_zhuyin
        if not (extra_pinyin or missing_pinyin or extra_zhuyin or missing_zhuyin):
            summary["exact_matches"] += 1
            continue
        summary["review_required"] += 1
        reviews.append(
            {
                "record": str(path.relative_to(root)),
                "codepoint": record["codepoint"],
                "traditional": term,
                "frequency_rank": record.get("frequency", {}).get("rank"),
                "classification": mismatch_classification(
                    extra_pinyin | extra_zhuyin, missing_pinyin | missing_zhuyin
                ),
                "corpus": {
                    "pinyin": sorted(corpus_pinyin),
                    "zhuyin": sorted(corpus_zhuyin),
                },
                "moe": {
                    "entry_ids": sorted({row["entry_id"] for row in rows}),
                    "pinyin": sorted(source_pinyin),
                    "zhuyin": sorted(source_zhuyin),
                },
                "differences": {
                    "corpus_only_pinyin": sorted(extra_pinyin),
                    "moe_only_pinyin": sorted(missing_pinyin),
                    "corpus_only_zhuyin": sorted(extra_zhuyin),
                    "moe_only_zhuyin": sorted(missing_zhuyin),
                },
            }
        )
    reviews.sort(key=lambda item: (item["frequency_rank"] or 10**9, item["codepoint"]))
    return summary, reviews


def audit_words(
    root: Path, source: dict[str, list[dict[str, str]]]
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    summary = {
        "total_records": 0,
        "moe_covered": 0,
        "exact_matches": 0,
        "review_required": 0,
        "single_pair_multichar_replacement_candidates": 0,
        "manual_lexical_review": 0,
        "not_in_source": 0,
    }
    reviews: list[dict[str, Any]] = []
    for path in sorted((root / "words").glob("moe1996-*.json")):
        record = read_json(path)
        summary["total_records"] += 1
        term = record["traditional"]
        rows = source.get(term)
        if not rows:
            summary["not_in_source"] += 1
            continue
        summary["moe_covered"] += 1
        corpus = corpus_word_pairs(record)
        official = moe_pairs(rows)
        extra = corpus - official
        missing = official - corpus
        if not extra and not missing:
            summary["exact_matches"] += 1
            continue
        summary["review_required"] += 1
        if len(term) > 1 and len(corpus) == 1 and len(official) == 1:
            action = "replace_with_moe_after_entry_review"
            summary["single_pair_multichar_replacement_candidates"] += 1
        else:
            action = "manual_lexical_review"
            summary["manual_lexical_review"] += 1
        reviews.append(
            {
                "record": str(path.relative_to(root)),
                "id": record["id"],
                "traditional": term,
                "frequency_rank": record.get("frequency", {}).get("rank"),
                "classification": mismatch_classification(extra, missing),
                "recommended_action": action,
                "corpus_pairs": [list(pair) for pair in sorted(corpus)],
                "moe_pairs": [list(pair) for pair in sorted(official)],
                "moe_entry_ids": sorted({row["entry_id"] for row in rows}),
                "corpus_only_pairs": [list(pair) for pair in sorted(extra)],
                "moe_only_pairs": [list(pair) for pair in sorted(missing)],
            }
        )
    reviews.sort(key=lambda item: (item["frequency_rank"] or 10**9, item["id"]))
    return summary, reviews


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    workbook = args.moe_xlsx.resolve()
    profile_name = args.profile
    if profile_name == "auto":
        if "dict_revised_" in workbook.name:
            profile_name = "revised"
        elif "dict_concised_" in workbook.name:
            profile_name = "concised"
        else:
            raise RuntimeError(
                "cannot infer MOE profile from workbook filename; pass --profile"
            )
    profile = PROFILES[profile_name]
    source = load_moe_rows(workbook)
    character_summary, character_reviews = audit_characters(root, source)
    word_summary, word_reviews = audit_words(root, source)
    report = {
        "schema_version": "1.1.0",
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "purpose": (
            "Taiwan-MOE-first pronunciation cross-check. Differences are review "
            "items and must not be auto-applied without lexical/context review."
        ),
        "source": {
            "source_id": profile["source_id"],
            "full_name": profile["full_name"],
            "version": profile["version"],
            "download_url": profile["download_url"],
            "license_id": MOE_LICENSE,
            "workbook_filename": workbook.name,
            "workbook_sha256": sha256_path(workbook),
            "workbook_bytes": workbook.stat().st_size,
            "indexed_terms": len(source),
        },
        "interpretation": {
            "exact_match": "Corpus and MOE pronunciation sets agree after NFC and whitespace normalization.",
            "review_required": (
                "At least one pronunciation differs. Additional corpus readings may "
                "be rare/historical CNS readings rather than errors."
            ),
            "not_in_source": (
                "The exact headword is outside this pinned dictionary and needs "
                "another Taiwanese authority or manual review."
            ),
        },
        "characters": {
            "summary": character_summary,
            "review_queue": character_reviews,
        },
        "words": {"summary": word_summary, "review_queue": word_reviews},
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
        print(f"wrote {args.output}")
        print(json.dumps({"characters": character_summary, "words": word_summary}))
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
