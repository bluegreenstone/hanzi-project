#!/usr/bin/env python3
"""Expose the pinned Unihan radical gloss as a single display field."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase1 as phase1  # noqa: E402
import build_phase2 as phase2  # noqa: E402


def main() -> None:
    records: list[dict] = []
    for number in range(1, 215):
        path = ROOT / "radicals" / f"{number}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        definitions = record.get("definitions") or []
        if len(definitions) != 1 or definitions[0].get("lang") != "en":
            raise RuntimeError(
                f"radical {number} does not have exactly one structured English definition"
            )
        if record.get("sources", {}).get("definitions") != [phase1.UNIHAN_ID]:
            raise RuntimeError(f"radical {number} definition is not sourced exactly to Unihan")
        definition = definitions[0]["gloss"]
        if not definition:
            raise RuntimeError(f"radical {number} has an empty Unihan definition")
        record["english_definition"] = definition
        record["sources"]["english_definition"] = [phase1.UNIHAN_ID]
        normalized = phase1.normalize_tree(record)
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        records.append(normalized)

    manifest_path = ROOT / "metadata" / "manifests" / "phase2.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["english_definition_count"] = len(records)
    manifest["record_digest_sha256"] = phase2.deterministic_record_digest(records)
    manifest["last_updated_at"] = phase2.utc_now()
    manifest_path.write_text(
        json.dumps(phase1.normalize_tree(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"added single English definitions to {len(records)} radical records")


if __name__ == "__main__":
    main()
