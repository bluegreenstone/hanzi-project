#!/usr/bin/env python3
"""Build Phase 4 common-word records and join them to Phase 3 characters."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import subprocess
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase3 as phase3  # noqa: E402


WORDS_PATH = ROOT / "words"
MANIFEST_PATH = ROOT / "phase4-manifest.json"
WORD_SCHEMA_PATH = ROOT / "schema" / "word.schema.json"
CHARACTER_SCHEMA_PATH = ROOT / "schema" / "character.schema.json"

WORDS_PER_CHARACTER = 10


def word_id(rank: int) -> str:
    return f"moe1996-{rank:05d}"


def read_moe_words(
    registry: dict[str, Any], path: Path
) -> tuple[list[dict[str, Any]], int]:
    acquisition = registry["sources"][phase3.MOE_ID]["acquisition"]
    member = acquisition["members"]["word_frequency"]
    with zipfile.ZipFile(path) as archive:
        payload = archive.read(member["path"])
    if phase3.sha256_bytes(payload) != member["sha256"]:
        raise RuntimeError("MOE word-frequency member SHA-256 mismatch")
    if len(payload) != member["bytes"]:
        raise RuntimeError("MOE word-frequency member byte-length mismatch")
    conversion = subprocess.run(
        ["iconv", "-f", acquisition["source_encoding"], "-t", "UTF-8"],
        input=payload,
        capture_output=True,
        check=False,
    )
    if conversion.returncode != 0:
        raise RuntimeError(
            "iconv could not decode the MOE legacy Big5 word file: "
            + conversion.stderr.decode("utf-8", errors="replace")
        )
    text = conversion.stdout.decode("utf-8", errors="strict")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    expected = ["序號", "詞目", "詞頻", "累計詞頻", "百分比", "累計百分比"]
    if reader.fieldnames != expected:
        raise RuntimeError(f"unexpected MOE word CSV fields: {reader.fieldnames!r}")
    rows: list[dict[str, Any]] = []
    for raw in reader:
        rows.append(
            {
                "rank": int(raw["序號"]),
                "traditional": unicodedata.normalize("NFC", raw["詞目"]),
                "count": int(raw["詞頻"]),
                "cumulative_count": int(raw["累計詞頻"]),
                "percentage": float(raw["百分比"]),
                "cumulative_percentage": float(raw["累計百分比"]),
            }
        )
    if [row["rank"] for row in rows] != list(range(1, len(rows) + 1)):
        raise RuntimeError("MOE word ranks are not a complete ascending sequence")
    if len(rows) != 46721:
        raise RuntimeError(f"MOE word table has {len(rows)} rows, expected 46721")
    corpus_total = rows[-1]["cumulative_count"]
    if corpus_total != 617306:
        raise RuntimeError(f"MOE word corpus total is {corpus_total}, expected 617306")
    return rows, corpus_total


def tone_mark_phrase(value: str) -> str | None:
    readings: list[str] = []
    for token in value.split():
        marked = phase3.tone_number_to_mark(token)
        if marked is None:
            return None
        readings.append(marked)
    return " ".join(readings) if readings else None


def parse_cc_cedict_words(
    registry: dict[str, Any], path: Path, wanted: set[str]
) -> dict[str, list[dict[str, Any]]]:
    acquisition = registry["sources"][phase3.CC_CEDICT_ID]["acquisition"]
    with gzip.open(path, "rb") as stream:
        payload = stream.read()
    if phase3.sha256_bytes(payload) != acquisition["uncompressed_sha256"]:
        raise RuntimeError("CC-CEDICT uncompressed SHA-256 mismatch")
    if len(payload) != acquisition["uncompressed_bytes"]:
        raise RuntimeError("CC-CEDICT uncompressed byte-length mismatch")
    text = payload.decode("utf-8", errors="strict")
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    entry_index = 0
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        entry_index += 1
        match = phase3.CC_CEDICT_RE.fullmatch(line)
        if not match:
            raise RuntimeError(
                f"malformed CC-CEDICT entry {entry_index}: {line[:120]!r}"
            )
        traditional, simplified, pinyin_raw, definitions_text = match.groups()
        traditional = unicodedata.normalize("NFC", traditional)
        if traditional not in wanted:
            continue
        definitions = phase3.unique(definitions_text.split("/"))
        if not definitions:
            raise RuntimeError(f"CC-CEDICT entry {entry_index} has no definition")
        result[traditional].append(
            {
                "entry_index": entry_index,
                "simplified": unicodedata.normalize("NFC", simplified),
                "pinyin_raw": pinyin_raw,
                "pinyin_marked": tone_mark_phrase(pinyin_raw),
                "definitions": definitions,
            }
        )
    if entry_index != acquisition["upstream_header"]["entries"]:
        raise RuntimeError("CC-CEDICT entry count differs from its pinned header")
    return result


def is_private_use(cp: int) -> bool:
    return (
        0xE000 <= cp <= 0xF8FF
        or 0xF0000 <= cp <= 0xFFFFD
        or 0x100000 <= cp <= 0x10FFFD
    )


def phrase_allowed(value: str) -> bool:
    return bool(value) and all(
        not phase3.is_forbidden_character(ord(char))
        and not is_private_use(ord(char))
        and unicodedata.category(char) not in {"Cc", "Cs"}
        for char in value
    )


def select_common_words(
    rows: list[dict[str, Any]],
    cedict: dict[str, list[dict[str, Any]]],
    selected_cps: set[int],
) -> tuple[dict[int, list[str]], dict[int, dict[str, Any]], dict[str, int]]:
    common: dict[int, list[str]] = {cp: [] for cp in selected_cps}
    seen_forms: dict[int, set[str]] = {cp: set() for cp in selected_cps}
    chosen_rows: dict[int, dict[str, Any]] = {}
    skipped = CounterLike()
    for row in rows:
        traditional = row["traditional"]
        if traditional not in cedict:
            skipped.add("no_exact_cc_cedict_headword")
            continue
        if not phrase_allowed(traditional):
            skipped.add("forbidden_or_private_use_character")
            continue
        members = {
            ord(char)
            for char in traditional
            if ord(char) in selected_cps
        }
        if not members:
            continue
        identifier = word_id(row["rank"])
        used = False
        for cp in members:
            if len(common[cp]) >= WORDS_PER_CHARACTER:
                continue
            if traditional in seen_forms[cp]:
                skipped.add("duplicate_form_for_character")
                continue
            common[cp].append(identifier)
            seen_forms[cp].add(traditional)
            used = True
        if used:
            chosen_rows[row["rank"]] = row
    return common, chosen_rows, skipped.as_dict()


class CounterLike:
    def __init__(self) -> None:
        self.values: dict[str, int] = defaultdict(int)

    def add(self, key: str) -> None:
        self.values[key] += 1

    def as_dict(self) -> dict[str, int]:
        return dict(sorted(self.values.items()))


def pinyin_to_zhuyin(
    pinyin: str, inverse: dict[str, list[str]]
) -> str | None:
    result: list[str] = []
    for token in pinyin.split():
        candidates = inverse.get(token, [])
        if len(candidates) != 1:
            return None
        result.append(candidates[0])
    return " ".join(result) if result else None


def aggregate_entries(
    entries: list[dict[str, Any]],
) -> tuple[
    dict[str, list[int]],
    dict[str, list[int]],
    dict[str, list[int]],
    list[int],
]:
    simplified: dict[str, list[int]] = defaultdict(list)
    pinyin: dict[str, list[int]] = defaultdict(list)
    definitions: dict[str, list[int]] = defaultdict(list)
    unconvertible: list[int] = []
    for entry in entries:
        index = entry["entry_index"]
        simplified[entry["simplified"]].append(index)
        if entry["pinyin_marked"]:
            pinyin[entry["pinyin_marked"]].append(index)
        else:
            unconvertible.append(index)
        for gloss in entry["definitions"]:
            definitions[gloss].append(index)
    return simplified, pinyin, definitions, unconvertible


def build_word_record(
    row: dict[str, Any],
    corpus_total: int,
    entries: list[dict[str, Any]],
    selected_cps: set[int],
    pinyin_to_bopomofo: dict[str, list[str]],
) -> dict[str, Any]:
    traditional = row["traditional"]
    simplified_map, pinyin_map, definition_map, unconvertible = aggregate_entries(
        entries
    )
    sources: dict[str, list[str]] = {
        "id": [phase3.MOE_ID],
        "traditional": [phase3.MOE_ID, phase3.CC_CEDICT_ID],
        "constituent_chars": [phase3.MOE_ID],
        "definitions": [phase3.CC_CEDICT_ID],
        "frequency": [phase3.MOE_ID],
        "cc_cedict_entry_indices": [phase3.CC_CEDICT_ID],
    }
    gaps: list[dict[str, str]] = []
    conflicts: list[dict[str, Any]] = []

    if len(simplified_map) == 1:
        simplified = next(iter(simplified_map))
        sources["simplified"] = [phase3.CC_CEDICT_ID]
    else:
        simplified = None
        gaps.append(
            phase3.make_gap(
                "simplified",
                "conflicting_sources",
                "Exact CC-CEDICT entries for this Traditional headword have multiple Simplified forms.",
            )
        )
        conflicts.append(
            {
                "field": "simplified",
                "resolution": "unresolved",
                "values": [
                    {
                        "value": value,
                        "source_ids": [phase3.CC_CEDICT_ID],
                        "source_entry_indices": indices,
                    }
                    for value, indices in simplified_map.items()
                ],
                "detail": "All exact dictionary mappings are retained; no Simplified word form is selected.",
            }
        )

    if pinyin_map:
        pinyin = [
            {
                "reading": reading,
                "context": "dictionary_entry",
                "source_entry_indices": indices,
            }
            for reading, indices in pinyin_map.items()
        ]
        sources["pinyin"] = [phase3.CC_CEDICT_ID]
        if unconvertible:
            gaps.append(
                phase3.make_gap(
                    "pinyin.partial",
                    "not_attested",
                    "Some CC-CEDICT entry Pinyin tokens could not be converted to tone marks: "
                    + ", ".join(str(index) for index in unconvertible),
                )
            )
    else:
        pinyin = None
        gaps.append(
            phase3.make_gap(
                "pinyin",
                "not_attested",
                "No exact CC-CEDICT entry supplies a fully convertible numeric-tone Pinyin sequence.",
            )
        )

    zhuyin_rows: list[dict[str, Any]] = []
    failed_zhuyin: list[str] = []
    for reading, indices in pinyin_map.items():
        zhuyin_value = pinyin_to_zhuyin(reading, pinyin_to_bopomofo)
        if zhuyin_value is None:
            failed_zhuyin.append(reading)
            continue
        zhuyin_rows.append(
            {
                "reading": zhuyin_value,
                "pinyin": reading,
                "source_entry_indices": indices,
            }
        )
    zhuyin = zhuyin_rows or None
    if zhuyin:
        sources["zhuyin"] = [phase3.CC_CEDICT_ID, phase3.CNS_ID]
        if failed_zhuyin:
            gaps.append(
                phase3.make_gap(
                    "zhuyin.partial",
                    "not_attested",
                    "The pinned CNS syllable table has no unique full conversion for: "
                    + ", ".join(failed_zhuyin),
                )
            )
    else:
        gaps.append(
            phase3.make_gap(
                "zhuyin",
                "not_attested",
                "No complete word reading can be converted through the pinned CNS Bopomofo-to-Pinyin table.",
            )
        )

    definitions = [
        {
            "gloss": gloss,
            "lang": "en",
            "register": "modern",
            "source_entry_indices": indices,
        }
        for gloss, indices in definition_map.items()
    ]
    constituents = [
        phase3.codepoint(ord(char))
        for char in traditional
        if phase3.is_han_unified(ord(char))
    ]
    external = sorted(
        {parse_codepoint(value) for value in constituents} - selected_cps
    )
    if external:
        gaps.append(
            phase3.make_gap(
                "constituent_chars.local_records",
                "source_unavailable",
                "The word contains unified Han characters outside the Phase 3 top-2,000 set: "
                + ", ".join(phase3.codepoint(cp) for cp in external),
            )
        )
    gaps.extend(
        [
            phase3.make_gap(
                "grading.hsk",
                "source_unavailable",
                "No versioned redistribution-approved HSK word source passed the Phase 0 audit.",
            ),
            phase3.make_gap(
                "segmentation_tool",
                "source_unavailable",
                "The MOE release publishes word-frequency rows but does not identify a named segmentation tool.",
            ),
        ]
    )

    record = {
        "id": word_id(row["rank"]),
        "traditional": traditional,
        "simplified": simplified,
        "constituent_chars": constituents,
        "pinyin": pinyin,
        "zhuyin": zhuyin,
        "definitions": definitions,
        "frequency": {
            "rank": row["rank"],
            "corpus_id": phase3.MOE_ID,
            "count": row["count"],
            "cumulative_count": row["cumulative_count"],
            "percentage": row["percentage"],
            "cumulative_percentage": row["cumulative_percentage"],
            "per_million": round(row["count"] / corpus_total * 1_000_000, 6),
            "corpus_total_count": corpus_total,
        },
        "grading": {"hsk": None},
        "segmentation_tool": None,
        "cc_cedict_entry_indices": sorted(
            entry["entry_index"] for entry in entries
        ),
        "sources": sources,
        "gaps": gaps,
        "conflicts": conflicts,
    }
    return phase3.normalize_tree(record)


def parse_codepoint(value: str) -> int:
    return int(value[2:], 16)


def phase3_projection(record: dict[str, Any]) -> dict[str, Any]:
    projected = json.loads(json.dumps(record, ensure_ascii=False))
    projected.pop("stroke_order", None)
    projected.pop("english_translation", None)
    projected.pop("common_words", None)
    projected.get("sources", {}).pop("stroke_order", None)
    for source_path in list(projected.get("sources", {})):
        if source_path.startswith("stroke_order."):
            projected["sources"].pop(source_path)
    projected.get("sources", {}).pop("english_translation", None)
    projected.get("sources", {}).pop("common_words", None)
    projected["gaps"] = [
        gap
        for gap in projected.get("gaps", [])
        if gap.get("field") != "common_words"
        and not gap.get("field", "").startswith("stroke_order")
    ]
    return projected


def deterministic_digest(records: list[dict[str, Any]]) -> str:
    return phase3.deterministic_record_digest(records)


def main() -> None:
    registry = phase3.load_registry()
    moe_path = phase3.acquired_path(registry, phase3.MOE_ID)
    cedict_path = phase3.acquired_path(registry, phase3.CC_CEDICT_ID)
    cns_path = phase3.acquired_path(registry, phase3.CNS_ID)

    character_paths = sorted((ROOT / "characters").glob("*.json"))
    characters = [
        json.loads(path.read_text(encoding="utf-8")) for path in character_paths
    ]
    characters.sort(key=lambda item: item["frequency"]["selection_rank"])
    if len(characters) != 2000:
        raise RuntimeError("Phase 4 requires exactly 2,000 Phase 3 character records")
    base_records = [phase3_projection(record) for record in characters]
    phase3_manifest = json.loads(
        (ROOT / "phase3-manifest.json").read_text(encoding="utf-8")
    )
    if deterministic_digest(base_records) != phase3_manifest["record_digest_sha256"]:
        raise RuntimeError("Phase 3 base-record digest does not match its manifest")
    selected_cps = {parse_codepoint(record["codepoint"]) for record in characters}

    rows, corpus_total = read_moe_words(registry, moe_path)
    cedict = parse_cc_cedict_words(
        registry, cedict_path, {row["traditional"] for row in rows}
    )
    common, chosen_rows, skipped = select_common_words(rows, cedict, selected_cps)
    _, bopomofo_to_pinyin, _ = phase3.parse_cns(registry, cns_path)
    pinyin_to_bopomofo: dict[str, list[str]] = defaultdict(list)
    for bopomofo, pinyin in bopomofo_to_pinyin.items():
        if bopomofo not in pinyin_to_bopomofo[pinyin]:
            pinyin_to_bopomofo[pinyin].append(bopomofo)

    word_records: list[dict[str, Any]] = []
    WORDS_PATH.mkdir(parents=True, exist_ok=True)
    expected_filenames: set[str] = set()
    for rank in sorted(chosen_rows):
        row = chosen_rows[rank]
        record = build_word_record(
            row,
            corpus_total,
            cedict[row["traditional"]],
            selected_cps,
            pinyin_to_bopomofo,
        )
        filename = f"{record['id']}.json"
        expected_filenames.add(filename)
        (WORDS_PATH / filename).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        word_records.append(record)
    for path in WORDS_PATH.glob("moe1996-*.json"):
        if path.name not in expected_filenames:
            path.unlink()

    enriched_characters: list[dict[str, Any]] = []
    for record in characters:
        cp = parse_codepoint(record["codepoint"])
        unihan_glosses = [
            definition["gloss"]
            for definition in record.get("definitions") or []
            if definition.get("source_id") == phase3.UNIHAN_ID
        ]
        if len(unihan_glosses) != 1:
            raise RuntimeError(
                f"{record['codepoint']} has {len(unihan_glosses)} Unihan English glosses; expected exactly one"
            )
        record["english_translation"] = unihan_glosses[0]
        record["sources"]["english_translation"] = [phase3.UNIHAN_ID]
        record["gaps"] = [
            gap for gap in record["gaps"] if gap.get("field") != "common_words"
        ]
        record["sources"].pop("common_words", None)
        record["common_words"] = common[cp]
        record["sources"]["common_words"] = [phase3.MOE_ID, phase3.CC_CEDICT_ID]
        if len(common[cp]) < WORDS_PER_CHARACTER:
            record["gaps"].append(
                phase3.make_gap(
                    "common_words",
                    "not_attested",
                    f"Only {len(common[cp])} distinct MOE-ranked rows with an exact CC-CEDICT Traditional headword were available.",
                )
            )
        output = json.dumps(phase3.normalize_tree(record), ensure_ascii=False, indent=2) + "\n"
        if not unicodedata.is_normalized("NFC", output):
            raise RuntimeError(f"enriched character is not NFC: {record['codepoint']}")
        (ROOT / "characters" / f"{record['codepoint']}.json").write_text(
            output, encoding="utf-8"
        )
        enriched_characters.append(record)

    distribution = defaultdict(int)
    for values in common.values():
        distribution[str(len(values))] += 1
    manifest = {
        "phase": 4,
        "generated_at": phase3.utc_now(),
        "word_record_count": len(word_records),
        "character_record_count": len(enriched_characters),
        "common_word_reference_count": sum(len(values) for values in common.values()),
        "english_translation_count": sum(
            bool(record.get("english_translation")) for record in enriched_characters
        ),
        "words_per_character_limit": WORDS_PER_CHARACTER,
        "words_per_character_distribution": dict(
            sorted(distribution.items(), key=lambda item: int(item[0]))
        ),
        "single_character_word_count": sum(
            len(record["traditional"]) == 1 for record in word_records
        ),
        "selected_moe_rank_range": [
            word_records[0]["frequency"]["rank"],
            word_records[-1]["frequency"]["rank"],
        ],
        "selection_skip_counts": skipped,
        "word_record_digest_sha256": deterministic_digest(word_records),
        "character_record_digest_sha256": deterministic_digest(enriched_characters),
        "phase3_base_record_digest_sha256": deterministic_digest(
            [phase3_projection(record) for record in enriched_characters]
        ),
        "word_records_with_conflicts": sum(
            bool(record["conflicts"]) for record in word_records
        ),
        "word_gap_count": sum(len(record["gaps"]) for record in word_records),
        "source_acquisitions": {
            source_id: registry["sources"][source_id]["acquisition"]
            for source_id in (phase3.MOE_ID, phase3.CC_CEDICT_ID, phase3.CNS_ID)
        },
        "builder": "scripts/build_phase4.py",
        "schemas": [
            "schema/character.schema.json",
            "schema/word.schema.json",
        ],
    }
    MANIFEST_PATH.write_text(
        json.dumps(phase3.normalize_tree(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"built {len(word_records)} word records and "
        f"{manifest['common_word_reference_count']} character-word references"
    )


if __name__ == "__main__":
    main()
