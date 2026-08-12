#!/usr/bin/env python3
"""Label scholarly-source images indexed under multiple Kangxi radicals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import integrate_historical_assets as historical  # noqa: E402
import quarantine_unverified_historical_assets as quarantine  # noqa: E402


EXPECTED_GROUPS = 23
EXPECTED_AFFECTED_ASSETS = 46


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
        help="Exit nonzero if annotations are absent or stale.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    manifest_path = root / "assets" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    active = manifest["assets"]
    groups = historical.annotate_cross_identifications(active)
    affected = sum(
        asset.get("identity_status") == "source_cross_identified"
        for asset in active
    )
    if len(groups) != EXPECTED_GROUPS or affected != EXPECTED_AFFECTED_ASSETS:
        raise RuntimeError(
            f"expected {EXPECTED_GROUPS} groups/{EXPECTED_AFFECTED_ASSETS} assets, "
            f"found {len(groups)} groups/{affected} assets"
        )
    manifest["cross_identified_asset_groups"] = groups

    changed_records = 0
    records = []
    active_by_id = {asset["asset_id"]: asset for asset in active}
    for number in range(1, 215):
        path = root / "radicals" / f"{number}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        updated = json.loads(json.dumps(record, ensure_ascii=False))
        for field, references in updated["historical_forms"].items():
            updated["historical_forms"][field] = [
                historical.asset_reference(active_by_id[reference["asset_id"]])
                for reference in references
            ]
        if updated != record:
            changed_records += 1
            if not args.check:
                path.write_text(
                    json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        records.append(updated)

    current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed_manifest = manifest != current_manifest
    print(
        json.dumps(
            {
                "groups": len(groups),
                "affected_assets": affected,
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
