#!/usr/bin/env python3
"""Validate Phase 4 common words and write its audit reports."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase3 as phase3  # noqa: E402
import build_phase4 as builder  # noqa: E402
import validate_phase3 as validate3  # noqa: E402


WORDS_PATH = ROOT / "words"
CHARACTERS_PATH = ROOT / "characters"
RADICALS_PATH = ROOT / "radicals"
MANIFEST_PATH = ROOT / "metadata" / "manifests" / "phase4.json"
WORD_SCHEMA_PATH = ROOT / "schema" / "word.schema.json"
CHARACTER_SCHEMA_PATH = ROOT / "schema" / "character.schema.json"
RADICAL_SCHEMA_PATH = ROOT / "schema" / "radical.schema.json"
VALIDATION_REPORT_PATH = ROOT / "docs" / "validation.md"
GAPS_REPORT_PATH = ROOT / "docs" / "gaps.md"
PHASE_REPORT_PATH = ROOT / "phase4-report.md"

WORD_ID_RE = re.compile(r"^moe1996-([0-9]{5})$")
CODEPOINT_RE = re.compile(r"^U\+([0-9A-F]{4,6})$")


def load_records() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
]:
    errors: list[str] = []
    word_files = sorted(WORDS_PATH.glob("*.json"))
    character_files = sorted(CHARACTERS_PATH.glob("*.json"))
    words: list[dict[str, Any]] = []
    characters: list[dict[str, Any]] = []
    radicals: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in word_files:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        identifier = record.get("id")
        if path.stem != identifier:
            errors.append(f"{path.name}: filename does not match id {identifier!r}")
        if identifier in seen_ids:
            errors.append(f"duplicate word id: {identifier}")
        seen_ids.add(identifier)
        words.append(record)
    for path in character_files:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if path.stem != record.get("codepoint"):
            errors.append(f"{path.name}: filename does not match codepoint")
        characters.append(record)
    for number in range(1, 215):
        path = RADICALS_PATH / f"{number}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if record.get("kangxi_number") != number:
            errors.append(f"{path.name}: filename does not match kangxi_number")
        radicals.append(record)
    words.sort(key=lambda item: item.get("frequency", {}).get("rank", 0))
    characters.sort(key=lambda item: item.get("frequency", {}).get("selection_rank", 0))
    radicals.sort(key=lambda item: item.get("kangxi_number", 0))
    return words, characters, radicals, errors


def load_context(registry: dict[str, Any]) -> dict[str, Any]:
    moe_path = phase3.acquired_path(registry, phase3.MOE_ID)
    cedict_path = phase3.acquired_path(registry, phase3.CC_CEDICT_ID)
    cns_path = phase3.acquired_path(registry, phase3.CNS_ID)
    moe_concised_path = phase3.acquired_path(registry, builder.MOE_CONCISED_ID)
    moe_revised_path = phase3.acquired_path(registry, builder.MOE_REVISED_ID)
    rows, corpus_total = builder.read_moe_words(registry, moe_path)
    cedict = builder.parse_cc_cedict_words(
        registry, cedict_path, {row["traditional"] for row in rows}
    )
    selected_cps = {
        builder.parse_codepoint(record["codepoint"])
        for record in (
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(CHARACTERS_PATH.glob("*.json"))
        )
    }
    common, chosen_rows, skipped = builder.select_common_words(
        rows, cedict, selected_cps
    )
    _, bopomofo_to_pinyin, _, _ = phase3.parse_cns(registry, cns_path)
    pinyin_to_bopomofo: dict[str, list[str]] = defaultdict(list)
    for bopomofo, pinyin in bopomofo_to_pinyin.items():
        if bopomofo not in pinyin_to_bopomofo[pinyin]:
            pinyin_to_bopomofo[pinyin].append(bopomofo)
    moe_concised = builder.load_moe_rows(moe_concised_path)
    moe_revised = builder.load_moe_rows(moe_revised_path)
    expected_words = [
        builder.build_word_record(
            chosen_rows[rank],
            corpus_total,
            cedict[chosen_rows[rank]["traditional"]],
            selected_cps,
            pinyin_to_bopomofo,
            moe_concised.get(chosen_rows[rank]["traditional"], []),
            moe_revised.get(chosen_rows[rank]["traditional"], []),
        )
        for rank in sorted(chosen_rows)
    ]
    return {
        "rows": rows,
        "corpus_total": corpus_total,
        "cedict": cedict,
        "selected_cps": selected_cps,
        "common": common,
        "chosen_rows": chosen_rows,
        "skipped": skipped,
        "pinyin_to_bopomofo": pinyin_to_bopomofo,
        "moe_concised": moe_concised,
        "moe_revised": moe_revised,
        "expected_words": expected_words,
    }


def check_record_sets(
    words: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    radicals: list[dict[str, Any]],
    initial_errors: list[str],
    manifest: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors = list(initial_errors)
    if len(words) != manifest.get("word_record_count"):
        errors.append(
            f"words/ has {len(words)} JSON files; manifest says "
            f"{manifest.get('word_record_count')}"
        )
    if len(characters) != 2000:
        errors.append(f"characters/ has {len(characters)} JSON files, expected 2000")
    if len(radicals) != 214:
        errors.append(f"radicals/ has {len(radicals)} JSON files, expected 214")
    if [record.get("frequency", {}).get("selection_rank") for record in characters] != list(
        range(1, 2001)
    ):
        errors.append("character selection_rank values are not exactly 1–2000")
    ranks = [record.get("frequency", {}).get("rank") for record in words]
    if ranks != sorted(set(ranks)):
        errors.append("word frequency ranks are duplicated or not strictly ascending")
    for record in words:
        match = WORD_ID_RE.fullmatch(record.get("id", ""))
        if not match or int(match.group(1)) != record.get("frequency", {}).get("rank"):
            errors.append(f"{record.get('id')}: ID does not encode its MOE rank")
    return errors


def check_schema(
    words: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    radicals: list[dict[str, Any]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    for schema_path, records, key in (
        (WORD_SCHEMA_PATH, words, "id"),
        (CHARACTER_SCHEMA_PATH, characters, "codepoint"),
        (RADICAL_SCHEMA_PATH, radicals, "kangxi_number"),
    ):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for record in records:
            for error in sorted(
                validator.iter_errors(record), key=lambda item: list(item.path)
            ):
                location = ".".join(str(part) for part in error.path) or "<root>"
                errors.append(
                    f"{record.get(key)}, {location}: {error.message}"
                )
    return errors


def check_deterministic_words(
    words: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    expected = context["expected_words"]
    if len(words) != len(expected):
        return [f"built word count is {len(words)}, deterministic rebuild is {len(expected)}"]
    for actual, rebuilt in zip(words, expected):
        if actual != rebuilt:
            errors.append(f"{actual.get('id')}: differs from deterministic source rebuild")
    return errors


def check_character_links(
    words: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    context: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    word_map = {record["id"]: record for record in words}
    for character in characters:
        cp = builder.parse_codepoint(character["codepoint"])
        actual = character.get("common_words")
        expected = context["common"][cp]
        if actual != expected:
            errors.append(
                f"{character['codepoint']}: common_words differs from ranked source selection"
            )
            continue
        if len(actual) > builder.WORDS_PER_CHARACTER:
            errors.append(f"{character['codepoint']}: more than 10 common words")
        forms: set[str] = set()
        ranks: list[int] = []
        for identifier in actual:
            word = word_map.get(identifier)
            if word is None:
                errors.append(f"{character['codepoint']}: unresolved word {identifier}")
                continue
            if character["codepoint"] not in word["constituent_chars"]:
                errors.append(
                    f"{character['codepoint']}: linked word {identifier} lacks character"
                )
            if word["traditional"] in forms:
                errors.append(
                    f"{character['codepoint']}: duplicate Traditional form in common words"
                )
            forms.add(word["traditional"])
            ranks.append(word["frequency"]["rank"])
        if ranks != sorted(ranks):
            errors.append(f"{character['codepoint']}: common words are not rank-ordered")
        has_gap = any(gap["field"] == "common_words" for gap in character["gaps"])
        if (len(actual) < builder.WORDS_PER_CHARACTER) != has_gap:
            errors.append(
                f"{character['codepoint']}: short common-word list and gap disagree"
            )
    return errors


def check_radical_examples(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    context: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    character_map = {record["codepoint"]: record for record in characters}
    expected = builder.derive_radical_examples(characters, context["common"])
    expected_sources = [phase3.MOE_ID, phase3.CNS_ID, phase3.CC_CEDICT_ID]
    seen: set[str] = set()
    for radical in radicals:
        number = radical["kangxi_number"]
        actual = radical.get("example_characters")
        if actual != expected[number]:
            errors.append(
                f"radical {number}: example_characters differs from the ranked eligible set"
            )
            continue
        if radical.get("sources", {}).get("example_characters") != expected_sources:
            errors.append(f"radical {number}: example-character provenance differs")
        matching_gaps = [
            gap for gap in radical["gaps"] if gap["field"] == "example_characters"
        ]
        expected_gap_count = 0 if actual else 1
        if len(matching_gaps) != expected_gap_count:
            errors.append(
                f"radical {number}: example-character coverage and gap disagree"
            )
        ranks: list[int] = []
        for codepoint in actual:
            if codepoint in seen:
                errors.append(f"{codepoint}: assigned to more than one radical example list")
            seen.add(codepoint)
            character = character_map.get(codepoint)
            if character is None:
                errors.append(f"radical {number}: unresolved example {codepoint}")
                continue
            if character["radical"]["kangxi_number"] != number:
                errors.append(f"radical {number}: {codepoint} has a different assignment")
            cp = builder.parse_codepoint(codepoint)
            if not context["common"].get(cp):
                errors.append(f"radical {number}: {codepoint} lacks ranked-word evidence")
            ranks.append(character["frequency"]["rank"])
        if ranks != sorted(ranks):
            errors.append(f"radical {number}: examples are not in character-frequency order")
    eligible = {
        record["codepoint"]
        for record in characters
        if context["common"].get(builder.parse_codepoint(record["codepoint"]))
    }
    if seen != eligible:
        errors.append(
            f"radical example union differs from eligible characters: {len(seen)} != {len(eligible)}"
        )
    return errors


def check_english_translations(
    characters: list[dict[str, Any]], **_: Any
) -> list[str]:
    errors: list[str] = []
    for record in characters:
        unihan_glosses = [
            definition["gloss"]
            for definition in record.get("definitions") or []
            if definition.get("source_id") == phase3.UNIHAN_ID
        ]
        if len(unihan_glosses) != 1:
            errors.append(
                f"{record['codepoint']}: expected exactly one Unihan English gloss, found {len(unihan_glosses)}"
            )
            continue
        if record.get("english_translation") != unihan_glosses[0]:
            errors.append(
                f"{record['codepoint']}: english_translation differs from Unihan kDefinition"
            )
        if record.get("sources", {}).get("english_translation") != [phase3.UNIHAN_ID]:
            errors.append(
                f"{record['codepoint']}: english_translation provenance is not exact"
            )
    return errors


def check_taiwan_definitions(
    words: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    for record in words:
        term = record["traditional"]
        concised_rows = context["moe_concised"].get(term, [])
        revised_rows = context["moe_revised"].get(term, [])
        rows = concised_rows or revised_rows
        source_id = (
            builder.MOE_CONCISED_ID if concised_rows else builder.MOE_REVISED_ID
        )
        expected = (
            phase3.build_taiwan_definitions(rows, source_id) if rows else None
        )
        if record.get("definitions_zh_TW") != expected:
            errors.append(f"{record['id']}: Taiwan definition differs from source")
        if expected is not None:
            if record["sources"].get("definitions_zh_TW") != [source_id]:
                errors.append(f"{record['id']}: Taiwan definition provenance differs")
        else:
            matching_gaps = [
                gap
                for gap in record["gaps"]
                if gap["field"] == "definitions_zh_TW"
                and gap["reason"] == "not_attested"
            ]
            if len(matching_gaps) != 1:
                errors.append(f"{record['id']}: Taiwan definition gap differs")
    return errors


def walk_non_null(value: Any, path: str = "") -> list[str]:
    fields: list[str] = []
    if path.split(".", 1)[0] in {"sources", "gaps", "conflicts"}:
        return fields
    if isinstance(value, dict):
        for key, item in value.items():
            fields.extend(walk_non_null(item, f"{path}.{key}" if path else key))
    elif isinstance(value, list):
        if value and all(not isinstance(item, (dict, list)) for item in value):
            fields.append(path)
        else:
            for index, item in enumerate(value):
                fields.extend(walk_non_null(item, f"{path}[{index}]"))
    elif value is not None:
        fields.append(path)
    return fields


def source_covers(path: str, sources: set[str]) -> bool:
    return any(
        path == source
        or path.startswith(source + ".")
        or path.startswith(source + "[")
        for source in sources
    )


def check_provenance(
    words: list[dict[str, Any]], registry: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    registered = registry["sources"]
    for record in words:
        source_paths = set(record["sources"])
        for field in walk_non_null(record):
            if not source_covers(field, source_paths):
                errors.append(f"{record['id']}: non-null field lacks source: {field}")
        for field, source_ids in record["sources"].items():
            for source_id in source_ids:
                source = registered.get(source_id)
                if source is None:
                    errors.append(f"{record['id']}, {field}: unknown source {source_id}")
                elif source.get("status") != "approved":
                    errors.append(
                        f"{record['id']}, {field}: source is not approved: {source_id}"
                    )
                elif not source.get("license", {}).get("verified"):
                    errors.append(
                        f"{record['id']}, {field}: source license is not verified"
                    )
        for conflict in record["conflicts"]:
            for value in conflict["values"]:
                for source_id in value["source_ids"]:
                    if source_id not in registered:
                        errors.append(
                            f"{record['id']}: unknown conflict source {source_id}"
                        )
    return errors


def walk_nulls(value: Any, path: str = "") -> list[str]:
    fields: list[str] = []
    if path.split(".", 1)[0] in {"sources", "gaps", "conflicts"}:
        return fields
    if value is None:
        fields.append(path)
    elif isinstance(value, dict):
        for key, item in value.items():
            fields.extend(walk_nulls(item, f"{path}.{key}" if path else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            fields.extend(walk_nulls(item, f"{path}[{index}]"))
    return fields


def check_null_gaps(words: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    for record in words:
        gap_fields = {gap["field"] for gap in record["gaps"]}
        for field in walk_nulls(record):
            if field not in gap_fields:
                errors.append(f"{record['id']}: null field lacks exact gap: {field}")
        for required in ("grading.hsk", "segmentation_tool"):
            if required not in gap_fields:
                errors.append(f"{record['id']}: required source-unavailable gap missing: {required}")
    return errors


def check_unicode_scope(words: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    for record in words:
        if not phase3.is_nfc_except_verbatim_text(record):
            errors.append(f"{record['id']}: a non-verbatim record field is not NFC")
        expected_constituents = [
            phase3.codepoint(ord(char))
            for char in record["traditional"]
            if phase3.is_han_unified(ord(char))
        ]
        if record["constituent_chars"] != expected_constituents:
            errors.append(f"{record['id']}: constituent codepoints do not match headword")
        for value in (record["traditional"], record.get("simplified") or ""):
            for char in value:
                cp = ord(char)
                if phase3.is_forbidden_character(cp) or builder.is_private_use(cp):
                    errors.append(f"{record['id']}: forbidden U+{cp:04X} in word form")
        for value in record["constituent_chars"]:
            match = CODEPOINT_RE.fullmatch(value)
            if not match or not phase3.is_han_unified(int(match.group(1), 16)):
                errors.append(f"{record['id']}: invalid constituent {value}")
    supplementary = chr(0x20000)
    if ord(json.loads(json.dumps(supplementary, ensure_ascii=False))) != 0x20000:
        errors.append("non-BMP U+20000 failed numeric codepoint JSON round-trip")
    return errors


def check_readings(words: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    tone_marks = {0x02C7, 0x02CA, 0x02CB, 0x02D9}
    for record in words:
        pinyin_by_value = {
            item["reading"]: builder.moe_pronunciations.source_refs(item)
            for item in record["pinyin"] or []
        }
        for reading in pinyin_by_value:
            if any(char.isdigit() for char in reading):
                errors.append(f"{record['id']}: numeric-tone Pinyin {reading!r}")
            if not unicodedata.is_normalized("NFC", reading):
                errors.append(f"{record['id']}: non-NFC Pinyin {reading!r}")
        for item in record["zhuyin"] or []:
            if item["pinyin"] not in pinyin_by_value:
                errors.append(f"{record['id']}: Zhuyin has no matching Pinyin")
            elif builder.moe_pronunciations.source_refs(item) != pinyin_by_value[item["pinyin"]]:
                errors.append(f"{record['id']}: Zhuyin/Pinyin source entries differ")
            for char in item["reading"]:
                cp = ord(char)
                if char == " ":
                    continue
                if not (
                    0x3105 <= cp <= 0x312F
                    or 0x31A0 <= cp <= 0x31BF
                    or cp in tone_marks
                ):
                    errors.append(
                        f"{record['id']}: invalid Zhuyin codepoint U+{cp:04X}"
                    )
    return errors


def check_exact_join(
    words: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    rows = {row["rank"]: row for row in context["rows"]}
    for record in words:
        rank = record["frequency"]["rank"]
        row = rows.get(rank)
        if row is None or row["traditional"] != record["traditional"]:
            errors.append(f"{record['id']}: does not match its pinned MOE row")
            continue
        entries = context["cedict"].get(record["traditional"], [])
        expected_indices = sorted(entry["entry_index"] for entry in entries)
        if record["cc_cedict_entry_indices"] != expected_indices:
            errors.append(f"{record['id']}: exact CC-CEDICT entry indices differ")
        moe_rows = context["moe_concised"].get(record["traditional"], [])
        if moe_rows:
            expected_pinyin, expected_zhuyin = (
                builder.moe_pronunciations.moe_readings(moe_rows)
            )
            if record.get("pinyin") != expected_pinyin:
                errors.append(f"{record['id']}: exact Taiwan MOE Pinyin differs")
            if record.get("zhuyin") != expected_zhuyin:
                errors.append(f"{record['id']}: exact Taiwan MOE Zhuyin differs")
            if record["sources"].get("pinyin") != [builder.MOE_CONCISED_ID]:
                errors.append(f"{record['id']}: Concised Pinyin provenance differs")
            if record["sources"].get("zhuyin") != [builder.MOE_CONCISED_ID]:
                errors.append(f"{record['id']}: Concised Zhuyin provenance differs")
        else:
            revised_rows = context["moe_revised"].get(record["traditional"], [])
            if revised_rows:
                expected_pinyin, expected_zhuyin = (
                    builder.moe_pronunciations.moe_readings(revised_rows)
                )
                if record.get("pinyin") != expected_pinyin:
                    errors.append(
                        f"{record['id']}: exact Revised Dictionary Pinyin differs"
                    )
                if record.get("zhuyin") != expected_zhuyin:
                    errors.append(
                        f"{record['id']}: exact Revised Dictionary Zhuyin differs"
                    )
                if record["sources"].get("pinyin") != [builder.MOE_REVISED_ID]:
                    errors.append(
                        f"{record['id']}: Revised Dictionary Pinyin provenance differs"
                    )
                if record["sources"].get("zhuyin") != [builder.MOE_REVISED_ID]:
                    errors.append(
                        f"{record['id']}: Revised Dictionary Zhuyin provenance differs"
                    )
                continue
            gap_fields = {gap["field"] for gap in record["gaps"]}
            for field in builder.moe_pronunciations.TAIWAN_GAP_FIELDS:
                if field not in gap_fields:
                    errors.append(
                        f"{record['id']}: uncovered Taiwan pronunciation lacks {field} gap"
                    )
    return errors


def check_phase3_regression(
    characters: list[dict[str, Any]], **_: Any
) -> list[str]:
    errors: list[str] = []
    phase3_manifest = json.loads(
        (ROOT / "metadata" / "manifests" / "phase3.json").read_text(encoding="utf-8")
    )
    projection = [builder.phase3_projection(record) for record in characters]
    digest = phase3.deterministic_record_digest(projection)
    if digest != phase3_manifest["record_digest_sha256"]:
        errors.append("Phase 3 base character digest changed during Phase 4")
    errors.extend(validate3.check_phase2_regression())
    return errors


def check_manifest(
    words: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    radicals: list[dict[str, Any]],
    context: dict[str, Any],
    manifest: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    expected = {
        "phase": 4,
        "word_record_count": len(words),
        "character_record_count": len(characters),
        "common_word_reference_count": sum(
            len(record["common_words"]) for record in characters
        ),
        "radical_record_count": len(radicals),
        "radical_example_character_reference_count": sum(
            len(record.get("example_characters", [])) for record in radicals
        ),
        "radicals_with_example_characters": sum(
            bool(record.get("example_characters")) for record in radicals
        ),
        "radicals_without_example_characters": [
            record["kangxi_number"]
            for record in radicals
            if not record.get("example_characters")
        ],
        "radical_example_digest_sha256": phase3.deterministic_record_digest(
            builder.radical_example_projection(radicals)
        ),
        "english_translation_count": sum(
            bool(record.get("english_translation")) for record in characters
        ),
        "taiwan_definition_covered_count": sum(
            bool(record.get("definitions_zh_TW")) for record in words
        ),
        "taiwan_definition_gap_count": sum(
            record.get("definitions_zh_TW") is None for record in words
        ),
        "words_per_character_limit": builder.WORDS_PER_CHARACTER,
        "single_character_word_count": sum(
            len(record["traditional"]) == 1 for record in words
        ),
        "word_record_digest_sha256": phase3.deterministic_record_digest(words),
        "character_record_digest_sha256": phase3.deterministic_record_digest(
            [phase4_projection(record) for record in characters]
        ),
        "phase3_base_record_digest_sha256": phase3.deterministic_record_digest(
            [builder.phase3_projection(record) for record in characters]
        ),
        "word_records_with_conflicts": sum(bool(record["conflicts"]) for record in words),
        "moe_pronunciation_covered_count": sum(
            record["sources"].get("pinyin") == [builder.MOE_CONCISED_ID]
            for record in words
        ),
        "moe_pronunciation_conflict_count": sum(
            any(
                conflict.get("resolution") == "taiwan_moe_canonical"
                for conflict in record["conflicts"]
            )
            for record in words
        ),
        "taiwan_pronunciation_verification_gap_count": sum(
            any(
                gap.get("field") == "pinyin.taiwan_verification"
                for gap in record["gaps"]
            )
            for record in words
        ),
        "word_gap_count": sum(len(record["gaps"]) for record in words),
        "moe_revised_additional_word_covered_count": sum(
            record["sources"].get("pinyin") == [builder.MOE_REVISED_ID]
            and record["sources"].get("zhuyin") == [builder.MOE_REVISED_ID]
            for record in words
        ),
        "moe_revised_additional_conflict_count": sum(
            record["sources"].get("pinyin") == [builder.MOE_REVISED_ID]
            and any(
                conflict.get("resolution") == "taiwan_moe_canonical"
                for conflict in record["conflicts"]
            )
            for record in words
        ),
        "moe_revised_additional_zhuyin_fill_count": len(
            builder.moe_pronunciations.REVISED_ZHUYIN_FILL_IDS
        ),
        "taiwan_word_pronunciation_covered_count": sum(
            record["sources"].get("pinyin")
            in ([builder.MOE_CONCISED_ID], [builder.MOE_REVISED_ID])
            and record["sources"].get("zhuyin")
            in ([builder.MOE_CONCISED_ID], [builder.MOE_REVISED_ID])
            and record["sources"].get("pinyin")
            == record["sources"].get("zhuyin")
            for record in words
        ),
        "unresolved_word_pronunciation_count": sum(
            any(
                gap.get("field") == "pinyin.taiwan_verification"
                for gap in record["gaps"]
            )
            for record in words
        ),
        "selection_skip_counts": context["skipped"],
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"manifest {key} differs: {manifest.get(key)!r} != {value!r}")
    distribution = Counter(str(len(record["common_words"])) for record in characters)
    expected_distribution = dict(sorted(distribution.items(), key=lambda item: int(item[0])))
    if manifest.get("words_per_character_distribution") != expected_distribution:
        errors.append("manifest words_per_character_distribution differs")
    rank_range = [words[0]["frequency"]["rank"], words[-1]["frequency"]["rank"]]
    if manifest.get("selected_moe_rank_range") != rank_range:
        errors.append("manifest selected_moe_rank_range differs")
    return errors


def phase4_projection(record: dict[str, Any]) -> dict[str, Any]:
    """Remove backward-compatible Phase 5 enrichment from a Phase 4 character."""
    return builder.phase4_character_projection(record)


def format_ids(values: list[str], width: int = 12) -> list[str]:
    return [
        " ".join(values[index : index + width])
        for index in range(0, len(values), width)
    ]


def write_reports(
    words: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    radicals: list[dict[str, Any]],
    checks: list[tuple[str, str, list[str]]],
    manifest: dict[str, Any],
) -> None:
    passed = all(not errors for _, _, errors in checks)
    validation = [
        "# Validation report",
        "",
        f"Phase 4 status: **{'PASS' if passed else 'FAIL'}**",
        "",
        f"Generated: {phase3.utc_now()}",
        "",
        "| Check | Result | Detail |",
        "|---|---:|---|",
    ]
    for check_id, detail, errors in checks:
        validation.append(
            f"| {check_id} | {'PASS' if not errors else 'FAIL'} | "
            + (detail if not errors else f"{len(errors)} failure(s)")
            + " |"
        )
    for check_id, _, errors in checks:
        if errors:
            validation.extend(["", f"## {check_id} failures", ""])
            validation.extend(f"- {error}" for error in errors)
    VALIDATION_REPORT_PATH.write_text("\n".join(validation) + "\n", encoding="utf-8")

    grouped: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for record in characters:
        for gap in record["gaps"]:
            grouped[(gap["reason"], f"character.{gap['field']}", gap["detail"])].append(
                record["codepoint"]
            )
    for record in words:
        for gap in record["gaps"]:
            grouped[(gap["reason"], f"word.{gap['field']}", gap["detail"])].append(
                record["id"]
            )
    for record in radicals:
        for gap in record["gaps"]:
            if gap["field"] == "example_characters":
                grouped[(gap["reason"], f"radical.{gap['field']}", gap["detail"])].append(
                    f"R{record['kangxi_number']:03d}"
                )
    gap_lines = [
        "# Gaps report",
        "",
        "All explicit Phase 4 character and word gaps, grouped by allowed reason and exact field.",
        "",
    ]
    for reason in (
        "not_attested",
        "source_unavailable",
        "conflicting_sources",
        "license_prohibits_use",
    ):
        items = sorted(
            ((field, detail, ids) for (item_reason, field, detail), ids in grouped.items() if item_reason == reason),
            key=lambda item: (item[0], item[1]),
        )
        gap_lines.extend([f"## {reason}", ""])
        if not items:
            gap_lines.extend(["None.", ""])
            continue
        for field, detail, ids in items:
            unique_ids = sorted(set(ids))
            gap_lines.extend(
                [
                    f"### `{field}` — {len(unique_ids)} record(s)",
                    "",
                    detail,
                    "",
                    *format_ids(unique_ids),
                    "",
                ]
            )
    GAPS_REPORT_PATH.write_text("\n".join(gap_lines), encoding="utf-8")

    distribution = manifest["words_per_character_distribution"]
    word_gap_reasons = Counter(
        gap["reason"] for record in words for gap in record["gaps"]
    )
    conflict_fields = Counter(
        conflict["field"] for record in words for conflict in record["conflicts"]
    )
    phase_lines = [
        "# Phase 4 report — common-word layer",
        "",
        f"Status: **{'PASS' if passed else 'FAIL'}**",
        "",
        "## Completed",
        "",
        f"- Word records: **{len(words):,}**.",
        f"- Character-to-word references: **{manifest['common_word_reference_count']:,}**.",
        f"- Radical-to-common-character references: **{manifest['radical_example_character_reference_count']:,}**, covering **{manifest['radicals_with_example_characters']} / 214** radicals.",
        f"- Characters with a dedicated English translation: **{manifest['english_translation_count']:,} / {len(characters):,}**.",
        f"- Words with an exact verbatim Taiwan MOE definition: **{manifest['taiwan_definition_covered_count']:,} / {len(words):,}**; exact-headword gaps: **{manifest['taiwan_definition_gap_count']:,}**.",
        f"- Characters with 10 words: **{distribution.get('10', 0):,} / {len(characters):,}**.",
        f"- Single-character published MOE word rows retained: **{manifest['single_character_word_count']:,}**.",
        f"- Word records flagged by mapping conflicts: **{manifest['word_records_with_conflicts']:,}**.",
        f"- Explicit word gaps: **{manifest['word_gap_count']:,}**.",
        "",
        "## Words per character",
        "",
        "| Words | Characters |",
        "|---:|---:|",
    ]
    phase_lines.extend(
        f"| {count} | {distribution[count]:,} |"
        for count in sorted(distribution, key=int)
    )
    phase_lines.extend(
        [
            "",
            "## Conflicts and gaps",
            "",
            "| Category | Count |",
            "|---|---:|",
        ]
    )
    phase_lines.extend(
        f"| conflict: `{field}` | {count:,} |"
        for field, count in sorted(conflict_fields.items())
    )
    phase_lines.extend(
        f"| gap: `{reason}` | {count:,} |"
        for reason, count in sorted(word_gap_reasons.items())
    )
    phase_lines.extend(
        [
            "",
            "## Implementation decisions introduced in this phase",
            "",
            "1. The corpus's 46,721 published `85rest02.csv` rows are the word-boundary authority. The release names no segmentation software, so `segmentation_tool` remains null with a `source_unavailable` gap.",
            "2. One-character rows are retained because the source publishes them as word rows and no approved rule excludes them.",
            "3. Eligibility requires an exact NFC Traditional headword match in the pinned CC-CEDICT snapshot. No local segmentation, script conversion, substring lookup, or approximate matching is used.",
            "4. Each character receives the first 10 distinct eligible Traditional forms in ascending MOE rank. A shared word is stored once and joined by its rank-derived ID.",
            "5. Every top-2,000 character with at least one eligible ranked-word link is joined to its canonical Taiwan CNS radical in character-frequency order. Empty radical lists are explicit and are never padded with obscure characters.",
            "6. Multiple exact CC-CEDICT Simplified mappings remain null and are preserved in `conflicts[]`.",
            "7. Exact Concised Dictionary Pinyin, Zhuyin, definitions, and entry IDs are canonical; Revised Dictionary rows fill exact-headword Concised omissions. Earlier CC-CEDICT/CNS readings remain conflict evidence when they differ.",
            "8. For the 1,477 words absent from both official downloads, earlier readings remain provisional and definitions_zh_TW remains null with exact gaps.",
            "",
            "## Source limitations",
            "",
            f"- **{manifest['selection_skip_counts'].get('no_exact_cc_cedict_headword', 0):,}** MOE rows had no exact CC-CEDICT Traditional headword and were ineligible.",
            "- No approved HSK word-level source passed the source audit; `grading.hsk` remains null.",
            "- Phase 5 supplies full radical/character stroke-order SVG coverage in this snapshot.",
            "",
        ]
    )
    PHASE_REPORT_PATH.write_text("\n".join(phase_lines), encoding="utf-8")


def main() -> None:
    registry = phase3.load_registry()
    words, characters, radicals, initial_errors = load_records()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    context = load_context(registry)
    specs: list[tuple[str, str, Callable[..., list[str]]]] = [
        ("P4-01 Record sets", "Word IDs/files are unique and both record sets have the manifest counts.", check_record_sets),
        ("P4-02 JSON Schema", "All word and enriched character records validate against their schemas.", check_schema),
        ("P4-03 Deterministic rebuild", "Every word exactly reproduces from the pinned source snapshots.", check_deterministic_words),
        ("P4-04 Ranked joins", "Every character has its first 10 distinct eligible MOE-ranked words, or an explicit short-list gap.", check_character_links),
        ("P4-04b Radical examples", "Every eligible common character appears exactly once under its Taiwan CNS radical, in character-frequency order; uncovered radicals remain explicitly empty.", check_radical_examples),
        ("P4-05 English translations", "Every character exposes its exact Unihan English gloss with explicit provenance.", check_english_translations),
        ("P4-05b Taiwan definitions", "Every available Taiwan definition exactly reproduces a decoded MOE cell and entry ID; dual-dictionary absences remain explicit gaps.", check_taiwan_definitions),
        ("P4-06 Provenance", "Every non-null word leaf is covered by an approved, license-verified source.", check_provenance),
        ("P4-07 Null/gap pairing", "Every word null and every unavailable grading/segmentation field has an exact gap.", check_null_gaps),
        ("P4-08 Unicode scope", "Word forms are NFC, constituents match, non-BMP round-trips, and forbidden blocks are absent.", check_unicode_scope),
        ("P4-09 Reading syntax", "Pinyin uses tone marks and Zhuyin uses valid Bopomofo with aligned source entries.", check_readings),
        ("P4-10 Exact source joins", "Word rank/headword and CC-CEDICT entry references resolve exactly.", check_exact_join),
        ("P4-11 Prior-phase regression", "Phase 3 base characters and Phase 2 radical/assets remain unchanged.", check_phase3_regression),
        ("P4-12 Manifest", "All Phase 4 counts, distributions, source skips, translations, and deterministic digests match.", check_manifest),
    ]
    shared = {
        "words": words,
        "characters": characters,
        "radicals": radicals,
        "initial_errors": initial_errors,
        "manifest": manifest,
        "registry": registry,
        "context": context,
    }
    checks = [(check_id, detail, function(**shared)) for check_id, detail, function in specs]
    write_reports(words, characters, radicals, checks, manifest)
    failures = sum(bool(errors) for _, _, errors in checks)
    print(
        f"Phase 4 validation: {'PASS' if failures == 0 else 'FAIL'} "
        f"({len(checks) - failures}/{len(checks)} checks passed)"
    )
    if failures:
        for check_id, _, errors in checks:
            if errors:
                print(f"{check_id}: {len(errors)} failure(s)")
                for error in errors[:20]:
                    print(f"  - {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
