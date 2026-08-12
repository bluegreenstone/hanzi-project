#!/usr/bin/env python3
"""Synchronize copied source-acquisition evidence in phase manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "sources.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"]
    changed: list[str] = []
    for path in sorted((ROOT / "metadata" / "manifests").glob("phase*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        acquisitions = manifest.get("source_acquisitions")
        if isinstance(acquisitions, dict):
            for source_id in list(acquisitions):
                current = registry.get(source_id, {}).get("acquisition")
                if current is not None:
                    acquisitions[source_id] = current
        if path.name == "phase5.json":
            asset = manifest.get("asset_manifest", {})
            local_path = asset.get("local_path")
            if local_path:
                asset["sha256"] = sha256(ROOT / local_path)
        rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        if rendered != path.read_text(encoding="utf-8"):
            changed.append(path.name)
            if not args.check:
                path.write_text(rendered, encoding="utf-8")
    print(json.dumps({"changed": changed, "check": args.check}, indent=2))
    if args.check and changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
