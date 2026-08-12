#!/usr/bin/env python3
"""Validate Phase 3 and write the current validation, gap, and phase reports."""

from __future__ import annotations

import hashlib
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
import build_phase3 as builder  # noqa: E402
import validate_phase2 as validate2  # noqa: E402


CHARACTERS_PATH = ROOT / "characters"
SCHEMA_PATH = ROOT / "schema" / "character.schema.json"
MANIFEST_PATH = ROOT / "metadata" / "manifests" / "phase3.json"
VALIDATION_REPORT_PATH = ROOT / "docs" / "validation.md"
GAPS_REPORT_PATH = ROOT / "docs" / "gaps.md"
PHASE_REPORT_PATH = ROOT / "phase3-report.md"

CODEPOINT_RE = re.compile(r"^U\+([0-9A-F]{4,6})$")


def phase3_projection(record: dict[str, Any]) -> dict[str, Any]:
    """Remove backward-compatible Phase 4 enrichment from a character record."""
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


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_codepoint(value: str) -> int:
    match = CODEPOINT_RE.fullmatch(value)
    if not match:
        raise ValueError(value)
    return int(match.group(1), 16)


def load_records() -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    files = sorted(CHARACTERS_PATH.glob("*.json"))
    if len(files) != 2000:
        errors.append(f"characters/ has {len(files)} JSON files, expected 2000")
    records: list[dict[str, Any]] = []
    seen_codepoints: set[str] = set()
    seen_selection_ranks: set[int] = set()
    for path in files:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        record_cp = record.get("codepoint")
        if path.stem != record_cp:
            errors.append(f"{path.name}: filename does not match codepoint {record_cp!r}")
        if record_cp in seen_codepoints:
            errors.append(f"duplicate record codepoint: {record_cp}")
        seen_codepoints.add(record_cp)
        selection_rank = record.get("frequency", {}).get("selection_rank")
        if selection_rank in seen_selection_ranks:
            errors.append(f"duplicate selection_rank: {selection_rank}")
        seen_selection_ranks.add(selection_rank)
        records.append(record)
    records.sort(key=lambda item: item.get("frequency", {}).get("selection_rank", 0))
    if [record.get("frequency", {}).get("selection_rank") for record in records] != list(
        range(1, 2001)
    ):
        errors.append("selection_rank values are not exactly 1–2000")
    return records, errors


def load_context(registry: dict[str, Any]) -> dict[str, Any]:
    paths = {
        source_id: builder.acquired_path(registry, source_id)
        for source_id in (
            builder.MOE_ID,
            builder.UNIHAN_ID,
            builder.CJK_RADICALS_ID,
            builder.EQUIVALENT_IDEOGRAPH_ID,
            builder.CNS_ID,
            builder.MMAH_DICTIONARY_ID,
            builder.MMAH_GRAPHICS_ID,
            builder.CC_CEDICT_ID,
            builder.PRC_STANDARD_ID,
            builder.MOE_CONCISED_ID,
        )
    }
    rows, corpus_total, exclusions = builder.read_moe_frequency(
        registry, paths[builder.MOE_ID]
    )
    selected_cps = {ord(row["character"]) for row in rows}
    radical_map, _ = builder.parse_cjk_radicals(paths[builder.CJK_RADICALS_ID])
    radical_mapping_sources = {
        cp: builder.CJK_RADICALS_ID for cp in radical_map
    }
    equivalent_map = builder.parse_equivalent_ideographs(
        paths[builder.EQUIVALENT_IDEOGRAPH_ID]
    )
    radical_map.update(equivalent_map)
    radical_mapping_sources.update(
        {cp: builder.EQUIVALENT_IDEOGRAPH_ID for cp in equivalent_map}
    )
    unihan, all_variants = builder.parse_unihan(
        paths[builder.UNIHAN_ID], selected_cps
    )
    cns_readings, bopomofo_to_pinyin, cns_sequences, cns_radicals = builder.parse_cns(
        registry, paths[builder.CNS_ID]
    )
    mmah_dictionary = builder.parse_mmah_dictionary(
        paths[builder.MMAH_DICTIONARY_ID], selected_cps
    )
    mmah_graphics = builder.parse_mmah_graphics(
        paths[builder.MMAH_GRAPHICS_ID], selected_cps
    )
    cedict, cedict_inverse = builder.parse_cc_cedict(
        registry, paths[builder.CC_CEDICT_ID], selected_cps
    )
    simplification_audit = builder.load_simplification_audit(
        registry, selected_cps
    )
    moe_concised = builder.load_moe_rows(paths[builder.MOE_CONCISED_ID])
    radical_strokes: dict[int, tuple[int, list[str]]] = {}
    for number in range(1, 215):
        record = json.loads(
            (ROOT / "radicals" / f"{number}.json").read_text(encoding="utf-8")
        )
        radical_strokes[number] = (
            record["stroke_count"],
            record["sources"]["stroke_count"],
        )
    return {
        "paths": paths,
        "rows": rows,
        "corpus_total": corpus_total,
        "exclusions": exclusions,
        "selected_cps": selected_cps,
        "radical_map": radical_map,
        "radical_mapping_sources": radical_mapping_sources,
        "unihan": unihan,
        "all_variants": all_variants,
        "cns_readings": cns_readings,
        "bopomofo_to_pinyin": bopomofo_to_pinyin,
        "cns_sequences": cns_sequences,
        "cns_radicals": cns_radicals,
        "mmah_dictionary": mmah_dictionary,
        "mmah_graphics": mmah_graphics,
        "cedict": cedict,
        "cedict_inverse": cedict_inverse,
        "simplification_audit": simplification_audit,
        "moe_concised": moe_concised,
        "radical_strokes": radical_strokes,
    }


