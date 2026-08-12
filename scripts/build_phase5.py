#!/usr/bin/env python3
"""Build Phase 5 ordered SVGs and attach them to radicals and characters."""

from __future__ import annotations

import hashlib
import html
import json
import sys
import unicodedata
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_phase2 as phase2  # noqa: E402
import build_phase3 as phase3  # noqa: E402
import build_phase4 as phase4  # noqa: E402
import validate_phase2 as validate2  # noqa: E402
import validate_phase4 as validate4  # noqa: E402


ASSET_ROOT = ROOT / "assets" / "stroke-order"
ASSET_MANIFEST_PATH = ROOT / "assets" / "manifest.json"
MANIFEST_PATH = ROOT / "metadata" / "manifests" / "phase5.json"
GF_ID = "prc-stroke-order-gf0023-2020"
KANJIVG_GAP_ID = "kanjivg-u6c59-gap-audit-2026-08-11"
TYPE_NAMES = {"1": "橫", "2": "豎", "3": "撇", "4": "點", "5": "折"}
STANDARD = "PRC GF 0023-2020 (provisional baseline)"
SOURCE_CONVENTION = "Make Me a Hanzi PRC stroke order"
RECONSTRUCTED_CP = 0x6C59
LEFT_COMPONENT_CP = 0x6C61
RIGHT_COMPONENT_CP = 0x4E8E
RECONSTRUCTION_VERSION = "components-v1"
RECONSTRUCTION_CONVENTION = (
    "Reconstructed component geometry; Taiwan CNS stroke sequence"
)
RIGHT_COMPONENT_TRANSFORM = "matrix(0.65 0 0 0.9 320 0)"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def codepoint(cp: int) -> str:
    return f"U+{cp:04X}"


def asset_id(cp: int, reconstructed: bool = False) -> str:
    if reconstructed:
        return f"stroke-order-{codepoint(cp)}-reconstructed-{RECONSTRUCTION_VERSION}"
    return f"stroke-order-{codepoint(cp)}-mmah-bddc96d4"


def parse_graphics(
    registry: dict[str, Any], path: Path
) -> dict[int, dict[str, Any]]:
    acquisition = registry["sources"][phase3.MMAH_GRAPHICS_ID]["acquisition"]
    if sha256_path(path) != acquisition["sha256"]:
        raise RuntimeError("Make Me a Hanzi graphics SHA-256 mismatch")
    if path.stat().st_size != acquisition["expected_bytes"]:
        raise RuntimeError("Make Me a Hanzi graphics byte length mismatch")
    result: dict[int, dict[str, Any]] = {}
    with path.open("rb") as stream:
        for index, raw in enumerate(stream, start=1):
            row = json.loads(raw.decode("utf-8"))
            char = unicodedata.normalize("NFC", row["character"])
            if len(char) != 1:
                raise RuntimeError(f"graphics row {index} is not one character")
            cp = ord(char)
            if cp in result:
                raise RuntimeError(f"duplicate graphics character {codepoint(cp)}")
            strokes = row.get("strokes")
            medians = row.get("medians")
            if (
                not isinstance(strokes, list)
                or not strokes
                or not all(isinstance(item, str) and item for item in strokes)
                or not isinstance(medians, list)
                or len(medians) != len(strokes)
            ):
                raise RuntimeError(f"malformed graphics row {index}")
            result[cp] = {
                "character": char,
                "strokes": strokes,
                "medians": medians,
                "source_record_index": index,
                "source_record_sha256": hashlib.sha256(raw).hexdigest(),
            }
    if len(result) != 9574:
        raise RuntimeError(f"graphics row count is {len(result)}, expected 9574")
    return result


