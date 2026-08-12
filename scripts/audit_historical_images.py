#!/usr/bin/env python3
"""Audit historical-image identity evidence and exact-file duplication.

This complements the release validators, which primarily check schema,
licensing, file hashes, and referential integrity. Those checks do not prove
that a depicted glyph is the claimed historical form of the radical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_TIERS = {
    "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10": {
        "tier": "taiwan_scholarly_database",
        "identity_evidence": (
            "Exact Traditional-character query plus source glyph code and "
            "bibliographic reference."
        ),
        "review_status": "source_verified_mapping",
    },
    "codh-henrui-liushutong-te00010-2026-08-10": {
        "tier": "scholarly_primary_scan_index",
        "identity_evidence": (
            "Exact Unicode character index, book/page locator, and source crop."
        ),
        "review_status": "source_verified_mapping",
    },
    "codh-henrui-liushutong-te00008-21-series-2026-08-11": {
        "tier": "scholarly_primary_scan_index",
        "identity_evidence": (
            "Exact Unicode character index, volume/page locator, and source crop."
        ),
        "review_status": "source_verified_mapping",
    },
    "commons-shuowen-540-svg-series-2026-08-10": {
        "tier": "community_vector_transcription",
        "identity_evidence": (
            "Numbered Shuowen-radical mapping, but no primary-scan comparison "
            "recorded per asset."
        ),
        "review_status": "independent_primary_comparison_required",
    },
    "commons-ancient-chinese-historical-form-files-2026-08-10": {
        "tier": "community_derivative_index",
        "identity_evidence": (
            "Community project table, filename suffix, and category only; no "
            "independent scholarly identity check recorded per asset."
        ),
        "review_status": "quarantine_recommended",
    },
    "commons-ancient-chinese-character-seal-files-2026-08-10": {
        "tier": "community_vector_transcription",
        "identity_evidence": "Commons filename and metadata; mapping needs a primary comparison.",
        "review_status": "independent_primary_comparison_required",
    },
    "commons-shuowen-seal-files-2026-08-10": {
        "tier": "community_vector_transcription",
        "identity_evidence": "Commons filename and metadata; mapping needs a primary comparison.",
        "review_status": "independent_primary_comparison_required",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Corpus repository root (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("metadata/audits/historical-images.json"),
        help="Report path, relative to the repository root unless absolute.",
    )
    return parser.parse_args()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact_asset(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset["asset_id"],
        "source_id": asset["source_id"],
        "kangxi_number": asset.get("kangxi_number"),
        "primary": asset.get("primary"),
        "historical_form": asset.get("historical_form"),
        "identity_status": asset.get("identity_status"),
        "cross_identified_with": asset.get("cross_identified_with"),
        "local_path": asset["local_path"],
        "source_file": asset.get("source_file"),
    }


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    manifest_path = root / "assets" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    published_assets = manifest["assets"]
    quarantined_assets = manifest.get("quarantined_assets", [])
    provenance_alias_assets = manifest.get("provenance_alias_assets", [])
    retired_unverified_assets = manifest.get("retired_unverified_assets", [])
    assets = (
        published_assets
        + quarantined_assets
        + provenance_alias_assets
        + retired_unverified_assets
    )
    published_ids = {asset["asset_id"] for asset in published_assets}

    integrity_errors: list[dict[str, str]] = []
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    published_by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_source = Counter()
    by_status = Counter()
    by_form = Counter()
    published_by_form = Counter()
    source_details: dict[str, dict[str, Any]] = {}

    for asset in assets:
        local_path = root / asset["local_path"]
        if not local_path.is_file():
            integrity_errors.append(
                {"asset_id": asset["asset_id"], "error": "missing_local_file"}
            )
        elif sha256_path(local_path) != asset["sha256"]:
            integrity_errors.append(
                {"asset_id": asset["asset_id"], "error": "sha256_mismatch"}
            )
        by_hash[asset["sha256"]].append(asset)
        if asset["asset_id"] in published_ids:
            published_by_hash[asset["sha256"]].append(asset)
        source_id = asset["source_id"]
        quality = SOURCE_TIERS.get(
            source_id,
            {
                "tier": "unclassified",
                "identity_evidence": "No audit rule is registered for this source.",
                "review_status": "manual_review_required",
            },
        )
        if asset.get("publication_status") == "quarantined_identity_unverified":
            quality = {
                **quality,
                "review_status": "quarantined_identity_unverified",
            }
        elif asset.get("publication_status") == "provenance_alias_exact_duplicate":
            quality = {
                **quality,
                "review_status": "provenance_alias_exact_duplicate",
            }
        elif (
            asset.get("publication_status")
            == "superseded_unverified_community_vector"
        ):
            quality = {
                **quality,
                "review_status": "superseded_unverified_community_vector",
            }
        form = asset.get("historical_form") or "shuowen_seal_說文解字"
        by_source[source_id] += 1
        by_status[quality["review_status"]] += 1
        by_form[form] += 1
        if asset["asset_id"] in published_ids:
            published_by_form[form] += 1
        source_details[source_id] = {**quality, "asset_count": by_source[source_id]}

    all_duplicate_groups = [group for group in by_hash.values() if len(group) > 1]
    duplicate_groups = [
        group for group in published_by_hash.values() if len(group) > 1
    ]
    cross_radical_groups = [
        group
        for group in duplicate_groups
        if len({asset.get("kangxi_number") for asset in group}) > 1
    ]
    annotated_cross_radical_groups = [
        group
        for group in cross_radical_groups
        if all(
            asset.get("identity_status") == "source_cross_identified"
            and asset.get("cross_identified_with")
            for asset in group
        )
    ]
    same_radical_duplicates = [
        group
        for group in duplicate_groups
        if len({asset.get("kangxi_number") for asset in group}) == 1
    ]
    source_details = {
        source_id: {**details, "asset_count": by_source[source_id]}
        for source_id, details in sorted(source_details.items())
    }

    findings = [
        {
            "id": "HIST-001",
            "severity": "high",
            "confidence": "high",
            "status": "mitigated_by_quarantine",
            "title": "Community-derived historical glyphs lack independent identity verification",
            "evidence": {
                "affected_assets": len(quarantined_assets),
                "source_id": "commons-ancient-chinese-historical-form-files-2026-08-10",
                "current_gate": "Excluded from release-facing records and release packaging; original bytes and metadata retained for audit.",
            },
            "risk": (
                "A correctly licensed and unmodified file can still depict the "
                "wrong character or the wrong historical script."
            ),
            "remediation": "Do not restore an asset until its mapping is matched to Academia Sinica, a primary scan, or another scholarly catalogue with a per-asset citation.",
        },
        {
            "id": "HIST-002",
            "severity": "high",
            "confidence": "high",
            "status": (
                "mitigated_by_annotation"
                if len(annotated_cross_radical_groups) == len(cross_radical_groups)
                else "open"
            ),
            "title": "Exact image bytes are assigned to different Kangxi radicals",
            "evidence": {
                "cross_radical_hash_groups": len(cross_radical_groups),
                "annotated_groups": len(annotated_cross_radical_groups),
                "affected_assets": sum(len(group) for group in cross_radical_groups),
            },
            "risk": (
                "Some may be legitimate historical equivalences or scholarly "
                "cross-identifications. Without the explicit annotation, consumers "
                "could misread byte-identical evidence as independent forms."
            ),
            "remediation": "Keep the source-cross-identification visible unless a palaeographic review establishes that one mapping is erroneous or that the forms should be modeled as an explicit equivalence.",
        },
        {
            "id": "HIST-003",
            "severity": "medium",
            "confidence": "high",
            "status": (
                "mitigated_by_alias_deduplication"
                if not same_radical_duplicates
                and len(provenance_alias_assets) == 1676
                else "open"
            ),
            "title": "Exact duplicate image files inflate historical-form counts",
            "evidence": {
                "published_same_radical_duplicate_hash_groups": len(same_radical_duplicates),
                "provenance_alias_assets": len(provenance_alias_assets),
            },
            "risk": (
                "Coverage and variant counts overstate distinct visual evidence, "
                "especially where paired CODH volume identifiers serve identical bytes."
            ),
            "remediation": "Continue counting the canonical asset once while preserving exact duplicate edition/source records as release-excluded provenance aliases.",
        },
        {
            "id": "HIST-004",
            "severity": "high",
            "confidence": "high",
            "status": (
                "mitigated_by_official_replacement_and_gap_model"
                if len(retired_unverified_assets) == 214
                and sum(
                    asset.get("historical_form") == "shuowen_seal_說文解字"
                    for asset in published_assets
                )
                == 211
                else "open"
            ),
            "title": "Community-rendered Commons seal forms lacked an independent identity comparison",
            "evidence": {
                "retired_commons_assets": len(retired_unverified_assets),
                "published_exact_query_sinica_assets": sum(
                    asset.get("historical_form") == "shuowen_seal_說文解字"
                    and asset.get("source_id")
                    == "academia-sinica-xiaoxuetang-historical-glyphs-2026-08-10"
                    for asset in published_assets
                ),
                "official_exact_query_gaps": manifest.get(
                    "sinica_small_seal_acquisition", {}
                ).get("gap_count"),
            },
            "risk": (
                "A modern community vector can be licensed and consistently "
                "numbered while still being the wrong glyph for the corpus's "
                "Traditional-primary radical."
            ),
            "remediation": (
                "Keep all 214 Commons vectors release-excluded. Publish only "
                "the 211 exact-character Academia Sinica results and preserve "
                "亠, 爿, and 靑 as explicit zero-result query gaps."
            ),
        },
    ]

    report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "scope": (
            "All historical assets in assets/manifest.json. File integrity, source "
            "identity-evidence strength, exact duplicates, and cross-radical reuse."
        ),
        "summary": {
            "asset_count": len(assets),
            "published_asset_count": len(published_assets),
            "quarantined_asset_count": len(quarantined_assets),
            "provenance_alias_asset_count": len(provenance_alias_assets),
            "retired_unverified_asset_count": len(retired_unverified_assets),
            "unique_sha256_count": len(by_hash),
            "published_unique_sha256_count": len(published_by_hash),
            "integrity_error_count": len(integrity_errors),
            "by_historical_form": dict(sorted(by_form.items())),
            "published_by_historical_form": dict(
                sorted(published_by_form.items())
            ),
            "by_review_status": dict(sorted(by_status.items())),
            "duplicate_hash_group_count": len(duplicate_groups),
            "all_asset_duplicate_hash_group_count": len(all_duplicate_groups),
            "same_radical_duplicate_hash_group_count": len(same_radical_duplicates),
            "cross_radical_hash_group_count": len(cross_radical_groups),
            "annotated_cross_radical_hash_group_count": len(
                annotated_cross_radical_groups
            ),
        },
        "source_quality": source_details,
        "findings": findings,
        "integrity_errors": integrity_errors,
        "cross_radical_duplicate_groups": [
            {
                "sha256": group[0]["sha256"],
                "assets": [compact_asset(asset) for asset in group],
            }
            for group in sorted(cross_radical_groups, key=lambda item: item[0]["sha256"])
        ],
        "same_radical_duplicate_groups": [
            {
                "sha256": group[0]["sha256"],
                "assets": [compact_asset(asset) for asset in group],
            }
            for group in sorted(
                same_radical_duplicates, key=lambda item: item[0]["sha256"]
            )
        ],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output.relative_to(root)}")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
