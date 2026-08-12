#!/usr/bin/env python3
"""Validate Phase 5 stroke-order SVGs and write cumulative reports."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase2 as phase2  # noqa: E402
import build_phase3 as phase3  # noqa: E402
import build_phase5 as builder  # noqa: E402
import validate_phase2 as validate2  # noqa: E402
import validate_phase4 as validate4  # noqa: E402


MANIFEST_PATH = ROOT / "metadata" / "manifests" / "phase5.json"
VALIDATION_REPORT_PATH = ROOT / "docs" / "validation.md"
GAPS_REPORT_PATH = ROOT / "docs" / "gaps.md"
PHASE_REPORT_PATH = ROOT / "phase5-report.md"
SVG_NS = "{http://www.w3.org/2000/svg}"
PATH_ID_RE = re.compile(r"^stroke-(U\+[0-9A-F]{4,6})-([0-9]+)$")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_records() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[str],
]:
    errors: list[str] = []
    radicals: list[dict[str, Any]] = []
    characters: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    for number in range(1, 215):
        path = ROOT / "radicals" / f"{number}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if record.get("kangxi_number") != number:
            errors.append(f"{path.name}: radical number differs")
        radicals.append(record)
    for path in sorted((ROOT / "characters").glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if path.stem != record.get("codepoint"):
            errors.append(f"{path.name}: character filename differs")
        characters.append(record)
    characters.sort(key=lambda item: item.get("frequency", {}).get("selection_rank", 0))
    for path in sorted((ROOT / "words").glob("*.json")):
        try:
            words.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
    words.sort(key=lambda item: item.get("frequency", {}).get("rank", 0))
    asset_manifest = json.loads(
        (ROOT / "assets" / "manifest.json").read_text(encoding="utf-8")
    )
    return radicals, characters, words, asset_manifest, errors


def load_context(
    registry: dict[str, Any],
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
) -> dict[str, Any]:
    builder.audit_kanjivg_gap(registry)
    graphics_path = phase3.acquired_path(registry, phase3.MMAH_GRAPHICS_ID)
    cns_path = phase3.acquired_path(registry, phase3.CNS_ID)
    builder.audit_cns_type_documentation(registry, cns_path)
    unihan_path = phase3.acquired_path(registry, phase3.UNIHAN_ID)
    graphics = builder.parse_graphics(registry, graphics_path)
    _, _, sequences, _ = phase3.parse_cns(registry, cns_path)
    cps = {ord(record["primary"]["char"]) for record in radicals} | {
        int(record["codepoint"][2:], 16) for record in characters
    }
    unihan, _ = phase3.parse_unihan(unihan_path, cps)
    return {
        "graphics": graphics,
        "sequences": sequences,
        "unihan": unihan,
        "target_cps": cps,
    }


def check_record_sets(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    asset_manifest: dict[str, Any],
    initial_errors: list[str],
    manifest: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors = list(initial_errors)
    assets = asset_manifest.get("stroke_order_assets", [])
    if len(radicals) != 214:
        errors.append(f"loaded {len(radicals)} radicals, expected 214")
    if len(characters) != 2000:
        errors.append(f"loaded {len(characters)} characters, expected 2000")
    if len(assets) != manifest.get("stroke_order_asset_count"):
        errors.append("stroke-order asset count differs from manifest")
    ids = [asset.get("asset_id") for asset in assets]
    paths = [asset.get("local_path") for asset in assets]
    if len(ids) != len(set(ids)):
        errors.append("stroke-order asset IDs are duplicated")
    if len(paths) != len(set(paths)):
        errors.append("stroke-order asset paths are duplicated")
    return errors


def check_schema(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    asset_manifest: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    specs = (
        (ROOT / "schema" / "radical.schema.json", radicals, "kangxi_number"),
        (ROOT / "schema" / "character.schema.json", characters, "codepoint"),
        (
            ROOT / "schema" / "stroke-order-asset.schema.json",
            asset_manifest.get("stroke_order_assets", []),
            "asset_id",
        ),
    )
    for schema_path, records, key in specs:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for record in records:
            for error in sorted(
                validator.iter_errors(record), key=lambda item: list(item.path)
            ):
                location = ".".join(str(part) for part in error.path) or "<root>"
                errors.append(f"{record.get(key)}, {location}: {error.message}")
    return errors


def check_source_integrity(context: dict[str, Any], **_: Any) -> list[str]:
    errors: list[str] = []
    if len(context["graphics"]) != 9574:
        errors.append("pinned Make Me a Hanzi row count differs")
    covered = context["target_cps"] & set(context["graphics"])
    if len(context["target_cps"]) != 2097 or len(covered) != 2096:
        errors.append("target/source intersection is not 2,096 of 2,097")
    missing = context["target_cps"] - set(context["graphics"])
    if missing != {0x6C59}:
        errors.append(f"unexpected exact-codepoint graphics gaps: {sorted(missing)}")
    return errors


def check_svg_assets(
    asset_manifest: dict[str, Any], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    entries = asset_manifest.get("stroke_order_assets", [])
    by_cp = {int(entry["codepoint"][2:], 16): entry for entry in entries}
    expected_cps = context["target_cps"]
    if set(by_cp) != expected_cps:
        errors.append("asset manifest codepoint set differs from full target coverage")
    expected_paths = {entry["local_path"] for entry in entries}
    actual_paths = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "assets" / "stroke-order").glob("*/*.svg")
    }
    if actual_paths != expected_paths:
        errors.append("stroke-order directory and manifest file sets differ")
    for cp, entry in by_cp.items():
        path = ROOT / entry["local_path"]
        if not path.is_file():
            errors.append(f"{entry['asset_id']}: SVG is missing")
            continue
        if sha256_path(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            errors.append(f"{entry['asset_id']}: byte integrity differs")
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            errors.append(f"{entry['asset_id']}: invalid XML: {exc}")
            continue
        if root.tag != SVG_NS + "svg" or root.get("viewBox") != "0 0 1024 1024":
            errors.append(f"{entry['asset_id']}: invalid SVG root/viewBox")
        groups = root.findall(SVG_NS + "g")
        if len(groups) != 1 or groups[0].get("transform") != "scale(1,-1) translate(0,-900)":
            errors.append(f"{entry['asset_id']}: source coordinate transform differs")
            continue
        paths = groups[0].findall(SVG_NS + "path")
        reconstructed = entry.get("provenance_type") == "reconstructed"
        if reconstructed:
            if cp != builder.RECONSTRUCTED_CP:
                errors.append(f"{entry['asset_id']}: unexpected reconstructed codepoint")
                continue
            expected_strokes = builder.reconstruction_strokes(context["graphics"])
            expected_sequence = builder.cns_sequence_for(
                cp, context["unihan"], context["sequences"]
            )
        else:
            source = context["graphics"].get(cp)
            if source is None:
                errors.append(f"{entry['asset_id']}: exact graphics row is missing")
                continue
            expected_strokes = [
                {
                    "path": source_path,
                    "source_codepoint": entry["codepoint"],
                    "source_character": source["character"],
                    "source_stroke_index": index,
                    "transform": None,
                }
                for index, source_path in enumerate(source["strokes"], start=1)
            ]
            expected_sequence = None
        if len(paths) != len(expected_strokes) or len(paths) != entry["stroke_count"]:
            errors.append(f"{entry['asset_id']}: SVG stroke count differs")
            continue
        for index, (element, expected_stroke) in enumerate(
            zip(paths, expected_strokes), start=1
        ):
            match = PATH_ID_RE.fullmatch(element.get("id", ""))
            if (
                not match
                or match.group(1) != entry["codepoint"]
                or int(match.group(2)) != index
                or element.get("data-stroke-index") != str(index)
            ):
                errors.append(f"{entry['asset_id']}: path {index} index tag differs")
            if element.get("d") != expected_stroke["path"]:
                errors.append(f"{entry['asset_id']}: path {index} source geometry differs")
            if reconstructed:
                expected_type = expected_sequence[index - 1]
                expected_transform = expected_stroke["transform"]
                if element.get("data-geometry-status") != "reconstructed":
                    errors.append(f"{entry['asset_id']}: path {index} reconstruction marker differs")
                if element.get("data-source-codepoint") != expected_stroke["source_codepoint"]:
                    errors.append(f"{entry['asset_id']}: path {index} source codepoint differs")
                if element.get("data-source-character") != expected_stroke["source_character"]:
                    errors.append(f"{entry['asset_id']}: path {index} source character differs")
                if element.get("data-source-stroke-index") != str(expected_stroke["source_stroke_index"]):
                    errors.append(f"{entry['asset_id']}: path {index} source index differs")
                if element.get("data-taiwan-cns-type-code") != expected_type:
                    errors.append(f"{entry['asset_id']}: path {index} CNS type code differs")
                if element.get("data-taiwan-cns-type-name") != builder.TYPE_NAMES[expected_type]:
                    errors.append(f"{entry['asset_id']}: path {index} CNS type name differs")
                if element.get("transform") != expected_transform:
                    errors.append(f"{entry['asset_id']}: path {index} component transform differs")
            elif element.get("data-stroke-type-status") != "source-unavailable":
                errors.append(f"{entry['asset_id']}: path {index} type status differs")
        if reconstructed:
            left = context["graphics"][builder.LEFT_COMPONENT_CP]
            right = context["graphics"][builder.RIGHT_COMPONENT_CP]
            component_rows = entry.get("component_sources", [])
            expected_rows = [left, right]
            if len(component_rows) != 2:
                errors.append(f"{entry['asset_id']}: component-source count differs")
            else:
                for component, source in zip(component_rows, expected_rows):
                    if component["source_record_index"] != source["source_record_index"]:
                        errors.append(f"{entry['asset_id']}: component row index differs")
                    if component["source_record_sha256"] != source["source_record_sha256"]:
                        errors.append(f"{entry['asset_id']}: component row digest differs")
            if entry.get("order_source", {}).get("sequence") != expected_sequence:
                errors.append(f"{entry['asset_id']}: Taiwan CNS sequence differs")
        else:
            source = context["graphics"][cp]
            if entry["source_record_index"] != source["source_record_index"]:
                errors.append(f"{entry['asset_id']}: source row index differs")
            if entry["source_record_sha256"] != source["source_record_sha256"]:
                errors.append(f"{entry['asset_id']}: source row digest differs")
    return errors


def expected_order(
    cp: int,
    row: dict[str, Any],
    taiwan_count: int,
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, list[str]], list[dict[str, str]]]:
    sources: dict[str, list[str]] = {}
    gaps: list[dict[str, str]] = []
    sequence = builder.cns_sequence_for(
        cp, context["unihan"], context["sequences"]
    )
    order = builder.make_stroke_order(
        cp, len(row["strokes"]), taiwan_count, sequence, sources, gaps
    )
    return order, sources, gaps


def phase5_sources(record: dict[str, Any]) -> dict[str, list[str]]:
    return {
        key: value
        for key, value in record["sources"].items()
        if key == "stroke_order" or key.startswith("stroke_order.")
    }


def phase5_gaps(record: dict[str, Any]) -> list[dict[str, str]]:
    return [
        gap
        for gap in record["gaps"]
        if gap.get("field", "").startswith("stroke_order")
    ]


def canonical_gaps(gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    """Compare gaps by content; later integrations may canonicalize list order."""
    return sorted(
        gaps,
        key=lambda gap: (gap.get("field", ""), gap.get("reason", ""), gap.get("detail", "")),
    )


def check_radical_joins(
    radicals: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    for record in radicals:
        cp = ord(record["primary"]["char"])
        row = context["graphics"].get(cp)
        if row is None:
            errors.append(f"radical {record['kangxi_number']}: exact graphics missing")
            continue
        order, sources, gaps = expected_order(cp, row, record["stroke_count"], context)
        if record.get("stroke_order") != order:
            errors.append(f"radical {record['kangxi_number']}: stroke order differs")
        if phase5_sources(record) != sources:
            errors.append(f"radical {record['kangxi_number']}: Phase 5 sources differ")
        if canonical_gaps(phase5_gaps(record)) != canonical_gaps(gaps):
            errors.append(f"radical {record['kangxi_number']}: Phase 5 gaps differ")
    return errors


def check_character_joins(
    characters: list[dict[str, Any]], context: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    for record in characters:
        cp = int(record["codepoint"][2:], 16)
        row = context["graphics"].get(cp)
        if row is None:
            if cp != builder.RECONSTRUCTED_CP:
                errors.append(f"{record['codepoint']}: unexpected exact-source gap")
                continue
            sources: dict[str, list[str]] = {}
            gaps: list[dict[str, str]] = []
            sequence = builder.cns_sequence_for(
                cp, context["unihan"], context["sequences"]
            )
            order = builder.make_stroke_order(
                cp,
                6,
                record["total_strokes"],
                sequence,
                sources,
                gaps,
                reconstructed=True,
            )
            gaps.append(
                phase3.make_gap(
                    "stroke_order.exact_source_asset",
                    "source_unavailable",
                    "The pinned Make Me a Hanzi source has no exact U+6C59 row, and the official KanjiVG index also has no exact U+6C59 entry. The linked SVG is an explicitly labeled component reconstruction, not a substituted exact-source glyph.",
                )
            )
            if record.get("stroke_order") != order:
                errors.append(f"{record['codepoint']}: reconstructed stroke order differs")
            if phase5_sources(record) != sources:
                errors.append(f"{record['codepoint']}: reconstruction provenance differs")
            if canonical_gaps(phase5_gaps(record)) != canonical_gaps(gaps):
                errors.append(f"{record['codepoint']}: exact-source gap differs")
            continue
        order, sources, gaps = expected_order(cp, row, record["total_strokes"], context)
        if record.get("stroke_order") != order:
            errors.append(f"{record['codepoint']}: stroke order differs")
        if phase5_sources(record) != sources:
            errors.append(f"{record['codepoint']}: Phase 5 sources differ")
        if canonical_gaps(phase5_gaps(record)) != canonical_gaps(gaps):
            errors.append(f"{record['codepoint']}: Phase 5 gaps differ")
    return errors


def check_type_and_conflict_model(
    radicals: list[dict[str, Any]], characters: list[dict[str, Any]], **_: Any
) -> list[str]:
    errors: list[str] = []
    for label, record in [
        *[(f"radical {item['kangxi_number']}", item) for item in radicals],
        *[(item["codepoint"], item) for item in characters],
    ]:
        order = record.get("stroke_order")
        if order is None:
            continue
        if order["stroke_types"] is not None:
            errors.append(f"{label}: unsourced per-path stroke types are populated")
        if not any(gap["field"] == "stroke_order.stroke_types" for gap in record["gaps"]):
            errors.append(f"{label}: null stroke types lack exact gap")
        conflicts = order["standard_conflicts"]
        if bool(conflicts) != (order["stroke_count"] != (
            record["stroke_count"] if "stroke_count" in record else record["total_strokes"]
        )):
            errors.append(f"{label}: count conflict flag differs")
        sequence = order["taiwan_cns_stroke_sequence"]
        if sequence:
            for item in sequence:
                if builder.TYPE_NAMES[item["code"]] != item["name_zh"]:
                    errors.append(f"{label}: CNS type code/name differs")
    return errors


def check_asset_licensing(
    asset_manifest: dict[str, Any], registry: dict[str, Any], **_: Any
) -> list[str]:
    errors: list[str] = []
    source = registry["sources"].get(phase3.MMAH_GRAPHICS_ID)
    if not source or source.get("status") != "approved":
        errors.append("Make Me a Hanzi source is not approved")
    elif not source.get("license", {}).get("verified"):
        errors.append("Make Me a Hanzi license is not verified")
    for entry in asset_manifest.get("stroke_order_assets", []):
        if entry["license_id"] != source["license"]["id"]:
            errors.append(f"{entry['asset_id']}: license ID differs from registry")
        if not entry["attribution_required"] or not entry["required_attribution"]:
            errors.append(f"{entry['asset_id']}: attribution notice is absent")
        if not entry["transformations"]:
            errors.append(f"{entry['asset_id']}: generated modifications are undisclosed")
        if entry.get("provenance_type") == "reconstructed":
            if entry.get("geometry_status") != "reconstructed_not_attested":
                errors.append(f"{entry['asset_id']}: reconstruction status is absent")
            if not entry.get("component_sources") or not entry.get("exact_source_gap"):
                errors.append(f"{entry['asset_id']}: reconstruction provenance is incomplete")
    return errors


def check_prior_phase_regression(
    radicals: list[dict[str, Any]], characters: list[dict[str, Any]], **_: Any
) -> list[str]:
    errors: list[str] = []
    phase2_manifest = json.loads((ROOT / "metadata" / "manifests" / "phase2.json").read_text())
    phase4_manifest = json.loads((ROOT / "metadata" / "manifests" / "phase4.json").read_text())
    phase2_digest = phase2.deterministic_record_digest(
        [validate2.phase2_projection(record) for record in radicals]
    )
    phase4_digest = phase3.deterministic_record_digest(
        [validate4.phase4_projection(record) for record in characters]
    )
    if phase2_digest != phase2_manifest["record_digest_sha256"]:
        errors.append("Phase 2 radical projection changed")
    if phase4_digest != phase4_manifest["character_record_digest_sha256"]:
        errors.append("Phase 4 character projection changed")
    return errors


def check_manifest(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    asset_manifest: dict[str, Any],
    context: dict[str, Any],
    manifest: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    entries = asset_manifest["stroke_order_assets"]
    expected = {
        "phase": 5,
        "standard": builder.STANDARD,
        "formal_conformance": "not_verified",
        "unique_target_character_count": len(context["target_cps"]),
        "stroke_order_asset_count": len(entries),
        "exact_source_asset_count": sum(
            item.get("provenance_type") != "reconstructed" for item in entries
        ),
        "reconstructed_asset_count": sum(
            item.get("provenance_type") == "reconstructed" for item in entries
        ),
        "radical_record_count": len(radicals),
        "radical_svg_reference_count": sum(bool(item["stroke_order"]) for item in radicals),
        "character_record_count": len(characters),
        "character_svg_reference_count": sum(bool(item["stroke_order"]) for item in characters),
        "missing_character_codepoints": [item["codepoint"] for item in characters if item["stroke_order"] is None],
        "exact_source_missing_codepoints": ["U+6C59"],
        "reconstructed_character_codepoints": ["U+6C59"],
        "radical_standard_conflict_count": sum(bool(item["stroke_order"]["standard_conflicts"]) for item in radicals),
        "character_standard_conflict_count": sum(bool(item["stroke_order"] and item["stroke_order"]["standard_conflicts"]) for item in characters),
        "radical_cns_sequence_count": sum(bool(item["stroke_order"]["taiwan_cns_stroke_sequence"]) for item in radicals),
        "character_cns_sequence_count": sum(bool(item["stroke_order"] and item["stroke_order"]["taiwan_cns_stroke_sequence"]) for item in characters),
        "per_path_stroke_type_name_count": 0,
        "stroke_type_gap_reference_count": sum(bool(item["stroke_order"]) for item in radicals + characters),
        "stroke_order_asset_digest_sha256": phase3.deterministic_record_digest(entries),
        "radical_record_digest_sha256": phase3.deterministic_record_digest(radicals),
        "character_record_digest_sha256": phase3.deterministic_record_digest(characters),
        "phase2_base_record_digest_sha256": phase2.deterministic_record_digest([validate2.phase2_projection(item) for item in radicals]),
        "phase4_base_character_digest_sha256": phase3.deterministic_record_digest([validate4.phase4_projection(item) for item in characters]),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"manifest {key} differs")
    if manifest.get("asset_manifest", {}).get("sha256") != sha256_path(
        ROOT / manifest["asset_manifest"]["local_path"]
    ):
        errors.append("asset manifest digest differs")
    return errors


def format_ids(values: list[str], width: int = 12) -> list[str]:
    return [
        " ".join(values[index : index + width])
        for index in range(0, len(values), width)
    ]


def write_reports(
    radicals: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    words: list[dict[str, Any]],
    checks: list[tuple[str, str, list[str]]],
    manifest: dict[str, Any],
) -> None:
    passed = all(not errors for _, _, errors in checks)
    validation = [
        "# Validation report",
        "",
        f"Phase 5 status: **{'PASS' if passed else 'FAIL'}**",
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
    for prefix, records, id_getter in (
        ("radical", radicals, lambda item: f"R{item['kangxi_number']:03d}"),
        ("character", characters, lambda item: item["codepoint"]),
        ("word", words, lambda item: item["id"]),
    ):
        for record in records:
            for gap in record["gaps"]:
                grouped[(gap["reason"], f"{prefix}.{gap['field']}", gap["detail"])].append(
                    id_getter(record)
                )
    gap_lines = [
        "# Gaps report",
        "",
        "Cumulative radical, character, and word gaps through Phase 5, grouped by allowed reason and exact field.",
        "",
    ]
    for reason in (
        "not_attested",
        "source_unavailable",
        "conflicting_sources",
        "license_prohibits_use",
    ):
        items = sorted(
            (
                (field, detail, ids)
                for (item_reason, field, detail), ids in grouped.items()
                if item_reason == reason
            ),
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

    phase_lines = [
        "# Phase 5 report — stroke order",
        "",
        f"Status: **{'PASS' if passed else 'FAIL'}**",
        "",
        "## Completed",
        "",
        f"- Unique target unified ideographs: **{manifest['unique_target_character_count']:,}**.",
        f"- Generated, licensed ordered SVGs: **{manifest['stroke_order_asset_count']:,}**.",
        f"- Exact-source SVGs: **{manifest['exact_source_asset_count']:,}**; explicitly reconstructed SVGs: **{manifest['reconstructed_asset_count']}**.",
        f"- Radical coverage: **{manifest['radical_svg_reference_count']} / 214**.",
        f"- Character coverage: **{manifest['character_svg_reference_count']:,} / 2,000**.",
        f"- Taiwan CNS comparison sequences: **{manifest['radical_cns_sequence_count']} radicals** and **{manifest['character_cns_sequence_count']:,} characters**.",
        f"- Taiwan/PRC path-count conflicts: **{manifest['radical_standard_conflict_count']} radicals** and **{manifest['character_standard_conflict_count']} characters**.",
        "",
        "## Explicit limitations",
        "",
        "- 汙 (U+6C59) is the sole character without an exact Make Me a Hanzi row. Its delivered fallback is explicitly marked `reconstructed`: strokes 1-3 reuse the left-side 氵 geometry from 污, strokes 4-6 reuse 于 with a disclosed affine placement, and order metadata follows the exact Taiwan CNS sequence 444115. The official KanjiVG index also has no exact U+6C59 entry.",
        "- Make Me a Hanzi declares PRC stroke-order convention but does not claim formal per-character GF 0023-2020 conformance. The standard is therefore a provisional baseline and `formal_conformance` is `not_verified`.",
        f"- Make Me a Hanzi supplies ordered paths but no per-path PRC stroke-type names. All {manifest['stroke_type_gap_reference_count']:,} populated record references keep `stroke_types` null with a source gap; 汙 retains its Taiwan CNS types separately.",
        "- CNS publishes Taiwan stroke types as 1=橫, 2=豎, 3=撇, 4=點, 5=折. These sequences are retained separately and never assigned to PRC path indices without proof that the regional orders align.",
        "",
        "## Implementation decisions introduced in this phase",
        "",
        "1. One SVG is generated per unique unified ideograph and reused when a radical also appears in the top-2,000 character set.",
        "2. Exact-source SVGs preserve source Bézier path strings and order byte-for-value. The single 汙 reconstruction also preserves its selected component path strings, but applies a disclosed affine placement to 于 and must not be presented as attested source geometry.",
        "3. Stroke-count differences against the canonical Taiwan record values are preserved in `stroke_order.standard_conflicts`; no path is added, removed, or reassigned to force agreement.",
        "4. The reference-only GF publication supplies the standard identifier, not redistributable path data. All path content comes from the Arphic-licensed Make Me a Hanzi snapshot.",
        "",
        "## Phase boundary",
        "",
        "Phase 6 validation and deterministic packaging are complete in this snapshot.",
        "",
    ]
    PHASE_REPORT_PATH.write_text("\n".join(phase_lines), encoding="utf-8")


def main() -> None:
    registry = phase3.load_registry()
    radicals, characters, words, asset_manifest, initial_errors = load_records()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    context = load_context(registry, radicals, characters)
    specs: list[tuple[str, str, Callable[..., list[str]]]] = [
        ("P5-01 Record and asset sets", "All radical, character, and unique asset counts and IDs are complete.", check_record_sets),
        ("P5-02 JSON Schema", "Radicals, characters, and stroke-asset entries validate against their schemas.", check_schema),
        ("P5-03 Source integrity", "Pinned graphics and CNS sources reproduce the exact 2,096-of-2,097 coverage boundary.", check_source_integrity),
        ("P5-04 SVG integrity", "Every SVG resolves, hashes, parses, and reproduces either exact source geometry or the disclosed U+6C59 reconstruction plan.", check_svg_assets),
        ("P5-05 Radical joins", "All 214 radicals reproduce their exact source-backed stroke-order objects, sources, and gaps.", check_radical_joins),
        ("P5-06 Character joins", "All exact character joins and the explicitly reconstructed U+6C59 fallback reproduce.", check_character_joins),
        ("P5-07 Type/conflict model", "Unsourced path types remain null and every Taiwan/PRC count difference is flagged.", check_type_and_conflict_model),
        ("P5-08 Asset licensing", "Every generated SVG carries the registered Arphic license, attribution, and modification notice.", check_asset_licensing),
        ("P5-09 Prior-phase regression", "Phase 2 radicals and Phase 4 characters are unchanged after removing Phase 5 fields.", check_prior_phase_regression),
        ("P5-10 Manifest", "Phase 5 counts, coverage, conflicts, digests, and asset-manifest integrity match.", check_manifest),
    ]
    shared = {
        "radicals": radicals,
        "characters": characters,
        "words": words,
        "asset_manifest": asset_manifest,
        "initial_errors": initial_errors,
        "manifest": manifest,
        "registry": registry,
        "context": context,
    }
    checks = [(check_id, detail, function(**shared)) for check_id, detail, function in specs]
    write_reports(radicals, characters, words, checks, manifest)
    failures = sum(bool(errors) for _, _, errors in checks)
    print(
        f"Phase 5 validation: {'PASS' if failures == 0 else 'FAIL'} "
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