def audit_kanjivg_gap(registry: dict[str, Any]) -> None:
    path = phase3.acquired_path(registry, KANJIVG_GAP_ID)
    acquisition = registry["sources"][KANJIVG_GAP_ID]["acquisition"]
    if sha256_path(path) != acquisition["sha256"] or path.stat().st_size != acquisition["bytes"]:
        raise RuntimeError("KanjiVG gap-audit index integrity mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    if "汙" in serialized or "06c59" in serialized:
        raise RuntimeError("KanjiVG now contains an exact U+6C59 index entry")
    commit_path = ROOT / acquisition["commit_metadata_path"]
    if (
        sha256_path(commit_path) != acquisition["commit_metadata_sha256"]
        or commit_path.stat().st_size != acquisition["commit_metadata_bytes"]
    ):
        raise RuntimeError("KanjiVG commit metadata integrity mismatch")
    commit = json.loads(commit_path.read_text(encoding="utf-8"))
    if commit.get("sha") != acquisition["commit"]:
        raise RuntimeError("KanjiVG commit metadata does not match the pinned commit")


def audit_cns_type_documentation(registry: dict[str, Any], path: Path) -> None:
    expected = registry["sources"][phase3.CNS_ID]["acquisition"][
        "documentation_member"
    ]
    matches: list[bytes] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.file_size != expected["bytes"]:
                continue
            payload = archive.read(info)
            if hashlib.sha256(payload).hexdigest() == expected["sha256"]:
                matches.append(payload)
    if len(matches) != 1:
        raise RuntimeError("CNS property documentation member is not uniquely pinned")
    text = matches[0].decode(expected["encoding"])
    required = (
        expected["heading"],
        "1表示「橫」",
        "2表示「豎」",
        "3表示「撇」",
        "4表示「點」",
        "5表示「折」",
    )
    if not all(item in text for item in required):
        raise RuntimeError("CNS stroke-type documentation differs from the pinned mapping")


def make_svg(cp: int, row: dict[str, Any]) -> str:
    title = html.escape(f"{row['character']} {codepoint(cp)} ordered strokes")
    paths = []
    for index, path_data in enumerate(row["strokes"], start=1):
        paths.append(
            "    <path "
            f'id="stroke-{codepoint(cp)}-{index}" '
            f'data-stroke-index="{index}" '
            'data-stroke-type-status="source-unavailable" '
            f'd="{html.escape(path_data, quote=True)}"/>'
        )
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img">',
            f"  <title>{title}</title>",
            "  <metadata>Derived without path alteration from Make Me a Hanzi graphics.txt commit bddc96d41bef78427ed0e034e9f7e31d71fd1b92; Arphic Public License; generated wrapper adds path indices and the source coordinate transform. Stroke-type names are unavailable in the path source.</metadata>",
            '  <g fill="#000" transform="scale(1,-1) translate(0,-900)">',
            *paths,
            "  </g>",
            "</svg>",
            "",
        ]
    )


