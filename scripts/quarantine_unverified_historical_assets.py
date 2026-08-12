#!/usr/bin/env python3
"""Exclude weakly mapped Commons historical glyphs from published records.

The original files and metadata remain in the repository for auditability, but
they move to the manifest's ``quarantined_assets`` collection and are removed
from every radical's release-facing historical forms. No bytes are deleted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase2 as phase2  # noqa: E402
import validate_phase2 as validate2  # noqa: E402


SOURCE_ID = "commons-ancient-chinese-historical-form-files-2026-08-10"
FORM_FIELDS = (
    "oracle_bone_甲骨文",
    "bronze_金文",
    "liushutong_六書通",
)
EXPECTED_QUARANTINE_COUNT = 455


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
        help="Exit nonzero if any release-facing reference still needs removal.",
    )
    return parser.parse_args()


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


def quarantine_metadata(asset: dict[str, Any]) -> dict[str, Any]:
    result = dict(asset)
    result.update(
        {
            "publication_status": "quarantined_identity_unverified",
            "release_excluded": True,
            "quarantine_reason": (
                "The mapping is supported by a Commons community project table, "
                "filename, and category, but lacks an independent scholarly "
                "catalogue or primary-image identity comparison."
            ),
        }
    )
    return result


def gap_detail(field: str) -> str:
    label = {
        "oracle_bone_甲骨文": "oracle-bone",
        "bronze_金文": "bronze-script",
        "liushutong_六書通": "六書通",
    }[field]
    return (
        f"No independently verified {label} asset remains for this radical. "
        "Community-derived Commons files are retained in the audit manifest but "
        "quarantined from publication until a scholarly catalogue or primary "
        "scan verifies the character-to-image mapping. Absence here is not proof "
        "of historical non-attestation."
    )


def update_record(record: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(record, ensure_ascii=False))
    for field in FORM_FIELDS:
        source_key = f"historical_forms.{field}"
        result["historical_forms"][field] = [
            reference
            for reference in result["historical_forms"][field]
            if reference.get("source_id") != SOURCE_ID
        ]
        result["gaps"] = [
            gap for gap in result["gaps"] if gap.get("field") != source_key
        ]
        sources = list(
            dict.fromkeys(
                reference["source_id"]
                for reference in result["historical_forms"][field]
            )
        )
        if sources:
            result["sources"][source_key] = sources
        else:
            result["sources"].pop(source_key, None)
            result["gaps"].append(
                {
                    "field": source_key,
                    "reason": "source_unavailable",
                    "detail": gap_detail(field),
                }
            )
    result["gaps"].sort(key=lambda gap: (gap["field"], gap["reason"]))
    return result


def update_manifests(root: Path, records: list[dict[str, Any]]) -> None:
    phase2_path = root / "metadata" / "manifests" / "phase2.json"
    manifest2 = json.loads(phase2_path.read_text(encoding="utf-8"))
    coverage = {
        field: sum(bool(record["historical_forms"][field]) for record in records)
        for field in FORM_FIELDS
    }
    references = {
        field: sum(len(record["historical_forms"][field]) for record in records)
        for field in FORM_FIELDS
    }
    active_assets = sum(references.values())
    manifest2.update(
        {
            "generated_at": utc_now(),
            "record_digest_sha256": phase2.deterministic_record_digest(
                [validate2.phase2_projection(record) for record in records]
            ),
            "historical_asset_count": active_assets,
            "quarantined_historical_asset_count": EXPECTED_QUARANTINE_COUNT,
            "historical_form_coverage": coverage,
            "historical_form_reference_counts": references,
            "asset_manifest": {
                "local_path": "assets/manifest.json",
                "sha256": sha256_path(root / "assets" / "manifest.json"),
            },
        }
    )
    asset_manifest = json.loads(
        (root / "assets" / "manifest.json").read_text(encoding="utf-8")
    )
    published_historical = [
        asset
        for asset in asset_manifest.get("assets", [])
        if asset.get("historical_form")
        not in (None, "shuowen_seal_說文解字")
    ]
    published_sources = Counter(
        asset["source_id"] for asset in published_historical
    )
    published_sources[SOURCE_ID] = 0
    manifest2["historical_asset_source_counts"] = dict(
        sorted(published_sources.items())
    )
    manifest2["quarantined_historical_asset_source_counts"] = {
        SOURCE_ID: EXPECTED_QUARANTINE_COUNT
    }
    alias_assets = asset_manifest.get("provenance_alias_assets", [])
    manifest2["provenance_alias_historical_asset_count"] = len(alias_assets)
    manifest2["provenance_alias_historical_asset_source_counts"] = dict(
        sorted(Counter(asset["source_id"] for asset in alias_assets).items())
    )
    phase2_path.write_text(
        json.dumps(manifest2, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    phase5_path = root / "metadata" / "manifests" / "phase5.json"
    manifest5 = json.loads(phase5_path.read_text(encoding="utf-8"))
    manifest5.update(
        {
            "generated_at": utc_now(),
            "radical_record_digest_sha256": phase2.deterministic_record_digest(
                records
            ),
            "phase2_base_record_digest_sha256": manifest2[
                "record_digest_sha256"
            ],
        }
    )
    manifest5["asset_manifest"]["sha256"] = sha256_path(
        root / "assets" / "manifest.json"
    )
    phase5_path.write_text(
        json.dumps(manifest5, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    manifest_path = root / "assets" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    active = manifest.get("assets", [])
    newly_quarantined = [
        asset for asset in active if asset.get("source_id") == SOURCE_ID
    ]
    prior_quarantined = manifest.get("quarantined_assets", [])
    quarantined_by_id = {
        asset["asset_id"]: quarantine_metadata(asset)
        for asset in [*prior_quarantined, *newly_quarantined]
        if asset.get("source_id") == SOURCE_ID
    }
    if len(quarantined_by_id) != EXPECTED_QUARANTINE_COUNT:
        raise RuntimeError(
            "expected exactly "
            f"{EXPECTED_QUARANTINE_COUNT} quarantined assets, found "
            f"{len(quarantined_by_id)}"
        )

    records = []
    changed_records = 0
    for number in range(1, 215):
        path = root / "radicals" / f"{number}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        updated = update_record(record)
        if updated != record:
            changed_records += 1
            if not args.check:
                path.write_text(
                    json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        records.append(updated)

    changed_manifest = bool(newly_quarantined)
    if args.check:
        print(
            json.dumps(
                {
                    "quarantined_assets": len(quarantined_by_id),
                    "changed_records": changed_records,
                    "changed_manifest": changed_manifest,
                    "mode": "check",
                }
            )
        )
        if changed_records or changed_manifest:
            raise SystemExit(1)
        return

    manifest["assets"] = [
        asset for asset in active if asset.get("source_id") != SOURCE_ID
    ]
    manifest["quarantined_assets"] = sorted(
        quarantined_by_id.values(), key=lambda asset: asset["asset_id"]
    )
    if changed_manifest:
        manifest["generated_at"] = utc_now()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    update_manifests(root, records)
    print(
        json.dumps(
            {
                "published_assets": len(manifest["assets"]),
                "quarantined_assets": len(manifest["quarantined_assets"]),
                "changed_records": changed_records,
                "mode": "write",
            }
        )
    )


if __name__ == "__main__":
    main()