def check_file_set(
    records: list[dict[str, Any]], initial_errors: list[str], **_: Any
) -> list[str]:
    errors = list(initial_errors)
    if len(records) != 2000:
        errors.append(f"loaded {len(records)} records, expected 2000")
    return errors


def check_schema(
    records: list[dict[str, Any]], schema: dict[str, Any], **_: Any
) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for record in records:
        for error in sorted(validator.iter_errors(record), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.path) or "<root>"
            errors.append(f"{record.get('codepoint')}, {location}: {error.message}")
    return errors


def check_source_selection(
    records: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    for selection_rank, (record, row) in enumerate(
        zip(records, context["rows"]), start=1
    ):
        expected = {
            "codepoint": builder.codepoint(ord(row["character"])),
            "traditional": row["character"],
            "rank": row["rank"],
            "selection_rank": selection_rank,
            "count": row["count"],
            "cumulative_count": row["cumulative_count"],
            "cumulative_percentage": row["cumulative_percentage"],
            "total_strokes": row["strokes"],
        }
        actual = {
            "codepoint": record["codepoint"],
            "traditional": record["traditional"],
            "rank": record["frequency"]["rank"],
            "selection_rank": record["frequency"]["selection_rank"],
            "count": record["frequency"]["count"],
            "cumulative_count": record["frequency"]["cumulative_count"],
            "cumulative_percentage": record["frequency"]["cumulative_percentage"],
            "total_strokes": record["total_strokes"],
        }
        if actual != expected:
            errors.append(f"selection row {selection_rank} differs from pinned MOE data")
    return errors


def check_deterministic_rebuild(
    records: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    rebuilt: list[dict[str, Any]] = []
    for selection_rank, row in enumerate(context["rows"], start=1):
        cp = ord(row["character"])
        rebuilt.append(
            builder.build_record(
                selection_rank,
                row,
                context["corpus_total"],
                context["unihan"][cp],
                context["all_variants"],
                context["cedict"].get(cp, {}),
                context["cedict_inverse"],
                context["simplification_audit"],
                context["moe_concised"].get(row["character"], []),
                context["mmah_dictionary"].get(cp),
                context["mmah_graphics"].get(cp),
                context["radical_map"],
                context["radical_mapping_sources"],
                context["selected_cps"],
                context["radical_strokes"],
                context["cns_readings"],
                context["bopomofo_to_pinyin"],
                context["cns_sequences"],
                context["cns_radicals"],
            )
        )
    # The source rebuild is followed by the audited Taiwan-MOE pronunciation
    # overlay. Applying the same deterministic overlay here keeps this check a
    # true rebuild test rather than treating deliberate corrections as drift.
    import integrate_moe_character_pronunciations as moe_characters

    revised = moe_characters.load_moe_rows(ROOT / moe_characters.REVISED_XLSX)
    variant_log = json.loads(
        (ROOT / moe_characters.VARIANTS_LOG).read_text(encoding="utf-8")
    )
    variants = {
        entry["codepoint"]: entry for entry in variant_log["entries"]
    }
    rebuilt = [
        (
            moe_characters.update_targeted_record(
                record,
                revised[record["traditional"]],
                variants[record["codepoint"]],
            )
            if record["codepoint"] in variants
            else moe_characters.update_revised_record(
                record, revised[record["traditional"]]
            )
        )
        for record in rebuilt
    ]
    for actual, expected in zip(records, rebuilt):
        if phase3_projection(actual) != expected:
            errors.append(f"{actual['codepoint']}: differs from deterministic source rebuild")
    return errors


def walk_provenance_fields(value: Any, path: str = "") -> list[str]:
    fields: list[str] = []
    if path.split(".", 1)[0] in {"sources", "gaps", "conflicts"}:
        return fields
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}" if path else key
            fields.extend(walk_provenance_fields(item, next_path))
    elif isinstance(value, list):
        if value and all(not isinstance(item, (dict, list)) for item in value):
            fields.append(path)
        else:
            for index, item in enumerate(value):
                fields.extend(walk_provenance_fields(item, f"{path}[{index}]"))
    elif value is not None:
        fields.append(path)
    return fields


def source_covers(path: str, source_paths: set[str]) -> bool:
    return any(
        path == source_path
        or path.startswith(f"{source_path}.")
        or path.startswith(f"{source_path}[")
        for source_path in source_paths
    )


def check_provenance(
    records: list[dict[str, Any]], registry: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    valid_sources = registry["sources"]
    for record in records:
        source_paths = set(record["sources"])
        for field in walk_provenance_fields(record):
            if not source_covers(field, source_paths):
                errors.append(f"{record['codepoint']}: non-null field lacks source: {field}")
        for field, source_ids in record["sources"].items():
            for source_id in source_ids:
                if source_id not in valid_sources:
                    errors.append(
                        f"{record['codepoint']}, {field}: unknown source ID {source_id}"
                    )
                elif valid_sources[source_id]["status"] != "approved":
                    reference_only_allowed = (
                        valid_sources[source_id]["status"] == "reference_only"
                        and field
                        in {
                            "stroke_order.standard",
                            "stroke_order.formal_conformance",
                        }
                    )
                    if not reference_only_allowed:
                        errors.append(
                            f"{record['codepoint']}, {field}: source is not approved: {source_id}"
                        )
        inline_source_ids: list[str] = []
        inline_source_ids.extend(
            item["source_id"] for item in record["stroke_count_variants"]
        )
        if record["definitions"]:
            inline_source_ids.extend(item["source_id"] for item in record["definitions"])
        inline_source_ids.extend(
            item["source_id"] for item in record["readings"].get("pinyin_variants", [])
        )
        for conflict in record["conflicts"]:
            for value in conflict["values"]:
                inline_source_ids.extend(value["source_ids"])
        for source_id in inline_source_ids:
            if source_id not in valid_sources:
                errors.append(f"{record['codepoint']}: unknown inline source ID {source_id}")
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


def check_null_gaps(records: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    for record in records:
        gap_fields = {gap["field"] for gap in record["gaps"]}
        for field in walk_nulls(record):
            if field not in gap_fields:
                errors.append(f"{record['codepoint']}: null field lacks exact gap: {field}")
    return errors


def check_codepoints_and_blocks(records: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    for record in records:
        try:
            cp = parse_codepoint(record["codepoint"])
        except ValueError:
            errors.append(f"{record.get('codepoint')!r}: invalid codepoint syntax")
            continue
        if len(record["traditional"]) != 1 or ord(record["traditional"]) != cp:
            errors.append(f"{record['codepoint']}: Traditional character/codepoint mismatch")
        if not builder.is_han_unified(cp) or builder.is_forbidden_character(cp):
            errors.append(f"{record['codepoint']}: primary is not an allowed unified Han codepoint")
        content_chars: list[str] = [record["traditional"]]
        if record["simplified"]:
            content_chars.append(record["simplified"])
        content_chars.extend(item["char"] for item in record["variants_異體字"])
        if record["ids_decomposition"]:
            content_chars.extend(record["ids_decomposition"])
        for char in content_chars:
            if builder.is_forbidden_character(ord(char)):
                errors.append(
                    f"{record['codepoint']}: forbidden radical/compatibility character U+{ord(char):04X}"
                )
        for item in record["variants_異體字"]:
            if ord(item["char"]) != parse_codepoint(item["codepoint"]):
                errors.append(f"{record['codepoint']}: variant character/codepoint mismatch")
        for component in record["components"] or []:
            component_cp = parse_codepoint(component)
            if component_cp not in {parse_codepoint(item["codepoint"]) for item in records}:
                errors.append(f"{record['codepoint']}: unresolved component {component}")
        if not builder.is_nfc_except_verbatim_text(record):
            errors.append(
                f"{record['codepoint']}: a non-verbatim record field is not NFC"
            )
    supplementary = chr(0x20000)
    decoded = json.loads(json.dumps({"char": supplementary}, ensure_ascii=False))["char"]
    if len(decoded) != 1 or ord(decoded) != 0x20000:
        errors.append("non-BMP U+20000 failed numeric codepoint JSON round-trip")
    return errors


def check_readings(records: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    tone_marks = {0x02C7, 0x02CA, 0x02CB, 0x02D9}
    for record in records:
        for item in record["readings"].get("pinyin", []) + record["readings"].get(
            "pinyin_variants", []
        ):
            reading = item["reading"]
            if any(char.isdigit() for char in reading):
                errors.append(f"{record['codepoint']}: numeric-tone Pinyin {reading!r}")
            if not unicodedata.is_normalized("NFC", reading):
                errors.append(f"{record['codepoint']}: non-NFC Pinyin {reading!r}")
        for reading in record["readings"].get("zhuyin", []):
            for char in reading:
                cp = ord(char)
                if not (0x3105 <= cp <= 0x312F or 0x31A0 <= cp <= 0x31BF or cp in tone_marks):
                    errors.append(
                        f"{record['codepoint']}: invalid Zhuyin codepoint U+{cp:04X}"
                    )
    return errors


def check_simplification_flags(records: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    for record in records:
        note = record["simplification_note"]
        if note is not None:
            if len(note["traditional_origins"]) < 2:
                errors.append(f"{record['codepoint']}: many-to-one note has fewer than two origins")
            if not record["simplified"]:
                errors.append(f"{record['codepoint']}: note exists without a Simplified mapping")
            elif note["simplified"] != builder.codepoint(ord(record["simplified"])):
                errors.append(f"{record['codepoint']}: note points to a different Simplified character")
        simplified_conflicts = [
            item for item in record["conflicts"] if item["field"] == "simplified"
        ]
        if record["simplified"] is None and not simplified_conflicts:
            no_mapping_gap = any(
                gap["field"] == "simplified" and gap["reason"] == "not_attested"
                for gap in record["gaps"]
            )
            if not no_mapping_gap:
                errors.append(
                    f"{record['codepoint']}: null Simplified mapping is neither conflicted nor unattested"
                )
    return errors


def check_official_simplification_audit(
    records: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    by_cp = {parse_codepoint(record["codepoint"]): record for record in records}
    audit = context["simplification_audit"]
    if len(audit) != 37:
        errors.append(f"official audit covers {len(audit)} records, expected 37")
    for cp, decision in sorted(audit.items()):
        record = by_cp[cp]
        conflicts = [
            item for item in record["conflicts"] if item["field"] == "simplified"
        ]
        if len(conflicts) != 1:
            errors.append(
                f"{record['codepoint']}: audited mapping does not have exactly one conflict"
            )
            continue
        conflict = conflicts[0]
        if conflict["detail"] != decision["detail"]:
            errors.append(f"{record['codepoint']}: audit decision detail differs")
        if decision["decision"] == "selected":
            if record["simplified"] != decision["selected"]:
                errors.append(f"{record['codepoint']}: official selected mapping differs")
            if builder.PRC_STANDARD_ID not in record["sources"].get("simplified", []):
                errors.append(f"{record['codepoint']}: official mapping source is absent")
            if (
                conflict["resolution"]
                != "prc_standard_canonical_other_candidates_retained"
            ):
                errors.append(f"{record['codepoint']}: official selection resolution differs")
        else:
            if record["simplified"] is not None:
                errors.append(f"{record['codepoint']}: context-dependent mapping is not null")
            if "simplified" in record["sources"]:
                errors.append(f"{record['codepoint']}: null mapping has a field source")
            matching_gaps = [
                gap
                for gap in record["gaps"]
                if gap["field"] == "simplified"
                and gap["reason"] == "conflicting_sources"
                and gap["detail"] == decision["detail"]
            ]
            if len(matching_gaps) != 1:
                errors.append(f"{record['codepoint']}: context-dependent gap differs")
            if conflict["resolution"] != "context_dependent_official_standard":
                errors.append(f"{record['codepoint']}: context-dependent resolution differs")
        if not any(
            builder.PRC_STANDARD_ID in value["source_ids"]
            for value in conflict["values"]
        ):
            errors.append(f"{record['codepoint']}: official evidence is absent from conflict")
    return errors


def check_taiwan_definitions(
    records: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    for record in records:
        expected = builder.build_taiwan_definitions(
            context["moe_concised"].get(record["traditional"], []),
            builder.MOE_CONCISED_ID,
        )
        if not expected:
            errors.append(f"{record['codepoint']}: no exact Concised definition")
        elif record.get("definitions_zh_TW") != expected:
            errors.append(f"{record['codepoint']}: Taiwan definition differs from source")
        if record["sources"].get("definitions_zh_TW") != [
            builder.MOE_CONCISED_ID
        ]:
            errors.append(f"{record['codepoint']}: Taiwan definition provenance differs")
    return errors


def check_structural_flags(
    records: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    for record in records:
        radical = record["radical"]
        radical_count = context["radical_strokes"][radical["kangxi_number"]][0]
        equation_matches = (
            radical_count + radical["residual_strokes"] == record["total_strokes"]
        )
        flags = [
            conflict
            for conflict in record["conflicts"]
            if conflict["field"] == "radical.total_strokes_equation"
        ]
        if equation_matches and flags:
            errors.append(f"{record['codepoint']}: structural equation matches but is flagged")
        if not equation_matches and len(flags) != 1:
            errors.append(
                f"{record['codepoint']}: structural equation mismatch is not flagged exactly once"
            )
    return errors


def check_manifest(records: list[dict[str, Any]], context: dict[str, Any], **_: Any) -> list[str]:
    errors: list[str] = []
    base_records = [phase3_projection(record) for record in records]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("phase") != 3 or manifest.get("record_count") != 2000:
        errors.append("Phase 3 manifest phase or record_count is incorrect")
    if manifest.get("record_digest_sha256") != builder.deterministic_record_digest(base_records):
        errors.append("Phase 3 deterministic record digest does not match records")
    if manifest.get("excluded_rows_before_selection_completed") != context["exclusions"]:
        errors.append("Phase 3 manifest exclusion audit differs from source selection")
    expected_range = [
        base_records[0]["frequency"]["rank"],
        base_records[-1]["frequency"]["rank"],
    ]
    if manifest.get("source_rank_range") != expected_range:
        errors.append("Phase 3 manifest source_rank_range is incorrect")
    if manifest.get("records_with_conflicts") != sum(
        bool(record["conflicts"]) for record in base_records
    ):
        errors.append("Phase 3 manifest records_with_conflicts is incorrect")
    if manifest.get("conflict_count") != sum(
        len(record["conflicts"]) for record in base_records
    ):
        errors.append("Phase 3 manifest conflict_count is incorrect")
    if manifest.get("gap_count") != sum(
        len(record["gaps"]) for record in base_records
    ):
        errors.append("Phase 3 manifest gap_count is incorrect")
    return errors


def check_phase2_regression(**_: Any) -> list[str]:
    errors: list[str] = []
    phase2 = json.loads((ROOT / "metadata" / "manifests" / "phase2.json").read_text(encoding="utf-8"))
    radical_records = [
        json.loads((ROOT / "radicals" / f"{number}.json").read_text(encoding="utf-8"))
        for number in range(1, 215)
    ]
    phase2_records = [
        validate2.phase2_projection(record) for record in radical_records
    ]
    if builder.deterministic_record_digest(phase2_records) != phase2["record_digest_sha256"]:
        errors.append("Phase 2 radical-record digest changed during Phase 3")
    asset_manifest = json.loads(
        (ROOT / phase2["asset_manifest"]["local_path"]).read_text(encoding="utf-8")
    )
    assets = asset_manifest["assets"]
    if len(assets) != (
        phase2["historical_asset_count"] + phase2["shuowen_asset_count"]
    ):
        errors.append("Phase 2 asset-manifest record count changed during Phase 3")
    historical_counts = Counter(
        item["historical_form"]
        for item in assets
        if item.get("historical_form") not in (None, "shuowen_seal_說文解字")
    )
    if dict(historical_counts) != phase2["historical_form_reference_counts"]:
        errors.append("Phase 2 historical-form reference counts changed during Phase 3")
    source_counts = Counter(
        item["source_id"]
        for item in assets
        if item.get("historical_form") not in (None, "shuowen_seal_說文解字")
    )
    expected_source_counts = {
        source_id: count
        for source_id, count in phase2["historical_asset_source_counts"].items()
        if count
    }
    if dict(source_counts) != expected_source_counts:
        errors.append("Phase 2 historical asset source counts changed during Phase 3")
    asset_ids = [item["asset_id"] for item in assets]
    if len(set(asset_ids)) != len(asset_ids):
        errors.append("Phase 2 asset IDs are no longer unique")
    for item in assets:
        path = ROOT / item["local_path"]
        if not path.is_file():
            errors.append(f"Phase 2 asset is missing: {item['local_path']}")
    return errors


def format_codepoints(values: list[str], width: int = 20) -> str:
    return "\n".join(
        " ".join(values[index : index + width])
        for index in range(0, len(values), width)
    )


def write_reports(
    records: list[dict[str, Any]],
    checks: list[tuple[str, str, list[str]]],
    context: dict[str, Any],
) -> None:
    passed = all(not errors for _, _, errors in checks)
    status = "PASS" if passed else "FAIL"
    validation_lines = [
        "# Validation report",
        "",
        f"Phase 3 status: **{status}**",
        "",
        f"Generated: {builder.utc_now()}",
        "",
        "| Check | Result | Detail |",
        "|---|---:|---|",
    ]
    for check_id, detail, errors in checks:
        validation_lines.append(
            f"| {check_id} | {'PASS' if not errors else 'FAIL'} | "
            + (detail if not errors else f"{len(errors)} failure(s)")
            + " |"
        )
    for check_id, _, errors in checks:
        if errors:
            validation_lines.extend(["", f"## {check_id} failures", ""])
            validation_lines.extend(f"- {error}" for error in errors)

    structural = [
        record["codepoint"]
        for record in records
        if any(
            conflict["field"] == "radical.total_strokes_equation"
            for conflict in record["conflicts"]
        )
    ]
    validation_lines.extend(
        [
            "",
            "## Review flags (validation-preserving)",
            "",
            f"The radical-stroke equation differs for {len(structural)} records. Each is retained as a source conflict rather than rewritten:",
            "",
            format_codepoints(structural),
            "",
            "Phase 2 regression checks cover the 214-record deterministic digest, the 4,457-entry asset inventory, historical-form/source counts, unique asset IDs, and local-file presence.",
            "",
        ]
    )
    VALIDATION_REPORT_PATH.write_text("\n".join(validation_lines), encoding="utf-8")

    gap_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for record in records:
        for gap in record["gaps"]:
            gap_groups[(gap["reason"], gap["field"])].append(record["codepoint"])
    gap_lines = [
        "# Gaps report",
        "",
        "Phase 3 explicit null/unavailable coverage, grouped by allowed reason and field.",
        "",
    ]
    for reason in (
        "conflicting_sources",
        "not_attested",
        "source_unavailable",
        "license_prohibits_use",
    ):
        groups = sorted(
            ((field, cps) for (item_reason, field), cps in gap_groups.items() if item_reason == reason),
            key=lambda item: item[0],
        )
        gap_lines.extend([f"## {reason}", ""])
        if not groups:
            gap_lines.extend(["None.", ""])
            continue
        for field, cps in groups:
            gap_lines.extend(
                [
                    f"<details><summary><code>{field}</code> — {len(cps)} record(s)</summary>",
                    "",
                    format_codepoints(cps),
                    "",
                    "</details>",
                    "",
                ]
            )
    GAPS_REPORT_PATH.write_text("\n".join(gap_lines), encoding="utf-8")

    coverage = {
        "Simplified mapping": sum(record["simplified"] is not None for record in records),
        "many-to-one simplification note": sum(
            record["simplification_note"] is not None for record in records
        ),
        "IDS decomposition": sum(record["ids_decomposition"] is not None for record in records),
        "locally resolvable component list": sum(record["components"] is not None for record in records),
        "Make Me a Hanzi etymology": sum(record["liushu_六書"] is not None for record in records),
        "Taiwan MOE canonical Pinyin": sum(
            record["readings"].get("pinyin", [{}])[0].get("region") == "TW"
            for record in records
        ),
        "Zhuyin": sum(bool(record["readings"].get("zhuyin")) for record in records),
        "English definition": sum(record["definitions"] is not None for record in records),
        "verbatim Taiwan MOE definition": sum(
            bool(record["definitions_zh_TW"]) for record in records
        ),
        "Kangxi citation": sum(record["kangxi_citation"] is not None for record in records),
    }
    gap_counts = Counter(gap["reason"] for record in records for gap in record["gaps"])
    conflict_counts = Counter(
        conflict["field"] for record in records for conflict in record["conflicts"]
    )
    phase_lines = [
        "# Phase 3 report — Character set",
        "",
        f"Status: **{'complete and validated' if passed else 'validation failed'}**",
        "",
        "## Outcome",
        "",
        f"- Records: **{len(records)}** Traditional-primary character files.",
        f"- MOE source ranks consumed: **{records[0]['frequency']['rank']}–{records[-1]['frequency']['rank']}**.",
        f"- Excluded source rows before selection completed: **{len(context['exclusions'])}**.",
        f"- Records with reviewable conflicts: **{sum(bool(record['conflicts']) for record in records)}**.",
        f"- Total conflicts: **{sum(conflict_counts.values())}**.",
        f"- Total explicit gaps: **{sum(gap_counts.values())}**.",
        "",
        "## Coverage",
        "",
        "| Field | Populated | Coverage |",
        "|---|---:|---:|",
    ]
    for field, count in coverage.items():
        phase_lines.append(f"| {field} | {count} | {count / len(records):.1%} |")
    phase_lines.extend(["", "## Conflicts by field", "", "| Field | Count |", "|---|---:|"])
    for field, count in conflict_counts.most_common():
        phase_lines.append(f"| `{field}` | {count} |")
    phase_lines.extend(["", "## Gaps by reason", "", "| Reason | Count |", "|---|---:|"])
    for reason, count in sorted(gap_counts.items()):
        phase_lines.append(f"| `{reason}` | {count} |")
    phase_lines.extend(
        [
            "",
            "## Implementation decisions introduced in this phase",
            "",
            "1. The stable MDBG CC-CEDICT page forbids scripted access. The build therefore uses and pins the CC-CEDICT project's own dated editor-export snapshot (`2026-08-11T14:10:23Z`) and labels it as such; it is not represented as the stable 2026-08-10 MDBG release.",
            "2. The MOE CSV's published `筆畫` value is the canonical Taiwan MOE stroke count. CNS sequence length, Unicode IRG values, and Make Me a Hanzi PRC path counts are retained as variants whenever they differ.",
            "3. Components outside the selected top-2,000 set are not emitted as dangling references. The full normalized IDS remains available, while `components` is null with a gap until the character set expands.",
            "4. Make Me a Hanzi `pictophonetic` is normalized to `形聲`. Its broader `pictographic` and `ideographic` labels are preserved without forcing a narrower 六書 classification.",
            "5. English definitions use exact one-character Unihan/CC-CEDICT evidence. A separate definitions_zh_TW array copies exact-headword Taiwan MOE Concised Dictionary cells verbatim with entry IDs.",
            "6. The official PRC 2013 table adjudicates all 37 conflicting Simplified candidates: 21 context-independent mappings are selected and 16 context-dependent cases remain null with explicit evidence.",
            "7. Taiwan CNS radical assignments are canonical. Five differing first Unihan assignments remain explicit conflicts, and same-radical Unihan residuals are retained to represent positional radical forms.",
            "",
            "## Handled by later phases in this snapshot",
            "",
            "- Phase 4 supplies common-word joins, word records, prioritized Taiwan MOE word readings, and verbatim Taiwan definitions.",
            "- Phase 5 supplies stroke-order SVG assets; Phase 3 retains path counts only as explicit PRC comparison evidence.",
            "- HSK, TOCFL, and curated confusable fields remain null because no approved versioned sources passed the audit.",
            "",
        ]
    )
    PHASE_REPORT_PATH.write_text("\n".join(phase_lines), encoding="utf-8")


def main() -> None:
    registry = builder.load_registry()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    records, initial_errors = load_records()
    context = load_context(registry)
    checks_spec: list[
        tuple[str, str, Callable[..., list[str]]]
    ] = [
        ("P3-01 Record set", "Exactly 2,000 uniquely ranked character files.", check_file_set),
        ("P3-02 JSON Schema", "All records validate against character.schema.json.", check_schema),
        ("P3-03 Source selection", "Every identity, rank, count, and canonical stroke count matches the pinned MOE rows.", check_source_selection),
        ("P3-04 Deterministic rebuild", "Every record exactly reproduces from the pinned source snapshots.", check_deterministic_rebuild),
        ("P3-05 Provenance", "Every non-null leaf is covered by approved registered source IDs.", check_provenance),
        ("P3-06 Null/gap pairing", "Every explicit null has an exact gaps[] entry.", check_null_gaps),
        ("P3-07 Unicode scope", "Codepoints round-trip, remain NFC, avoid forbidden radical/compatibility blocks, and component references resolve.", check_codepoints_and_blocks),
        ("P3-08 Reading syntax", "Pinyin is tone-marked rather than numeric and Zhuyin uses valid Bopomofo codepoints.", check_readings),
        ("P3-09 Simplification", "One-to-many mappings are flagged and unresolved mappings remain explicit.", check_simplification_flags),
        ("P3-09b Official simplification audit", "All 37 formerly unresolved mappings reproduce the official PRC-table adjudication and preserve context-dependent cases.", check_official_simplification_audit),
        ("P3-09c Taiwan definitions", "All 2,000 definition arrays exactly reproduce decoded Concised Dictionary cells and entry IDs.", check_taiwan_definitions),
        ("P3-10 Structural conflicts", "Every radical-plus-residual mismatch is retained exactly once as a conflict.", check_structural_flags),
        ("P3-11 Manifest", "Manifest counts, exclusions, and deterministic digest match the corpus.", check_manifest),
        ("P3-12 Phase 2 regression", "Phase 2 radical digest and validated asset inventory remain unchanged.", check_phase2_regression),
    ]
    checks: list[tuple[str, str, list[str]]] = []
    shared = {
        "records": records,
        "initial_errors": initial_errors,
        "schema": schema,
        "registry": registry,
        "context": context,
    }
    for check_id, detail, function in checks_spec:
        checks.append((check_id, detail, function(**shared)))
    write_reports(records, checks, context)
    failures = sum(bool(errors) for _, _, errors in checks)
    print(
        f"Phase 3 validation: {'PASS' if failures == 0 else 'FAIL'} "
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
