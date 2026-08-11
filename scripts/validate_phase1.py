#!/usr/bin/env python3
"""Validate Phase 1 records and write the Phase 1 reports."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase1 as builder  # noqa: E402


RADICALS_PATH = ROOT / "radicals"
SCHEMA_PATH = ROOT / "schema" / "radical.schema.json"
VALIDATION_REPORT_PATH = ROOT / "validation-report.md"
GAPS_REPORT_PATH = ROOT / "gaps-report.md"
PHASE_REPORT_PATH = ROOT / "phase1-report.md"

CODEPOINT_RE = re.compile(r"^U\+([0-9A-F]{4,6})$")
JYUTPING_RE = re.compile(r"^[a-z]+[1-6]$")
EXPECTED_NAMES = ("zh", "en", "ja", "ko")
EXPECTED_READINGS = (
    "pinyin",
    "zhuyin",
    "jyutping",
    "fanqie",
    "japanese_on",
    "japanese_kun",
    "korean",
    "hangul",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_records() -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    files = list(RADICALS_PATH.glob("*.json"))
    numeric_files: dict[int, Path] = {}
    for path in files:
        if not path.stem.isdigit():
            errors.append(f"non-record JSON file in radicals/: {path.name}")
            continue
        number = int(path.stem)
        if number in numeric_files:
            errors.append(f"duplicate filename number: {number}")
        numeric_files[number] = path
    expected = set(range(1, 215))
    missing = sorted(expected - set(numeric_files))
    extra = sorted(set(numeric_files) - expected)
    if missing:
        errors.append(f"missing radical files: {missing}")
    if extra:
        errors.append(f"out-of-range radical files: {extra}")

    records: list[dict[str, Any]] = []
    for number in sorted(numeric_files):
        try:
            record = json.loads(numeric_files[number].read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{numeric_files[number].name}: {exc}")
            continue
        records.append(record)
        if record.get("kangxi_number") != number:
            errors.append(
                f"{numeric_files[number].name}: kangxi_number is {record.get('kangxi_number')!r}"
            )
    return records, errors


def parse_codepoint(value: str) -> int:
    match = CODEPOINT_RE.fullmatch(value)
    if not match:
        raise ValueError(value)
    return int(match.group(1), 16)


def walk_strings(value: Any, path: str = "") -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if isinstance(value, str):
        result.append((path, value))
    elif isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}" if path else key
            result.extend(walk_strings(item, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.extend(walk_strings(item, f"{path}[{index}]"))
    return result


def provenance_fields(record: dict[str, Any]) -> list[str]:
    fields: list[str] = []

    def visit(value: Any, path: str) -> None:
        if path.split(".", 1)[0] in {"sources", "gaps", "conflicts"}:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                visit(item, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            if value:
                fields.append(path)
        elif value is not None:
            fields.append(path)

    visit(record, "")
    return fields


def source_covers(path: str, source_paths: set[str]) -> bool:
    return any(
        path == source_path
        or path.startswith(f"{source_path}.")
        or path.startswith(f"{source_path}[")
        for source_path in source_paths
    )


def check_record_count(records: list[dict[str, Any]], initial_errors: list[str], **_: Any) -> list[str]:
    errors = list(initial_errors)
    numbers = [record.get("kangxi_number") for record in records]
    if len(records) != 214:
        errors.append(f"loaded {len(records)} records, expected 214")
    if numbers != list(range(1, 215)):
        errors.append("record numbers are not exactly 1–214 in order")
    if len(set(numbers)) != len(numbers):
        errors.append("duplicate kangxi_number values")
    return errors


def check_schema(records: list[dict[str, Any]], schema: dict[str, Any], **_: Any) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for record in records:
        for error in sorted(validator.iter_errors(record), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.path) or "<root>"
            errors.append(f"radical {record.get('kangxi_number')}, {location}: {error.message}")
    return errors


def check_nfc_and_roundtrip(records: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    for record in records:
        number = record["kangxi_number"]
        for path, value in walk_strings(record):
            if not unicodedata.is_normalized("NFC", value):
                errors.append(f"radical {number}, {path}: string is not NFC")
        for path in ("primary", "radical_block"):
            item = record[path]
            try:
                cp = parse_codepoint(item["codepoint"])
            except ValueError:
                errors.append(f"radical {number}, {path}: invalid codepoint string")
                continue
            if len(item["char"]) != 1 or ord(item["char"]) != cp:
                errors.append(f"radical {number}, {path}: character/codepoint mismatch")
        for index, item in enumerate(record["variants"]):
            try:
                cp = parse_codepoint(item["codepoint"])
            except ValueError:
                errors.append(f"radical {number}, variants[{index}]: invalid codepoint string")
                continue
            if len(item["char"]) != 1 or ord(item["char"]) != cp:
                errors.append(f"radical {number}, variants[{index}]: character/codepoint mismatch")

    supplementary = chr(0x20000)
    decoded = json.loads(json.dumps({"char": supplementary}, ensure_ascii=False))["char"]
    if len(decoded) != 1 or ord(decoded) != 0x20000:
        errors.append("non-BMP U+20000 failed numeric codepoint JSON round-trip")
    return errors


def check_identity(
    records: list[dict[str, Any]], cjk_bases: dict[int, dict[str, Any]], **_: Any
) -> list[str]:
    errors: list[str] = []
    for record in records:
        number = record["kangxi_number"]
        expected = cjk_bases[number]
        if parse_codepoint(record["primary"]["codepoint"]) != expected["unified_cp"]:
            errors.append(f"radical {number}: primary differs from CJKRadicals.txt")
        if parse_codepoint(record["radical_block"]["codepoint"]) != expected["radical_cp"]:
            errors.append(f"radical {number}: radical_block differs from CJKRadicals.txt")
    return errors


def check_structure_precedence(
    records: list[dict[str, Any]],
    cjk_bases: dict[int, dict[str, Any]],
    unihan: dict[int, dict[str, str]],
    kanji: dict[int, list[dict[str, str]]],
    cns_stroke_sequences: dict[str, str],
    mmah_stroke_counts: dict[int, int],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    for record in records:
        number = record["kangxi_number"]
        cp = cjk_bases[number]["unified_cp"]
        properties = unihan[cp]
        stroke_values = properties.get("kTotalStrokes", "").split()
        if not stroke_values or not all(value.isdigit() for value in stroke_values):
            errors.append(f"radical {number}: missing or malformed Unihan kTotalStrokes")
            continue
        unihan_count = int(stroke_values[-1])
        cns_code = properties.get("kIRG_TSource", "")
        cns_code = cns_code[1:] if cns_code.startswith("T") else ""
        sequence = cns_stroke_sequences.get(cns_code)
        expected_count = len(sequence) if sequence else unihan_count
        expected_standard = "TW-CNS11643" if sequence else "Unicode-IRG-fallback"
        if record["stroke_count"] != expected_count:
            errors.append(
                f"radical {number}: stroke_count {record['stroke_count']} != precedence result {expected_count}"
            )
        if record["stroke_count_standard"] != expected_standard:
            errors.append(
                f"radical {number}: stroke_count_standard is not {expected_standard}"
            )

        expected_variants: list[tuple[int, str, str]] = []
        mmah_count = mmah_stroke_counts[cp]
        if mmah_count != expected_count:
            expected_variants.append(
                (mmah_count, "CN", builder.MMAH_GRAPHICS_ID)
            )
        if unihan_count != expected_count:
            expected_variants.append((unihan_count, "und", builder.UNIHAN_ID))
        radical_cp = cjk_bases[number]["radical_cp"]
        for row in kanji.get(number, []):
            if (
                row["Radical"] == chr(radical_cp)
                and row["Stroke#"].isdigit()
                and int(row["Stroke#"]) != expected_count
            ):
                expected_variants.append(
                    (int(row["Stroke#"]), "JP", builder.KANJI_ALIVE_ID)
                )
        actual_variants = [
            (item["count"], item["region"], item["source_id"])
            for item in record["stroke_count_variants"]
        ]
        if Counter(actual_variants) != Counter(expected_variants):
            errors.append(
                f"radical {number}: stroke-count variants do not preserve all comparison sources"
            )
        if any(item["count"] == expected_count for item in record["stroke_count_variants"]):
            errors.append(f"radical {number}: canonical count repeated as a variant")
        assignments = properties.get("kRSUnicode", "").split()
        assigned_numbers = {
            token.split(".", 1)[0].rstrip("'") for token in assignments if "." in token
        }
        if str(number) not in assigned_numbers:
            errors.append(
                f"radical {number}: Unihan kRSUnicode {assignments!r} lacks its own radical number"
            )
    return errors


def check_provenance(
    records: list[dict[str, Any]], registry: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    source_registry = registry["sources"]
    for record in records:
        number = record["kangxi_number"]
        sources = record["sources"]
        source_paths = set(sources)
        for field in provenance_fields(record):
            if not source_covers(field, source_paths):
                errors.append(f"radical {number}: non-null field {field} has no source mapping")
        for path, source_ids in sources.items():
            for source_id in source_ids:
                if source_id not in source_registry:
                    errors.append(f"radical {number}, {path}: unknown source ID {source_id}")
                elif source_registry[source_id]["status"] != "approved":
                    reference_only_allowed = (
                        source_registry[source_id]["status"] == "reference_only"
                        and path
                        in {
                            "stroke_order.standard",
                            "stroke_order.formal_conformance",
                        }
                    )
                    if not reference_only_allowed:
                        errors.append(
                            f"radical {number}, {path}: source {source_id} is not approved"
                        )

        gap_fields = {gap["field"] for gap in record["gaps"]}
        for name in EXPECTED_NAMES:
            path = f"names.{name}"
            if name not in record["names"] and path not in gap_fields:
                errors.append(f"radical {number}: missing {path} without a gap")
        for reading in EXPECTED_READINGS:
            path = f"readings.{reading}"
            if reading not in record["readings"] and path not in gap_fields:
                errors.append(f"radical {number}: missing {path} without a gap")

        if sources.get("kangxi_number") != [builder.CJK_RADICALS_ID]:
            errors.append(f"radical {number}: kangxi_number source is not CJKRadicals only")
        if sources.get("primary") != [builder.CJK_RADICALS_ID]:
            errors.append(f"radical {number}: primary source is not CJKRadicals only")
        if sources.get("radical_block") != [builder.CJK_RADICALS_ID]:
            errors.append(f"radical {number}: radical_block source is not CJKRadicals only")
        expected_stroke_sources = (
            [builder.CNS_ID, builder.UNIHAN_ID]
            if record["stroke_count_standard"] == "TW-CNS11643"
            else [builder.UNIHAN_ID]
        )
        if sources.get("stroke_count") != expected_stroke_sources:
            errors.append(f"radical {number}: stroke_count sources do not match its standard")
        if sources.get("stroke_count_standard") != expected_stroke_sources:
            errors.append(
                f"radical {number}: stroke_count_standard sources do not match its value"
            )
        expected_variant_sources = [
            builder.MMAH_GRAPHICS_ID,
            builder.UNIHAN_ID,
            builder.KANJI_ALIVE_ID,
        ]
        if sources.get("stroke_count_variants") != expected_variant_sources:
            errors.append(
                f"radical {number}: stroke_count_variants lacks comparison provenance"
            )
        if not set(sources.get("variants", [])).issubset(
            {builder.CJK_RADICALS_ID, builder.UNIHAN_ID}
        ):
            errors.append(f"radical {number}: variants use a non-structural source")
    return errors


def check_block_leakage(records: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    for record in records:
        number = record["kangxi_number"]
        for path, value in walk_strings(record):
            if path.startswith("sources") or path.startswith("gaps") or path.startswith("conflicts"):
                continue
            for character in value:
                cp = ord(character)
                if 0x2F00 <= cp <= 0x2FD5 or 0x2E80 <= cp <= 0x2EF3:
                    if path != "radical_block.char":
                        errors.append(
                            f"radical {number}, {path}: radical-block/supplement character {codepoint(cp)}"
                        )
    return errors


def check_variants(records: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    for record in records:
        number = record["kangxi_number"]
        primary = record["primary"]["codepoint"]
        values = [item["codepoint"] for item in record["variants"]]
        if len(values) != len(set(values)):
            errors.append(f"radical {number}: duplicate variant codepoints")
        if primary in values:
            errors.append(f"radical {number}: primary appears in variants")
    return errors


def valid_pinyin(value: str) -> bool:
    if not value or not unicodedata.is_normalized("NFC", value):
        return False
    for character in value:
        if character in {"'", "-"}:
            continue
        if not unicodedata.name(character, "").startswith("LATIN "):
            return False
    return not any(character.isdigit() for character in value)


def valid_zhuyin(value: str) -> bool:
    if not value or not unicodedata.is_normalized("NFC", value):
        return False
    tones = {0x02C9, 0x02CA, 0x02C7, 0x02CB, 0x02D9}
    return all(0x3105 <= ord(character) <= 0x312F or ord(character) in tones for character in value)


def check_readings(
    records: list[dict[str, Any]],
    cjk_bases: dict[int, dict[str, Any]],
    unihan: dict[int, dict[str, str]],
    cns_readings: dict[str, list[str]],
    bopomofo_to_pinyin: dict[str, str],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    for record in records:
        number = record["kangxi_number"]
        properties = unihan[cjk_bases[number]["unified_cp"]]
        cns_code = properties.get("kIRG_TSource", "")
        cns_code = cns_code[1:] if cns_code.startswith("T") else ""
        zhuyin_expected = builder.unique(cns_readings.get(cns_code, []))
        cns_pinyin = builder.unique(
            [bopomofo_to_pinyin[value] for value in zhuyin_expected if value in bopomofo_to_pinyin]
        )
        fallback = builder.unique(
            properties.get("kMandarin", "").split()
            + builder.parse_hanyu_pinyin(properties.get("kHanyuPinyin"))
        )
        expected_pinyin = cns_pinyin or fallback
        pinyin_items = record["readings"].get("pinyin", [])
        pinyin_list = [item["reading"] for item in pinyin_items]
        pinyin = set(pinyin_list)
        if pinyin_list != expected_pinyin:
            errors.append(
                f"radical {number}: canonical Pinyin does not follow Taiwan-first precedence"
            )
        for index, item in enumerate(pinyin_items):
            expected_context = "primary" if index == 0 else "additional"
            expected_region = "TW" if cns_pinyin else "und"
            expected_standard = (
                "TW-CNS11643" if cns_pinyin else "Unicode-kMandarin-fallback"
            )
            if (
                item["context"] != expected_context
                or item["region"] != expected_region
                or item["standard"] != expected_standard
            ):
                errors.append(f"radical {number}: malformed canonical Pinyin metadata")
        for value in pinyin:
            if not valid_pinyin(value):
                errors.append(f"radical {number}: invalid Pinyin {value!r}")
        expected_variants = builder.build_pinyin_variants(properties, expected_pinyin)
        actual_variants = record["readings"].get("pinyin_variants", [])
        if actual_variants != expected_variants:
            errors.append(
                f"radical {number}: Pinyin variants do not preserve Unihan/PRC evidence"
            )
        for item in actual_variants:
            if not valid_pinyin(item["reading"]):
                errors.append(
                    f"radical {number}: invalid variant Pinyin {item['reading']!r}"
                )
            if item["reading"] in pinyin:
                errors.append(
                    f"radical {number}: canonical Pinyin repeated as a variant"
                )
        for value in record["readings"].get("jyutping", []):
            if not JYUTPING_RE.fullmatch(value):
                errors.append(f"radical {number}: invalid Jyutping {value!r}")
        for value in record["readings"].get("zhuyin", []):
            if not valid_zhuyin(value):
                errors.append(f"radical {number}: invalid Zhuyin codepoints {value!r}")
                continue
            converted = bopomofo_to_pinyin.get(value)
            if converted is None:
                errors.append(f"radical {number}: Zhuyin {value!r} absent from conversion table")
            elif converted not in pinyin:
                errors.append(
                    f"radical {number}: Zhuyin {value!r} converts to {converted!r}, absent from Pinyin"
                )
    return errors


def check_acquisitions(registry: dict[str, Any], **_: Any) -> list[str]:
    errors: list[str] = []
    for source_id in (
        builder.UNIHAN_ID,
        builder.CJK_RADICALS_ID,
        builder.KANJI_ALIVE_ID,
        builder.CNS_ID,
        builder.MMAH_GRAPHICS_ID,
    ):
        try:
            builder.acquired_path(registry, source_id)
        except (KeyError, OSError, RuntimeError) as exc:
            errors.append(f"{source_id}: {exc}")
    try:
        cns_path = builder.acquired_path(registry, builder.CNS_ID)
        builder.parse_cns_readings(
            cns_path, registry["sources"][builder.CNS_ID]["acquisition"]
        )
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        errors.append(f"{builder.CNS_ID} member integrity: {exc}")
    try:
        mmah_path = builder.acquired_path(registry, builder.MMAH_GRAPHICS_ID)
        counts = builder.parse_mmah_stroke_counts(mmah_path, {ord("一")})
        if counts.get(ord("一")) != 1:
            errors.append(f"{builder.MMAH_GRAPHICS_ID}: sentinel 一 does not have one path")
    except (KeyError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        errors.append(f"{builder.MMAH_GRAPHICS_ID} parse integrity: {exc}")
    return errors


def compress_numbers(numbers: list[int]) -> str:
    if not numbers:
        return "—"
    numbers = sorted(set(numbers))
    ranges: list[str] = []
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number == previous + 1:
            previous = number
            continue
        ranges.append(str(start) if start == previous else f"{start}–{previous}")
        start = previous = number
    ranges.append(str(start) if start == previous else f"{start}–{previous}")
    return ", ".join(ranges)


def write_gaps_report(records: list[dict[str, Any]]) -> None:
    grouped: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        for gap in record["gaps"]:
            grouped[gap["reason"]][gap["field"]].append(record["kangxi_number"])
    total = sum(len(gaps) for record in records for gaps in [record["gaps"]])
    lines = [
        "# Gaps report",
        "",
        "Scope: Phase 1 radical identity, variants, stroke counts, names, and readings.",
        "",
        f"Total explicit gaps: **{total}**.",
        "",
    ]
    for reason in sorted(grouped):
        lines.extend([f"## `{reason}`", "", "| Field | Count | Kangxi radical numbers |", "|---|---:|---|"])
        for field in sorted(grouped[reason]):
            numbers = grouped[reason][field]
            lines.append(f"| `{field}` | {len(numbers)} | {compress_numbers(numbers)} |")
        lines.append("")
    lines.extend(
        [
            "Every omitted Phase 1 name or reading field is represented above. Future-phase fields are not counted as gaps until their phase begins.",
            "",
        ]
    )
    GAPS_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_validation_report(
    checks: list[tuple[str, str, list[str]]], records: list[dict[str, Any]]
) -> None:
    all_errors = [error for _, _, errors in checks for error in errors]
    lines = [
        "# Validation report",
        "",
        f"Generated: {utc_now()}",
        "",
        "Scope: Phase 1 automated validation of the 214-radical spine.",
        "",
        f"Overall result: **{'PASS' if not all_errors else 'FAIL'}**",
        "",
        "| Check | Result | Failures |",
        "|---|---|---:|",
    ]
    for name, _, errors in checks:
        lines.append(f"| {name} | **{'PASS' if not errors else 'FAIL'}** | {len(errors)} |")
    lines.extend(["", "## Check definitions", ""])
    for name, description, _ in checks:
        lines.append(f"- **{name}:** {description}")
    lines.extend(["", "## Full failure list", ""])
    if all_errors:
        lines.extend(f"- {error}" for error in all_errors)
    else:
        lines.append("None.")
    pinyin_variant_records = sum(
        bool(record["readings"].get("pinyin_variants")) for record in records
    )
    cn_pinyin_variant_records = sum(
        any(item["region"] == "CN" for item in record["readings"].get("pinyin_variants", []))
        for record in records
    )
    stroke_variant_records = sum(bool(record["stroke_count_variants"]) for record in records)
    cn_stroke_variant_records = sum(
        any(item["region"] == "CN" for item in record["stroke_count_variants"])
        for record in records
    )
    lines.extend(["", "## Resolved variants", ""])
    lines.append(
        f"Unresolved conflict records: **{sum(bool(record['conflicts']) for record in records)}**."
    )
    lines.append(f"- Records with noncanonical Pinyin evidence: **{pinyin_variant_records}**")
    lines.append(f"- Records with an explicit PRC Pinyin variant: **{cn_pinyin_variant_records}**")
    lines.append(f"- Records with a noncanonical stroke count: **{stroke_variant_records}**")
    lines.append(f"- Records with an explicit PRC-convention stroke count: **{cn_stroke_variant_records}**")
    lines.append("")
    VALIDATION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_phase_report(records: list[dict[str, Any]], checks: list[tuple[str, str, list[str]]]) -> None:
    gap_reasons = Counter(gap["reason"] for record in records for gap in record["gaps"])
    all_errors = [error for _, _, errors in checks for error in errors]
    tw_pinyin = [
        record["kangxi_number"]
        for record in records
        if record["readings"].get("pinyin", [{}])[0].get("region") == "TW"
    ]
    pinyin_variant_records = [
        record["kangxi_number"]
        for record in records
        if record["readings"].get("pinyin_variants")
    ]
    cn_pinyin_records = [
        record["kangxi_number"]
        for record in records
        if any(
            item["region"] == "CN"
            for item in record["readings"].get("pinyin_variants", [])
        )
    ]
    stroke_variant_records = [
        record["kangxi_number"] for record in records if record["stroke_count_variants"]
    ]
    cn_stroke_records = [
        record["kangxi_number"]
        for record in records
        if any(item["region"] == "CN" for item in record["stroke_count_variants"])
    ]
    unresolved = sum(bool(record["conflicts"]) for record in records)
    lines = [
        "# Phase 1 report",
        "",
        f"Status: **{'complete and validated' if not all_errors else 'validation failed'}**",
        "",
        "## Outcome",
        "",
        f"- Radical records completed: **{len(records)} / 214**",
        f"- Unresolved conflict records: **{unresolved}**",
        f"- Automated validation: **{'PASS' if not all_errors else 'FAIL'}**",
        "",
        "## Taiwan precedence and retained variants",
        "",
        f"- Taiwan CNS Pinyin is canonical for **{len(tw_pinyin)}** records; radicals 8, 15, and 20 use a documented Unicode fallback because CNS has no phonetic row.",
        f"- Noncanonical Unihan Pinyin evidence is retained for **{len(pinyin_variant_records)}** records.",
        f"- Explicit PRC `kTGHZ2013`/regional Pinyin variants occur in **{len(cn_pinyin_records)}** records ({compress_numbers(cn_pinyin_records)}).",
        f"- Noncanonical stroke counts occur in **{len(stroke_variant_records)}** records ({compress_numbers(stroke_variant_records)}).",
        f"- Explicit Make Me a Hanzi PRC-convention counts occur in **{len(cn_stroke_records)}** records ({compress_numbers(cn_stroke_records)}).",
        "- Unicode IRG and Japanese counts remain separately labeled when they differ; no losing value is discarded.",
    ]
    lines.extend(["", "## New gaps", ""])
    for reason, count in sorted(gap_reasons.items()):
        lines.append(f"- `{reason}`: {count}")
    lines.extend(
        [
            "",
            "The dominant gaps are systematic Traditional-Chinese and Korean learner-style radical names. Four radicals also lack a Unicode-mappable Kanji Alive row for English/Japanese labels.",
            "",
            "## Sources used",
            "",
            "- Unicode 17.0.0 `CJKRadicals.txt`: radical number, unified primary, and radical-block identity.",
            "- Unicode 17.0.0 Unihan: structural cross-check, Unicode IRG counts, variants, general readings, and PRC `kTGHZ2013` readings.",
            "- Kanji Alive commit `2d2a4931eec6e0cb532d5102766273c2323f96db`: English meanings used as radical labels and Japanese radical names.",
            "- CNS11643 server snapshot dated 2026-08-05: canonical Taiwan Zhuyin/Pinyin and stroke-sequence counts, using three independently hashed members that pass ZIP CRC checks.",
            "- Make Me a Hanzi commit `bddc96d41bef78427ed0e034e9f7e31d71fd1b92`: PRC-convention ordered-path counts for all 214 primary radical ideographs.",
            "",
            "## Failed or limited access",
            "",
            "- The CNS11643 `Properties.zip` snapshot has a valid central directory and exact advertised byte length, but full-archive testing fails on unrelated members. `CNS_phonetic.txt`, `CNS_pinyin_2.txt`, and `CNS_strokes_sequence.txt` independently pass CRC and SHA-256 checks and are admitted; damaged `CNS_source.txt` and `CNS_stroke.txt` remain excluded.",
            "- Kanji Alive has no Unicode-mappable primary radical row for Kangxi numbers 43, 52, 92, and 168; their English/Japanese labels remain gaps.",
            "- No source refused access during this phase.",
            "",
            "## Judgment calls made in Phase 1",
            "",
            "1. Kanji Alive's `Meaning` cell is represented as an English radical label, while `Reading-J` is represented as a Japanese radical name. Source strings are preserved without semantic rewriting.",
            "2. The radical schema extends the example with Unihan Japanese on/kun, Korean romanization, and Hangul readings so available sourced readings are not discarded.",
            "3. Taiwan CNS readings are canonical. PRC dictionary readings and other Unihan attestations are separate variants, so display precedence is resolved without erasing evidence.",
            "4. Taiwan stroke-sequence length is canonical when present. Make Me a Hanzi PRC-convention, Unicode IRG, and Kanji Alive Japanese disagreements are separate variants.",
            "5. Direct extraction from Taiwan MOE dictionary/stroke-learning datasets remains disallowed by their no-derivatives terms; CNS11643 is the open-data, MOE-aligned implementation source.",
            "6. Future Phase 2–5 fields are omitted rather than mislabeled as Phase 1 gaps.",
            "",
            "## Stop boundary",
            "",
            "Phase 2 has not begun. Review this revised Phase 1 precedence before radical enrichment.",
            "",
        ]
    )
    PHASE_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    registry = builder.load_registry()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    records, initial_errors = load_records()

    cjk_path = builder.acquired_path(registry, builder.CJK_RADICALS_ID)
    unihan_path = builder.acquired_path(registry, builder.UNIHAN_ID)
    cns_path = builder.acquired_path(registry, builder.CNS_ID)
    kanji_path = builder.acquired_path(registry, builder.KANJI_ALIVE_ID)
    mmah_path = builder.acquired_path(registry, builder.MMAH_GRAPHICS_ID)
    cjk_bases, cjk_variants = builder.parse_cjk_radicals(cjk_path)
    primary_cps = {row["unified_cp"] for row in cjk_bases.values()}
    unihan = builder.parse_unihan(
        unihan_path, primary_cps
    )
    kanji = builder.parse_kanji_alive(kanji_path, cjk_bases, cjk_variants)
    mmah_stroke_counts = builder.parse_mmah_stroke_counts(mmah_path, primary_cps)
    cns_readings, bopomofo_to_pinyin, cns_stroke_sequences = builder.parse_cns_readings(
        cns_path, registry["sources"][builder.CNS_ID]["acquisition"]
    )

    context = {
        "records": records,
        "initial_errors": initial_errors,
        "schema": schema,
        "registry": registry,
        "cjk_bases": cjk_bases,
        "unihan": unihan,
        "kanji": kanji,
        "mmah_stroke_counts": mmah_stroke_counts,
        "cns_readings": cns_readings,
        "bopomofo_to_pinyin": bopomofo_to_pinyin,
        "cns_stroke_sequences": cns_stroke_sequences,
    }
    definitions: list[tuple[str, str, Callable[..., list[str]]]] = [
        ("P1-01 Record set", "Exactly 214 numbered records, 1–214, with no gaps or duplicates.", check_record_count),
        ("P1-02 JSON Schema", "Every record validates against schema/radical.schema.json.", check_schema),
        ("P1-03 Unicode", "All strings are NFC; every character/codepoint pair and a non-BMP sentinel round-trip numerically.", check_nfc_and_roundtrip),
        ("P1-04 Radical identity", "Primary and radical-block codepoints exactly match Unicode CJKRadicals 17.0.0.", check_identity),
        ("P1-05 Taiwan stroke precedence", "Canonical counts use CNS11643 stroke sequences when present, all comparison values are preserved as variants, and primary ideographs carry their own kRSUnicode assignment.", check_structure_precedence),
        ("P1-06 Provenance and gaps", "Every non-null Phase 1 field has approved provenance; every absent scoped field has a valid gap.", check_provenance),
        ("P1-07 Radical-block isolation", "Kangxi/Supplement radical characters occur only in radical_block.char.", check_block_leakage),
        ("P1-08 Variant integrity", "Variant codepoints are unique and never repeat the primary ideograph.", check_variants),
        ("P1-09 Taiwan reading precedence", "Canonical Pinyin exactly follows CNS11643 where attested; PRC/Unihan alternatives remain variants; Pinyin, Jyutping, and Zhuyin syntax and conversion are valid.", check_readings),
        ("P1-10 Acquisition integrity", "Pinned source files, Make Me a Hanzi JSON rows, and admitted CNS members match their recorded integrity data.", check_acquisitions),
    ]
    checks: list[tuple[str, str, list[str]]] = []
    for name, description, function in definitions:
        checks.append((name, description, function(**context)))

    write_gaps_report(records)
    write_validation_report(checks, records)
    write_phase_report(records, checks)

    failures = sum(len(errors) for _, _, errors in checks)
    for name, _, errors in checks:
        print(f"{name}: {'PASS' if not errors else 'FAIL'} ({len(errors)} failures)")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
