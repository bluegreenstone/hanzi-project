#!/usr/bin/env python3
"""Enrich the 214-radical spine with the approved Phase 2 sources."""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase1 as phase1  # noqa: E402


RADICALS_PATH = ROOT / "radicals"
MANIFEST_PATH = ROOT / "phase2-manifest.json"
ASSET_MANIFEST_PATH = ROOT / "assets" / "manifest.json"
ASSET_CANDIDATES_PATH = ROOT / "phase2-asset-candidates.json"

SHUOWEN_ID = "zhwikisource-shuowen-2026-08-10"
SHUOWEN_ASSET_ID = "commons-shuowen-seal-files-2026-08-10"
SHUOWEN_540_SERIES_ID = "commons-shuowen-540-svg-series-2026-08-10"
SHUOWEN_540_COMPOSITE_ID = "commons-shuowen-540-numbered-composite-2026-08-10"
EXACT_CHARACTER_SEAL_ID = "commons-ancient-chinese-character-seal-files-2026-08-10"
WAYBACK_MIRROR_ID = "internet-archive-wayback-commons-mirror-2026-08-10"
GITHUB_MIRROR_ID = "github-hanzi-etymology-commons-mirror-2026-08-10"
SHUOWEN_SCAN_ID = "commons-shuowen-ncl-00915"
LIUSHUTONG_ID = "commons-liushutong-harvard-1795"
KANGXI_SCAN_ID = "commons-kangxi-dictionary-1716"
KANGXI_COUNTS_ID = "enwiki-kangxi-radicals-2026-08-10"

HEADING_RE = re.compile(r"^==\s*(.*?)部\s*==\s*$", re.MULTILINE)
FILE_RE = re.compile(r"\[\[(?:File|文件|檔案):([^\]|]+)", re.IGNORECASE)
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]|\[\[([^\]]+)\]\]")
TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")


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


def normalize_heading(value: str) -> str:
    value = html.unescape(value).strip()
    if value.startswith("-{") and value.endswith("}-"):
        value = value[2:-2]
    value = re.sub(r"'''?", "", value)
    return unicodedata.normalize("NFC", value.strip())


def clean_markup(value: str) -> str:
    value = re.sub(r"-\{([^{}]+)\}-", r"\1", value)
    value = FILE_RE.sub("", value)
    value = re.sub(r"\[\[[^\]]*\]\]", "", value) if "File:" in value else value

    def replace_link(match: re.Match[str]) -> str:
        return match.group(2) or match.group(3) or ""

    value = WIKI_LINK_RE.sub(replace_link, value)
    for name in ("lang", "+", "nowrap"):
        value = re.sub(
            rf"\{{\{{{re.escape(name)}\|(?:[^{{}}|]+\|)*([^{{}}|]+)\}}\}}",
            r"\1",
            value,
            flags=re.IGNORECASE,
        )
    previous = None
    while previous != value:
        previous = value
        value = TEMPLATE_RE.sub("", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("'''", "").replace("''", "")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip(" |\n\t")
    return unicodedata.normalize("NFC", value)


def first_file_title(value: str) -> str | None:
    match = FILE_RE.search(value)
    if not match:
        return None
    return unicodedata.normalize("NFC", match.group(1).strip())


def extract_section_entry(section: str) -> tuple[str, str | None, str | None]:
    yw = re.search(r"\{\{yw\|([^{}]+)\}\}", section)
    if yw:
        entry_text = clean_markup(yw.group(1))
        row_start = section.rfind("\n|-", 0, yw.start())
        row_start = 0 if row_start < 0 else row_start
        row_end = section.find("\n|-", yw.end())
        row_end = len(section) if row_end < 0 else row_end
        row = section[row_start:row_end]
        notes = [clean_markup(value) for value in re.findall(r"\{\{\*\|([^{}]+)\}\}", row)]
        edition_notes = " ".join(value for value in notes if value) or None
        return entry_text, edition_notes, first_file_title(row)

    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("{{", "{|", "|", "<", "__", "==")):
            continue
        if "：" in line:
            prefix, value = line.split("：", 1)
        elif ":" in line and "[[File:" not in line and "[[文件:" not in line:
            prefix, value = line.split(":", 1)
        else:
            continue
        entry_text = clean_markup(value)
        if not entry_text:
            continue
        notes = [clean_markup(note) for note in re.findall(r"\{\{\*\|([^{}]+)\}\}", value)]
        edition_notes = " ".join(note for note in notes if note) or None
        return entry_text, edition_notes, first_file_title(prefix)
    raise RuntimeError("no Shuowen entry text found in section")


