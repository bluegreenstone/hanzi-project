#!/usr/bin/env python3
"""Apply mapping, classification, format, and license gates to historical assets."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA = ROOT / "source-data" / "wikimedia-2026-08-10"
MAPPINGS = SOURCE_DATA / "commons-acc-radical-historical-candidates.json"
METADATA = SOURCE_DATA / "commons-acc-historical-file-metadata.json"
OUTPUT = ROOT / "metadata" / "audits" / "phase2-historical-asset-candidates.json"


def metadata_value(metadata: dict[str, Any], name: str) -> str:
    return str(metadata.get(name, {}).get("value", "")).strip()


def main() -> None:
    mappings = json.loads(MAPPINGS.read_text(encoding="utf-8"))
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    pages = {
        page.get("title", "").removeprefix("File:"): page
        for page in metadata["pages"]
    }
    decisions: list[dict[str, Any]] = []
    for mapped in mappings["records"]:
        decision = dict(mapped)
        if mapped["status"] == "project_missing":
            decision.update(
                {
                    "decision": "not_acquired",
                    "reason": "project_index_has_no_file",
                    "historical_status": "source_unavailable",
                    "license_review": "not_applicable",
                }
            )
            decisions.append(decision)
            continue
        source_file = mapped["source_file"]
        page = pages.get(source_file)
        if page is None or page.get("missing") is not None or not page.get("imageinfo"):
            decision.update(
                {
                    "decision": "rejected",
                    "reason": "commons_file_or_metadata_missing",
                    "historical_status": "source_unavailable",
                }
            )
            decisions.append(decision)
            continue
        imageinfo = page["imageinfo"][0]
        extmetadata = imageinfo.get("extmetadata", {})
        license_id = metadata_value(extmetadata, "License")
        license_short_name = metadata_value(extmetadata, "LicenseShortName")
        usage_terms = metadata_value(extmetadata, "UsageTerms")
        copyrighted = metadata_value(extmetadata, "Copyrighted")
        categories = sorted(category["title"] for category in page.get("categories", []))
        suffix = {
            "oracle_bone_甲骨文": "-oracle.svg",
            "bronze_金文": "-bronze.svg",
            "liushutong_六書通": "-bigseal.svg",
        }[mapped["kind"]]
        classification_ok = source_file.endswith(suffix)
        classification_evidence = [
            f"{mapped['source_page']}@{mapped['source_revision_id']}"
        ]
        if mapped["kind"] == "liushutong_六書通":
            liushutong_categories = [
                category for category in categories if "Liushutong script" in category
            ]
            classification_ok = classification_ok and bool(liushutong_categories)
            classification_evidence.extend(liushutong_categories)
        license_ok = (
            license_id.casefold() == "pd"
            and license_short_name.casefold() == "public domain"
            and usage_terms.casefold() == "public domain"
            and copyrighted.casefold() == "false"
        )
        format_ok = imageinfo.get("mime") == "image/svg+xml"
        admitted = classification_ok and license_ok and format_ok
        decision.update(
            {
                "decision": "admitted" if admitted else "rejected",
                "reason": None if admitted else "classification_license_or_format_gate_failed",
                "historical_status": "source_attested" if admitted else "source_unavailable",
                "classification_ok": classification_ok,
                "classification_evidence": classification_evidence,
                "license_review": "allowed" if license_ok else "rejected",
                "license_id": license_id,
                "license_short_name": license_short_name,
                "usage_terms": usage_terms,
                "copyrighted": copyrighted,
                "format_ok": format_ok,
                "mime_type": imageinfo.get("mime"),
                "media_type": imageinfo.get("mediatype"),
                "commons_sha1": imageinfo.get("sha1"),
                "commons_timestamp": imageinfo.get("timestamp"),
                "original_url": imageinfo.get("url"),
                "source_file_page": imageinfo.get("descriptionurl"),
                "categories": categories,
            }
        )
        decisions.append(decision)
    counts = Counter(
        (decision["kind"], decision["decision"]) for decision in decisions
    )
    output = {
        "mapping_path": str(MAPPINGS.relative_to(ROOT)),
        "mapping_sha256": hashlib.sha256(MAPPINGS.read_bytes()).hexdigest(),
        "metadata_path": str(METADATA.relative_to(ROOT)),
        "metadata_sha256": hashlib.sha256(METADATA.read_bytes()).hexdigest(),
        "policy": {
            "mapping": "Explicit pinned Commons project radical-table position.",
            "license": (
                "Commons extmetadata must identify the current original as public "
                "domain, public-domain usage terms, and Copyrighted=False."
            ),
            "format": "Original SVG only.",
            "liushutong_classification": (
                "The -bigseal.svg name must also have a Liushutong-script category."
            ),
            "absence": (
                "An unfilled project cell is source_unavailable, never evidence of "
                "historical non-attestation."
            ),
        },
        "summary": [
            {"kind": kind, "decision": status, "count": count}
            for (kind, status), count in sorted(counts.items())
        ],
        "decisions": decisions,
    }
    OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    for row in output["summary"]:
        print(f"{row['kind']} {row['decision']}: {row['count']}")


if __name__ == "__main__":
    main()