def reconstruction_strokes(
    graphics: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the fully disclosed U+6C59 component/path assembly plan."""
    left = graphics[LEFT_COMPONENT_CP]
    right = graphics[RIGHT_COMPONENT_CP]
    if left["character"] != "污" or len(left["strokes"]) != 6:
        raise RuntimeError("pinned 污 component source differs")
    if right["character"] != "于" or len(right["strokes"]) != 3:
        raise RuntimeError("pinned 于 component source differs")
    result: list[dict[str, Any]] = []
    for source_index, path_data in enumerate(left["strokes"][:3], start=1):
        result.append(
            {
                "path": path_data,
                "source_codepoint": codepoint(LEFT_COMPONENT_CP),
                "source_character": left["character"],
                "source_stroke_index": source_index,
                "transform": None,
            }
        )
    for source_index, path_data in enumerate(right["strokes"], start=1):
        result.append(
            {
                "path": path_data,
                "source_codepoint": codepoint(RIGHT_COMPONENT_CP),
                "source_character": right["character"],
                "source_stroke_index": source_index,
                "transform": RIGHT_COMPONENT_TRANSFORM,
            }
        )
    return result


def make_reconstructed_svg(
    graphics: dict[int, dict[str, Any]], cns_sequence: str
) -> str:
    strokes = reconstruction_strokes(graphics)
    if cns_sequence != "444115" or len(cns_sequence) != len(strokes):
        raise RuntimeError("U+6C59 Taiwan CNS sequence differs from pinned 444115")
    paths: list[str] = []
    for index, (stroke, type_code) in enumerate(
        zip(strokes, cns_sequence), start=1
    ):
        transform = (
            f' transform="{stroke["transform"]}"' if stroke["transform"] else ""
        )
        paths.append(
            "    <path "
            f'id="stroke-{codepoint(RECONSTRUCTED_CP)}-{index}" '
            f'data-stroke-index="{index}" '
            'data-geometry-status="reconstructed" '
            f'data-source-codepoint="{stroke["source_codepoint"]}" '
            f'data-source-character="{stroke["source_character"]}" '
            f'data-source-stroke-index="{stroke["source_stroke_index"]}" '
            f'data-taiwan-cns-type-code="{type_code}" '
            f'data-taiwan-cns-type-name="{TYPE_NAMES[type_code]}"'
            f'{transform} d="{html.escape(stroke["path"], quote=True)}"/>'
        )
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img">',
            f"  <title>汙 {codepoint(RECONSTRUCTED_CP)} reconstructed ordered strokes</title>",
            "  <metadata>RECONSTRUCTED ASSET: no exact U+6C59 row exists in the pinned Make Me a Hanzi snapshot. Strokes 1-3 reuse the left-side water component from 污 U+6C61; strokes 4-6 reuse 于 U+4E8E with the disclosed affine transform matrix(0.65 0 0 0.9 320 0). Order and type metadata follow the pinned Taiwan CNS11643 sequence 444115. Geometry is a corpus-generated composition, not an attested historical or official glyph.</metadata>",
            '  <g fill="#000" transform="scale(1,-1) translate(0,-900)">',
            *paths,
            "  </g>",
            "</svg>",
            "",
        ]
    )


def stroke_types(sequence: str) -> list[dict[str, str]]:
    return [{"code": item, "name_zh": TYPE_NAMES[item]} for item in sequence]


def clear_phase5(record: dict[str, Any]) -> None:
    record.pop("stroke_order", None)
    record.get("sources", {}).pop("stroke_order", None)
    for key in list(record.get("sources", {})):
        if key.startswith("stroke_order."):
            record["sources"].pop(key)
    record["gaps"] = [
        gap
        for gap in record.get("gaps", [])
        if not gap.get("field", "").startswith("stroke_order")
    ]


def make_stroke_order(
    cp: int,
    path_count: int,
    taiwan_count: int,
    cns_sequence: str | None,
    sources: dict[str, list[str]],
    gaps: list[dict[str, str]],
    reconstructed: bool = False,
) -> dict[str, Any]:
    if reconstructed:
        svg_sources = [phase3.MMAH_GRAPHICS_ID, phase3.CNS_ID]
        convention_sources = [phase3.MMAH_GRAPHICS_ID, phase3.CNS_ID]
        count_sources = [phase3.MMAH_GRAPHICS_ID, phase3.CNS_ID]
        source_convention = RECONSTRUCTION_CONVENTION
    else:
        svg_sources = [phase3.MMAH_GRAPHICS_ID]
        convention_sources = [phase3.MMAH_GRAPHICS_ID]
        count_sources = [phase3.MMAH_GRAPHICS_ID]
        source_convention = SOURCE_CONVENTION
    sources.update(
        {
            "stroke_order.svg_asset_id": svg_sources,
            "stroke_order.standard": [GF_ID],
            "stroke_order.source_convention": convention_sources,
            "stroke_order.formal_conformance": [*convention_sources, GF_ID],
            "stroke_order.stroke_count": count_sources,
        }
    )
    gaps.extend(
        [
            phase3.make_gap(
                "stroke_order.stroke_types",
                "source_unavailable",
                "Make Me a Hanzi supplies ordered paths but no authoritative per-path stroke-type names; Taiwan CNS types are retained separately and are not assigned to PRC path indices.",
            ),
            phase3.make_gap(
                "stroke_order.formal_standard_verification",
                "source_unavailable",
                "The GF 0023-2020 publication is reference-only and the path source claims PRC convention without formal per-character conformance evidence.",
            ),
        ]
    )
    if cns_sequence:
        taiwan_sequence = stroke_types(cns_sequence)
        sources["stroke_order.taiwan_cns_stroke_sequence"] = [phase3.CNS_ID]
    else:
        taiwan_sequence = None
        gaps.append(
            phase3.make_gap(
                "stroke_order.taiwan_cns_stroke_sequence",
                "not_attested",
                "The pinned CNS11643 stroke-sequence table has no row for this exact unified ideograph.",
            )
        )
    conflicts: list[dict[str, Any]] = []
    if path_count != taiwan_count:
        conflicts.append(
            {
                "field": "stroke_count",
                "prc_path_count": path_count,
                "taiwan_count": taiwan_count,
                "source_ids": [phase3.MMAH_GRAPHICS_ID, phase3.CNS_ID],
                "detail": "The PRC-convention SVG path count differs from the canonical Taiwan count; neither source value is changed.",
            }
        )
        sources["stroke_order.standard_conflicts"] = [
            phase3.MMAH_GRAPHICS_ID,
            phase3.CNS_ID,
        ]
    return {
        "svg_asset_id": asset_id(cp, reconstructed=reconstructed),
        "standard": STANDARD,
        "source_convention": source_convention,
        "formal_conformance": "not_verified",
        "stroke_count": path_count,
        "stroke_types": None,
        "taiwan_cns_stroke_sequence": taiwan_sequence,
        "standard_conflicts": conflicts,
    }


def cns_sequence_for(
    cp: int, unihan: dict[int, dict[str, str]], sequences: dict[str, str]
) -> str | None:
    t_source = unihan[cp].get("kIRG_TSource", "")
    cns_code = t_source[1:] if t_source.startswith("T") else ""
    return sequences.get(cns_code)


def write_asset(
    cp: int,
    row: dict[str, Any],
    acquisition: dict[str, Any],
) -> dict[str, Any]:
    directory = ASSET_ROOT / codepoint(cp)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "makemeahanzi-bddc96d4.svg"
    svg = make_svg(cp, row)
    if not unicodedata.is_normalized("NFC", svg):
        raise RuntimeError(f"generated SVG is not NFC: {codepoint(cp)}")
    path.write_text(svg, encoding="utf-8")
    return {
        "asset_id": asset_id(cp),
        "asset_type": "stroke_order",
        "codepoint": codepoint(cp),
        "character": row["character"],
        "source_id": phase3.MMAH_GRAPHICS_ID,
        "source_file": acquisition["local_path"],
        "source_commit": acquisition["commit"],
        "source_record_index": row["source_record_index"],
        "source_record_sha256": row["source_record_sha256"],
        "local_path": str(path.relative_to(ROOT)),
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
        "mime_type": "image/svg+xml",
        "width": 1024,
        "height": 1024,
        "stroke_count": len(row["strokes"]),
        "license_id": "Arphic-1999",
        "license_url": "https://github.com/skishore/makemeahanzi/blob/bddc96d41bef78427ed0e034e9f7e31d71fd1b92/APL/english/ARPHICPL.TXT",
        "attribution_required": True,
        "required_attribution": "Stroke paths from Make Me a Hanzi, used under the Arphic Public License; generated SVG wrapper and stroke-index metadata added by this corpus.",
        "transformations": [
            "Preserved every source Bézier path string and source order unchanged.",
            "Wrapped paths in a 1024×1024 SVG and applied scale(1,-1) translate(0,-900) to display the source coordinate system.",
            "Added stable per-path IDs, one-based stroke indices, source/license metadata, and a source-unavailable stroke-type marker.",
        ],
        "standard": STANDARD,
        "source_convention": SOURCE_CONVENTION,
        "formal_conformance": "not_verified",
    }


def write_reconstructed_asset(
    graphics: dict[int, dict[str, Any]],
    acquisition: dict[str, Any],
    cns_sequence: str,
) -> dict[str, Any]:
    cp = RECONSTRUCTED_CP
    directory = ASSET_ROOT / codepoint(cp)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"reconstructed-{RECONSTRUCTION_VERSION}.svg"
    svg = make_reconstructed_svg(graphics, cns_sequence)
    if not unicodedata.is_normalized("NFC", svg):
        raise RuntimeError("reconstructed U+6C59 SVG is not NFC")
    path.write_text(svg, encoding="utf-8")
    left = graphics[LEFT_COMPONENT_CP]
    right = graphics[RIGHT_COMPONENT_CP]
    return {
        "asset_id": asset_id(cp, reconstructed=True),
        "asset_type": "stroke_order",
        "codepoint": codepoint(cp),
        "character": "汙",
        "provenance_type": "reconstructed",
        "source_ids": [phase3.MMAH_GRAPHICS_ID, phase3.CNS_ID],
        "source_files": [
            acquisition["local_path"],
            "source-data/cns11643-2026-08-05/Properties.zip",
        ],
        "source_commit": acquisition["commit"],
        "component_sources": [
            {
                "role": "left-side water component",
                "character": left["character"],
                "codepoint": codepoint(LEFT_COMPONENT_CP),
                "source_record_index": left["source_record_index"],
                "source_record_sha256": left["source_record_sha256"],
                "source_stroke_indices": [1, 2, 3],
                "target_stroke_indices": [1, 2, 3],
                "path_transform": "identity",
            },
            {
                "role": "right-side 于 component",
                "character": right["character"],
                "codepoint": codepoint(RIGHT_COMPONENT_CP),
                "source_record_index": right["source_record_index"],
                "source_record_sha256": right["source_record_sha256"],
                "source_stroke_indices": [1, 2, 3],
                "target_stroke_indices": [4, 5, 6],
                "path_transform": RIGHT_COMPONENT_TRANSFORM,
            },
        ],
        "order_source": {
            "source_id": phase3.CNS_ID,
            "sequence": cns_sequence,
            "type_mapping": "1=橫, 2=豎, 3=撇, 4=點, 5=折",
        },
        "geometry_status": "reconstructed_not_attested",
        "exact_source_gap": {
            "reason": "source_unavailable",
            "detail": "No exact U+6C59 row exists in the pinned Make Me a Hanzi snapshot or pinned official KanjiVG index.",
        },
        "local_path": str(path.relative_to(ROOT)),
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
        "mime_type": "image/svg+xml",
        "width": 1024,
        "height": 1024,
        "stroke_count": 6,
        "license_id": "Arphic-1999",
        "license_url": "https://github.com/skishore/makemeahanzi/blob/bddc96d41bef78427ed0e034e9f7e31d71fd1b92/APL/english/ARPHICPL.TXT",
        "attribution_required": True,
        "required_attribution": "Component stroke paths from Make Me a Hanzi, used under the Arphic Public License; 汙 composition, affine placement, SVG wrapper, and metadata generated by this corpus. Stroke sequence from Taiwan CNS11643 open data.",
        "transformations": [
            "Copied strokes 1-3 from the left-side water component in the exact 污 U+6C61 source row without changing their path strings.",
            f"Copied all three 于 U+4E8E path strings and displayed them with {RIGHT_COMPONENT_TRANSFORM} as strokes 4-6.",
            "Composed the two sources as 汙 and assigned order/type metadata from the exact Taiwan CNS11643 sequence 444115.",
            "Added stable per-path IDs plus explicit reconstruction, source-component, license, and transformation metadata.",
        ],
        "standard": STANDARD,
        "source_convention": RECONSTRUCTION_CONVENTION,
        "formal_conformance": "not_verified",
    }


def main() -> None:
    registry = phase3.load_registry()
    audit_kanjivg_gap(registry)
    graphics_path = phase3.acquired_path(registry, phase3.MMAH_GRAPHICS_ID)
    cns_path = phase3.acquired_path(registry, phase3.CNS_ID)
    audit_cns_type_documentation(registry, cns_path)
    unihan_path = phase3.acquired_path(registry, phase3.UNIHAN_ID)
    graphics = parse_graphics(registry, graphics_path)
    _, _, sequences, _ = phase3.parse_cns(registry, cns_path)

    radicals = [
        json.loads((ROOT / "radicals" / f"{number}.json").read_text(encoding="utf-8"))
        for number in range(1, 215)
    ]
    character_paths = sorted((ROOT / "characters").glob("*.json"))
    characters = [json.loads(path.read_text(encoding="utf-8")) for path in character_paths]
    characters.sort(key=lambda item: item["frequency"]["selection_rank"])
    if len(characters) != 2000:
        raise RuntimeError("Phase 5 requires exactly 2,000 character records")
    target_cps = {
        ord(record["primary"]["char"]) for record in radicals
    } | {int(record["codepoint"][2:], 16) for record in characters}
    unihan, _ = phase3.parse_unihan(unihan_path, target_cps)

    asset_entries: list[dict[str, Any]] = []
    covered_cps = sorted(target_cps & set(graphics))
    acquisition = registry["sources"][phase3.MMAH_GRAPHICS_ID]["acquisition"]
    for cp in covered_cps:
        asset_entries.append(write_asset(cp, graphics[cp], acquisition))
    reconstructed_sequence = cns_sequence_for(
        RECONSTRUCTED_CP, unihan, sequences
    )
    if reconstructed_sequence is None:
        raise RuntimeError("U+6C59 lacks its pinned Taiwan CNS stroke sequence")
    asset_entries.append(
        write_reconstructed_asset(graphics, acquisition, reconstructed_sequence)
    )
    asset_entries.sort(key=lambda item: int(item["codepoint"][2:], 16))
    expected_paths = {entry["local_path"] for entry in asset_entries}
    for path in ASSET_ROOT.glob("*/*.svg"):
        if str(path.relative_to(ROOT)) not in expected_paths:
            path.unlink()

    for record in radicals:
        clear_phase5(record)
        cp = ord(record["primary"]["char"])
        row = graphics.get(cp)
        if row is None:
            raise RuntimeError(f"radical unexpectedly lacks graphics: {record['kangxi_number']}")
        sequence = cns_sequence_for(cp, unihan, sequences)
        record["stroke_order"] = make_stroke_order(
            cp,
            len(row["strokes"]),
            record["stroke_count"],
            sequence,
            record["sources"],
            record["gaps"],
        )
        output = phase3.normalize_tree(record)
        (ROOT / "radicals" / f"{record['kangxi_number']}.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    missing_characters: list[str] = []
    exact_source_missing: list[str] = []
    reconstructed_characters: list[str] = []
    for record in characters:
        clear_phase5(record)
        cp = int(record["codepoint"][2:], 16)
        row = graphics.get(cp)
        if row is None:
            if cp != RECONSTRUCTED_CP:
                record["stroke_order"] = None
                missing_characters.append(record["codepoint"])
                record["gaps"].append(
                    phase3.make_gap(
                        "stroke_order",
                        "source_unavailable",
                        "No exact or approved reconstructed stroke-order asset is available.",
                    )
                )
                continue
            sequence = cns_sequence_for(cp, unihan, sequences)
            record["stroke_order"] = make_stroke_order(
                cp,
                6,
                record["total_strokes"],
                sequence,
                record["sources"],
                record["gaps"],
                reconstructed=True,
            )
            exact_source_missing.append(record["codepoint"])
            reconstructed_characters.append(record["codepoint"])
            record["gaps"].append(
                phase3.make_gap(
                    "stroke_order.exact_source_asset",
                    "source_unavailable",
                    "The pinned Make Me a Hanzi source has no exact U+6C59 row, and the official KanjiVG index also has no exact U+6C59 entry. The linked SVG is an explicitly labeled component reconstruction, not a substituted exact-source glyph.",
                )
            )
        else:
            sequence = cns_sequence_for(cp, unihan, sequences)
            record["stroke_order"] = make_stroke_order(
                cp,
                len(row["strokes"]),
                record["total_strokes"],
                sequence,
                record["sources"],
                record["gaps"],
            )
        output = phase3.normalize_tree(record)
        (ROOT / "characters" / f"{record['codepoint']}.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    asset_manifest = json.loads(ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
    asset_manifest["stroke_order_assets"] = asset_entries
    asset_manifest["generated_at"] = phase3.utc_now()
    ASSET_MANIFEST_PATH.write_text(
        json.dumps(phase3.normalize_tree(asset_manifest), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    radical_records = [
        json.loads((ROOT / "radicals" / f"{number}.json").read_text(encoding="utf-8"))
        for number in range(1, 215)
    ]
    character_records = [
        json.loads((ROOT / "characters" / f"{record['codepoint']}.json").read_text(encoding="utf-8"))
        for record in characters
    ]
    manifest = {
        "phase": 5,
        "generated_at": phase3.utc_now(),
        "standard": STANDARD,
        "formal_conformance": "not_verified",
        "unique_target_character_count": len(target_cps),
        "stroke_order_asset_count": len(asset_entries),
        "exact_source_asset_count": sum(
            item.get("provenance_type") != "reconstructed"
            for item in asset_entries
        ),
        "reconstructed_asset_count": sum(
            item.get("provenance_type") == "reconstructed"
            for item in asset_entries
        ),
        "radical_record_count": len(radical_records),
        "radical_svg_reference_count": sum(bool(item["stroke_order"]) for item in radical_records),
        "character_record_count": len(character_records),
        "character_svg_reference_count": sum(bool(item["stroke_order"]) for item in character_records),
        "missing_character_codepoints": missing_characters,
        "exact_source_missing_codepoints": exact_source_missing,
        "reconstructed_character_codepoints": reconstructed_characters,
        "radical_standard_conflict_count": sum(bool(item["stroke_order"]["standard_conflicts"]) for item in radical_records),
        "character_standard_conflict_count": sum(bool(item["stroke_order"] and item["stroke_order"]["standard_conflicts"]) for item in character_records),
        "radical_cns_sequence_count": sum(bool(item["stroke_order"]["taiwan_cns_stroke_sequence"]) for item in radical_records),
        "character_cns_sequence_count": sum(bool(item["stroke_order"] and item["stroke_order"]["taiwan_cns_stroke_sequence"]) for item in character_records),
        "per_path_stroke_type_name_count": 0,
        "stroke_type_gap_reference_count": sum(bool(item["stroke_order"]) for item in radical_records + character_records),
        "stroke_order_asset_digest_sha256": phase3.deterministic_record_digest(asset_entries),
        "radical_record_digest_sha256": phase3.deterministic_record_digest(radical_records),
        "character_record_digest_sha256": phase3.deterministic_record_digest(character_records),
        "phase2_base_record_digest_sha256": phase2.deterministic_record_digest([validate2.phase2_projection(item) for item in radical_records]),
        "phase4_base_character_digest_sha256": phase3.deterministic_record_digest([validate4.phase4_projection(item) for item in character_records]),
        "asset_manifest": {
            "local_path": "assets/manifest.json",
            "sha256": sha256_path(ASSET_MANIFEST_PATH),
        },
        "source_acquisitions": {
            phase3.MMAH_GRAPHICS_ID: registry["sources"][phase3.MMAH_GRAPHICS_ID]["acquisition"],
            phase3.CNS_ID: registry["sources"][phase3.CNS_ID]["acquisition"],
            KANJIVG_GAP_ID: registry["sources"][KANJIVG_GAP_ID]["acquisition"],
        },
        "standard_reference": {
            "source_id": GF_ID,
            "status": registry["sources"][GF_ID]["status"],
            "version": registry["sources"][GF_ID]["version"],
            "url": registry["sources"][GF_ID]["url"],
        },
        "builder": "scripts/build_phase5.py",
        "schemas": [
            "schema/radical.schema.json",
            "schema/character.schema.json",
            "schema/stroke-order-asset.schema.json",
        ],
    }
    MANIFEST_PATH.write_text(
        json.dumps(phase3.normalize_tree(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"built {len(asset_entries)} unique stroke-order SVGs; "
        f"radicals {manifest['radical_svg_reference_count']}/214, "
        f"characters {manifest['character_svg_reference_count']}/2000"
    )


if __name__ == "__main__":
    main()
