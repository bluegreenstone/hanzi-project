#!/usr/bin/env python3
"""Integrate verified Oracle, bronze, and 六書通 assets into Phase 2."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase2 as phase2  # noqa: E402


MANIFEST = ROOT / "assets" / "manifest.json"
PHASE2_MANIFEST = ROOT / "metadata" / "manifests" / "phase2.json"
SOURCES = ROOT / "sources.json"
COMMON_CANDIDATES = ROOT / "metadata" / "audits" / "phase2-historical-asset-candidates.json"
COMMON_METADATA = (
    ROOT
    / "source-data"
    / "wikimedia-2026-08-10"
    / "commons-acc-historical-file-metadata.json"
)
COMMON_REVISIONS = (
    ROOT
    / "source-data"
    / "wikimedia-2026-08-10"
    / "commons-acc-historical-file-revisions.json"
)
COMMON_LOG = (
    ROOT
    / "source-data"
    / "wikimedia-2026-08-10"
    / "commons-acc-historical-original-acquisition-log.json"
)
SINICA_INDEX = (
    ROOT
    / "source-data"
    / "sinica-xiaoxuetang-2026-08-10"
    / "radical-historical-glyph-index.json"
)
SINICA_LOG = (
    ROOT
    / "source-data"
    / "sinica-xiaoxuetang-2026-08-10"
    / "representative-original-acquisition-log.json"
)
CODH_INDEX = (
    ROOT
    / "source-data"
    / "codh-liushutong-2026-08-10"
    / "radical-candidates.json"
)
CODH_LOG = (
    ROOT
    / "source-data"
    / "codh-liushutong-2026-08-10"
    / "original-acquisition-log.json"
)
CODH_SERIES_INDEX = (
    ROOT
    / "source-data"
    / "codh-liushutong-series-2026-08-11"
    / "radical-candidates-series.json"
)
CODH_SERIES_LOG = (
    ROOT
    / "source-data"
    / "codh-liushutong-series-2026-08-11"
    / "original-acquisition-log.json"
)
MIRROR_LOG = (
    ROOT
    / "source-data"
    / "github-analects-data-2026-08-10"
    / "mirror-acquisition-log.json"
)

COMMON_SOURCE_ID = "commons-ancient-chinese-historical-form-files-2026-08-10"
SINICA_SOURCE_ID = "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10"
CODH_SOURCE_ID = "codh-henrui-liushutong-te00010-2026-08-10"
CODH_SERIES_SOURCE_ID = (
    "codh-henrui-liushutong-te00008-21-series-2026-08-11"
)
FORM_ORDER = {
    "oracle_bone_甲骨文": 0,
    "bronze_金文": 1,
    "shuowen_seal_說文解字": 2,
    "liushutong_六書通": 3,
}
SOURCE_ORDER = {
    SINICA_SOURCE_ID: 0,
    COMMON_SOURCE_ID: 1,
    CODH_SOURCE_ID: 2,
    CODH_SERIES_SOURCE_ID: 3,
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metadata_value(metadata: dict[str, Any], name: str) -> str:
    return str(metadata.get(name, {}).get("value", "")).strip()


def source_pointer(path: Path, **extra: Any) -> dict[str, Any]:
    return {
        "local_path": str(path.relative_to(ROOT)),
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
        **extra,
    }


def update_commons_source_registry(commons_assets: list[dict[str, Any]]) -> None:
    registry = json.loads(SOURCES.read_text(encoding="utf-8"))
    source = registry["sources"][COMMON_SOURCE_ID]
    log = json.loads(COMMON_LOG.read_text(encoding="utf-8"))
    source["acquisition"]["originals"].update(
        {
            "updated_at": log["updated_at"],
            "path": str(COMMON_LOG.relative_to(ROOT)),
            "sha256": sha256_path(COMMON_LOG),
            "bytes": COMMON_LOG.stat().st_size,
            "completed_count": len(commons_assets),
            "oracle_count": sum(
                asset["historical_form"] == "oracle_bone_甲骨文"
                for asset in commons_assets
            ),
            "bronze_count": sum(
                asset["historical_form"] == "bronze_金文"
                for asset in commons_assets
            ),
            "liushutong_count": sum(
                asset["historical_form"] == "liushutong_六書通"
                for asset in commons_assets
            ),
        }
    )
    SOURCES.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def update_codh_series_source_registry(series_assets: list[dict[str, Any]]) -> None:
    registry = json.loads(SOURCES.read_text(encoding="utf-8"))
    source = registry["sources"][CODH_SERIES_SOURCE_ID]
    log = json.loads(CODH_SERIES_LOG.read_text(encoding="utf-8"))
    source["acquisition"].update(
        {
            "original_log_path": str(CODH_SERIES_LOG.relative_to(ROOT)),
            "original_log_sha256": sha256_path(CODH_SERIES_LOG),
            "original_log_bytes": CODH_SERIES_LOG.stat().st_size,
            "original_image_count": len(series_assets),
            "failure_count": log["failure_count"],
            "originals_retrieved_at": log["updated_at"],
        }
    )
    SOURCES.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build_commons_assets() -> list[dict[str, Any]]:
    candidates = json.loads(COMMON_CANDIDATES.read_text(encoding="utf-8"))
    decision_by_file = {
        decision["source_file"]: decision
        for decision in candidates["decisions"]
        if decision["decision"] == "admitted"
    }
    metadata = json.loads(COMMON_METADATA.read_text(encoding="utf-8"))
    page_by_file = {
        page["title"].removeprefix("File:"): page for page in metadata["pages"]
    }
    revision_payload = json.loads(COMMON_REVISIONS.read_text(encoding="utf-8"))
    historical_info_by_key = {
        (item["source_file"], item["matched_revision"]["sha1"]): item[
            "matched_revision"
        ]
        for item in revision_payload["matches"]
    }
    log = json.loads(COMMON_LOG.read_text(encoding="utf-8"))
    assets = []
    for entry in log["entries"]:
        source_file = entry["source_file"]
        decision = decision_by_file[source_file]
        page = page_by_file[source_file]
        current_info = page["imageinfo"][0]
        selected_info = historical_info_by_key.get(
            (source_file, entry["commons_sha1"]), current_info
        )
        if selected_info["sha1"] != entry["commons_sha1"]:
            raise RuntimeError(f"no pinned Commons revision matches {source_file}")
        extmetadata = current_info.get("extmetadata", {})
        local_path = ROOT / entry["local_path"]
        if not local_path.is_file():
            raise RuntimeError(f"missing acquired Commons asset: {local_path}")
        if sha256_path(local_path) != entry["sha256"]:
            raise RuntimeError(f"Commons acquisition-log SHA-256 mismatch: {source_file}")
        assets.append(
            {
                "asset_id": entry["asset_id"],
                "source_id": COMMON_SOURCE_ID,
                "source_index_id": decision["source_id"],
                "source_file": source_file,
                "source_file_page": current_info["descriptionurl"],
                "original_url": selected_info["url"],
                "local_path": entry["local_path"],
                "retrieved_at": entry["retrieved_at"],
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
                "mime_type": selected_info["mime"],
                "media_type": selected_info.get("mediatype"),
                "width": selected_info["width"],
                "height": selected_info["height"],
                "commons_sha1": selected_info["sha1"],
                "commons_timestamp": selected_info["timestamp"],
                "commons_revision": entry.get("commons_revision", "current"),
                "license_id": metadata_value(extmetadata, "License"),
                "license_short_name": metadata_value(extmetadata, "LicenseShortName"),
                "license_url": metadata_value(extmetadata, "LicenseUrl") or None,
                "usage_terms": metadata_value(extmetadata, "UsageTerms") or None,
                "artist": metadata_value(extmetadata, "Artist") or None,
                "credit": metadata_value(extmetadata, "Credit") or None,
                "attribution_required": (
                    metadata_value(extmetadata, "AttributionRequired") or None
                ),
                "image_description": (
                    metadata_value(extmetadata, "ImageDescription") or None
                ),
                "categories": sorted(
                    category["title"] for category in page.get("categories", [])
                ),
                "kangxi_number": decision["kangxi_number"],
                "primary": decision["primary"],
                "historical_form": decision["kind"],
                "mapping_method": decision["mapping_method"],
                "source_page": decision["source_page"],
                "source_revision_id": decision["source_revision_id"],
                "acquisition_route": entry["acquisition_route"],
                "transformations": [],
                "representation_note": (
                    "Unchanged Commons original SVG revision: a modern vector "
                    "transcription of the historical glyph identified by the pinned "
                    "radical index and file metadata, not a locally cropped rubbing."
                ),
            }
        )
    return assets


def build_sinica_assets() -> list[dict[str, Any]]:
    log = json.loads(SINICA_LOG.read_text(encoding="utf-8"))
    if log["completed_count"] != log["expected_count"]:
        raise RuntimeError("Sinica representative acquisition is incomplete")
    assets = []
    for source_entry in log["entries"]:
        asset = dict(source_entry)
        asset["source_file"] = asset["source_glyph_code"]
        asset["source_file_page"] = asset["source_page"]
        assets.append(asset)
    return assets


def build_codh_log_assets(log_path: Path, label: str) -> list[dict[str, Any]]:
    log = json.loads(log_path.read_text(encoding="utf-8"))
    if log["completed_count"] != log["expected_count"] or log["failure_count"]:
        raise RuntimeError(f"CODH {label} acquisition is incomplete")
    assets = []
    for source_entry in log["entries"]:
        asset = dict(source_entry)
        asset["source_file_page"] = asset["source_character_page"]
        assets.append(asset)
    return assets


def build_codh_assets() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        build_codh_log_assets(CODH_LOG, "TE00010"),
        build_codh_log_assets(CODH_SERIES_LOG, "TE00008–21 series"),
    )


def asset_reference(asset: dict[str, Any]) -> dict[str, Any]:
    reference = {
        "asset_id": asset["asset_id"],
        "path": asset["local_path"],
        "source_id": asset["source_id"],
        "source_file": asset["source_file"],
        "license_id": asset["license_id"],
    }
    if asset.get("identity_status"):
        reference["identity_status"] = asset["identity_status"]
        reference["cross_identified_with"] = asset["cross_identified_with"]
    return reference


def annotate_cross_identifications(
    assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for asset in assets:
        asset.pop("identity_status", None)
        asset.pop("cross_identified_with", None)
        by_hash[asset["sha256"]].append(asset)
    groups = []
    for sha256, group in sorted(by_hash.items()):
        if len({asset.get("kangxi_number") for asset in group}) < 2:
            continue
        groups.append(
            {
                "sha256": sha256,
                "asset_ids": sorted(asset["asset_id"] for asset in group),
                "status": "source_cross_identified",
            }
        )
        for asset in group:
            asset["identity_status"] = "source_cross_identified"
            asset["cross_identified_with"] = sorted(
                [
                    {
                        "kangxi_number": other["kangxi_number"],
                        "primary": other["primary"],
                        "asset_id": other["asset_id"],
                    }
                    for other in group
                    if other["kangxi_number"] != asset["kangxi_number"]
                ],
                key=lambda item: (item["kangxi_number"], item["asset_id"]),
            )
    return groups


def deduplicate_same_radical_assets(
    assets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    grouped: dict[tuple[int | None, str | None, str], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for asset in assets:
        asset.pop("provenance_alias_asset_ids", None)
        asset.pop("identity_status", None)
        asset.pop("cross_identified_with", None)
        grouped[
            (
                asset.get("kangxi_number"),
                asset.get("historical_form"),
                asset["sha256"],
            )
        ].append(asset)

    published: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    duplicate_groups = 0
    for group in grouped.values():
        radical_numbers = {asset.get("kangxi_number") for asset in group}
        if len(group) == 1 or len(radical_numbers) != 1:
            published.extend(group)
            continue
        duplicate_groups += 1
        canonical = min(group, key=lambda asset: asset["asset_id"])
        alias_rows = [asset for asset in group if asset is not canonical]
        canonical["provenance_alias_asset_ids"] = sorted(
            asset["asset_id"] for asset in alias_rows
        )
        published.append(canonical)
        for asset in alias_rows:
            aliases.append(
                {
                    **asset,
                    "publication_status": "provenance_alias_exact_duplicate",
                    "release_excluded": True,
                    "alias_of_asset_id": canonical["asset_id"],
                    "alias_reason": (
                        "Exact SHA-256 duplicate for the same radical and "
                        "historical-form field; retained as source/edition "
                        "provenance rather than counted as a distinct glyph."
                    ),
                }
            )
    return published, sorted(aliases, key=lambda asset: asset["asset_id"]), duplicate_groups


def gap_detail(
    field: str,
    number: int,
    common_decisions: dict[tuple[int, str], dict[str, Any]],
    acquired_keys: set[tuple[int, str]],
    quarantined_keys: set[tuple[int, str]],
) -> str:
    key = (number, field)
    decision = common_decisions.get(key)
    if key in quarantined_keys:
        return (
            f"The pinned Commons radical index supplies {decision['source_file']}, "
            "but that community-derived mapping is quarantined from publication "
            "until an independent scholarly catalogue or primary scan verifies "
            "the character-to-image identity. Absence here is not proof of "
            "historical non-attestation."
        )
    if decision and decision["decision"] == "admitted" and key not in acquired_keys:
        return (
            f"The pinned Commons radical index maps {decision['source_file']}, but no "
            "byte-exact original was recoverable through the registered direct or "
            "mirror routes. Absence of a deliverable is not evidence of historical "
            "non-attestation."
        )
    if field == "liushutong_六書通":
        return (
            "Neither the pinned Commons 六書通 radical index nor the exact-codepoint "
            "CODH 偏類六書通 TE00008–TE00021 indexes supplied a deliverable image for this "
            "Traditional-primary radical. Index absence is not treated as proof that "
            "the form never existed."
        )
    source_label = "oracle-bone" if field == "oracle_bone_甲骨文" else "bronze"
    return (
        f"The exact Traditional-primary 小學堂 {source_label} query returned no "
        "candidate, and no deliverable from the pinned Commons radical index was "
        "acquired. These source absences are not proof of historical non-attestation."
    )


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    seal_assets = [
        asset
        for asset in manifest["assets"]
        if asset.get("historical_form") == "shuowen_seal_說文解字"
        or (
            asset.get("historical_form") is None
            and asset["source_id"] != COMMON_SOURCE_ID
            and asset["source_id"]
            not in {SINICA_SOURCE_ID, CODH_SOURCE_ID, CODH_SERIES_SOURCE_ID}
        )
    ]
    commons_assets = build_commons_assets()
    sinica_assets = build_sinica_assets()
    codh_assets, codh_series_assets = build_codh_assets()
    update_commons_source_registry(commons_assets)
    update_codh_series_source_registry(codh_series_assets)
    historical_assets = sinica_assets + codh_assets + codh_series_assets
    quarantined_assets = [
        {
            **asset,
            "publication_status": "quarantined_identity_unverified",
            "release_excluded": True,
            "quarantine_reason": (
                "The mapping is supported by a Commons community project table, "
                "filename, and category, but lacks an independent scholarly "
                "catalogue or primary-image identity comparison."
            ),
        }
        for asset in commons_assets
    ]
    asset_ids = [
        asset["asset_id"]
        for asset in seal_assets + historical_assets + quarantined_assets
    ]
    if len(asset_ids) != len(set(asset_ids)):
        raise RuntimeError("historical integration would create duplicate asset IDs")
    assets = seal_assets + historical_assets
    assets.sort(
        key=lambda asset: (
            asset.get("kangxi_number", 999),
            FORM_ORDER.get(asset.get("historical_form", "shuowen_seal_說文解字"), 2),
            SOURCE_ORDER.get(asset["source_id"], -1),
            asset.get("variant_index", 0),
            asset["asset_id"],
        )
    )
    assets, provenance_alias_assets, duplicate_group_count = (
        deduplicate_same_radical_assets(assets)
    )
    cross_identified_groups = annotate_cross_identifications(assets)

    common_candidates = json.loads(COMMON_CANDIDATES.read_text(encoding="utf-8"))
    common_decisions = {
        (decision["kangxi_number"], decision["kind"]): decision
        for decision in common_candidates["decisions"]
    }
    common_acquired_files = {asset["source_file"] for asset in commons_assets}
    acquired_keys = {
        (asset["kangxi_number"], asset["historical_form"])
        for asset in historical_assets
    }
    quarantined_keys = {
        (asset["kangxi_number"], asset["historical_form"])
        for asset in quarantined_assets
    }
    transport_gaps = [
        decision
        for decision in common_candidates["decisions"]
        if decision["decision"] == "admitted"
        and decision["source_file"] not in common_acquired_files
    ]
    source_gaps = [
        decision
        for decision in common_candidates["decisions"]
        if decision["decision"] == "not_acquired"
    ]
    manifest["assets"] = assets
    manifest["quarantined_assets"] = sorted(
        quarantined_assets, key=lambda asset: asset["asset_id"]
    )
    manifest["provenance_alias_assets"] = provenance_alias_assets
    manifest["same_radical_duplicate_group_count"] = duplicate_group_count
    manifest["cross_identified_asset_groups"] = cross_identified_groups
    manifest["generated_at"] = utc_now()
    manifest["historical_sources"] = {
        "commons_candidates": source_pointer(
            COMMON_CANDIDATES,
            admitted_count=sum(
                decision["decision"] == "admitted"
                for decision in common_candidates["decisions"]
            ),
        ),
        "commons_metadata": source_pointer(COMMON_METADATA),
        "commons_revision_metadata": source_pointer(COMMON_REVISIONS),
        "commons_original_log": source_pointer(
            COMMON_LOG, completed_count=len(commons_assets)
        ),
        "sinica_index": source_pointer(SINICA_INDEX),
        "sinica_representative_log": source_pointer(
            SINICA_LOG, completed_count=len(sinica_assets)
        ),
        "codh_index": source_pointer(CODH_INDEX),
        "codh_original_log": source_pointer(
            CODH_LOG, completed_count=len(codh_assets)
        ),
        "codh_series_index": source_pointer(CODH_SERIES_INDEX),
        "codh_series_original_log": source_pointer(
            CODH_SERIES_LOG, completed_count=len(codh_series_assets)
        ),
        "github_mirror_log": source_pointer(MIRROR_LOG),
    }
    manifest["historical_source_gaps"] = [
        {
            "kangxi_number": decision["kangxi_number"],
            "primary": decision["primary"],
            "historical_form": decision["kind"],
            "reason": decision["reason"],
            "historical_status": decision["historical_status"],
            "source_page": decision["source_page"],
            "source_revision_id": decision["source_revision_id"],
        }
        for decision in source_gaps
    ]
    manifest["historical_transport_gaps"] = [
        {
            "kangxi_number": decision["kangxi_number"],
            "primary": decision["primary"],
            "historical_form": decision["kind"],
            "source_file": decision["source_file"],
            "reason": "source_unavailable",
            "detail": (
                "Mapped and license-approved, but no byte-exact original was "
                "recoverable through the registered routes in this acquisition pass."
            ),
        }
        for decision in transport_gaps
    ]
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    by_number_and_form: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for asset in historical_assets:
        by_number_and_form[(asset["kangxi_number"], asset["historical_form"])].append(asset)
    for values in by_number_and_form.values():
        values.sort(
            key=lambda asset: (
                SOURCE_ORDER[asset["source_id"]],
                asset.get("variant_index", 0),
                asset["asset_id"],
            )
        )

    records = []
    form_fields = (
        "oracle_bone_甲骨文",
        "bronze_金文",
        "liushutong_六書通",
    )
    for number in range(1, 215):
        path = ROOT / "radicals" / f"{number}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["gaps"] = [
            gap
            for gap in record["gaps"]
            if gap["field"]
            not in {f"historical_forms.{field}" for field in form_fields}
        ]
        for field in form_fields:
            source_key = f"historical_forms.{field}"
            record["sources"].pop(source_key, None)
            form_assets = by_number_and_form.get((number, field), [])
            record["historical_forms"][field] = [
                asset_reference(asset) for asset in form_assets
            ]
            if form_assets:
                record["sources"][source_key] = list(
                    dict.fromkeys(asset["source_id"] for asset in form_assets)
                )
            else:
                record["gaps"].append(
                    {
                        "field": source_key,
                        "reason": "source_unavailable",
                        "detail": gap_detail(
                            field,
                            number,
                            common_decisions,
                            acquired_keys,
                            quarantined_keys,
                        ),
                    }
                )
        record["gaps"].sort(key=lambda gap: (gap["field"], gap["reason"]))
        path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        records.append(record)

    phase_manifest = json.loads(PHASE2_MANIFEST.read_text(encoding="utf-8"))
    phase_manifest["generated_at"] = utc_now()
    phase_manifest["record_digest_sha256"] = phase2.deterministic_record_digest(records)
    phase_manifest["transport_sources"] = [
        phase2.WAYBACK_MIRROR_ID,
        phase2.GITHUB_MIRROR_ID,
        "github-analects-data-commons-mirror-2026-08-10",
    ]
    phase_manifest["historical_asset_count"] = len(historical_assets)
    phase_manifest["historical_asset_source_counts"] = {
        source_id: sum(asset["source_id"] == source_id for asset in historical_assets)
        for source_id in (
            SINICA_SOURCE_ID,
            COMMON_SOURCE_ID,
            CODH_SOURCE_ID,
            CODH_SERIES_SOURCE_ID,
        )
    }
    phase_manifest["quarantined_historical_asset_count"] = len(
        quarantined_assets
    )
    phase_manifest["quarantined_historical_asset_source_counts"] = {
        COMMON_SOURCE_ID: len(quarantined_assets)
    }
    phase_manifest["historical_form_coverage"] = {
        field: sum(bool(record["historical_forms"][field]) for record in records)
        for field in form_fields
    }
    phase_manifest["historical_form_reference_counts"] = {
        field: sum(len(record["historical_forms"][field]) for record in records)
        for field in form_fields
    }
    phase_manifest["historical_transport_gap_count"] = len(transport_gaps)
    phase_manifest["historical_source_gap_count"] = len(source_gaps)
    PHASE2_MANIFEST.write_text(
        json.dumps(phase_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    coverage = phase_manifest["historical_form_coverage"]
    print(
        f"integrated {len(historical_assets)} historical assets; manifest total "
        f"{len(assets)}; coverage oracle {coverage['oracle_bone_甲骨文']}/214, "
        f"bronze {coverage['bronze_金文']}/214, "
        f"六書通 {coverage['liushutong_六書通']}/214"
    )


if __name__ == "__main__":
    main()
