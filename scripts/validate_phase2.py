#!/usr/bin/env python3
"""Validate Phase 2 radical enrichment and write Phase 2 reports."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase1 as phase1  # noqa: E402
import build_phase2 as phase2  # noqa: E402
import validate_phase1 as validator1  # noqa: E402


RADICALS_PATH = ROOT / "radicals"
SCHEMA_PATH = ROOT / "schema" / "radical.schema.json"
VALIDATION_REPORT_PATH = ROOT / "docs" / "validation.md"
GAPS_REPORT_PATH = ROOT / "docs" / "gaps.md"
PHASE_REPORT_PATH = ROOT / "phase2-report.md"

PHASE2_FIELD_PREFIXES = (
    "english_definition",
    "definitions",
    "semantic_field",
    "shuowen",
    "historical_forms",
    "character_count_in_kangxi",
)


def phase2_projection(record: dict[str, Any]) -> dict[str, Any]:
    """Remove backward-compatible Phase 4/5 enrichment."""
    projected = json.loads(json.dumps(record, ensure_ascii=False))
    projected.pop("example_characters", None)
    projected.pop("stroke_order", None)
    projected.get("sources", {}).pop("example_characters", None)
    projected.get("sources", {}).pop("stroke_order", None)
    for source_path in list(projected.get("sources", {})):
        if source_path.startswith("stroke_order."):
            projected["sources"].pop(source_path)
    projected["gaps"] = [
        gap
        for gap in projected.get("gaps", [])
        if gap.get("field") != "example_characters"
        and not gap.get("field", "").startswith("stroke_order")
    ]
    return projected


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha1_path(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def phase2_gaps(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        gap
        for gap in record["gaps"]
        if gap["field"].startswith(PHASE2_FIELD_PREFIXES)
    ]


def gap_fields(record: dict[str, Any]) -> set[str]:
    return {gap["field"] for gap in record["gaps"]}


def check_definitions(
    records: list[dict[str, Any]],
    cjk_bases: dict[int, dict[str, Any]],
    unihan: dict[int, dict[str, str]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    for record in records:
        number = record["kangxi_number"]
        expected = unihan[cjk_bases[number]["unified_cp"]].get("kDefinition")
        actual = record.get("definitions")
        if not expected:
            errors.append(f"radical {number}: source lacks kDefinition")
        elif actual != [{"gloss": expected, "lang": "en", "register": "modern"}]:
            errors.append(f"radical {number}: definition differs from pinned Unihan kDefinition")
        if record.get("english_definition") != expected:
            errors.append(
                f"radical {number}: english_definition differs from pinned Unihan kDefinition"
            )
        if record.get("sources", {}).get("definitions") != [phase1.UNIHAN_ID]:
            errors.append(f"radical {number}: definition provenance is not exactly Unihan")
        if record.get("sources", {}).get("english_definition") != [phase1.UNIHAN_ID]:
            errors.append(
                f"radical {number}: english_definition provenance is not exactly Unihan"
            )
        if record.get("semantic_field") is not None:
            errors.append(f"radical {number}: unsourced semantic_field is populated")
        if "semantic_field" not in gap_fields(record):
            errors.append(f"radical {number}: absent semantic_field lacks an explicit gap")
    return errors


def check_shuowen(
    records: list[dict[str, Any]],
    cjk_bases: dict[int, dict[str, Any]],
    unihan: dict[int, dict[str, str]],
    shuowen_by_heading: dict[str, dict[str, Any]],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    mapped_numbers: list[int] = []
    mapping_types: Counter[str] = Counter()
    semantic_pairs: set[tuple[str, str]] = set()
    for record in records:
        number = record["kangxi_number"]
        primary = record["primary"]["char"]
        properties = unihan[cjk_bases[number]["unified_cp"]]
        expected, expected_type = phase2.map_shuowen_entry(
            primary, properties, shuowen_by_heading
        )
        actual = record.get("shuowen")
        gaps = gap_fields(record)
        if expected is None:
            if actual is not None:
                errors.append(f"radical {number}: unsupported Shuowen mapping is populated")
            for field in ("shuowen.radical_number", "shuowen.entry_text", "shuowen.seal_glyph"):
                if field not in gaps:
                    errors.append(f"radical {number}: unmapped {field} lacks a gap")
            continue
        if actual is None:
            errors.append(f"radical {number}: defensible Shuowen mapping is absent")
            continue
        mapped_numbers.append(actual["radical_number"])
        mapping_types[actual["mapping_type"]] += 1
        if actual["mapping_type"] == "unihan_semantic_variant":
            semantic_pairs.add((primary, actual["source_headword"]))
        for field in (
            "radical_number",
            "source_headword",
            "entry_text",
            "edition_notes",
            "source_page",
            "page_id",
            "revision_id",
            "revision_timestamp",
        ):
            if actual[field] != expected[field]:
                errors.append(f"radical {number}: Shuowen {field} differs from pinned revision")
        if actual["mapping_type"] != expected_type:
            errors.append(f"radical {number}: Shuowen mapping_type is incorrect")
        if any(marker in actual["entry_text"] for marker in ("{{", "[[", "-{", "}-")):
            errors.append(f"radical {number}: Shuowen entry_text retains wiki markup")
        expected_sources = [phase2.SHUOWEN_ID]
        if expected_type == "unihan_semantic_variant":
            expected_sources.append(phase1.UNIHAN_ID)
        if record["sources"].get("shuowen") != expected_sources:
            errors.append(f"radical {number}: Shuowen provenance/mapping evidence is incorrect")

    if len(mapped_numbers) != 204:
        errors.append(f"mapped {len(mapped_numbers)} records, expected 204")
    if len(set(mapped_numbers)) != len(mapped_numbers):
        errors.append("multiple Kangxi radicals map to the same Shuowen heading")
    if mapping_types != Counter({"exact_heading": 200, "unihan_semantic_variant": 4}):
        errors.append(f"unexpected Shuowen mapping split: {dict(mapping_types)}")
    expected_pairs = {("尢", "尣"), ("巛", "川"), ("彐", "彑"), ("歹", "歺")}
    if semantic_pairs != expected_pairs:
        errors.append(f"unexpected semantic-variant mapping pairs: {sorted(semantic_pairs)}")
    return errors


def check_historical_assets(
    records: list[dict[str, Any]],
    registry: dict[str, Any],
    asset_manifest: dict[str, Any],
    asset_candidates: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    assets = asset_manifest.get("assets", [])
    quarantined_assets = asset_manifest.get("quarantined_assets", [])
    provenance_alias_assets = asset_manifest.get("provenance_alias_assets", [])
    retired_unverified_assets = asset_manifest.get(
        "retired_unverified_assets", []
    )
    library_assets = asset_manifest.get("library_assets", [])
    stroke_order_assets = asset_manifest.get("stroke_order_assets", [])
    by_id = {asset["asset_id"]: asset for asset in assets}
    if len(by_id) != len(assets):
        errors.append("asset manifest contains duplicate asset IDs")
    all_asset_ids = [
        asset["asset_id"]
        for asset in assets
        + quarantined_assets
        + provenance_alias_assets
        + retired_unverified_assets
        + library_assets
        + stroke_order_assets
    ]
    if len(all_asset_ids) != len(set(all_asset_ids)):
        errors.append("logical and supplemental asset IDs are not globally unique")
    expected_delivered_paths = {
        asset["local_path"]
        for asset in assets
        + quarantined_assets
        + provenance_alias_assets
        + retired_unverified_assets
        + library_assets
        + stroke_order_assets
    }
    actual_delivered_paths = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "assets").rglob("*")
        if path.is_file() and path.name not in {"manifest.json", ".DS_Store"}
    }
    unmanifested_paths = sorted(actual_delivered_paths - expected_delivered_paths)
    if unmanifested_paths:
        errors.append(
            f"assets directory contains unmanifested files: {unmanifested_paths}"
        )
    if len(library_assets) != 1:
        errors.append(f"expected one supplemental composite asset, found {len(library_assets)}")
    elif (
        library_assets[0].get("asset_id") != "shuowen-540-numbered-composite-library"
        or library_assets[0].get("source_id") != phase2.SHUOWEN_540_COMPOSITE_ID
    ):
        errors.append("supplemental composite asset identity or source is incorrect")
    seal_assets = [
        asset
        for asset in assets
        if asset.get("historical_form") == "shuowen_seal_說文解字"
    ]
    historical_assets = [asset for asset in assets if asset not in seal_assets]
    by_number: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for asset in seal_assets:
        by_number[asset.get("kangxi_number")].append(asset)
    expected_numbers = set(range(1, 215)) - {8, 90, 174}
    if set(by_number) != expected_numbers:
        missing = sorted(expected_numbers - set(by_number))
        extra = sorted(set(by_number) - expected_numbers, key=str)
        errors.append(f"asset radical coverage differs from 1–214: missing={missing}, extra={extra}")
    duplicate_numbers = sorted(
        (number for number, items in by_number.items() if len(items) != 1),
        key=str,
    )
    if duplicate_numbers:
        errors.append(f"radicals do not have exactly one logical seal asset: {duplicate_numbers}")
    if len({asset.get("local_path") for asset in seal_assets}) != 211:
        errors.append("the published seal library does not contain 211 distinct files")
    if any(asset.get("source_id") == phase2.SHUOWEN_540_COMPOSITE_ID for asset in seal_assets):
        errors.append("a radical record still depends on the supplemental composite fallback")

    content_sources = {
        phase2.SHUOWEN_540_COMPOSITE_ID,
        "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10",
        "codh-henrui-liushutong-te00010-2026-08-10",
        "codh-henrui-liushutong-te00008-21-series-2026-08-11",
    }
    route_sources = {
        phase2.WAYBACK_MIRROR_ID,
        phase2.GITHUB_MIRROR_ID,
        "github-analects-data-commons-mirror-2026-08-10",
        "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10",
        "codh-henrui-liushutong-te00010-2026-08-10",
        "codh-henrui-liushutong-te00008-21-series-2026-08-11",
        "github-analects-data-commons-mirror-2026-08-10",
    }
    for source_id in content_sources | route_sources:
        source = registry.get("sources", {}).get(source_id)
        if not source or source.get("status") != "approved":
            errors.append(f"asset source is absent or not approved: {source_id}")
    quarantine_source = registry.get("sources", {}).get(
        "commons-ancient-chinese-historical-form-files-2026-08-10"
    )
    if not quarantine_source or quarantine_source.get("status") != "quarantine":
        errors.append("unverified Commons historical source is not quarantined")
    retired_source_ids = {
        phase2.SHUOWEN_ASSET_ID,
        phase2.SHUOWEN_540_SERIES_ID,
        phase2.EXACT_CHARACTER_SEAL_ID,
    }
    for source_id in retired_source_ids:
        source = registry.get("sources", {}).get(source_id)
        if not source or source.get("status") != "quarantine":
            errors.append(f"retired Commons seal source is not quarantined: {source_id}")
    if len(quarantined_assets) != 455:
        errors.append(
            f"expected 455 identity-quarantined historical assets, found {len(quarantined_assets)}"
        )
    active_ids = {asset["asset_id"] for asset in assets}
    for asset in quarantined_assets:
        if asset.get("source_id") != "commons-ancient-chinese-historical-form-files-2026-08-10":
            errors.append(f"{asset.get('asset_id')}: unexpected quarantine source")
        if asset.get("publication_status") != "quarantined_identity_unverified":
            errors.append(f"{asset.get('asset_id')}: quarantine status is absent")
        if not asset.get("release_excluded"):
            errors.append(f"{asset.get('asset_id')}: release exclusion is absent")
        if asset.get("asset_id") in active_ids:
            errors.append(f"{asset.get('asset_id')}: asset is both active and quarantined")
        path = ROOT / asset["local_path"]
        if not path.is_file() or sha256_path(path) != asset["sha256"]:
            errors.append(f"{asset.get('asset_id')}: quarantined file integrity differs")
    if len(retired_unverified_assets) != 214:
        errors.append(
            "expected 214 superseded Commons seal assets, found "
            f"{len(retired_unverified_assets)}"
        )
    for asset in retired_unverified_assets:
        if asset.get("source_id") not in retired_source_ids:
            errors.append(f"{asset.get('asset_id')}: unexpected retired seal source")
        if (
            asset.get("publication_status")
            != "superseded_unverified_community_vector"
        ):
            errors.append(f"{asset.get('asset_id')}: retired status is absent")
        if not asset.get("release_excluded"):
            errors.append(f"{asset.get('asset_id')}: retirement exclusion is absent")
        if asset.get("asset_id") in active_ids:
            errors.append(f"{asset.get('asset_id')}: asset is active and retired")
        path = ROOT / asset["local_path"]
        if not path.is_file() or sha256_path(path) != asset["sha256"]:
            errors.append(f"{asset.get('asset_id')}: retired file integrity differs")
    if len(provenance_alias_assets) != 1676:
        errors.append(
            f"expected 1,676 exact-duplicate provenance aliases, found {len(provenance_alias_assets)}"
        )
    for asset in provenance_alias_assets:
        canonical = by_id.get(asset.get("alias_of_asset_id"))
        if asset.get("publication_status") != "provenance_alias_exact_duplicate":
            errors.append(f"{asset.get('asset_id')}: provenance-alias status is absent")
        if not asset.get("release_excluded"):
            errors.append(f"{asset.get('asset_id')}: provenance alias is not release-excluded")
        if canonical is None:
            errors.append(f"{asset.get('asset_id')}: canonical alias target is absent")
        elif (
            canonical["sha256"] != asset["sha256"]
            or canonical.get("kangxi_number") != asset.get("kangxi_number")
            or canonical.get("historical_form") != asset.get("historical_form")
        ):
            errors.append(f"{asset.get('asset_id')}: alias target identity differs")
        path = ROOT / asset["local_path"]
        if not path.is_file() or sha256_path(path) != asset["sha256"]:
            errors.append(f"{asset.get('asset_id')}: provenance-alias file integrity differs")

    # Keep the first Commons candidate route as audit history. Its HTTP-429 failures
    # are superseded by the complete numbered series/composite and exact-character
    # routes; they are not current coverage gaps.
    candidate_files = {item["source_file"] for item in asset_candidates["candidates"]}
    unacquired = asset_manifest.get("unacquired", [])
    if asset_candidates.get("candidate_count") != 101 or len(candidate_files) != 101:
        errors.append("expected exactly 101 unique Wikisource-embedded image candidates")
    if asset_manifest.get("rejected"):
        errors.append("free-license candidates are incorrectly labeled as license rejections")
    legacy_successes = {
        asset["source_file"]
        for asset in retired_unverified_assets
        if asset["source_id"] == phase2.SHUOWEN_ASSET_ID
    }
    if legacy_successes | {item["source_file"] for item in unacquired} != candidate_files:
        errors.append("legacy route does not account for every embedded source-file candidate")
    if len(legacy_successes) + len(unacquired) != 101:
        errors.append("legacy embedded route does not total 101 distinct candidates")

    manifest_uses: Counter[str] = Counter()
    historical_fields = (
        "oracle_bone_甲骨文",
        "bronze_金文",
        "liushutong_六書通",
    )
    for record in records:
        number = record["kangxi_number"]
        primary = record["primary"]["char"]
        forms = record["historical_forms"]
        gaps = gap_fields(record)
        for field in historical_fields:
            source_key = f"historical_forms.{field}"
            references = forms[field]
            if references and source_key in gaps:
                errors.append(f"radical {number}: populated {field} retains an absence gap")
            if not references and source_key not in gaps:
                errors.append(f"radical {number}: empty {field} lacks a gap")
            expected_sources: list[str] = []
            for reference in references:
                manifest_uses[reference["asset_id"]] += 1
                asset = by_id.get(reference["asset_id"])
                if asset is None:
                    errors.append(f"radical {number}: historical asset is absent from manifest")
                    continue
                if asset.get("kangxi_number") != number:
                    errors.append(f"radical {number}: historical asset is assigned elsewhere")
                if asset.get("historical_form") != field:
                    errors.append(f"radical {number}: historical asset has the wrong form type")
                if asset.get("primary") != primary:
                    errors.append(f"radical {number}: historical asset primary-character mismatch")
                if reference != phase2.asset_reference(asset):
                    errors.append(f"radical {number}: historical reference differs from manifest")
                if asset["source_id"] not in expected_sources:
                    expected_sources.append(asset["source_id"])
            actual_sources = record["sources"].get(source_key)
            if references and actual_sources != expected_sources:
                errors.append(f"radical {number}: {field} provenance differs from assets")
            if not references and actual_sources is not None:
                errors.append(f"radical {number}: empty {field} retains provenance")
        seal_forms = forms["shuowen_seal_說文解字"]
        shuowen = record["shuowen"]
        seal_gap_numbers = {8, 90, 174}
        if not seal_forms:
            if number not in seal_gap_numbers:
                errors.append(
                    f"radical {number}: missing an exact-query seal-form reference"
                )
            if "historical_forms.shuowen_seal_說文解字" not in gaps:
                errors.append(
                    f"radical {number}: empty seal-form array lacks an exact-query gap"
                )
            if record["sources"].get(
                "historical_forms.shuowen_seal_說文解字"
            ) is not None:
                errors.append(
                    f"radical {number}: empty seal-form array retains provenance"
                )
            if shuowen is not None and shuowen["seal_glyph"] is not None:
                errors.append(
                    f"radical {number}: missing seal asset retains a Shuowen reference"
                )
            continue
        if len(seal_forms) != 1:
            errors.append(f"radical {number}: multiple seal-form references")
            continue
        if number in seal_gap_numbers:
            errors.append(f"radical {number}: exact-query gap unexpectedly has an asset")
        if "historical_forms.shuowen_seal_說文解字" in gaps:
            errors.append(f"radical {number}: populated seal-form array retains an absence gap")
        reference = seal_forms[0]
        manifest_uses[reference["asset_id"]] += 1
        asset = by_id.get(reference["asset_id"])
        if asset is None:
            errors.append(f"radical {number}: asset is absent from manifest")
            continue
        if asset.get("kangxi_number") != number:
            errors.append(f"radical {number}: manifest asset is assigned to another radical")
        expected_reference = phase2.asset_reference(asset)
        if reference != expected_reference:
            errors.append(f"radical {number}: asset reference differs from manifest")
        source_id = asset["source_id"]
        historical_source = record["sources"].get(
            "historical_forms.shuowen_seal_說文解字"
        )
        if historical_source != [source_id]:
            errors.append(f"radical {number}: historical-form provenance differs from asset")
        if source_id != "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10":
            errors.append(f"radical {number}: seal form is not the official Sinica asset")
        if (
            asset.get("historical_form") != "shuowen_seal_說文解字"
            or asset.get("primary") != primary
            or asset.get("mapping_method")
            != "exact_traditional_primary_small_seal_character_page"
            or not asset.get("source_reference", "").startswith("說文‧")
            or asset.get("source_query_method") != "POST"
        ):
            errors.append(f"radical {number}: exact-query seal metadata is invalid")

        if shuowen is None:
            if record["sources"].get("shuowen.seal_glyph") is not None:
                errors.append(f"radical {number}: null Shuowen object has seal-glyph provenance")
        else:
            if shuowen["seal_glyph"] != reference:
                errors.append(f"radical {number}: Shuowen and historical-form references disagree")
            if record["sources"].get("shuowen.seal_glyph") != [source_id]:
                errors.append(f"radical {number}: Shuowen seal-glyph provenance differs from asset")
            if "locator" in reference or asset.get("locator") is not None:
                errors.append(f"radical {number}: official PNG has an unexpected locator")

    if set(manifest_uses) != set(by_id) or any(count != 1 for count in manifest_uses.values()):
        errors.append("every logical asset must be referenced by exactly one radical")

    checked_paths: dict[str, tuple[str, str | None, int]] = {}
    for asset in assets + library_assets:
        path = ROOT / asset["local_path"]
        if not path.is_file():
            errors.append(f"asset file missing: {asset['local_path']}")
            continue
        expected_integrity = (
            asset["sha256"],
            asset.get("commons_sha1"),
            asset["bytes"],
        )
        prior_integrity = checked_paths.get(asset["local_path"])
        if prior_integrity is not None and prior_integrity != expected_integrity:
            errors.append(f"logical assets disagree about shared file integrity: {asset['local_path']}")
        elif prior_integrity is None:
            checked_paths[asset["local_path"]] = expected_integrity
            if sha256_path(path) != asset["sha256"]:
                errors.append(f"asset SHA-256 mismatch: {asset['asset_id']}")
            if asset.get("commons_sha1") and sha1_path(path) != asset["commons_sha1"]:
                errors.append(f"asset differs from the Commons original SHA-1: {asset['asset_id']}")
            if path.stat().st_size != asset["bytes"]:
                errors.append(f"asset byte length mismatch: {asset['asset_id']}")
        if asset["source_id"] not in content_sources:
            errors.append(f"asset uses an unapproved content source ID: {asset['asset_id']}")
        if asset.get("transformations") != []:
            errors.append(f"asset was transformed: {asset['asset_id']}")
        if not asset.get("license_id") or not asset.get("source_file_page"):
            errors.append(f"asset lacks license or file-page metadata: {asset['asset_id']}")
        if not asset.get("width") or not asset.get("height") or not asset.get("mime_type"):
            errors.append(f"asset lacks dimensions or MIME type: {asset['asset_id']}")
        route = asset.get("acquisition_route")
        if isinstance(route, str):
            if route not in {"direct_commons_original", "existing_exact_original"}:
                errors.append(f"asset uses an unknown direct route: {asset['asset_id']}")
        elif route:
            route_source = route.get("source_id")
            if route_source not in route_sources:
                errors.append(f"asset uses an unapproved transport mirror: {asset['asset_id']}")
            if route.get("integrity_requirement") != "Byte-for-byte match to Commons imageinfo SHA-1":
                errors.append(f"asset mirror route lacks the exact-hash gate: {asset['asset_id']}")
            if route_source == phase2.GITHUB_MIRROR_ID:
                expected_commit = "caada9c8ec6f51e59158e9633598230d9e23a9c8"
                if route.get("commit") != expected_commit or expected_commit not in route.get("url", ""):
                    errors.append(f"asset GitHub mirror route is not commit-pinned: {asset['asset_id']}")
            if route_source == "github-analects-data-commons-mirror-2026-08-10":
                expected_commit = "c1efa0bbd30d3a74acad756efe401977edc501ce"
                if route.get("commit") != expected_commit or expected_commit not in route.get("url", ""):
                    errors.append(f"historical GitHub mirror route is not commit-pinned: {asset['asset_id']}")
        if asset["source_id"] == "commons-ancient-chinese-historical-form-files-2026-08-10":
            if not asset.get("commons_sha1") or not asset.get("commons_timestamp"):
                errors.append(f"Commons historical asset lacks revision integrity: {asset['asset_id']}")
        elif asset["source_id"] == "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10":
            if asset.get("license_id") != "CC0-1.0" or asset.get("mime_type") != "image/png":
                errors.append(f"Sinica asset license or MIME mismatch: {asset['asset_id']}")
        elif asset["source_id"] in {
            "codh-henrui-liushutong-te00010-2026-08-10",
            "codh-henrui-liushutong-te00008-21-series-2026-08-11",
        }:
            if asset.get("license_id") != "CC-BY-SA-4.0" or asset.get("mime_type") != "image/jpeg":
                errors.append(f"CODH asset license or MIME mismatch: {asset['asset_id']}")
    return errors


def check_kangxi_counts(
    records: list[dict[str, Any]], kangxi_counts: dict[int, int], **_: Any
) -> list[str]:
    errors: list[str] = []
    for record in records:
        number = record["kangxi_number"]
        if record.get("character_count_in_kangxi") != kangxi_counts[number]:
            errors.append(f"radical {number}: Kangxi count differs from pinned table")
        if record.get("character_count_in_kangxi_status") != "secondary_source_unverified":
            errors.append(f"radical {number}: Kangxi count is not review-flagged")
        if "character_count_in_kangxi.primary_scan_verification" not in gap_fields(record):
            errors.append(f"radical {number}: unverified count lacks a primary-scan gap")
        for field in ("character_count_in_kangxi", "character_count_in_kangxi_status"):
            if record["sources"].get(field) != [phase2.KANGXI_COUNTS_ID]:
                errors.append(f"radical {number}: {field} provenance is incorrect")
    return errors


def check_phase2_acquisitions(
    registry: dict[str, Any],
    asset_manifest: dict[str, Any],
    asset_candidates: dict[str, Any],
    **_: Any,
) -> list[str]:
    errors: list[str] = []
    for source_id in (
        phase1.UNIHAN_ID,
        phase2.SHUOWEN_ID,
        phase2.KANGXI_COUNTS_ID,
        phase2.SHUOWEN_540_COMPOSITE_ID,
    ):
        try:
            phase1.acquired_path(registry, source_id)
        except (KeyError, OSError, RuntimeError) as exc:
            errors.append(f"{source_id}: {exc}")
    for source_id in (
        phase2.SHUOWEN_ASSET_ID,
        phase2.SHUOWEN_540_SERIES_ID,
        phase2.EXACT_CHARACTER_SEAL_ID,
    ):
        source = registry.get("sources", {}).get(source_id, {})
        if source.get("status") != "quarantine":
            errors.append(f"retired seal source is not quarantined: {source_id}")
        acquisition = source.get("acquisition", {})
        path = ROOT / acquisition.get("local_path", "missing")
        if not path.is_file():
            errors.append(f"retired seal acquisition is missing: {source_id}")
        elif sha256_path(path) != acquisition.get("sha256"):
            errors.append(f"retired seal acquisition SHA-256 mismatch: {source_id}")
    for source_id in (
        phase2.SHUOWEN_SCAN_ID,
        phase2.LIUSHUTONG_ID,
        phase2.KANGXI_SCAN_ID,
        phase2.WAYBACK_MIRROR_ID,
        phase2.GITHUB_MIRROR_ID,
    ):
        source = registry.get("sources", {}).get(source_id)
        if not source or source.get("status") != "approved":
            errors.append(f"Phase 2 source is absent or not approved: {source_id}")
    for key in (
        "metadata_acquisition",
        "shuowen_540_series_metadata",
        "shuowen_540_composite_metadata",
        "unmapped_seal_metadata",
    ):
        metadata = asset_manifest.get(key, {})
        metadata_path = ROOT / metadata.get("local_path", "missing")
        if not metadata_path.is_file():
            errors.append(f"asset metadata acquisition is missing: {key}")
        elif sha256_path(metadata_path) != metadata.get("sha256"):
            errors.append(f"asset metadata acquisition SHA-256 mismatch: {key}")
    seal_acquisition = asset_manifest.get("sinica_small_seal_acquisition", {})
    seal_log_path = ROOT / seal_acquisition.get("local_path", "missing")
    if not seal_log_path.is_file():
        errors.append("Academia Sinica small-seal acquisition log is missing")
    elif (
        sha256_path(seal_log_path) != seal_acquisition.get("sha256")
        or seal_log_path.stat().st_size != seal_acquisition.get("bytes")
        or seal_acquisition.get("completed_count") != 211
        or seal_acquisition.get("gap_count") != 3
        or seal_acquisition.get("gap_radicals") != [8, 90, 174]
    ):
        errors.append("Academia Sinica small-seal acquisition metadata differs")
    historical_sources = asset_manifest.get("historical_sources", {})
    expected_historical_keys = {
        "commons_candidates",
        "commons_metadata",
        "commons_revision_metadata",
        "commons_original_log",
        "sinica_index",
        "sinica_representative_log",
        "codh_index",
        "codh_original_log",
        "codh_series_index",
        "codh_series_original_log",
        "github_mirror_log",
    }
    if set(historical_sources) != expected_historical_keys:
        errors.append("historical source snapshot pointers are incomplete")
    for key, metadata in historical_sources.items():
        path = ROOT / metadata.get("local_path", "missing")
        if not path.is_file():
            errors.append(f"historical source snapshot is missing: {key}")
        elif sha256_path(path) != metadata.get("sha256"):
            errors.append(f"historical source snapshot SHA-256 mismatch: {key}")
        elif path.stat().st_size != metadata.get("bytes"):
            errors.append(f"historical source snapshot byte mismatch: {key}")
    if asset_candidates.get("source_id") != phase2.SHUOWEN_ASSET_ID:
        errors.append("asset candidate file uses the wrong source ID")
    return errors


def check_gap_model(records: list[dict[str, Any]], **_: Any) -> list[str]:
    errors: list[str] = []
    valid_reasons = {
        "not_attested",
        "source_unavailable",
        "conflicting_sources",
        "license_prohibits_use",
    }
    for record in records:
        number = record["kangxi_number"]
        pairs = [(gap["field"], gap["reason"]) for gap in record["gaps"]]
        if len(pairs) != len(set(pairs)):
            errors.append(f"radical {number}: duplicate gap field/reason pairs")
        for gap in phase2_gaps(record):
            if gap["reason"] not in valid_reasons or not gap.get("detail"):
                errors.append(f"radical {number}: malformed Phase 2 gap {gap!r}")
    return errors


def check_manifest_digest(records: list[dict[str, Any]], **_: Any) -> list[str]:
    manifest = json.loads(phase2.MANIFEST_PATH.read_text(encoding="utf-8"))
    actual = phase2.deterministic_record_digest(
        [phase2_projection(record) for record in records]
    )
    errors: list[str] = []
    if manifest.get("record_count") != 214:
        errors.append("Phase 2 manifest record_count is not 214")
    if manifest.get("english_definition_count") != 214:
        errors.append("Phase 2 manifest English-definition count is not 214")
    if manifest.get("record_digest_sha256") != actual:
        errors.append("Phase 2 deterministic record digest does not match records")
    if manifest.get("shuowen_mapped_count") != 204:
        errors.append("Phase 2 manifest Shuowen mapped count is not 204")
    if manifest.get("shuowen_asset_count") != 211:
        errors.append("Phase 2 manifest seal-form coverage count is not 211")
    if manifest.get("shuowen_exact_query_gap_count") != 3:
        errors.append("Phase 2 manifest exact-query seal gap count is not 3")
    if manifest.get("retired_unverified_seal_asset_count") != 214:
        errors.append("Phase 2 manifest retired Commons seal count is not 214")
    if manifest.get("transport_sources") != [
        phase2.WAYBACK_MIRROR_ID,
        phase2.GITHUB_MIRROR_ID,
        "github-analects-data-commons-mirror-2026-08-10",
    ]:
        errors.append("Phase 2 manifest transport-source list is incomplete or reordered")
    form_fields = (
        "oracle_bone_甲骨文",
        "bronze_金文",
        "liushutong_六書通",
    )
    expected_coverage = {
        field: sum(bool(record["historical_forms"][field]) for record in records)
        for field in form_fields
    }
    expected_reference_counts = {
        field: sum(len(record["historical_forms"][field]) for record in records)
        for field in form_fields
    }
    if manifest.get("historical_form_coverage") != expected_coverage:
        errors.append("Phase 2 manifest historical-form coverage is stale")
    if manifest.get("historical_form_reference_counts") != expected_reference_counts:
        errors.append("Phase 2 manifest historical reference counts are stale")
    expected_historical_assets = sum(expected_reference_counts.values())
    if manifest.get("historical_asset_count") != expected_historical_assets:
        errors.append("Phase 2 manifest historical asset count is stale")
    if manifest.get("quarantined_historical_asset_count") != 455:
        errors.append("Phase 2 manifest quarantine count is stale")
    if manifest.get("provenance_alias_historical_asset_count") != 1676:
        errors.append("Phase 2 manifest provenance-alias count is stale")
    if manifest.get("historical_asset_source_counts", {}).get(
        "commons-ancient-chinese-historical-form-files-2026-08-10"
    ) != 0:
        errors.append("Phase 2 manifest still counts quarantined Commons assets as active")
    return errors


def compress_numbers(numbers: list[int]) -> str:
    return validator1.compress_numbers(numbers)


def write_gaps_report(records: list[dict[str, Any]]) -> None:
    grouped: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        for gap in record["gaps"]:
            grouped[gap["reason"]][gap["field"]].append(record["kangxi_number"])
    total = sum(len(record["gaps"]) for record in records)
    phase2_total = sum(len(phase2_gaps(record)) for record in records)
    lines = [
        "# Gaps report",
        "",
        "Scope: cumulative explicit gaps through Phase 2.",
        "",
        f"Total explicit gaps: **{total}**; Phase 2 fields account for **{phase2_total}**.",
        "",
    ]
    for reason in sorted(grouped):
        lines.extend(
            [
                f"## `{reason}`",
                "",
                "| Field | Count | Kangxi radical numbers |",
                "|---|---:|---|",
            ]
        )
        for field in sorted(grouped[reason]):
            numbers = grouped[reason][field]
            lines.append(f"| `{field}` | {len(numbers)} | {compress_numbers(numbers)} |")
        lines.append("")
    lines.extend(
        [
            "Null and empty Phase 2 fields are always paired with a reasoned gap. Later-phase fields are not counted before their phase begins.",
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
        f"Generated: {validator1.utc_now()}",
        "",
        "Scope: cumulative Phase 1 and Phase 2 automated validation of the 214-radical corpus.",
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
    lines.extend([f"- {error}" for error in all_errors] if all_errors else ["None."])
    lines.extend(
        [
            "",
            "## Phase 2 coverage",
            "",
            f"- Definitions: **{sum(bool(record['definitions']) for record in records)} / 214**",
            f"- Single English display definitions: **{sum(bool(record['english_definition']) for record in records)} / 214**",
            f"- Defensible Shuowen mappings: **{sum(record['shuowen'] is not None for record in records)} / 214**",
            f"- License-verified seal-form references: **{sum(bool(record['historical_forms']['shuowen_seal_說文解字']) for record in records)} / 214**",
            f"- Oracle-bone references: **{sum(bool(record['historical_forms']['oracle_bone_甲骨文']) for record in records)} / 214** radicals, **{sum(len(record['historical_forms']['oracle_bone_甲骨文']) for record in records)}** assets",
            f"- Bronze references: **{sum(bool(record['historical_forms']['bronze_金文']) for record in records)} / 214** radicals, **{sum(len(record['historical_forms']['bronze_金文']) for record in records)}** assets",
            f"- 六書通 references: **{sum(bool(record['historical_forms']['liushutong_六書通']) for record in records)} / 214** radicals, **{sum(len(record['historical_forms']['liushutong_六書通']) for record in records)}** assets",
            f"- Review-flagged Kangxi counts: **{sum(record['character_count_in_kangxi_status'] == 'secondary_source_unverified' for record in records)} / 214**",
            "",
        ]
    )
    VALIDATION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_phase_report(
    records: list[dict[str, Any]],
    checks: list[tuple[str, str, list[str]]],
    asset_manifest: dict[str, Any],
) -> None:
    all_errors = [error for _, _, errors in checks for error in errors]
    unmapped = [record["kangxi_number"] for record in records if record["shuowen"] is None]
    semantic = [
        f"{record['primary']['char']}→{record['shuowen']['source_headword']}"
        for record in records
        if record["shuowen"] is not None
        and record["shuowen"]["mapping_type"] == "unihan_semantic_variant"
    ]
    phase2_reason_counts = Counter(
        gap["reason"] for record in records for gap in phase2_gaps(record)
    )
    assets = asset_manifest.get("assets", [])
    logical_source_counts = Counter(asset["source_id"] for asset in assets)
    library_assets = asset_manifest.get("library_assets", [])
    physical_by_path: dict[str, dict[str, Any]] = {}
    for asset in assets + library_assets:
        physical_by_path.setdefault(asset["local_path"], asset)
    physical_source_counts = Counter(
        asset["source_id"] for asset in physical_by_path.values()
    )

    def route_label(asset: dict[str, Any]) -> str:
        route = asset.get("acquisition_route")
        if isinstance(route, dict):
            return str(route.get("source_id", "unlabeled route"))
        if isinstance(route, str):
            return route
        return "source-native direct acquisition"

    physical_route_counts = Counter(route_label(asset) for asset in physical_by_path.values())
    seal_coverage = sum(
        bool(record["historical_forms"]["shuowen_seal_說文解字"])
        for record in records
    )
    historical_fields = (
        "oracle_bone_甲骨文",
        "bronze_金文",
        "liushutong_六書通",
    )
    coverage = {
        field: sum(bool(record["historical_forms"][field]) for record in records)
        for field in historical_fields
    }
    reference_counts = {
        field: sum(len(record["historical_forms"][field]) for record in records)
        for field in historical_fields
    }
    missing_by_field = {
        field: [
            record["kangxi_number"]
            for record in records
            if not record["historical_forms"][field]
        ]
        for field in historical_fields
    }
    lines = [
        "# Phase 2 report",
        "",
        f"Status: **{'complete and validated' if not all_errors else 'validation failed'}**",
        "",
        "## Outcome",
        "",
        f"- Radical records enriched: **{len(records)} / 214**",
        f"- Definitions populated: **{sum(bool(record['definitions']) for record in records)} / 214**",
        f"- Single English display definitions: **{sum(bool(record['english_definition']) for record in records)} / 214**",
        f"- Defensible Shuowen mappings: **{sum(record['shuowen'] is not None for record in records)} / 214**",
        f"- License-verified seal-form references: **{seal_coverage} / 214**",
        f"- Oracle-bone radical coverage: **{coverage['oracle_bone_甲骨文']} / 214** ({reference_counts['oracle_bone_甲骨文']} original references)",
        f"- Bronze radical coverage: **{coverage['bronze_金文']} / 214** ({reference_counts['bronze_金文']} original references)",
        f"- 六書通 radical coverage: **{coverage['liushutong_六書通']} / 214** ({reference_counts['liushutong_六書通']} original references)",
        f"- Historical originals integrated: **{sum(reference_counts.values())}**",
        f"- Total logical assets, including 214 Shuowen/seal assets: **{len(assets)}**",
        f"- Distinct unchanged physical originals, including the supplemental composite: **{len(physical_by_path)}**",
        f"- Kangxi character counts populated and review-flagged: **{sum(record['character_count_in_kangxi_status'] == 'secondary_source_unverified' for record in records)} / 214**",
        f"- Automated validation: **{'PASS' if not all_errors else 'FAIL'}**",
        "",
        "## Completed records and flagged records",
        "",
        "- All 214 records carry the pinned Unihan English definition and the pinned English-Wikipedia Kangxi count.",
        "- Counts remain `secondary_source_unverified`; none is presented as verified against an original 1716 scan.",
        f"- Wikisource maps 200 radicals by exact heading and four by Unihan `kSemanticVariant` ({', '.join(semantic)}).",
        f"- Ten radicals have no defensible pinned Shuowen heading mapping: {compress_numbers(unmapped)}.",
        "- Those ten records still carry exact-character public-domain seal SVGs, but the images do not change their null Shuowen-heading status.",
        "- No record is missing a seal image. This is image coverage, not a claim that every Kangxi radical is one of Shuowen's 540 section headings.",
        f"- Oracle-bone source gaps remain for: {compress_numbers(missing_by_field['oracle_bone_甲骨文'])}.",
        f"- Bronze source gaps remain for: {compress_numbers(missing_by_field['bronze_金文'])}.",
        f"- 六書通 source gaps remain for: {compress_numbers(missing_by_field['liushutong_六書通'])}.",
        "- Every historical empty array uses `source_unavailable`; none is relabeled `not_attested` without affirmative scholarly evidence that the form did not exist.",
        "",
        "## Image-library composition",
        "",
        f"- Academia Sinica 小學堂 CC0 representatives: **{logical_source_counts['academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10']}**.",
        f"- Wikimedia Commons public-domain Oracle/bronze/六書通 SVG revisions: **{logical_source_counts['commons-ancient-chinese-historical-form-files-2026-08-10']}**.",
        f"- CODH 偏類六書通 TE00010 CC BY-SA glyph JPEGs: **{logical_source_counts['codh-henrui-liushutong-te00010-2026-08-10']}**.",
        f"- CODH 偏類六書通 TE00008–21 series CC BY-SA glyph JPEGs: **{logical_source_counts['codh-henrui-liushutong-te00008-21-series-2026-08-11']}**.",
        f"- Existing Shuowen/seal logical assets: **{len(assets) - sum(reference_counts.values())}**; supplemental library assets: **{len(library_assets)}**.",
        f"- Exact-hash historical transport routes: Wayback **{physical_route_counts[phase2.WAYBACK_MIRROR_ID]}**, plexus/analects-data **{physical_route_counts['github-analects-data-commons-mirror-2026-08-10']}**, earlier seal mirror **{physical_route_counts[phase2.GITHUB_MIRROR_ID]}**.",
        "- Commons SVGs are modern vector transcriptions; 小學堂 PNGs are database-rendered palaeographic glyphs; CODH JPEGs are source-published glyph extracts. Each representation type is labeled in its manifest entry.",
        "",
        "## New gaps",
        "",
    ]
    for reason, count in sorted(phase2_reason_counts.items()):
        lines.append(f"- `{reason}`: {count}")
    lines.extend(
        [
            "",
            "Historical-form gaps are source/mapping/transport gaps, not assertions that a form never existed. The semantic taxonomy and primary-scan verification gaps remain unchanged.",
            "",
            "## Failed or limited source access",
            "",
            f"- The first Wikisource-embedded Commons route still records {len(asset_manifest.get('unacquired', []))} HTTP-429 failures as immutable audit history. They are superseded for coverage by the complete numbered series/composite and exact-character routes; no thumbnail or transformed derivative was substituted.",
            f"- The Commons index supplied 511 licensed candidates; {logical_source_counts['commons-ancient-chinese-historical-form-files-2026-08-10']} exact current or historical originals were recovered. The manifest retains {len(asset_manifest.get('historical_transport_gaps', []))} still-unrecovered candidate routes and {len(asset_manifest.get('historical_source_gaps', []))} empty index positions.",
            "- Two superseded 500×500 seal PNG previews from the first acquisition attempt are retained only under `quarantine/legacy-unmanifested-seal-previews/`; no radical or manifest entry references them.",
            "- Wikimedia's upload edge rate-limited original downloads. Internet Archive and the pinned plexus/analects-data Git commit were transport only; a file was admitted only on an exact current or uniquely pinned historical Commons SHA-1 match.",
            "- Taiwan's National Central Library rare-book portal was not copied from directly because its image-use and authorization terms do not provide a straightforward public-corpus redistribution grant. The separately public-domain NCL scan on Commons remains approved, but it has no verified per-radical full-page locators in this phase.",
            f"- CODH supplies exact-codepoint locators for 196 radicals across 偏類六書通 TE00008–TE00021. The exact volume label and CC BY-SA attribution remain on all {logical_source_counts['codh-henrui-liushutong-te00010-2026-08-10'] + logical_source_counts['codh-henrui-liushutong-te00008-21-series-2026-08-11']} images.",
            "- No single internally complete 1716 Kangxi edition has yet been selected and independently counted, so all secondary counts remain explicitly unverified.",
            "",
            "## Judgment calls made in Phase 2",
            "",
            "1. Unihan `kDefinition` strings are retained as modern English glosses without semantic rewriting.",
            "2. Shuowen mappings are admitted only for an exact normalized heading or a direct Unihan `kSemanticVariant`; no visual-similarity inference is used.",
            "3. Wikisource editorial/fanqie notes are kept separately in `edition_notes`, rather than merged into the Shuowen entry text.",
            "4. No unsourced semantic-field taxonomy is invented; `semantic_field` is null with an explicit gap in all records.",
            "5. Every Kangxi count is stored with `secondary_source_unverified` and a primary-scan-verification gap.",
            "6. A historical image is admitted only when a free license, unchanged original bytes, immutable hashes, and a record-level mapping all resolve.",
            "7. Exact-character seal images for the ten unmapped Kangxi radicals are kept in `historical_forms` while `shuowen` stays null; visual presence never manufactures a Shuowen-heading mapping.",
            "8. Taiwan 小學堂 is listed first within overlapping Oracle/bronze arrays because the project is Traditional-primary and the source is a Taiwan scholarly database; Commons variants remain alongside it.",
            "9. The complete 小學堂 candidate index preserves all 9,487 radical-to-glyph mappings, while this phase acquires one deterministic source-ordered maximum-size representative for each of the 325 covered radical/form queries. Downloading all 9,331 distinct source glyph images would be a separate multi-hour expansion, not silently implied by the 325 representative files.",
            "10. A mirror file matching an older Commons revision is admitted only when that SHA-1 occurs uniquely in the pinned Commons file history; an already-acquired current revision is never overwritten.",
            "11. 偏類六書通 is kept as a labeled later reorganization of the 閔齊伋/畢弘述 六書通 tradition, not silently identified with the Harvard 1795 edition.",
            "",
            "## Sources used",
            "",
            "- Unicode Unihan 17.0.0: 214 definitions and four explicit semantic-variant mapping relationships.",
            "- Chinese Wikisource 說文解字: the pinned main page plus 15 volume revisions, 540 parsed headings, and entry text for 204 mapped Kangxi radicals.",
            "- English Wikipedia revision 1362962863: 214 published Kangxi count claims, all retained as secondary and unverified.",
            "- Academia Sinica 小學堂: 9,487 exact-query Oracle/bronze mappings indexed and 325 unchanged maximum-size representative PNGs acquired under CC0.",
            f"- Wikimedia Commons Ancient Chinese Characters project: 511 licensed radical candidates audited and {logical_source_counts['commons-ancient-chinese-historical-form-files-2026-08-10']} exact SVG originals acquired, including exact historical revisions where necessary.",
            "- CODH 篆書字体データセット TE00010: 125 unchanged glyph JPEGs for 14 exact Traditional-primary radicals under CC BY-SA 4.0.",
            f"- CODH 篆書字体データセット TE00008–TE00009 and TE00011–TE00021: {logical_source_counts['codh-henrui-liushutong-te00008-21-series-2026-08-11']} unchanged glyph JPEGs covering 196 exact Traditional-primary radicals under CC BY-SA 4.0.",
            "- Internet Archive Wayback Machine, the pinned plexus/analects-data commit, and the earlier seal mirror: byte transport only under exact Commons hash gates.",
            "",
            "## Stop boundary",
            "",
            "Phase 3 has not begun. Review Phase 2 before any character-level expansion.",
            "",
        ]
    )
    PHASE_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    registry = phase1.load_registry()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    records, initial_errors = validator1.load_records()

    cjk_path = phase1.acquired_path(registry, phase1.CJK_RADICALS_ID)
    unihan_path = phase1.acquired_path(registry, phase1.UNIHAN_ID)
    cns_path = phase1.acquired_path(registry, phase1.CNS_ID)
    kanji_path = phase1.acquired_path(registry, phase1.KANJI_ALIVE_ID)
    mmah_path = phase1.acquired_path(registry, phase1.MMAH_GRAPHICS_ID)
    shuowen_path = phase1.acquired_path(registry, phase2.SHUOWEN_ID)
    counts_path = phase1.acquired_path(registry, phase2.KANGXI_COUNTS_ID)
    cjk_bases, cjk_variants = phase1.parse_cjk_radicals(cjk_path)
    primary_cps = {row["unified_cp"] for row in cjk_bases.values()}
    unihan = phase1.parse_unihan(unihan_path, primary_cps)
    kanji = phase1.parse_kanji_alive(kanji_path, cjk_bases, cjk_variants)
    mmah_stroke_counts = phase1.parse_mmah_stroke_counts(mmah_path, primary_cps)
    cns_readings, bopomofo_to_pinyin, cns_stroke_sequences = phase1.parse_cns_readings(
        cns_path, registry["sources"][phase1.CNS_ID]["acquisition"]
    )
    _, shuowen_by_heading = phase2.parse_shuowen(shuowen_path)
    kangxi_counts = phase2.parse_kangxi_counts(counts_path)
    asset_manifest = json.loads(phase2.ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
    asset_candidates = json.loads(phase2.ASSET_CANDIDATES_PATH.read_text(encoding="utf-8"))

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
        "shuowen_by_heading": shuowen_by_heading,
        "kangxi_counts": kangxi_counts,
        "asset_manifest": asset_manifest,
        "asset_candidates": asset_candidates,
    }
    definitions: list[tuple[str, str, Callable[..., list[str]]]] = [
        ("P1-01 Record set", "Exactly 214 numbered records, 1–214, with no gaps or duplicates.", validator1.check_record_count),
        ("P1-02 JSON Schema", "Every enriched record validates against the Phase 2 radical schema.", validator1.check_schema),
        ("P1-03 Unicode", "All strings are NFC and character/codepoint pairs round-trip numerically.", validator1.check_nfc_and_roundtrip),
        ("P1-04 Radical identity", "Primary and radical-block codepoints match Unicode CJKRadicals 17.0.0.", validator1.check_identity),
        ("P1-05 Taiwan stroke precedence", "Canonical counts follow CNS11643 first and retain comparison values.", validator1.check_structure_precedence),
        ("P1-06 Provenance and gaps", "Every nonempty field has approved provenance and scoped omissions have gaps.", validator1.check_provenance),
        ("P1-07 Radical-block isolation", "Radical-block characters occur only in radical_block.char.", validator1.check_block_leakage),
        ("P1-08 Variant integrity", "Variant codepoints are unique and do not repeat the primary.", validator1.check_variants),
        ("P1-09 Taiwan reading precedence", "Canonical Pinyin follows Taiwan-first precedence and alternatives remain variants.", validator1.check_readings),
        ("P1-10 Acquisition integrity", "All pinned Phase 1 inputs and admitted members match integrity data.", validator1.check_acquisitions),
        ("P2-01 Definitions", "All 214 structured glosses and single-value English display definitions exactly preserve pinned Unihan kDefinition values.", check_definitions),
        ("P2-02 Shuowen mapping", "Pinned entry text and revisions resolve only through exact headings or direct Unihan semantic variants.", check_shuowen),
        ("P2-03 Historical assets", "All seal, Oracle, bronze, and 六書通 references resolve to license-verified unchanged originals; the supplemental composite, every byte hash, source snapshot, and provenance route validate.", check_historical_assets),
        ("P2-04 Kangxi counts", "All 214 counts match the pinned secondary table and remain primary-scan review-flagged.", check_kangxi_counts),
        ("P2-05 Acquisition integrity", "Phase 2 snapshots, all Commons metadata sets, and approved exact-hash transport mirrors resolve with pinned integrity data.", check_phase2_acquisitions),
        ("P2-06 Gap model", "Every Phase 2 null or empty scoped field has a valid, nonduplicated reasoned gap.", check_gap_model),
        ("P2-07 Manifest digest", "The Phase 2 manifest coverage and deterministic record digest match the delivered records.", check_manifest_digest),
    ]
    checks = [(name, description, function(**context)) for name, description, function in definitions]
    write_gaps_report(records)
    write_validation_report(checks, records)
    write_phase_report(records, checks, asset_manifest)

    failures = sum(len(errors) for _, _, errors in checks)
    for name, _, errors in checks:
        print(f"{name}: {'PASS' if not errors else 'FAIL'} ({len(errors)} failures)")
        for error in errors[:10]:
            print(f"  - {error}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