def parse_shuowen(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    pages = payload["query"]["pages"]
    entries: list[dict[str, Any]] = []
    for page in pages:
        title = page["title"]
        if not re.fullmatch(r"說文解字/(?:0[1-9]|1[0-4])", title):
            continue
        revision = page["revisions"][0]
        content = revision["slots"]["main"]["content"]
        headings = list(HEADING_RE.finditer(content))
        for index, match in enumerate(headings):
            start = match.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
            section = content[start:end]
            entry_text, edition_notes, file_title = extract_section_entry(section)
            entries.append(
                {
                    "radical_number": len(entries) + 1,
                    "source_headword": normalize_heading(match.group(1)),
                    "entry_text": entry_text,
                    "edition_notes": edition_notes,
                    "source_page": title,
                    "page_id": page["pageid"],
                    "revision_id": revision["revid"],
                    "revision_timestamp": revision["timestamp"],
                    "file_title": file_title,
                }
            )
    if len(entries) != 540:
        raise RuntimeError(f"parsed {len(entries)} Shuowen headings, expected 540")
    by_heading: dict[str, dict[str, Any]] = {}
    for entry in entries:
        heading = entry["source_headword"]
        if heading in by_heading:
            raise RuntimeError(f"duplicate Shuowen heading: {heading}")
        by_heading[heading] = entry
    return entries, by_heading


def parse_kangxi_counts(path: Path) -> dict[int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    content = payload["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    matches = list(re.finditer(r"\[\[Radical (\d+)\|\d+\]\]", content))
    counts: dict[int, int] = {}
    for index, match in enumerate(matches):
        number = int(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        row_start = content.rfind("|----", 0, match.start())
        row = content[row_start:end]
        cells = [line[1:].strip() for line in row.splitlines() if line.startswith("|") and not line.startswith("|----")]
        if len(cells) < 10:
            raise RuntimeError(f"radical {number} has only {len(cells)} table cells")
        frequency = cells[9].replace(",", "")
        if not frequency.isdigit():
            raise RuntimeError(f"radical {number} has malformed Kangxi count {cells[9]!r}")
        counts[number] = int(frequency)
    if set(counts) != set(range(1, 215)):
        raise RuntimeError("English Wikipedia table does not contain counts for radicals 1–214")
    return counts


def load_asset_manifest() -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    if not ASSET_MANIFEST_PATH.is_file():
        return {"schema_version": "1.0.0", "assets": []}, {}
    manifest = json.loads(ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
    assets = manifest.get("assets", [])
    priority = {
        SHUOWEN_540_SERIES_ID: 3,
        EXACT_CHARACTER_SEAL_ID: 2,
        SHUOWEN_ASSET_ID: 1,
        SHUOWEN_540_COMPOSITE_ID: 0,
    }
    by_number: dict[int, dict[str, Any]] = {}
    for asset in assets:
        number = asset.get("kangxi_number")
        if not isinstance(number, int) or asset.get("source_id") not in priority:
            continue
        current = by_number.get(number)
        if current is None or priority[asset["source_id"]] > priority[current["source_id"]]:
            by_number[number] = asset
    return manifest, by_number


def asset_reference(asset: dict[str, Any]) -> dict[str, Any]:
    reference = {
        "asset_id": asset["asset_id"],
        "path": asset["local_path"],
        "source_id": asset["source_id"],
        "source_file": asset["source_file"],
        "license_id": asset["license_id"],
    }
    if asset.get("locator"):
        reference["locator"] = asset["locator"]
    return reference


def make_gap(field: str, reason: str, detail: str) -> dict[str, str]:
    return {"field": field, "reason": reason, "detail": detail}


def map_shuowen_entry(
    primary: str,
    properties: dict[str, str],
    by_heading: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    if primary in by_heading:
        return by_heading[primary], "exact_heading"
    semantic_variants = phase1.unihan_variant_codepoints(properties.get("kSemanticVariant"))
    matches = [by_heading[chr(cp)] for cp in semantic_variants if chr(cp) in by_heading]
    if len(matches) > 1:
        raise RuntimeError(f"ambiguous Shuowen semantic-variant mapping for {primary}")
    if matches:
        return matches[0], "unihan_semantic_variant"
    return None, None


def enrich_record(
    record: dict[str, Any],
    properties: dict[str, str],
    by_heading: dict[str, dict[str, Any]],
    kangxi_count: int,
    assets_by_number: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    number = record["kangxi_number"]
    primary = record["primary"]["char"]
    definition = properties.get("kDefinition")
    if not definition:
        raise RuntimeError(f"radical {number} lacks Unihan kDefinition")

    record["definitions"] = [
        {"gloss": definition, "lang": "en", "register": "modern"}
    ]
    record["english_definition"] = definition
    record["semantic_field"] = None
    record["historical_forms"] = {
        "oracle_bone_甲骨文": [],
        "bronze_金文": [],
        "shuowen_seal_說文解字": [],
        "liushutong_六書通": [],
    }
    record["character_count_in_kangxi"] = kangxi_count
    record["character_count_in_kangxi_status"] = "secondary_source_unverified"
    record["sources"]["definitions"] = [phase1.UNIHAN_ID]
    record["sources"]["english_definition"] = [phase1.UNIHAN_ID]
    record["sources"]["character_count_in_kangxi"] = [KANGXI_COUNTS_ID]
    record["sources"]["character_count_in_kangxi_status"] = [KANGXI_COUNTS_ID]
    record["gaps"].extend(
        [
            make_gap(
                "semantic_field",
                "source_unavailable",
                "No approved Phase 2 source provides a systematic semantic-field taxonomy for all 214 radicals.",
            ),
            make_gap(
                "historical_forms.oracle_bone_甲骨文",
                "source_unavailable",
                "No approved, systematically mapped, redistributable oracle-bone image source is available in Phase 2.",
            ),
            make_gap(
                "historical_forms.bronze_金文",
                "source_unavailable",
                "No approved, systematically mapped, redistributable bronze-inscription image source is available in Phase 2.",
            ),
            make_gap(
                "historical_forms.liushutong_六書通",
                "source_unavailable",
                "The approved 六書通 scans lack verified per-radical page locators; no image is assigned without that mapping.",
            ),
            make_gap(
                "character_count_in_kangxi.primary_scan_verification",
                "source_unavailable",
                "The count is pinned secondary-source evidence; a single internally complete 1716 Kangxi scan has not yet been selected and counted.",
            ),
        ]
    )

    entry, mapping_type = map_shuowen_entry(primary, properties, by_heading)
    candidate: dict[str, Any] | None = None
    if entry is None:
        record["shuowen"] = None
        for field in ("shuowen.radical_number", "shuowen.entry_text", "shuowen.seal_glyph"):
            record["gaps"].append(
                make_gap(
                    field,
                    "not_attested",
                    "No exact heading or Unihan kSemanticVariant mapping connects this Kangxi radical to a pinned Shuowen heading.",
                )
            )
        exact_asset = assets_by_number.get(number)
        if exact_asset and exact_asset["source_id"] == EXACT_CHARACTER_SEAL_ID:
            exact_reference = asset_reference(exact_asset)
            record["historical_forms"]["shuowen_seal_說文解字"] = [exact_reference]
            record["sources"]["historical_forms.shuowen_seal_說文解字"] = [
                EXACT_CHARACTER_SEAL_ID
            ]
        else:
            record["gaps"].append(
                make_gap(
                    "historical_forms.shuowen_seal_說文解字",
                    "source_unavailable",
                    "No license-verified exact-character seal-form original has been acquired; the absence of a Shuowen heading is not treated as proof that no historical form exists.",
                )
            )
    else:
        source_ids = [SHUOWEN_ID]
        if mapping_type == "unihan_semantic_variant":
            source_ids.append(phase1.UNIHAN_ID)
        seal_asset = assets_by_number.get(number)
        seal_reference = asset_reference(seal_asset) if seal_asset else None
        record["shuowen"] = {
            "radical_number": entry["radical_number"],
            "source_headword": entry["source_headword"],
            "mapping_type": mapping_type,
            "entry_text": entry["entry_text"],
            "edition_notes": entry["edition_notes"],
            "source_page": entry["source_page"],
            "page_id": entry["page_id"],
            "revision_id": entry["revision_id"],
            "revision_timestamp": entry["revision_timestamp"],
            "seal_glyph": seal_reference,
        }
        record["sources"]["shuowen"] = source_ids
        if seal_reference:
            record["historical_forms"]["shuowen_seal_說文解字"] = [seal_reference]
            record["sources"]["shuowen.seal_glyph"] = [seal_asset["source_id"]]
            record["sources"]["historical_forms.shuowen_seal_說文解字"] = [
                seal_asset["source_id"]
            ]
        else:
            detail = (
                "The mapped Wikisource radical entry contains no embedded Commons seal-form file."
                if not entry["file_title"]
                else "The embedded Commons seal-form file has not passed the per-file license and integrity gate."
            )
            record["gaps"].extend(
                [
                    make_gap("shuowen.seal_glyph", "source_unavailable", detail),
                    make_gap(
                        "historical_forms.shuowen_seal_說文解字",
                        "source_unavailable",
                        detail,
                    ),
                ]
            )
        if entry["file_title"]:
            candidate = {
                "kangxi_number": number,
                "primary": primary,
                "source_page": entry["source_page"],
                "revision_id": entry["revision_id"],
                "source_file": entry["file_title"],
            }
    return phase1.normalize_tree(record), candidate


def deterministic_record_digest(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    phase1.main()
    registry = phase1.load_registry()
    cjk_path = phase1.acquired_path(registry, phase1.CJK_RADICALS_ID)
    unihan_path = phase1.acquired_path(registry, phase1.UNIHAN_ID)
    shuowen_path = phase1.acquired_path(registry, SHUOWEN_ID)
    counts_path = phase1.acquired_path(registry, KANGXI_COUNTS_ID)
    cjk_bases, _ = phase1.parse_cjk_radicals(cjk_path)
    primary_cps = {row["unified_cp"] for row in cjk_bases.values()}
    unihan = phase1.parse_unihan(unihan_path, primary_cps)
    entries, by_heading = parse_shuowen(shuowen_path)
    counts = parse_kangxi_counts(counts_path)
    _, assets_by_number = load_asset_manifest()

    records: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for number in range(1, 215):
        path = RADICALS_PATH / f"{number}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        cp = cjk_bases[number]["unified_cp"]
        enriched, candidate = enrich_record(
            record, unihan[cp], by_heading, counts[number], assets_by_number
        )
        records.append(enriched)
        if candidate:
            candidates.append(candidate)
        path.write_text(
            json.dumps(enriched, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    ASSET_CANDIDATES_PATH.write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "source_id": SHUOWEN_ASSET_ID,
                "candidate_count": len(candidates),
                "candidates": candidates,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    source_ids = [
        phase1.UNIHAN_ID,
        SHUOWEN_ID,
        KANGXI_COUNTS_ID,
        SHUOWEN_ASSET_ID,
        SHUOWEN_540_SERIES_ID,
        SHUOWEN_540_COMPOSITE_ID,
        EXACT_CHARACTER_SEAL_ID,
    ]
    manifest = {
        "phase": 2,
        "generated_at": utc_now(),
        "record_count": len(records),
        "english_definition_count": sum(
            bool(record.get("english_definition")) for record in records
        ),
        "shuowen_heading_count": len(entries),
        "shuowen_mapped_count": sum(record["shuowen"] is not None for record in records),
        "shuowen_asset_count": sum(
            bool(record["historical_forms"]["shuowen_seal_說文解字"])
            for record in records
        ),
        "record_digest_sha256": deterministic_record_digest(records),
        "source_acquisitions": {
            source_id: registry["sources"][source_id]["acquisition"]
            for source_id in source_ids
        },
        "transport_sources": [WAYBACK_MIRROR_ID, GITHUB_MIRROR_ID],
        "asset_manifest": (
            {
                "local_path": str(ASSET_MANIFEST_PATH.relative_to(ROOT)),
                "sha256": sha256_path(ASSET_MANIFEST_PATH),
            }
            if ASSET_MANIFEST_PATH.is_file()
            else None
        ),
        "builder": "scripts/build_phase2.py",
        "schema": "schema/radical.schema.json",
    }
    MANIFEST_PATH.write_text(
        json.dumps(phase1.normalize_tree(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"enriched {len(records)} records; "
        f"Shuowen mappings {manifest['shuowen_mapped_count']}, "
        f"assets {manifest['shuowen_asset_count']}"
    )


if __name__ == "__main__":
    main()
