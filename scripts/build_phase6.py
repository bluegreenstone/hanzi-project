#!/usr/bin/env python3
"""Run final corpus validation and build a deterministic release archive."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase1 as phase1  # noqa: E402
import build_phase3 as phase3  # noqa: E402
import build_phase4 as phase4  # noqa: E402
import validate_phase1 as validate1  # noqa: E402
import validate_phase3 as validate3  # noqa: E402
import validate_phase4 as validate4  # noqa: E402
import build_query_distributions as query_builder  # noqa: E402
import validate_query_distributions as query_validator  # noqa: E402


RELEASE_ID = "hanzi-corpus-2026-08-11"
ARCHIVE_PATH = ROOT / "dist" / f"{RELEASE_ID}.zip"
CHECKSUM_PATH = ROOT / "dist" / "SHA256SUMS"
RELEASE_METADATA_PATH = ROOT / "dist" / "release-metadata.json"
MANIFEST_PATH = ROOT / "metadata" / "manifests" / "phase6.json"
REPORT_PATH = ROOT / "docs" / "validation.md"
PHASE_REPORT_PATH = ROOT / "phase6-report.md"
REVIEW_PATH = ROOT / "metadata" / "audits" / "phase6-review-exceptions.json"
SVG_PATH = "{http://www.w3.org/2000/svg}path"
CODEPOINT_RE = re.compile(r"^U\+([0-9A-F]{4,6})$")
ZIP_TIMESTAMP = (2026, 8, 11, 0, 0, 0)
ALLOWED_PINYIN_MARKS = {"\u0300", "\u0301", "\u0302", "\u0304", "\u0308", "\u030c"}
ALLOWED_ZHUYIN_TONES = {0x02C9, 0x02CA, 0x02C7, 0x02CB, 0x02D9}
MOE_VARIANTS_ID = "moe-tw-dictionary-variants-2024-targeted-readings"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(stream: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(normalize(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_codepoint(value: str) -> int:
    match = CODEPOINT_RE.fullmatch(value)
    if not match:
        raise ValueError(value)
    return int(match.group(1), 16)


def load_json_records(directory: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted((ROOT / directory).glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return records, errors


def walk_strings(value: Any, path: str = "") -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if isinstance(value, str):
        result.append((path, value))
    elif isinstance(value, dict):
        for key, item in value.items():
            result.extend(walk_strings(item, f"{path}.{key}" if path else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.extend(walk_strings(item, f"{path}[{index}]"))
    return result


def collect_asset_references(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"asset_id", "svg_asset_id"} and isinstance(item, str):
                result.append(item)
            else:
                result.extend(collect_asset_references(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(collect_asset_references(item))
    return result


def valid_pinyin(value: str) -> bool:
    if not value or not unicodedata.is_normalized("NFC", value):
        return False
    if any(character.isdigit() or character.isupper() for character in value):
        return False
    for character in unicodedata.normalize("NFD", value):
        if character in {" ", "'", "-"}:
            continue
        if character in ALLOWED_PINYIN_MARKS:
            continue
        if character not in "abcdefghijklmnopqrstuvwxyz":
            return False
    return True


def valid_zhuyin(value: str) -> bool:
    if not value or not unicodedata.is_normalized("NFC", value):
        return False
    return all(
        character == " "
        or 0x3105 <= ord(character) <= 0x312F
        or 0x31A0 <= ord(character) <= 0x31BF
        or ord(character) in ALLOWED_ZHUYIN_TONES
        for character in value
    )


def check_radical_set(radicals: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    files = sorted((ROOT / "radicals").glob("*.json"))
    expected_names = {f"{number}.json" for number in range(1, 215)}
    actual_names = {path.name for path in files}
    if actual_names != expected_names:
        errors.append(
            f"radical filenames differ: missing={sorted(expected_names - actual_names)}, "
            f"extra={sorted(actual_names - expected_names)}"
        )
    numbers = sorted(item.get("kangxi_number") for item in radicals)
    if numbers != list(range(1, 215)):
        errors.append("kangxi_number values are not exactly 1-214")
    primaries = [item.get("primary", {}).get("codepoint") for item in radicals]
    if len(primaries) != len(set(primaries)):
        errors.append("radical primary codepoints are duplicated")
    return errors


def check_radical_unihan_counts(
    radicals: list[dict[str, Any]],
    unihan_radicals: dict[int, dict[str, str]],
    reviews: list[dict[str, Any]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    for record in radicals:
        cp = ord(record["primary"]["char"])
        raw_values = unihan_radicals.get(cp, {}).get("kTotalStrokes", "").split()
        if not raw_values or not all(item.isdigit() for item in raw_values):
            errors.append(f"radical {record['kangxi_number']}: malformed Unihan count")
            continue
        values = [int(item) for item in raw_values]
        if record["stroke_count"] in values:
            continue
        preserved = any(
            item["count"] in values
            and item["source_id"] == phase1.UNIHAN_ID
            for item in record["stroke_count_variants"]
        )
        if record["stroke_count_standard"] != "TW-CNS11643" or not preserved:
            errors.append(
                f"radical {record['kangxi_number']}: Taiwan/Unihan count mismatch is not preserved"
            )
            continue
        reviews.append(
            {
                "category": "radical_unihan_stroke_count",
                "record": f"radical:{record['kangxi_number']}",
                "codepoint": record["primary"]["codepoint"],
                "character": record["primary"]["char"],
                "canonical_taiwan_count": record["stroke_count"],
                "unihan_counts": values,
                "resolution": "Taiwan CNS remains canonical; Unihan is retained as a labeled variant.",
            }
        )
    return errors


def check_character_equations(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    radical_counts = {item["kangxi_number"]: item["stroke_count"] for item in radicals}
    for record in characters:
        radical = record["radical"]
        radical_count = radical_counts.get(radical["kangxi_number"])
        if radical_count is None:
            errors.append(f"{record['codepoint']}: radical number does not resolve")
            continue
        computed = radical_count + radical["residual_strokes"]
        conflicts = [
            item
            for item in record["conflicts"]
            if item["field"] == "radical.total_strokes_equation"
        ]
        if computed == record["total_strokes"]:
            if conflicts:
                errors.append(f"{record['codepoint']}: matching equation remains flagged")
            continue
        if len(conflicts) != 1:
            errors.append(
                f"{record['codepoint']}: {radical_count}+{radical['residual_strokes']} != "
                f"{record['total_strokes']} without exactly one review conflict"
            )
            continue
        reviews.append(
            {
                "category": "radical_total_strokes_equation",
                "record": record["codepoint"],
                "character": record["traditional"],
                "radical_number": radical["kangxi_number"],
                "radical_strokes": radical_count,
                "residual_strokes": radical["residual_strokes"],
                "computed_total": computed,
                "canonical_taiwan_total": record["total_strokes"],
                "resolution": conflicts[0]["resolution"],
                "detail": conflicts[0]["detail"],
            }
        )
    return errors


def check_referential_integrity(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    words: list[dict[str, Any]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    character_ids = {item["codepoint"] for item in characters}
    word_ids = {item["id"] for item in words}
    for radical in radicals:
        for value in radical.get("example_characters", []):
            if value not in character_ids:
                errors.append(f"radical {radical['kangxi_number']}: unresolved example {value}")
    for record in characters:
        for field in ("components", "confusable_with"):
            for value in record.get(field) or []:
                if value not in character_ids:
                    errors.append(f"{record['codepoint']}: unresolved {field} value {value}")
        for value in record.get("common_words", []):
            if value not in word_ids:
                errors.append(f"{record['codepoint']}: unresolved word {value}")
    for word in words:
        expected = [
            phase3.codepoint(ord(character))
            for character in word["traditional"]
            if phase3.is_han_unified(ord(character))
        ]
        if word["constituent_chars"] != expected:
            errors.append(f"{word['id']}: constituent codepoints differ from its headword")
    return errors


def check_provenance_and_schemas(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    words: list[dict[str, Any]],
    asset_manifest: dict[str, Any],
    registry: dict[str, Any],
    moe_concised: dict[str, list[dict[str, str]]],
    moe_revised: dict[str, list[dict[str, str]]],
    simplification_audit: dict[int, dict[str, Any]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate1.check_provenance(records=radicals, registry=registry))
    errors.extend(validate3.check_provenance(records=characters, registry=registry))
    errors.extend(validate4.check_provenance(words=words, registry=registry))
    phase3_context = {
        "moe_concised": moe_concised,
        "simplification_audit": simplification_audit,
    }
    errors.extend(
        validate3.check_official_simplification_audit(
            records=characters, context=phase3_context
        )
    )
    errors.extend(
        validate3.check_taiwan_definitions(
            records=characters, context=phase3_context
        )
    )
    errors.extend(
        validate4.check_taiwan_definitions(
            words=words,
            context={
                "moe_concised": moe_concised,
                "moe_revised": moe_revised,
            },
        )
    )
    specifications = (
        ("schema/radical.schema.json", radicals, "kangxi_number"),
        ("schema/character.schema.json", characters, "codepoint"),
        ("schema/word.schema.json", words, "id"),
        (
            "schema/stroke-order-asset.schema.json",
            asset_manifest.get("stroke_order_assets", []),
            "asset_id",
        ),
    )
    for schema_name, records, key in specifications:
        schema = json.loads((ROOT / schema_name).read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for record in records:
            for error in sorted(validator.iter_errors(record), key=lambda item: list(item.path)):
                location = ".".join(str(item) for item in error.path) or "<root>"
                errors.append(f"{record.get(key)}, {location}: {error.message}")
    for source_id, source in registry["sources"].items():
        if source["status"] == "approved" and not source.get("license", {}).get("verified"):
            errors.append(f"approved source lacks verified license: {source_id}")
    return errors


def check_assets(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    asset_manifest: dict[str, Any],
    registry: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    entries = (
        asset_manifest.get("assets", [])
        + asset_manifest.get("library_assets", [])
        + asset_manifest.get("stroke_order_assets", [])
    )
    quarantined_entries = asset_manifest.get("quarantined_assets", [])
    alias_entries = asset_manifest.get("provenance_alias_assets", [])
    retired_entries = asset_manifest.get("retired_unverified_assets", [])
    ids = [
        item.get("asset_id")
        for item in entries + quarantined_entries + alias_entries + retired_entries
    ]
    paths = [
        item.get("local_path")
        for item in entries + quarantined_entries + alias_entries + retired_entries
    ]
    if len(ids) != len(set(ids)):
        errors.append("asset IDs are not globally unique")
    if len(paths) != len(set(paths)):
        errors.append("asset paths are not globally unique")
    by_id = {item["asset_id"]: item for item in entries}
    for record in radicals + characters:
        label = record.get("codepoint", f"radical:{record.get('kangxi_number')}")
        for reference in collect_asset_references(record):
            if reference not in by_id:
                errors.append(f"{label}: unresolved asset reference {reference}")
    for entry in entries:
        label = entry["asset_id"]
        if not entry.get("license_id"):
            errors.append(f"{label}: license_id is absent")
        source_ids = entry.get("source_ids") or [entry.get("source_id")]
        for source_id in source_ids:
            source = registry["sources"].get(source_id)
            if source is None:
                errors.append(f"{label}: unknown asset source {source_id}")
            elif source.get("status") != "approved":
                errors.append(f"{label}: asset source is not approved: {source_id}")
        path = ROOT / entry["local_path"]
        if not path.is_file():
            errors.append(f"{label}: file is missing")
            continue
        if path.stat().st_size != entry["bytes"]:
            errors.append(f"{label}: byte count differs")
        if sha256_path(path) != entry["sha256"]:
            errors.append(f"{label}: SHA-256 differs")
    if len(quarantined_entries) != 455:
        errors.append("historical identity quarantine does not contain 455 assets")
    for entry in quarantined_entries:
        label = entry["asset_id"]
        source = registry["sources"].get(entry.get("source_id"))
        if not source or source.get("status") != "quarantine":
            errors.append(f"{label}: quarantine source status differs")
        if (
            entry.get("publication_status")
            != "quarantined_identity_unverified"
            or not entry.get("release_excluded")
        ):
            errors.append(f"{label}: publication quarantine markers are absent")
        path = ROOT / entry["local_path"]
        if not path.is_file() or sha256_path(path) != entry["sha256"]:
            errors.append(f"{label}: quarantined file integrity differs")
    if len(retired_entries) != 214:
        errors.append("superseded seal collection does not contain 214 assets")
    retired_source_ids = {
        "commons-shuowen-seal-files-2026-08-10",
        "commons-shuowen-540-svg-series-2026-08-10",
        "commons-ancient-chinese-character-seal-files-2026-08-10",
    }
    for entry in retired_entries:
        label = entry["asset_id"]
        source = registry["sources"].get(entry.get("source_id"))
        if (
            entry.get("source_id") not in retired_source_ids
            or not source
            or source.get("status") != "quarantine"
        ):
            errors.append(f"{label}: retired seal source status differs")
        if (
            entry.get("publication_status")
            != "superseded_unverified_community_vector"
            or not entry.get("release_excluded")
        ):
            errors.append(f"{label}: retired seal markers are absent")
        path = ROOT / entry["local_path"]
        if not path.is_file() or sha256_path(path) != entry["sha256"]:
            errors.append(f"{label}: retired seal file integrity differs")
    if len(alias_entries) != 1676:
        errors.append("exact-duplicate provenance alias count differs")
    for entry in alias_entries:
        label = entry["asset_id"]
        canonical = by_id.get(entry.get("alias_of_asset_id"))
        if (
            entry.get("publication_status")
            != "provenance_alias_exact_duplicate"
            or not entry.get("release_excluded")
        ):
            errors.append(f"{label}: provenance-alias markers are absent")
        if canonical is None or canonical["sha256"] != entry["sha256"]:
            errors.append(f"{label}: exact canonical alias target differs")
        path = ROOT / entry["local_path"]
        if not path.is_file() or sha256_path(path) != entry["sha256"]:
            errors.append(f"{label}: provenance-alias file integrity differs")
    expected_paths = set(paths)
    actual_paths = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "assets").rglob("*")
        if path.is_file() and path.name not in {"manifest.json", ".DS_Store"}
    }
    if actual_paths != expected_paths:
        for path in sorted(actual_paths - expected_paths):
            errors.append(f"unmanifested asset file: {path}")
        for path in sorted(expected_paths - actual_paths):
            errors.append(f"manifested asset file is absent: {path}")
    return errors


def check_stroke_svgs(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    asset_manifest: dict[str, Any],
    reviews: list[dict[str, Any]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    entries = {
        item["asset_id"]: item for item in asset_manifest.get("stroke_order_assets", [])
    }
    for label, record, canonical_count in [
        *[
            (f"radical:{item['kangxi_number']}", item, item["stroke_count"])
            for item in radicals
        ],
        *[
            (item["codepoint"], item, item["total_strokes"])
            for item in characters
        ],
    ]:
        order = record.get("stroke_order")
        if order is None:
            errors.append(f"{label}: stroke_order is null")
            continue
        entry = entries.get(order["svg_asset_id"])
        if entry is None:
            errors.append(f"{label}: stroke SVG asset does not resolve")
            continue
        try:
            root = ET.parse(ROOT / entry["local_path"]).getroot()
        except (OSError, ET.ParseError) as exc:
            errors.append(f"{label}: SVG cannot be parsed: {exc}")
            continue
        path_count = sum(1 for _ in root.iter(SVG_PATH))
        if path_count != order["stroke_count"] or path_count != entry["stroke_count"]:
            errors.append(f"{label}: SVG/order/manifest path counts differ")
            continue
        conflicts = order["standard_conflicts"]
        if path_count == canonical_count:
            if conflicts:
                errors.append(f"{label}: equal path/canonical counts remain flagged")
            continue
        if len(conflicts) != 1:
            errors.append(f"{label}: regional path-count difference lacks one conflict")
            continue
        conflict = conflicts[0]
        if (
            conflict["prc_path_count"] != path_count
            or conflict["taiwan_count"] != canonical_count
        ):
            errors.append(f"{label}: regional conflict values differ from records")
            continue
        reviews.append(
            {
                "category": "stroke_order_regional_count",
                "record": label,
                "character": entry["character"],
                "prc_svg_path_count": path_count,
                "canonical_taiwan_count": canonical_count,
                "resolution": "Both regional counts are retained; SVG paths are not altered.",
            }
        )
    return errors


def check_readings(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    words: list[dict[str, Any]],
    bopomofo_to_pinyin: dict[str, str],
    pinyin_to_bopomofo: dict[str, list[str]],
    moe_concised: dict[str, list[dict[str, str]]],
    moe_revised: dict[str, list[dict[str, str]]],
    moe_variant_pairs: dict[str, set[tuple[str, str]]],
    reviews: list[dict[str, Any]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    for label, readings in [
        *[(f"radical:{item['kangxi_number']}", item["readings"]) for item in radicals],
        *[(item["codepoint"], item["readings"]) for item in characters],
    ]:
        pinyin = [item["reading"] for item in readings.get("pinyin", [])]
        variants = [item["reading"] for item in readings.get("pinyin_variants", [])]
        for reading in pinyin + variants:
            if not valid_pinyin(reading):
                errors.append(f"{label}: invalid tone-mark Pinyin {reading!r}")
        zhuyin = readings.get("zhuyin", [])
        for reading in zhuyin:
            if not valid_zhuyin(reading):
                errors.append(f"{label}: invalid Zhuyin {reading!r}")
        if zhuyin:
            if len(zhuyin) != len(pinyin):
                errors.append(f"{label}: Pinyin/Zhuyin reading counts differ")
                continue
            for pinyin_reading, zhuyin_reading in zip(pinyin, zhuyin):
                mapped = bopomofo_to_pinyin.get(zhuyin_reading)
                if mapped == pinyin_reading:
                    continue
                if (pinyin_reading, zhuyin_reading) in moe_variant_pairs.get(label, set()):
                    reviews.append(
                        {
                            "category": "official_zhuyin_pinyin_outside_cns_table",
                            "record": label,
                            "character": next(
                                item["traditional"]
                                for item in characters
                                if item["codepoint"] == label
                            ),
                            "pinyin": pinyin_reading,
                            "zhuyin": zhuyin_reading,
                            "cns_conversion": mapped,
                            "source_id": MOE_VARIANTS_ID,
                            "resolution": (
                                "The exact paired Pinyin/Zhuyin values on the Taiwan MOE "
                                "Dictionary of Variants 正字 entry remain canonical; the "
                                "CNS conversion table has no row for this syllable."
                            ),
                        }
                    )
                    continue
                errors.append(f"{label}: Zhuyin-to-Pinyin table mapping differs")
    for word in words:
        pinyin_rows = word.get("pinyin") or []
        pinyin_by_value = {
            item["reading"]: phase4.moe_pronunciations.source_refs(item)
            for item in pinyin_rows
        }
        for reading in pinyin_by_value:
            if not valid_pinyin(reading):
                errors.append(f"{word['id']}: invalid tone-mark Pinyin {reading!r}")
        for item in word.get("zhuyin") or []:
            reading = item["reading"]
            if not valid_zhuyin(reading):
                errors.append(f"{word['id']}: invalid Zhuyin {reading!r}")
            if item["pinyin"] not in pinyin_by_value:
                errors.append(f"{word['id']}: Zhuyin lacks its Pinyin row")
                continue
            if phase4.moe_pronunciations.source_refs(item) != pinyin_by_value[item["pinyin"]]:
                errors.append(f"{word['id']}: Zhuyin/Pinyin source entries differ")
        pronunciation_source = word.get("sources", {}).get("pinyin")
        sources_agree = (
            pronunciation_source == word.get("sources", {}).get("zhuyin")
        )
        official_rows = {
            phase4.MOE_CONCISED_ID: moe_concised,
            phase4.MOE_REVISED_ID: moe_revised,
        }
        official_source = (
            pronunciation_source[0]
            if sources_agree
            and isinstance(pronunciation_source, list)
            and len(pronunciation_source) == 1
            and pronunciation_source[0] in official_rows
            else None
        )
        if official_source:
            source_rows = official_rows[official_source].get(
                word["traditional"], []
            )
            expected_pinyin, expected_zhuyin = phase4.moe_pronunciations.moe_readings(
                source_rows
            )
            if pinyin_rows != expected_pinyin or (word.get("zhuyin") or []) != expected_zhuyin:
                errors.append(
                    f"{word['id']}: Taiwan MOE reading or entry IDs differ"
                )
        else:
            for item in word.get("zhuyin") or []:
                expected = phase4.pinyin_to_zhuyin(
                    item["pinyin"], pinyin_to_bopomofo
                )
                if item["reading"] != expected:
                    errors.append(
                        f"{word['id']}: Zhuyin conversion-table result differs"
                    )
    return errors


def check_simplification_roundtrip(
    characters: list[dict[str, Any]], **_: Any
) -> list[str]:
    errors: list[str] = []
    by_simplified: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in characters:
        simplified = record["simplified"]
        note = record["simplification_note"]
        if simplified:
            by_simplified[simplified].append(record)
        if note is not None:
            expected = phase3.codepoint(ord(simplified)) if simplified else None
            if note["simplified"] != expected:
                errors.append(f"{record['codepoint']}: simplification note target differs")
            if len(note["traditional_origins"]) < 2:
                errors.append(f"{record['codepoint']}: one-to-many note has fewer than two origins")
            if record["codepoint"] not in note["traditional_origins"]:
                errors.append(f"{record['codepoint']}: one-to-many note omits its own origin")
        if simplified is None:
            has_conflict = any(item["field"] == "simplified" for item in record["conflicts"])
            has_gap = any(item["field"] == "simplified" for item in record["gaps"])
            if not has_conflict and not has_gap:
                errors.append(f"{record['codepoint']}: null Simplified mapping is unexplained")
    for simplified, records in by_simplified.items():
        if len(records) < 2:
            continue
        delivered_origins = {item["codepoint"] for item in records}
        for record in records:
            note = record["simplification_note"]
            if note is None or not delivered_origins.issubset(note["traditional_origins"]):
                errors.append(
                    f"{record['codepoint']}: shared Simplified form {simplified} is not fully flagged"
                )
    return errors


def check_radical_block_isolation(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    words: list[dict[str, Any]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    for label, record in [
        *[(f"radical:{item['kangxi_number']}", item) for item in radicals],
        *[(item["codepoint"], item) for item in characters],
        *[(item["id"], item) for item in words],
    ]:
        for path, value in walk_strings(record):
            for character in value:
                cp = ord(character)
                if 0x2F00 <= cp <= 0x2FD5 or 0x2E80 <= cp <= 0x2EF3:
                    if not (label.startswith("radical:") and path == "radical_block.char"):
                        errors.append(f"{label}, {path}: forbidden radical character U+{cp:04X}")
    return errors


def check_unicode_and_record_files(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    words: list[dict[str, Any]],
    load_errors: list[str],
    **_: Any,
) -> list[str]:
    errors = list(load_errors)
    if len(characters) != 2000:
        errors.append(f"character count is {len(characters)}, expected 2000")
    if len(words) != 13368:
        errors.append(f"word count is {len(words)}, expected 13368")
    character_ids = [item.get("codepoint") for item in characters]
    word_ids = [item.get("id") for item in words]
    if len(character_ids) != len(set(character_ids)):
        errors.append("character codepoints are duplicated")
    if len(word_ids) != len(set(word_ids)):
        errors.append("word IDs are duplicated")
    for label, record in [
        *[(f"radical:{item['kangxi_number']}", item) for item in radicals],
        *[(item["codepoint"], item) for item in characters],
        *[(item["id"], item) for item in words],
    ]:
        if not phase3.is_nfc_except_verbatim_text(record):
            errors.append(f"{label}: a non-verbatim record field is not NFC")
    sentinel = chr(0x20000)
    roundtrip = json.loads(json.dumps({"char": sentinel}, ensure_ascii=False))["char"]
    if len(roundtrip) != 1 or ord(roundtrip) != 0x20000:
        errors.append("non-BMP U+20000 failed numeric JSON round-trip")
    return errors


def release_payload_paths() -> list[Path]:
    paths: set[Path] = set()
    for directory, pattern in (
        ("radicals", "*.json"),
        ("characters", "*.json"),
        ("words", "*.json"),
        ("schema", "*.json"),
    ):
        root = ROOT / directory
        candidates = root.glob(pattern)
        paths.update(
            path for path in candidates if path.is_file() and path.name != ".DS_Store"
        )
    asset_manifest_path = ROOT / "assets" / "manifest.json"
    asset_manifest = json.loads(asset_manifest_path.read_text(encoding="utf-8"))
    paths.add(asset_manifest_path)
    for item in (
        asset_manifest.get("assets", [])
        + asset_manifest.get("library_assets", [])
        + asset_manifest.get("stroke_order_assets", [])
    ):
        paths.add(ROOT / item["local_path"])
    paths.update(
        {
            ROOT / "README.md",
            ROOT / "requirements-release.txt",
            ROOT / "sources.json",
            ROOT / "licenses" / "profiles.json",
            ROOT / "scripts" / "build_query_distributions.py",
            ROOT / "scripts" / "validate_query_distributions.py",
        }
    )
    paths.update(path for path in (ROOT / "docs").glob("*.md") if path.is_file())
    paths.update(
        path
        for path in (ROOT / "metadata" / "manifests").glob("phase[1-5].json")
        if path.is_file()
    )
    paths.update(path for path in (ROOT / "query").rglob("*") if path.is_file())
    return sorted(paths, key=lambda item: str(item.relative_to(ROOT)))


def check_query_distributions(query_errors: list[str], **_: Any) -> list[str]:
    return list(query_errors)


def check_release_plan(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    words: list[dict[str, Any]],
    asset_manifest: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    paths = release_payload_paths()
    relative = {str(path.relative_to(ROOT)) for path in paths}
    required = {
        "README.md",
        "sources.json",
        "assets/manifest.json",
        "docs/attribution.md",
        "docs/caveats.md",
        "docs/gaps.md",
        "docs/licensing.md",
        "docs/schema-versioning.md",
        "docs/source-audit.md",
        "docs/validation.md",
        "docs/verification-policy.md",
        "licenses/profiles.json",
        "metadata/manifests/phase5.json",
        "query/README.md",
        "query/examples.sql",
        "query/hanzi.sqlite3",
        "query/manifest.json",
        "query/migrations/0001_initial.sql",
        "schema/radical.schema.json",
        "schema/character.schema.json",
        "schema/word.schema.json",
        "schema/stroke-order-asset.schema.json",
        "scripts/build_query_distributions.py",
        "scripts/validate_query_distributions.py",
    }
    for path in sorted(required - relative):
        errors.append(f"release payload lacks required file: {path}")
    if any(
        path.startswith("source-data/")
        or path.startswith("quarantine/")
        or path.startswith("tmp/")
        or path.startswith("build/")
        or path.startswith("metadata/audits/")
        or path.endswith("-report.md")
        or path.endswith("/.DS_Store")
        or path == ".DS_Store"
        for path in relative
    ):
        errors.append("release payload includes internal build/audit material")
    manifest_paths = {
        item["local_path"]
        for item in (
            asset_manifest.get("assets", [])
            + asset_manifest.get("library_assets", [])
            + asset_manifest.get("stroke_order_assets", [])
        )
    }
    for path in sorted(manifest_paths - relative):
        errors.append(f"release payload omits manifested asset: {path}")
    quarantined_paths = {
        item["local_path"]
        for item in asset_manifest.get("quarantined_assets", [])
    }
    for path in sorted(quarantined_paths & relative):
        errors.append(f"release payload includes quarantined asset: {path}")
    alias_paths = {
        item["local_path"]
        for item in asset_manifest.get("provenance_alias_assets", [])
    }
    for path in sorted(alias_paths & relative):
        errors.append(f"release payload includes exact-duplicate alias asset: {path}")
    retired_paths = {
        item["local_path"]
        for item in asset_manifest.get("retired_unverified_assets", [])
    }
    for path in sorted(retired_paths & relative):
        errors.append(f"release payload includes a retired Commons seal asset: {path}")
    if len([path for path in relative if path.startswith("radicals/")]) != len(radicals):
        errors.append("release radical file count differs")
    if len([path for path in relative if path.startswith("characters/")]) != len(characters):
        errors.append("release character file count differs")
    if len([path for path in relative if path.startswith("words/")]) != len(words):
        errors.append("release word file count differs")
    query_manifest = json.loads((ROOT / "query" / "manifest.json").read_text())
    query_files = {
        query_manifest["database"]["path"],
        *(item["path"] for item in query_manifest["files"]),
    }
    for path in sorted(query_files - relative):
        errors.append(f"release payload omits query distribution file: {path}")
    return errors


def check_detail(check_id: str, context: dict[str, Any]) -> str:
    reviews = Counter(item["category"] for item in context["reviews"])
    details = {
        "P6-01": "Exactly 214 radical records, numbered 1-214, with unique unified primaries.",
        "P6-02": (
            "Radical counts match Unihan except "
            f"{reviews['radical_unihan_stroke_count']} reviewed Taiwan-precedence variants."
        ),
        "P6-03": (
            "Every character equation matches or has exactly one preserved review conflict; "
            f"{reviews['radical_total_strokes_equation']} reviewed positional-form exceptions."
        ),
        "P6-04": "All scoped character/component/confusable/word joins resolve, and word constituents reproduce their headword codepoints.",
        "P6-05": "Every non-null record field has registered provenance; schemas validate; official simplification adjudications and verbatim Taiwan definitions exactly reproduce pinned sources.",
        "P6-06": "Every asset reference resolves to one uniquely manifested, licensed, hash-verified file.",
        "P6-07": (
            "Every SVG path count matches its asset and stroke-order object; "
            f"{reviews['stroke_order_regional_count']} Taiwan/PRC record-count differences are preserved."
        ),
        "P6-08": (
            "Pinyin syntax and Zhuyin codepoints pass; MOE-covered records reproduce "
            "exact official readings/entry IDs, including "
            f"{reviews['official_zhuyin_pinyin_outside_cns_table']} exact MOE pair outside "
            "the CNS conversion table; uncovered words reproduce the declared CNS conversion."
        ),
        "P6-09": "Every delivered many-Traditional-to-one-Simplified mapping is flagged, and all 37 formerly conflicting candidates reproduce the official PRC-table adjudication.",
        "P6-10": "Kangxi Radical and CJK Radical Supplement characters occur only in radical_block.char.",
        "P6-11": "Record counts, unique IDs, NFC outside explicitly verbatim source cells, and a non-BMP JSON sentinel all pass.",
        "P6-12": "The deterministic release payload contains every final record, user document, query distribution, schema, manifest, and released asset while excluding internal build/audit material.",
        "P6-13": "SQLite integrity, relational counts, indexed lookups, profile isolation, JSONL/Parquet equivalence, and query-file hashes all pass.",
    }
    return details[check_id]


def write_reports(
    checks: list[tuple[str, str, list[str]]],
    context: dict[str, Any],
) -> None:
    passed = all(not errors for _, _, errors in checks)
    review_counts = Counter(item["category"] for item in context["reviews"])
    lines = [
        "# Validation report",
        "",
        f"Phase 6 status: **{'PASS' if passed else 'FAIL'}**",
        "",
        f"Release: `{RELEASE_ID}`",
        "",
        "| Check | Result | Detail |",
        "|---|---:|---|",
    ]
    for check_id, detail, errors in checks:
        lines.append(
            f"| {check_id} | {'PASS' if not errors else 'FAIL'} | "
            + (detail if not errors else f"{len(errors)} failure(s)")
            + " |"
        )
    for check_id, _, errors in checks:
        if errors:
            lines.extend(["", f"## {check_id} failures", ""])
            lines.extend(f"- {error}" for error in errors)
    lines.extend(
        [
            "",
            "## Reviewed exceptions (not validation failures)",
            "",
            f"- Taiwan radical count versus Unihan: **{review_counts['radical_unihan_stroke_count']}**",
            f"- Radical-plus-residual equation: **{review_counts['radical_total_strokes_equation']}**",
            f"- Taiwan canonical count versus PRC-convention SVG paths: **{review_counts['stroke_order_regional_count']}**",
            f"- Exact MOE Pinyin/Zhuyin pair absent from CNS conversion table: **{review_counts['official_zhuyin_pinyin_outside_cns_table']}**",
            "",
            "Every item is serialized in `metadata/audits/phase6-review-exceptions.json`; an unflagged mismatch fails its check.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    package_name = ARCHIVE_PATH.name
    phase_lines = [
        "# Phase 6 report — validation and packaging",
        "",
        f"Status: **{'PASS' if passed else 'FAIL'}**",
        "",
        "## Outcome",
        "",
        f"- Radical records: **{len(context['radicals'])}**",
        f"- Character records: **{len(context['characters']):,}**",
        f"- Word records: **{len(context['words']):,}**",
        f"- Manifested assets: **{context['asset_count']:,}**",
        f"- Validation checks: **{sum(not errors for _, _, errors in checks)} / {len(checks)} passed**",
        f"- Release archive: `dist/{package_name}`",
        "",
        "## Packaging profile",
        "",
        "The archive contains final records, released assets, schemas, provenance and license metadata, user documentation, a normalized SQLite database, and equivalent relational JSONL and Parquet tables. ZIP entry order, timestamps, permissions, and compression settings are fixed for deterministic output.",
        "",
        "Raw acquisitions, quarantine, temporary review files, detailed internal audits, and phase reports are intentionally excluded. Their source URLs, versions, hashes, and release decisions remain recorded in `sources.json`, the public manifests, and the Git repository.",
        "",
        "The package checksum is written beside the archive in `dist/SHA256SUMS`; `dist/release-metadata.json` records its byte length and SHA-256.",
        "",
    ]
    PHASE_REPORT_PATH.write_text("\n".join(phase_lines), encoding="utf-8")


def build_payload_manifest(context: dict[str, Any]) -> dict[str, Any]:
    payload = []
    for path in release_payload_paths():
        payload.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_path(path),
            }
        )
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()
    reviews = Counter(item["category"] for item in context["reviews"])
    phase5 = json.loads((ROOT / "metadata" / "manifests" / "phase5.json").read_text(encoding="utf-8"))
    return {
        "phase": 6,
        "release_id": RELEASE_ID,
        "release_date": "2026-08-11",
        "validation_status": "PASS",
        "record_counts": {
            "radicals": len(context["radicals"]),
            "characters": len(context["characters"]),
            "words": len(context["words"]),
        },
        "asset_count": context["asset_count"],
        "query_distribution": {
            "schema_version": context["query_manifest"]["query_schema_version"],
            "database": context["query_manifest"]["database"],
            "profiles": sorted(context["query_manifest"]["profiles"]),
            "row_counts": context["query_manifest"]["row_counts"],
        },
        "stroke_order_coverage": {
            "radicals": phase5["radical_svg_reference_count"],
            "characters": phase5["character_svg_reference_count"],
            "exact_source_assets": phase5["exact_source_asset_count"],
            "reconstructed_assets": phase5["reconstructed_asset_count"],
        },
        "review_exception_counts": dict(sorted(reviews.items())),
        "package": {
            "format": "zip",
            "filename": ARCHIVE_PATH.name,
            "root_directory": RELEASE_ID,
            "file_count": len(payload) + 1,
            "payload_file_count_excluding_this_manifest": len(payload),
            "payload_digest_sha256": digest,
            "fixed_zip_timestamp": "2026-08-11T00:00:00",
            "excludes": [
                "source-data/",
                "quarantine/",
                "tmp/",
                "build/",
                "metadata/audits/",
                "phase*-report.md",
                ".DS_Store",
                "scripts/__pycache__/",
            ],
        },
        "payload_files": payload,
        "builder": "scripts/build_phase6.py",
    }


def write_zip_entry(archive: zipfile.ZipFile, path: Path) -> None:
    relative = str(path.relative_to(ROOT))
    info = zipfile.ZipInfo(f"{RELEASE_ID}/{relative}", ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    with path.open("rb") as source, archive.open(info, "w") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def build_archive(payload_paths: list[Path]) -> dict[str, Any]:
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        ARCHIVE_PATH,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for path in sorted(
            [*payload_paths, MANIFEST_PATH],
            key=lambda item: str(item.relative_to(ROOT)),
        ):
            write_zip_entry(archive, path)

    expected = {
        f"{RELEASE_ID}/{path.relative_to(ROOT)}": (path.stat().st_size, sha256_path(path))
        for path in [*payload_paths, MANIFEST_PATH]
    }
    with zipfile.ZipFile(ARCHIVE_PATH) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise RuntimeError("release archive entry set differs from payload")
        if archive.testzip() is not None:
            raise RuntimeError("release archive CRC verification failed")
        for name, (expected_bytes, expected_sha) in expected.items():
            info = archive.getinfo(name)
            if info.file_size != expected_bytes:
                raise RuntimeError(f"archive byte count differs: {name}")
            with archive.open(name) as stream:
                if sha256_stream(stream) != expected_sha:
                    raise RuntimeError(f"archive content digest differs: {name}")

    metadata = {
        "release_id": RELEASE_ID,
        "archive": ARCHIVE_PATH.name,
        "bytes": ARCHIVE_PATH.stat().st_size,
        "sha256": sha256_path(ARCHIVE_PATH),
        "file_count": len(expected),
        "payload_manifest": str(MANIFEST_PATH.relative_to(ROOT)),
        "payload_manifest_sha256": sha256_path(MANIFEST_PATH),
        "verification": "ZIP CRC, entry set, uncompressed byte lengths, and per-file SHA-256 all passed.",
    }
    write_json(RELEASE_METADATA_PATH, metadata)
    CHECKSUM_PATH.write_text(
        f"{metadata['sha256']}  {ARCHIVE_PATH.name}\n",
        encoding="utf-8",
    )
    return metadata


def main() -> None:
    query_manifest = query_builder.build()
    query_errors = query_validator.validate()
    registry = phase3.load_registry()
    radicals, radical_errors = load_json_records("radicals")
    characters, character_errors = load_json_records("characters")
    words, word_errors = load_json_records("words")
    radicals.sort(key=lambda item: item.get("kangxi_number", 0))
    characters.sort(key=lambda item: item.get("frequency", {}).get("selection_rank", 0))
    words.sort(key=lambda item: item.get("frequency", {}).get("rank", 0))
    asset_manifest = json.loads((ROOT / "assets" / "manifest.json").read_text(encoding="utf-8"))
    asset_entries = (
        asset_manifest.get("assets", [])
        + asset_manifest.get("library_assets", [])
        + asset_manifest.get("stroke_order_assets", [])
    )

    radical_cps = {ord(item["primary"]["char"]) for item in radicals}
    unihan_radicals = phase1.parse_unihan(
        phase1.acquired_path(registry, phase1.UNIHAN_ID), radical_cps
    )
    _, bopomofo_to_pinyin, _, _ = phase3.parse_cns(
        registry, phase3.acquired_path(registry, phase3.CNS_ID)
    )
    pinyin_to_bopomofo: dict[str, list[str]] = defaultdict(list)
    for bopomofo, pinyin in bopomofo_to_pinyin.items():
        if bopomofo not in pinyin_to_bopomofo[pinyin]:
            pinyin_to_bopomofo[pinyin].append(bopomofo)
    moe_concised = phase4.load_moe_rows(
        phase3.acquired_path(registry, phase4.MOE_CONCISED_ID)
    )
    moe_revised = phase4.load_moe_rows(
        phase3.acquired_path(registry, phase4.MOE_REVISED_ID)
    )
    simplification_audit = phase3.load_simplification_audit(
        registry,
        {parse_codepoint(item["codepoint"]) for item in characters},
    )
    variant_payload = json.loads(
        phase3.acquired_path(registry, MOE_VARIANTS_ID).read_text(encoding="utf-8")
    )
    moe_variant_pairs: dict[str, set[tuple[str, str]]] = {}
    for entry in variant_payload["entries"]:
        if len(entry["pinyin"]) != len(entry["zhuyin"]):
            raise RuntimeError(
                f"MOE Variant reading pair count differs: {entry['codepoint']}"
            )
        moe_variant_pairs[entry["codepoint"]] = set(
            zip(entry["pinyin"], entry["zhuyin"])
        )

    context: dict[str, Any] = {
        "radicals": radicals,
        "characters": characters,
        "words": words,
        "asset_manifest": asset_manifest,
        "asset_count": len(asset_entries),
        "registry": registry,
        "unihan_radicals": unihan_radicals,
        "bopomofo_to_pinyin": bopomofo_to_pinyin,
        "pinyin_to_bopomofo": pinyin_to_bopomofo,
        "moe_concised": moe_concised,
        "moe_revised": moe_revised,
        "simplification_audit": simplification_audit,
        "moe_variant_pairs": moe_variant_pairs,
        "load_errors": radical_errors + character_errors + word_errors,
        "reviews": [],
        "query_manifest": query_manifest,
        "query_errors": query_errors,
    }
    definitions: list[tuple[str, Callable[..., list[str]]]] = [
        ("P6-01", check_radical_set),
        ("P6-02", check_radical_unihan_counts),
        ("P6-03", check_character_equations),
        ("P6-04", check_referential_integrity),
        ("P6-05", check_provenance_and_schemas),
        ("P6-06", check_assets),
        ("P6-07", check_stroke_svgs),
        ("P6-08", check_readings),
        ("P6-09", check_simplification_roundtrip),
        ("P6-10", check_radical_block_isolation),
        ("P6-11", check_unicode_and_record_files),
        ("P6-12", check_release_plan),
        ("P6-13", check_query_distributions),
    ]
    checks: list[tuple[str, str, list[str]]] = []
    for check_id, function in definitions:
        errors = function(**context)
        checks.append((check_id, check_detail(check_id, context), errors))

    context["reviews"].sort(
        key=lambda item: (item["category"], item["record"])
    )
    review_payload = {
        "phase": 6,
        "status": "reviewed_exceptions_not_validation_failures",
        "counts": dict(
            sorted(Counter(item["category"] for item in context["reviews"]).items())
        ),
        "exceptions": context["reviews"],
    }
    write_json(REVIEW_PATH, review_payload)
    write_reports(checks, context)

    failures = sum(bool(errors) for _, _, errors in checks)
    print(
        f"Phase 6 corpus validation: {'PASS' if failures == 0 else 'FAIL'} "
        f"({len(checks) - failures}/{len(checks)} checks passed)"
    )
    if failures:
        for check_id, _, errors in checks:
            if errors:
                print(f"{check_id}: {len(errors)} failure(s)")
                for error in errors[:20]:
                    print(f"  - {error}")
        raise SystemExit(1)

    manifest = build_payload_manifest(context)
    write_json(MANIFEST_PATH, manifest)
    payload_paths = release_payload_paths()
    metadata = build_archive(payload_paths)
    print(
        f"built {ARCHIVE_PATH.relative_to(ROOT)}: {metadata['file_count']:,} files, "
        f"{metadata['bytes']:,} bytes, sha256 {metadata['sha256']}"
    )


if __name__ == "__main__":
    main()
