#!/usr/bin/env python3
"""Count exact same-radical image duplicates as provenance aliases, not forms."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import integrate_historical_assets as historical  # noqa: E402
import quarantine_unverified_historical_assets as quarantine  # noqa: E402


EXPECTED_DUPLICATE_GROUPS = 1676
EXPECTED_ALIAS_ASSETS = 1676
EXPECTED_CROSS_GROUPS = 23
FORM_FIELDS = tuple(historical.FORM_ORDER)


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
        help="Exit nonzero if published references or alias metadata are stale.",
    )
    return parser.parse_args()


def restore_alias_asset(asset: dict) -> dict:
    result = dict(asset)
    for field in (
        "publication_status",
        "release_excluded",
        "alias_of_asset_id",
        "alias_reason",
    ):
        result.pop(field, None)
    return result


def missing_form_gap(field: str) -> dict:
    if field == "shuowen_seal_說文解字":
        detail = (
            "The official Academia Sinica 小學堂 exact-character small-seal "
            "query returned no result. No visually similar character or "
            "community vector is substituted; query absence is not proof that "
            "no historical form exists."
        )
    else:
        label = {
            "oracle_bone_甲骨文": "oracle-bone",
            "bronze_金文": "bronze-script",
            "liushutong_六書通": "六書通",
        }[field]
        detail = (
            f"No independently verified {label} asset remains for this radical. "
            "Source absence is not proof of historical non-attestation."
        )
    return {
        "field": f"historical_forms.{field}",
        "reason": "source_unavailable",
        "detail": detail,
    }


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    manifest_path = root / "assets" / "manifest.json"
    current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates = [
        *current_manifest["assets"],
        *(
            restore_alias_asset(asset)
            for asset in current_manifest.get("provenance_alias_assets", [])
        ),
    ]
    published, aliases, duplicate_groups = (
        historical.deduplicate_same_radical_assets(candidates)
    )
    cross_groups = historical.annotate_cross_identifications(published)
    if (
        duplicate_groups != EXPECTED_DUPLICATE_GROUPS
        or len(aliases) != EXPECTED_ALIAS_ASSETS
        or len(cross_groups) != EXPECTED_CROSS_GROUPS
    ):
        raise RuntimeError(
            "historical duplicate profile changed: "
            f"groups={duplicate_groups}, aliases={len(aliases)}, "
            f"cross_groups={len(cross_groups)}"
        )
    published.sort(
        key=lambda asset: (
            asset.get("kangxi_number", 999),
            historical.FORM_ORDER.get(
                asset.get("historical_form", "shuowen_seal_說文解字"), 2
            ),
            historical.SOURCE_ORDER.get(asset["source_id"], -1),
            asset.get("variant_index", 0),
            asset["asset_id"],
        )
    )
    manifest = json.loads(json.dumps(current_manifest, ensure_ascii=False))
    manifest["assets"] = published
    manifest["provenance_alias_assets"] = aliases
    manifest["same_radical_duplicate_group_count"] = duplicate_groups
    manifest["cross_identified_asset_groups"] = cross_groups

    by_number_and_form: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for asset in published:
        form = asset.get("historical_form")
        number = asset.get("kangxi_number")
        if form in FORM_FIELDS and isinstance(number, int):
            by_number_and_form[(number, form)].append(asset)
    records = []
    changed_records = 0
    for number in range(1, 215):
        path = root / "radicals" / f"{number}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        updated = json.loads(json.dumps(record, ensure_ascii=False))
        for field in FORM_FIELDS:
            source_key = f"historical_forms.{field}"
            form_assets = by_number_and_form.get((number, field), [])
            updated["historical_forms"][field] = [
                historical.asset_reference(asset) for asset in form_assets
            ]
            if form_assets:
                updated["gaps"] = [
                    gap for gap in updated["gaps"] if gap["field"] != source_key
                ]
                updated["sources"][source_key] = list(
                    dict.fromkeys(asset["source_id"] for asset in form_assets)
                )
            else:
                updated["sources"].pop(source_key, None)
                if not any(gap["field"] == source_key for gap in updated["gaps"]):
                    updated["gaps"].append(missing_form_gap(field))
        seal_references = updated["historical_forms"][
            "shuowen_seal_說文解字"
        ]
        if updated["shuowen"] is not None:
            updated["sources"].pop("shuowen.seal_glyph", None)
            updated["gaps"] = [
                gap
                for gap in updated["gaps"]
                if gap["field"] != "shuowen.seal_glyph"
            ]
            if seal_references:
                updated["shuowen"]["seal_glyph"] = seal_references[0]
                updated["sources"]["shuowen.seal_glyph"] = [
                    seal_references[0]["source_id"]
                ]
            else:
                updated["shuowen"]["seal_glyph"] = None
                updated["gaps"].append(
                    {
                        **missing_form_gap("shuowen_seal_說文解字"),
                        "field": "shuowen.seal_glyph",
                    }
                )
        updated["gaps"].sort(key=lambda gap: (gap["field"], gap["reason"]))
        if updated != record:
            changed_records += 1
            if not args.check:
                path.write_text(
                    json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        records.append(updated)

    changed_manifest = manifest != current_manifest
    print(
        json.dumps(
            {
                "published_assets": len(published),
                "duplicate_groups": duplicate_groups,
                "provenance_alias_assets": len(aliases),
                "cross_identified_groups": len(cross_groups),
                "changed_records": changed_records,
                "changed_manifest": changed_manifest,
                "mode": "check" if args.check else "write",
            }
        )
    )
    if args.check:
        if changed_records or changed_manifest:
            raise SystemExit(1)
        return

    if changed_manifest:
        manifest["generated_at"] = quarantine.utc_now()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    quarantine.update_manifests(root, records)


if __name__ == "__main__":
    main()
