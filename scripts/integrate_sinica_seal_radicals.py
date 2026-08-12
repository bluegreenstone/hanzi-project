#!/usr/bin/env python3
"""Publish exact-query Academia Sinica seal glyphs and retire Commons vectors.

The retired Commons files remain in the asset manifest for reproducibility but
are excluded from release payloads. Exact-query absences remain explicit gaps;
the script never substitutes a visually similar character.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase2 as phase2  # noqa: E402
import integrate_historical_assets as historical  # noqa: E402
import quarantine_unverified_historical_assets as quarantine  # noqa: E402


SOURCE_ID = "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10"
RETIRED_SOURCE_IDS = {
    "commons-shuowen-seal-files-2026-08-10",
    "commons-shuowen-540-svg-series-2026-08-10",
    "commons-ancient-chinese-character-seal-files-2026-08-10",
}
SEAL_FIELD = "shuowen_seal_說文解字"
SEAL_SOURCE_KEY = f"historical_forms.{SEAL_FIELD}"
EXPECTED_ASSETS = 211
EXPECTED_GAPS = 3
EXPECTED_RETIRED = 214


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Corpus repository root (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if the manifest, records, or registry need changes.",
    )
    return parser.parse_args()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def acquisition_log_path(root: Path) -> Path:
    return (
        root
        / "source-data"
        / "sinica-xiaoxuetang-seal-2026-08-11"
        / "radical-seal-acquisition-log.json"
    )


def seal_gap_detail(gap: dict[str, Any]) -> str:
    return (
        "The official Academia Sinica 小學堂 small-seal interface returned no "
        f"result for the exact Traditional primary {gap['primary']} "
        f"({gap['codepoint']}). The exact POST response is retained and hashed; "
        "no visually similar character or community vector is substituted. "
        "This query absence is not proof that no historical form exists."
    )


def retire_asset(
    asset: dict[str, Any], replacement_by_number: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    result = dict(asset)
    number = result["kangxi_number"]
    result.update(
        {
            "publication_status": "superseded_unverified_community_vector",
            "release_excluded": True,
            "retirement_reason": (
                "Community-authored Commons rendering retired from publication: "
                "its historical identity was not independently verified against "
                "an authoritative scholarly catalogue. The original bytes and "
                "metadata remain for auditability."
            ),
        }
    )
    replacement = replacement_by_number.get(number)
    if replacement:
        result["superseded_by_asset_id"] = replacement["asset_id"]
    else:
        result.pop("superseded_by_asset_id", None)
    return result


def validate_log(
    root: Path, log: dict[str, Any]
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    entries = log.get("entries", [])
    gaps = log.get("gaps", [])
    if (
        log.get("source_id") != SOURCE_ID
        or log.get("expected_count") != 214
        or log.get("completed_count") != EXPECTED_ASSETS
        or log.get("gap_count") != EXPECTED_GAPS
        or log.get("query_accounted_count") != 214
        or len(entries) != EXPECTED_ASSETS
        or len(gaps) != EXPECTED_GAPS
    ):
        raise RuntimeError("Academia Sinica seal acquisition log is incomplete")
    by_number = {entry["kangxi_number"]: entry for entry in entries}
    gap_by_number = {gap["kangxi_number"]: gap for gap in gaps}
    if len(by_number) != len(entries) or len(gap_by_number) != len(gaps):
        raise RuntimeError("duplicate Kangxi number in seal acquisition log")
    if set(by_number) | set(gap_by_number) != set(range(1, 215)):
        raise RuntimeError("seal acquisition log does not account for 1-214")
    if set(by_number) & set(gap_by_number):
        raise RuntimeError("seal acquisition record is both acquired and a gap")
    if set(gap_by_number) != {8, 90, 174}:
        raise RuntimeError(f"unexpected exact-query gap set: {set(gap_by_number)}")
    hashes: set[str] = set()
    for number, entry in by_number.items():
        record = json.loads(
            (root / "radicals" / f"{number}.json").read_text(encoding="utf-8")
        )
        if (
            entry.get("source_id") != SOURCE_ID
            or entry.get("historical_form") != SEAL_FIELD
            or entry.get("primary") != record["primary"]["char"]
            or not entry.get("source_reference", "").startswith("說文‧")
            or entry.get("mapping_method")
            != "exact_traditional_primary_small_seal_character_page"
            or entry.get("transformations") != []
        ):
            raise RuntimeError(f"invalid exact-query seal mapping for radical {number}")
        path = root / entry["local_path"]
        if (
            not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or sha256_path(path) != entry["sha256"]
        ):
            raise RuntimeError(f"seal asset integrity mismatch for radical {number}")
        if entry["sha256"] in hashes:
            raise RuntimeError("exact-query seal assets contain a duplicate hash")
        hashes.add(entry["sha256"])
    return by_number, gap_by_number


def update_record(
    record: dict[str, Any],
    asset: dict[str, Any] | None,
    gap: dict[str, Any] | None,
) -> dict[str, Any]:
    result = json.loads(json.dumps(record, ensure_ascii=False))
    result["gaps"] = [
        item
        for item in result["gaps"]
        if item.get("field") != SEAL_SOURCE_KEY
    ]
    result["sources"].pop(SEAL_SOURCE_KEY, None)
    result["sources"].pop("shuowen.seal_glyph", None)
    if asset is not None:
        reference = phase2.asset_reference(asset)
        result["historical_forms"][SEAL_FIELD] = [reference]
        result["sources"][SEAL_SOURCE_KEY] = [SOURCE_ID]
        if result["shuowen"] is not None:
            result["shuowen"]["seal_glyph"] = reference
            result["sources"]["shuowen.seal_glyph"] = [SOURCE_ID]
            result["gaps"] = [
                item
                for item in result["gaps"]
                if item.get("field") != "shuowen.seal_glyph"
            ]
    else:
        assert gap is not None
        result["historical_forms"][SEAL_FIELD] = []
        if result["shuowen"] is not None:
            result["shuowen"]["seal_glyph"] = None
            result["gaps"] = [
                item
                for item in result["gaps"]
                if item.get("field") != "shuowen.seal_glyph"
            ]
            result["gaps"].append(
                {
                    "field": "shuowen.seal_glyph",
                    "reason": "source_unavailable",
                    "detail": seal_gap_detail(gap),
                }
            )
        result["gaps"].append(
            {
                "field": SEAL_SOURCE_KEY,
                "reason": "source_unavailable",
                "detail": seal_gap_detail(gap),
            }
        )
    result["gaps"].sort(key=lambda item: (item["field"], item["reason"]))
    return result


def update_registry(
    registry: dict[str, Any], log_path: Path, log: dict[str, Any]
) -> dict[str, Any]:
    result = json.loads(json.dumps(registry, ensure_ascii=False))
    source = result["sources"][SOURCE_ID]
    source["full_name"] = (
        "中央研究院小學堂文字學資料庫（甲骨文、金文、小篆）字形圖片與字形屬性"
    )
    source["coverage"] = [
        "all exact-character oracle-script glyph variants returned for the 214 Traditional-primary Kangxi radical headings",
        "all exact-character bronze-inscription glyph variants returned for the 214 Traditional-primary Kangxi radical headings",
        "exact-character small-seal glyphs returned for 211 of 214 Traditional-primary Kangxi radical headings; 3 zero-result queries are preserved as explicit gaps",
        "source glyph code, displayed bibliographic reference, and query-to-character mapping",
    ]
    fields = source.setdefault("schema_fields", [])
    for field in (
        "radicals.*.shuowen.seal_glyph",
        "radicals.*.historical_forms.shuowen_seal_說文解字",
    ):
        if field not in fields:
            fields.append(field)
    source["acquisition"]["small_seal_originals"] = {
        "path": str(log_path.relative_to(log_path.parents[2])),
        "sha256": sha256_path(log_path),
        "bytes": log_path.stat().st_size,
        "retrieved_at": log["updated_at"],
        "query_count": 214,
        "original_image_count": EXPECTED_ASSETS,
        "exact_query_gap_count": EXPECTED_GAPS,
        "exact_query_gap_radicals": [8, 90, 174],
        "selection_policy": log["selection_policy"],
        "image_policy": log["image_policy"],
    }
    for source_id in RETIRED_SOURCE_IDS:
        commons = result["sources"][source_id]
        commons["status"] = "quarantine"
        commons["publication_policy"] = (
            "Retained only as superseded audit evidence. No asset from this "
            "community-rendered seal source is eligible for the release payload."
        )
    return result


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    log_path = acquisition_log_path(root)
    log = json.loads(log_path.read_text(encoding="utf-8"))
    by_number, gap_by_number = validate_log(root, log)

    manifest_path = root / "assets" / "manifest.json"
    current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_active = [
        asset
        for asset in current_manifest.get("assets", [])
        if asset.get("source_id") in RETIRED_SOURCE_IDS
        and asset.get("kangxi_number") in range(1, 215)
        and asset.get("local_path", "").startswith("assets/shuowen_seal/")
    ]
    prior_retired = current_manifest.get("retired_unverified_assets", [])
    retired_candidates = [*prior_retired, *old_active]
    retired_by_id = {
        asset["asset_id"]: retire_asset(asset, by_number)
        for asset in retired_candidates
        if asset.get("source_id") in RETIRED_SOURCE_IDS
    }
    if len(retired_by_id) != EXPECTED_RETIRED:
        raise RuntimeError(
            f"expected {EXPECTED_RETIRED} retired seal vectors, "
            f"found {len(retired_by_id)}"
        )

    other_active = [
        asset
        for asset in current_manifest.get("assets", [])
        if asset not in old_active
        and not (
            asset.get("source_id") == SOURCE_ID
            and asset.get("historical_form") == SEAL_FIELD
        )
    ]
    new_active = [*other_active, *by_number.values()]
    new_active.sort(
        key=lambda asset: (
            asset.get("kangxi_number", 999),
            historical.FORM_ORDER.get(
                asset.get("historical_form") or SEAL_FIELD, 2
            ),
            historical.SOURCE_ORDER.get(asset["source_id"], -1),
            asset.get("variant_index", 0),
            asset["asset_id"],
        )
    )
    manifest = json.loads(json.dumps(current_manifest, ensure_ascii=False))
    manifest["assets"] = new_active
    manifest["retired_unverified_assets"] = sorted(
        retired_by_id.values(), key=lambda asset: asset["asset_id"]
    )
    manifest["sinica_small_seal_acquisition"] = {
        "local_path": str(log_path.relative_to(root)),
        "sha256": sha256_path(log_path),
        "bytes": log_path.stat().st_size,
        "completed_count": EXPECTED_ASSETS,
        "gap_count": EXPECTED_GAPS,
        "gap_radicals": sorted(gap_by_number),
    }
    manifest["seal_source_gaps"] = [gap_by_number[n] for n in sorted(gap_by_number)]

    records: list[dict[str, Any]] = []
    changed_records = 0
    for number in range(1, 215):
        path = root / "radicals" / f"{number}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        updated = update_record(
            record, by_number.get(number), gap_by_number.get(number)
        )
        if updated != record:
            changed_records += 1
            if not args.check:
                path.write_text(
                    json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        records.append(updated)

    registry_path = root / "sources.json"
    current_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry = update_registry(current_registry, log_path, log)
    changed_registry = registry != current_registry
    changed_manifest = manifest != current_manifest
    print(
        json.dumps(
            {
                "published_seal_assets": EXPECTED_ASSETS,
                "exact_query_gaps": sorted(gap_by_number),
                "retired_commons_seal_assets": len(retired_by_id),
                "changed_records": changed_records,
                "changed_manifest": changed_manifest,
                "changed_registry": changed_registry,
                "mode": "check" if args.check else "write",
            }
        )
    )
    if args.check:
        if changed_records or changed_manifest or changed_registry:
            raise SystemExit(1)
        return

    if changed_manifest:
        manifest["generated_at"] = quarantine.utc_now()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    quarantine.update_manifests(root, records)
    phase2_path = root / "metadata" / "manifests" / "phase2.json"
    phase2_manifest = json.loads(phase2_path.read_text(encoding="utf-8"))
    phase2_manifest.update(
        {
            "generated_at": quarantine.utc_now(),
            "shuowen_asset_count": EXPECTED_ASSETS,
            "shuowen_exact_query_gap_count": EXPECTED_GAPS,
            "retired_unverified_seal_asset_count": EXPECTED_RETIRED,
        }
    )
    phase2_manifest["source_acquisitions"][SOURCE_ID] = registry["sources"][
        SOURCE_ID
    ]["acquisition"]
    phase2_manifest["asset_manifest"] = {
        "local_path": "assets/manifest.json",
        "sha256": sha256_path(manifest_path),
    }
    phase2_path.write_text(
        json.dumps(phase2_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
