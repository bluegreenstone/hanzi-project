#!/usr/bin/env python3
"""Build the Phase 3 Traditional-primary top-2,000 character corpus."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import subprocess
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "sources.json"
CHARACTERS_PATH = ROOT / "characters"
MANIFEST_PATH = ROOT / "phase3-manifest.json"

MOE_ID = "moe-tw-common-terms-1996"
UNIHAN_ID = "unicode-unihan-17.0.0"
CJK_RADICALS_ID = "unicode-cjk-radicals-17.0.0"
EQUIVALENT_IDEOGRAPH_ID = "unicode-equivalent-unified-ideograph-17.0.0"
CNS_ID = "cns11643-attributes-2026-08-05"
MMAH_DICTIONARY_ID = "makemeahanzi-dictionary-master-audit"
MMAH_GRAPHICS_ID = "makemeahanzi-graphics-master-audit"
CC_CEDICT_ID = "cc-cedict-editor-2026-08-11"

CODEPOINT_RE = re.compile(r"U\+([0-9A-F]{4,6})")
CC_CEDICT_RE = re.compile(r"^(\S+) (\S+) \[([^]]*)\] /(.*)/$")
RS_RE = re.compile(r"^(\d+)'?\.(-?\d+)$")

UNIHAN_FIELDS = {
    "kRSUnicode",
    "kIRG_TSource",
    "kTotalStrokes",
    "kMandarin",
    "kHanyuPinyin",
    "kTGHZ2013",
    "kCantonese",
    "kJapaneseOn",
    "kJapaneseKun",
    "kKorean",
    "kHangul",
    "kFanqie",
    "kDefinition",
    "kSimplifiedVariant",
    "kSemanticVariant",
    "kSpecializedSemanticVariant",
    "kSpoofingVariant",
    "kTraditionalVariant",
    "kZVariant",
    "kIRGKangXi",
    "kKangXi",
}

VARIANT_RELATIONSHIPS = {
    "kSemanticVariant": "semantic",
    "kSpecializedSemanticVariant": "specialized_semantic",
    "kSpoofingVariant": "spoofing",
    "kTraditionalVariant": "traditional",
    "kZVariant": "z_variant",
}

HAN_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0x20000, 0x2A6DF),
    (0x2A700, 0x2B73F),
    (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF),
    (0x2CEB0, 0x2EBEF),
    (0x30000, 0x3134F),
    (0x31350, 0x3347F),
)


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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def codepoint(value: int) -> str:
    return f"U+{value:04X}"


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = unicodedata.normalize("NFC", value.strip())
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def normalize_tree(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [normalize_tree(item) for item in value]
    if isinstance(value, dict):
        return {normalize_tree(key): normalize_tree(item) for key, item in value.items()}
    return value


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def acquired_path(registry: dict[str, Any], source_id: str) -> Path:
    source = registry["sources"][source_id]
    if source["status"] != "approved":
        raise RuntimeError(f"source is not approved: {source_id}")
    acquisition = source.get("acquisition")
    if not acquisition:
        raise RuntimeError(f"source is not pinned: {source_id}")
    path = ROOT / acquisition["local_path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_path(path)
    if actual != acquisition["sha256"]:
        raise RuntimeError(
            f"SHA-256 mismatch for {source_id}: "
            f"expected {acquisition['sha256']}, got {actual}"
        )
    if acquisition.get("expected_bytes") not in (None, path.stat().st_size):
        raise RuntimeError(f"byte-length mismatch for {source_id}")
    return path


def is_han_unified(cp: int) -> bool:
    return any(start <= cp <= end for start, end in HAN_RANGES)


def is_forbidden_character(cp: int) -> bool:
    return (
        0x2E80 <= cp <= 0x2EFF
        or 0x2F00 <= cp <= 0x2FDF
        or 0xF900 <= cp <= 0xFAFF
        or 0x2F800 <= cp <= 0x2FA1F
    )


def read_moe_frequency(
    registry: dict[str, Any], path: Path
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    acquisition = registry["sources"][MOE_ID]["acquisition"]
    member = acquisition["members"]["character_frequency"]
    with zipfile.ZipFile(path) as archive:
        payload = archive.read(member["path"])
    if sha256_bytes(payload) != member["sha256"]:
        raise RuntimeError("MOE character-frequency member SHA-256 mismatch")
    if len(payload) != member["bytes"]:
        raise RuntimeError("MOE character-frequency member byte-length mismatch")
    conversion = subprocess.run(
        ["iconv", "-f", acquisition["source_encoding"], "-t", "UTF-8"],
        input=payload,
        capture_output=True,
        check=False,
    )
    if conversion.returncode != 0:
        raise RuntimeError(
            "the platform iconv implementation could not decode the MOE legacy Big5 file: "
            + conversion.stderr.decode("utf-8", errors="replace")
        )
    text = conversion.stdout.decode("utf-8", errors="strict")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    expected_fields = ["字頻序號", "字", "部首", "筆畫", "出現頻次", "累積頻次", "累積百分比"]
    if reader.fieldnames != expected_fields:
        raise RuntimeError(f"unexpected MOE CSV fields: {reader.fieldnames!r}")

    all_rows: list[dict[str, Any]] = []
    ranks: set[int] = set()
    for raw in reader:
        rank = int(raw["字頻序號"])
        if rank in ranks:
            raise RuntimeError(f"duplicate MOE source rank {rank}")
        ranks.add(rank)
        row = {
            "rank": rank,
            "character": unicodedata.normalize("NFC", raw["字"]),
            "radical_label": unicodedata.normalize("NFC", raw["部首"]),
            "strokes": int(raw["筆畫"]),
            "count": int(raw["出現頻次"]),
            "cumulative_count": int(raw["累積頻次"]),
            "cumulative_percentage": float(raw["累積百分比"]),
        }
        all_rows.append(row)
    if not all_rows or [row["rank"] for row in all_rows] != list(
        range(1, len(all_rows) + 1)
    ):
        raise RuntimeError("MOE source ranks are not a complete ascending sequence")
    corpus_total = all_rows[-1]["cumulative_count"]

    selected: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen_chars: set[str] = set()
    for row in all_rows:
        char = row["character"]
        reason: str | None = None
        if len(char) != 1:
            reason = "not_single_codepoint"
        else:
            cp = ord(char)
            if is_forbidden_character(cp):
                reason = "forbidden_radical_or_compatibility_block"
            elif not is_han_unified(cp):
                reason = "not_unified_han"
            elif char in seen_chars:
                raise RuntimeError(f"duplicate valid Han character in MOE rank: {char}")
        if reason:
            if len(selected) < 2000:
                exclusions.append(
                    {"source_rank": row["rank"], "raw_value": char, "reason": reason}
                )
            continue
        seen_chars.add(char)
        selected.append(row)
        if len(selected) == 2000:
            break
    if len(selected) != 2000:
        raise RuntimeError(f"MOE source yielded only {len(selected)} valid Han rows")
    return selected, corpus_total, exclusions


def parse_cjk_radicals(path: Path) -> tuple[dict[int, int], dict[int, int]]:
    radical_to_unified: dict[int, int] = {}
    primary_to_number: dict[int, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        identifier, radical_text, unified_text = [part.strip() for part in line.split(";")]
        number = int(identifier.rstrip("'"))
        unified_cp = int(unified_text, 16)
        if radical_text:
            radical_to_unified[int(radical_text, 16)] = unified_cp
        if not identifier.endswith("'"):
            primary_to_number[unified_cp] = number
    return radical_to_unified, primary_to_number


def parse_equivalent_ideographs(path: Path) -> dict[int, int]:
    result: dict[int, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        source_text, target_text = [part.strip() for part in line.split(";", 1)]
        target = int(target_text, 16)
        if ".." in source_text:
            start_text, end_text = source_text.split("..", 1)
            for source in range(int(start_text, 16), int(end_text, 16) + 1):
                result[source] = target
        else:
            result[int(source_text, 16)] = target
    return result


def parse_unihan(
    path: Path, wanted: set[int]
) -> tuple[dict[int, dict[str, str]], dict[int, dict[str, str]]]:
    selected: dict[int, dict[str, str]] = defaultdict(dict)
    all_variants: dict[int, dict[str, str]] = defaultdict(dict)
    files = (
        "Unihan_IRGSources.txt",
        "Unihan_Readings.txt",
        "Unihan_Variants.txt",
        "Unihan_DictionaryIndices.txt",
    )
    with zipfile.ZipFile(path) as archive:
        for filename in files:
            with archive.open(filename) as raw_stream:
                stream = io.TextIOWrapper(raw_stream, encoding="utf-8")
                for raw in stream:
                    if raw.startswith("#") or not raw.strip():
                        continue
                    cp_text, field, value = raw.rstrip("\n").split("\t", 2)
                    cp = int(cp_text[2:], 16)
                    if filename == "Unihan_Variants.txt":
                        all_variants[cp][field] = unicodedata.normalize("NFC", value)
                    if cp in wanted and field in UNIHAN_FIELDS:
                        selected[cp][field] = unicodedata.normalize("NFC", value)
    return selected, all_variants


def parse_cns(
    registry: dict[str, Any], path: Path
) -> tuple[dict[str, list[str]], dict[str, str], dict[str, str]]:
    acquisition = registry["sources"][CNS_ID]["acquisition"]
    with zipfile.ZipFile(path) as archive:
        payloads: dict[str, bytes] = {}
        for member, metadata in acquisition["used_members"].items():
            payload = archive.read(member)
            if sha256_bytes(payload) != metadata["sha256"]:
                raise RuntimeError(f"CNS member SHA-256 mismatch: {member}")
            payloads[member] = payload

    readings: dict[str, list[str]] = defaultdict(list)
    for line in payloads["CNS_phonetic.txt"].decode("utf-8-sig").splitlines():
        cns_code, value = line.split("\t", 1)
        readings[cns_code].append(unicodedata.normalize("NFC", value))

    bopomofo_to_pinyin: dict[str, str] = {}
    for line in payloads["CNS_pinyin_2.txt"].decode("utf-8-sig").splitlines():
        columns = line.split("\t")
        if len(columns) < 2:
            raise RuntimeError("malformed CNS pinyin-conversion row")
        bopomofo_to_pinyin[unicodedata.normalize("NFC", columns[0])] = (
            unicodedata.normalize("NFC", columns[1])
        )

    stroke_sequences: dict[str, str] = {}
    for line in payloads["CNS_strokes_sequence.txt"].decode("utf-8-sig").splitlines():
        cns_code, sequence = line.split("\t", 1)
        if not sequence or any(item not in "12345" for item in sequence):
            raise RuntimeError("malformed CNS stroke-sequence row")
        stroke_sequences[cns_code] = sequence
    return readings, bopomofo_to_pinyin, stroke_sequences


def parse_mmah_dictionary(path: Path, wanted: set[int]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for raw in stream:
            row = json.loads(raw)
            char = row.get("character", "")
            if len(char) != 1 or ord(char) not in wanted:
                continue
            cp = ord(char)
            if cp in result:
                raise RuntimeError(f"duplicate Make Me a Hanzi dictionary row: {char}")
            result[cp] = normalize_tree(row)
    return result


def parse_mmah_graphics(path: Path, wanted: set[int]) -> dict[int, int]:
    result: dict[int, int] = {}
    with path.open(encoding="utf-8") as stream:
        for raw in stream:
            row = json.loads(raw)
            char = row.get("character", "")
            if len(char) != 1 or ord(char) not in wanted:
                continue
            strokes = row.get("strokes")
            medians = row.get("medians")
            if not isinstance(strokes, list) or not strokes:
                raise RuntimeError(f"invalid Make Me a Hanzi strokes: {char}")
            if not isinstance(medians, list) or len(medians) != len(strokes):
                raise RuntimeError(f"stroke/median mismatch: {char}")
            result[ord(char)] = len(strokes)
    return result


def tone_number_to_mark(value: str) -> str | None:
    value = value.strip().lower().replace("u:", "ü").replace("v", "ü")
    match = re.fullmatch(r"([a-züê]+)([1-5])", value)
    if not match:
        return None
    syllable, tone_text = match.groups()
    tone = int(tone_text)
    if tone == 5:
        return syllable
    candidates: list[int] = []
    if "a" in syllable:
        candidates = [syllable.index("a")]
    elif "e" in syllable:
        candidates = [syllable.index("e")]
    elif "ou" in syllable:
        candidates = [syllable.index("o")]
    else:
        candidates = [index for index, char in enumerate(syllable) if char in "aeiouüê"]
        if candidates:
            candidates = [candidates[-1]]
    if not candidates:
        if syllable in {"m", "n", "ng", "hm", "hng"}:
            candidates = [len(syllable) - 1]
        else:
            return None
    marks = {1: "\u0304", 2: "\u0301", 3: "\u030c", 4: "\u0300"}
    index = candidates[0]
    return unicodedata.normalize(
        "NFC", syllable[: index + 1] + marks[tone] + syllable[index + 1 :]
    )


def parse_cc_cedict(
    registry: dict[str, Any], path: Path, wanted: set[int]
) -> tuple[dict[int, dict[str, Any]], dict[int, set[int]]]:
    acquisition = registry["sources"][CC_CEDICT_ID]["acquisition"]
    with gzip.open(path, "rb") as stream:
        payload = stream.read()
    if sha256_bytes(payload) != acquisition["uncompressed_sha256"]:
        raise RuntimeError("CC-CEDICT uncompressed SHA-256 mismatch")
    if len(payload) != acquisition["uncompressed_bytes"]:
        raise RuntimeError("CC-CEDICT uncompressed byte-length mismatch")
    text = payload.decode("utf-8", errors="strict")

    result: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"simplified": set(), "definitions": [], "pinyin": []}
    )
    inverse: dict[int, set[int]] = defaultdict(set)
    entry_count = 0
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        entry_count += 1
        match = CC_CEDICT_RE.fullmatch(line)
        if not match:
            raise RuntimeError(f"malformed CC-CEDICT row {entry_count}: {line[:120]!r}")
        traditional, simplified, pinyin, definitions_text = match.groups()
        traditional = unicodedata.normalize("NFC", traditional)
        simplified = unicodedata.normalize("NFC", simplified)
        if len(traditional) == 1 and len(simplified) == 1:
            inverse[ord(simplified)].add(ord(traditional))
        if len(traditional) != 1 or ord(traditional) not in wanted:
            continue
        cp = ord(traditional)
        if len(simplified) == 1 and is_han_unified(ord(simplified)):
            result[cp]["simplified"].add(ord(simplified))
        for definition in definitions_text.split("/"):
            normalized = unicodedata.normalize("NFC", definition.strip())
            if normalized and normalized not in result[cp]["definitions"]:
                result[cp]["definitions"].append(normalized)
        tokens = pinyin.split()
        if len(tokens) == 1:
            marked = tone_number_to_mark(tokens[0])
            if marked and marked not in result[cp]["pinyin"]:
                result[cp]["pinyin"].append(marked)
    expected_entries = acquisition["upstream_header"]["entries"]
    if entry_count != expected_entries:
        raise RuntimeError(
            f"CC-CEDICT entry count {entry_count} != pinned header {expected_entries}"
        )
    return result, inverse


def unihan_codepoints(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(match, 16) for match in CODEPOINT_RE.findall(value)]


def parse_hanyu_pinyin(value: str | None) -> list[str]:
    if not value:
        return []
    readings: list[str] = []
    for group in value.split():
        if ":" in group:
            readings.extend(group.split(":", 1)[1].split(","))
    return unique(readings)


def cns_code(unihan: dict[str, str]) -> str:
    for token in unihan.get("kIRG_TSource", "").split():
        if token.startswith("T"):
            return token[1:]
    return ""


def make_gap(field: str, reason: str, detail: str) -> dict[str, str]:
    return {"field": field, "reason": reason, "detail": detail}


def make_conflict(
    field: str,
    resolution: str,
    values: list[dict[str, Any]],
    detail: str,
) -> dict[str, Any]:
    return {
        "field": field,
        "resolution": resolution,
        "values": values,
        "detail": detail,
    }


def build_simplification(
    cp: int,
    unihan: dict[str, str],
    all_variants: dict[int, dict[str, str]],
    cedict: dict[str, Any],
    cedict_inverse: dict[int, set[int]],
    sources: dict[str, list[str]],
    gaps: list[dict[str, str]],
    conflicts: list[dict[str, Any]],
) -> tuple[str | None, dict[str, Any] | None]:
    unihan_values = {
        item
        for item in unihan_codepoints(unihan.get("kSimplifiedVariant"))
        if is_han_unified(item) and not is_forbidden_character(item)
    }
    cedict_values = set(cedict.get("simplified", set()))
    candidate_sets = [values for values in (unihan_values, cedict_values) if values]
    candidates = set().union(*candidate_sets) if candidate_sets else set()
    used_sources: list[str] = []
    if unihan_values:
        used_sources.append(UNIHAN_ID)
    if cedict_values:
        used_sources.append(CC_CEDICT_ID)

    if len(candidates) == 1 and not (
        unihan_values and cedict_values and unihan_values != cedict_values
    ):
        simplified_cp = next(iter(candidates))
        simplified = chr(simplified_cp)
        sources["simplified"] = used_sources
    elif not candidates:
        simplified_cp = None
        simplified = None
        gaps.append(
            make_gap(
                "simplified",
                "not_attested",
                "Neither Unihan kSimplifiedVariant nor an exact one-character CC-CEDICT headword attests a Simplified mapping.",
            )
        )
    else:
        simplified_cp = None
        simplified = None
        gaps.append(
            make_gap(
                "simplified",
                "conflicting_sources",
                "The approved mapping sources do not yield one unambiguous Simplified character.",
            )
        )
        conflict_values: list[dict[str, Any]] = []
        for source_id, values in (
            (UNIHAN_ID, sorted(unihan_values)),
            (CC_CEDICT_ID, sorted(cedict_values)),
        ):
            for value in values:
                conflict_values.append(
                    {"value": codepoint(value), "source_ids": [source_id]}
                )
        conflicts.append(
            make_conflict(
                "simplified",
                "unresolved",
                conflict_values,
                "Multiple or disagreeing Simplified mappings are preserved without selecting one.",
            )
        )

    note: dict[str, Any] | None = None
    if simplified_cp is not None:
        unihan_origins = set(
            unihan_codepoints(
                all_variants.get(simplified_cp, {}).get("kTraditionalVariant")
            )
        )
        cedict_origins = set(cedict_inverse.get(simplified_cp, set()))
        origins = {
            item
            for item in unihan_origins | cedict_origins
            if is_han_unified(item) and not is_forbidden_character(item)
        }
        if len(origins) > 1:
            note = {
                "mapping_type": "many_traditional_to_one_simplified",
                "simplified": codepoint(simplified_cp),
                "traditional_origins": [codepoint(item) for item in sorted(origins)],
            }
            note_sources: list[str] = []
            if unihan_origins:
                note_sources.append(UNIHAN_ID)
            if cedict_origins:
                note_sources.append(CC_CEDICT_ID)
            sources["simplification_note"] = note_sources
    if note is None:
        if simplified_cp is None and candidates:
            note_reason = "conflicting_sources"
            note_detail = (
                "A many-to-one note cannot be computed while the Simplified mapping "
                "itself remains unresolved."
            )
        elif simplified_cp is None:
            note_reason = "not_attested"
            note_detail = (
                "No Simplified mapping is attested, so no many-to-one relationship "
                "can be established."
            )
        else:
            note_reason = "not_attested"
            note_detail = (
                "The approved mapping sources do not attest multiple Traditional "
                "origins for the selected Simplified character."
            )
        gaps.append(make_gap("simplification_note", note_reason, note_detail))
    return simplified, note


def build_variants(unihan: dict[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[int, str]] = set()
    for field, relationship in VARIANT_RELATIONSHIPS.items():
        for cp in unihan_codepoints(unihan.get(field)):
            if not is_han_unified(cp) or is_forbidden_character(cp):
                continue
            key = (cp, field)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "char": chr(cp),
                    "codepoint": codepoint(cp),
                    "relationship": relationship,
                    "source_property": field,
                }
            )
    return rows


def build_radical(unihan: dict[str, str]) -> dict[str, Any]:
    assignments = unihan.get("kRSUnicode", "").split()
    parsed: list[tuple[str, int, int, bool]] = []
    for assignment in assignments:
        match = RS_RE.fullmatch(assignment)
        if match:
            parsed.append(
                (
                    assignment,
                    int(match.group(1)),
                    int(match.group(2)),
                    "'" in assignment,
                )
            )
    if not parsed:
        raise RuntimeError("selected character has no usable Unihan kRSUnicode assignment")
    primary = next((item for item in parsed if not item[3]), parsed[0])
    return {
        "kangxi_number": primary[1],
        "residual_strokes": primary[2],
        "source_assignment": primary[0],
        "additional_assignments": [item[0] for item in parsed if item != primary],
    }


def build_stroke_data(
    moe_count: int,
    unihan: dict[str, str],
    cns_sequences: dict[str, str],
    mmah_count: int | None,
    conflicts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    cns = cns_sequences.get(cns_code(unihan))
    if cns and len(cns) != moe_count:
        variants.append(
            {
                "count": len(cns),
                "region": "TW",
                "convention": "TW-CNS11643 stroke-sequence length",
                "source_id": CNS_ID,
            }
        )
    unihan_counts = [
        int(value) for value in unihan.get("kTotalStrokes", "").split() if value.isdigit()
    ]
    for index, count in enumerate(unihan_counts):
        if count == moe_count:
            continue
        if len(unihan_counts) > 1 and index == 0:
            region = "CN"
            convention = "Unicode IRG kTotalStrokes first value"
        elif len(unihan_counts) > 1:
            region = "TW"
            convention = "Unicode IRG kTotalStrokes Traditional value"
        else:
            region = "und"
            convention = "Unicode IRG kTotalStrokes"
        item = {
            "count": count,
            "region": region,
            "convention": convention,
            "source_id": UNIHAN_ID,
        }
        if item not in variants:
            variants.append(item)
    if mmah_count is not None and mmah_count != moe_count:
        variants.append(
            {
                "count": mmah_count,
                "region": "CN",
                "convention": "Make Me a Hanzi PRC path count",
                "source_id": MMAH_GRAPHICS_ID,
            }
        )
    if variants:
        conflict_values = [
            {"value": moe_count, "source_ids": [MOE_ID]}
        ] + [
            {"value": item["count"], "source_ids": [item["source_id"]]}
            for item in variants
        ]
        conflicts.append(
            make_conflict(
                "total_strokes",
                "tw_canonical_variant_retained",
                conflict_values,
                "The Taiwan MOE frequency-table count remains canonical; differing CNS, Unicode IRG, or PRC path counts remain explicit variants.",
            )
        )
    return variants


def normalize_component_char(
    char: str,
    radical_map: dict[int, int],
    radical_mapping_sources: dict[int, str],
) -> tuple[str, str | None]:
    mapped = radical_map.get(ord(char))
    return (
        (chr(mapped), radical_mapping_sources[ord(char)])
        if mapped is not None
        else (char, None)
    )


def build_decomposition(
    row: dict[str, Any] | None,
    selected: set[int],
    radical_map: dict[int, int],
    radical_mapping_sources: dict[int, str],
    sources: dict[str, list[str]],
    gaps: list[dict[str, str]],
) -> tuple[str | None, list[str] | None]:
    if row is None:
        gaps.extend(
            [
                make_gap(
                    "ids_decomposition",
                    "not_attested",
                    "The pinned Make Me a Hanzi dictionary has no row for this character.",
                ),
                make_gap(
                    "components",
                    "not_attested",
                    "No approved decomposition row is available.",
                ),
            ]
        )
        return None, None
    decomposition = row.get("decomposition")
    if not isinstance(decomposition, str) or not decomposition or "？" in decomposition:
        gaps.extend(
            [
                make_gap(
                    "ids_decomposition",
                    "not_attested",
                    "Make Me a Hanzi marks the decomposition as wholly or partly unknown.",
                ),
                make_gap(
                    "components",
                    "not_attested",
                    "Components are not emitted from an unknown decomposition.",
                ),
            ]
        )
        return None, None

    normalized_chars: list[str] = []
    mapping_source_ids: list[str] = []
    for char in decomposition:
        normalized, mapping_source = normalize_component_char(
            char, radical_map, radical_mapping_sources
        )
        normalized_chars.append(normalized)
        if mapping_source and mapping_source not in mapping_source_ids:
            mapping_source_ids.append(mapping_source)
    normalized_decomposition = unicodedata.normalize("NFC", "".join(normalized_chars))
    forbidden = [
        codepoint(ord(char))
        for char in normalized_decomposition
        if is_forbidden_character(ord(char))
    ]
    if forbidden:
        gaps.extend(
            [
                make_gap(
                    "ids_decomposition",
                    "not_attested",
                    "The sourced IDS contains a forbidden radical-form character with no explicit Unicode equivalent-unified mapping: "
                    + ", ".join(forbidden),
                ),
                make_gap(
                    "components",
                    "not_attested",
                    "Components are not emitted from an IDS that cannot be normalized to unified ideographs.",
                ),
            ]
        )
        return None, None
    sources["ids_decomposition"] = [MMAH_DICTIONARY_ID]
    sources["ids_decomposition"].extend(mapping_source_ids)

    leaves: list[int] = []
    invalid_leaf = False
    for char in normalized_decomposition:
        cp = ord(char)
        if 0x2FF0 <= cp <= 0x2FFF:
            continue
        if not is_han_unified(cp) or is_forbidden_character(cp):
            invalid_leaf = True
            break
        if cp not in leaves:
            leaves.append(cp)
    if invalid_leaf:
        gaps.append(
            make_gap(
                "components",
                "not_attested",
                "The sourced decomposition contains a non-Han or non-resolvable leaf.",
            )
        )
        return normalized_decomposition, None
    outside = [cp for cp in leaves if cp not in selected]
    if outside:
        gaps.append(
            make_gap(
                "components",
                "source_unavailable",
                "Component references outside the Phase 3 top-2,000 set are not emitted as dangling record references: "
                + ", ".join(codepoint(cp) for cp in outside),
            )
        )
        return normalized_decomposition, None
    sources["components"] = [MMAH_DICTIONARY_ID]
    sources["components"].extend(mapping_source_ids)
    return normalized_decomposition, [codepoint(cp) for cp in leaves]


def component_codepoint(
    value: Any,
    radical_map: dict[int, int],
    radical_mapping_sources: dict[int, str],
) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or len(value) != 1:
        return None, None
    normalized, mapping_source = normalize_component_char(
        value, radical_map, radical_mapping_sources
    )
    cp = ord(normalized)
    if not is_han_unified(cp) or is_forbidden_character(cp):
        return None, mapping_source
    return codepoint(cp), mapping_source


def normalize_liushu_hint(
    value: Any,
    radical_map: dict[int, int],
    radical_mapping_sources: dict[int, str],
) -> tuple[str | None, list[str]]:
    """Remove forbidden radical glyphs without inventing semantic replacements."""
    if not isinstance(value, str) or not value.strip():
        return None, []
    result: list[str] = []
    mapping_sources: list[str] = []
    for char in value.strip():
        cp = ord(char)
        if not is_forbidden_character(cp):
            result.append(char)
            continue
        mapped = radical_map.get(cp)
        if mapped is not None and is_han_unified(mapped) and not is_forbidden_character(mapped):
            result.append(chr(mapped))
            source_id = radical_mapping_sources.get(cp)
            if source_id:
                mapping_sources.append(source_id)
        else:
            # U+2E80 has no Unicode equivalent-unified mapping. Preserve its
            # identity losslessly as ASCII instead of guessing a Han character.
            result.append(f"[U+{cp:04X}]")
    return unicodedata.normalize("NFC", "".join(result)), unique(mapping_sources)


def build_liushu(
    row: dict[str, Any] | None,
    radical_map: dict[int, int],
    radical_mapping_sources: dict[int, str],
    sources: dict[str, list[str]],
    gaps: list[dict[str, str]],
) -> dict[str, Any] | None:
    etymology = row.get("etymology") if row else None
    if not isinstance(etymology, dict) or etymology.get("type") not in {
        "pictophonetic",
        "pictographic",
        "ideographic",
    }:
        gaps.append(
            make_gap(
                "liushu_六書",
                "not_attested",
                "Make Me a Hanzi supplies no usable etymology classification.",
            )
        )
        return None
    source_type = etymology["type"]
    normalized_type = "形聲" if source_type == "pictophonetic" else None
    if normalized_type is None:
        gaps.append(
            make_gap(
                "liushu_六書.type",
                "source_unavailable",
                "The source's broad category is preserved but not forced into a more specific traditional 六書 category.",
            )
        )
    semantic, semantic_mapping_source = component_codepoint(
        etymology.get("semantic"), radical_map, radical_mapping_sources
    )
    phonetic, phonetic_mapping_source = component_codepoint(
        etymology.get("phonetic"), radical_map, radical_mapping_sources
    )
    hint, hint_mapping_sources = normalize_liushu_hint(
        etymology.get("hint"), radical_map, radical_mapping_sources
    )
    if source_type == "pictophonetic" and semantic is None:
        gaps.append(
            make_gap(
                "liushu_六書.semantic_component",
                "not_attested",
                "The source does not identify a single resolvable semantic component.",
            )
        )
    elif source_type != "pictophonetic" and semantic is None:
        gaps.append(
            make_gap(
                "liushu_六書.semantic_component",
                "not_attested",
                "The source category does not attest a separate semantic component.",
            )
        )
    if source_type == "pictophonetic" and phonetic is None:
        gaps.append(
            make_gap(
                "liushu_六書.phonetic_component",
                "not_attested",
                "The source does not identify a single resolvable phonetic component.",
            )
        )
    elif source_type != "pictophonetic" and phonetic is None:
        gaps.append(
            make_gap(
                "liushu_六書.phonetic_component",
                "not_attested",
                "The source category does not attest a separate phonetic component.",
            )
        )
    if hint is None:
        gaps.append(
            make_gap(
                "liushu_六書.hint",
                "not_attested",
                "Make Me a Hanzi supplies no explanatory hint for this etymology row.",
            )
        )
    sources["liushu_六書"] = unique(
        [
            MMAH_DICTIONARY_ID,
            semantic_mapping_source or "",
            phonetic_mapping_source or "",
            *hint_mapping_sources,
        ]
    )
    return {
        "source_type": source_type,
        "type": normalized_type,
        "semantic_component": semantic,
        "phonetic_component": phonetic,
        "hint": hint,
    }


def build_pinyin_variants(
    unihan: dict[str, str], cedict: dict[str, Any], canonical: list[str]
) -> list[dict[str, str]]:
    canonical_set = set(canonical)
    variants: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(
        reading: str,
        region: str,
        classification: str,
        source_id: str,
        source_property: str,
    ) -> None:
        reading = unicodedata.normalize("NFC", reading)
        key = (reading, source_id, source_property)
        if not reading or reading in canonical_set or key in seen:
            return
        seen.add(key)
        variants.append(
            {
                "reading": reading,
                "region": region,
                "classification": classification,
                "source_id": source_id,
                "source_property": source_property,
            }
        )

    for reading in parse_hanyu_pinyin(unihan.get("kTGHZ2013")):
        add(reading, "CN", "regional_attestation", UNIHAN_ID, "kTGHZ2013")
    mandarin = unique(unihan.get("kMandarin", "").split())
    for index, reading in enumerate(mandarin):
        is_cn_preference = len(mandarin) > 1 and index == 0
        add(
            reading,
            "CN" if is_cn_preference else "und",
            "regional_preference" if is_cn_preference else "unicode_attestation",
            UNIHAN_ID,
            "kMandarin",
        )
    for reading in parse_hanyu_pinyin(unihan.get("kHanyuPinyin")):
        add(reading, "und", "dictionary_attestation", UNIHAN_ID, "kHanyuPinyin")
    for reading in cedict.get("pinyin", []):
        add(reading, "CN", "dictionary_attestation", CC_CEDICT_ID, "headword_pinyin")
    return variants


def build_readings(
    unihan: dict[str, str],
    cedict: dict[str, Any],
    cns_readings: dict[str, list[str]],
    bopomofo_to_pinyin: dict[str, str],
    sources: dict[str, list[str]],
    gaps: list[dict[str, str]],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    code = cns_code(unihan)
    zhuyin = unique(cns_readings.get(code, []))
    cns_pinyin = unique(
        [bopomofo_to_pinyin[value] for value in zhuyin if value in bopomofo_to_pinyin]
    )
    fallback = unique(
        unihan.get("kMandarin", "").split()
        + parse_hanyu_pinyin(unihan.get("kHanyuPinyin"))
    )
    canonical = cns_pinyin or fallback
    if canonical:
        result["pinyin"] = [
            {
                "reading": reading,
                "context": "primary" if index == 0 else "additional",
                "region": "TW" if cns_pinyin else "und",
                "standard": "TW-CNS11643" if cns_pinyin else "Unicode-kMandarin-fallback",
            }
            for index, reading in enumerate(canonical)
        ]
        sources["readings.pinyin"] = [CNS_ID, UNIHAN_ID] if cns_pinyin else [UNIHAN_ID]
        if not cns_pinyin:
            gaps.append(
                make_gap(
                    "readings.pinyin.tw",
                    "not_attested",
                    "No Taiwan CNS reading is linked through Unihan kIRG_TSource; Unicode reading data is a labeled fallback.",
                )
            )
    else:
        gaps.append(
            make_gap(
                "readings.pinyin",
                "not_attested",
                "Neither Taiwan CNS nor Unihan attests a Mandarin reading.",
            )
        )
    if zhuyin:
        result["zhuyin"] = zhuyin
        sources["readings.zhuyin"] = [CNS_ID, UNIHAN_ID]
    else:
        gaps.append(
            make_gap(
                "readings.zhuyin",
                "not_attested",
                "The CRC-validated CNS phonetic member has no linked row for this character.",
            )
        )

    pinyin_variants = build_pinyin_variants(unihan, cedict, canonical)
    if pinyin_variants:
        result["pinyin_variants"] = pinyin_variants
        sources["readings.pinyin_variants"] = unique(
            [item["source_id"] for item in pinyin_variants]
        )
        prc = unique(
            [item["reading"] for item in pinyin_variants if item["region"] == "CN"]
        )
        if cns_pinyin and prc:
            conflicts.append(
                make_conflict(
                    "readings.pinyin",
                    "tw_canonical_prc_variant_retained",
                    [
                        {"value": cns_pinyin, "source_ids": [CNS_ID, UNIHAN_ID]},
                        {
                            "value": prc,
                            "source_ids": unique(
                                [
                                    item["source_id"]
                                    for item in pinyin_variants
                                    if item["region"] == "CN"
                                ]
                            ),
                        },
                    ],
                    "Taiwan CNS-derived Pinyin is canonical; distinct PRC dictionary readings remain explicit variants.",
                )
            )

    simple_fields = (
        ("jyutping", "kCantonese"),
        ("japanese_on", "kJapaneseOn"),
        ("japanese_kun", "kJapaneseKun"),
        ("korean", "kKorean"),
        ("fanqie", "kFanqie"),
    )
    for target, source_property in simple_fields:
        values = unique(unihan.get(source_property, "").split())
        if values:
            result[target] = values
            sources[f"readings.{target}"] = [UNIHAN_ID]
        else:
            gaps.append(
                make_gap(
                    f"readings.{target}",
                    "not_attested",
                    f"Unihan has no {source_property} value for this character.",
                )
            )
    hangul = unique(
        [token.split(":", 1)[0] for token in unihan.get("kHangul", "").split()]
    )
    if hangul:
        result["hangul"] = hangul
        sources["readings.hangul"] = [UNIHAN_ID]
    else:
        gaps.append(
            make_gap(
                "readings.hangul",
                "not_attested",
                "Unihan has no kHangul value for this character.",
            )
        )
    return result


def build_definitions(
    unihan: dict[str, str], cedict: dict[str, Any]
) -> tuple[list[dict[str, str]] | None, list[str]]:
    result: list[dict[str, str]] = []
    source_ids: list[str] = []
    unihan_gloss = unihan.get("kDefinition")
    if unihan_gloss:
        result.append(
            {
                "gloss": unihan_gloss,
                "lang": "en",
                "register": "modern",
                "source_id": UNIHAN_ID,
            }
        )
        source_ids.append(UNIHAN_ID)
    for gloss in cedict.get("definitions", []):
        item = {
            "gloss": gloss,
            "lang": "en",
            "register": "modern",
            "source_id": CC_CEDICT_ID,
        }
        if item not in result:
            result.append(item)
    if cedict.get("definitions"):
        source_ids.append(CC_CEDICT_ID)
    return (result or None), source_ids


def build_record(
    selection_rank: int,
    row: dict[str, Any],
    corpus_total: int,
    unihan: dict[str, str],
    all_variants: dict[int, dict[str, str]],
    cedict: dict[str, Any],
    cedict_inverse: dict[int, set[int]],
    mmah_dictionary: dict[str, Any] | None,
    mmah_graphics_count: int | None,
    radical_map: dict[int, int],
    radical_mapping_sources: dict[int, str],
    selected_cps: set[int],
    radical_stroke_counts: dict[int, tuple[int, list[str]]],
    cns_readings: dict[str, list[str]],
    bopomofo_to_pinyin: dict[str, str],
    cns_sequences: dict[str, str],
) -> dict[str, Any]:
    char = row["character"]
    cp = ord(char)
    sources: dict[str, list[str]] = {
        "codepoint": [MOE_ID],
        "traditional": [MOE_ID],
        "variants_異體字": [UNIHAN_ID],
        "radical": [UNIHAN_ID],
        "total_strokes": [MOE_ID],
        "total_strokes_standard": [MOE_ID],
        "stroke_count_variants": [CNS_ID, UNIHAN_ID, MMAH_GRAPHICS_ID],
        "frequency": [MOE_ID],
    }
    gaps: list[dict[str, str]] = []
    conflicts: list[dict[str, Any]] = []

    simplified, simplification_note = build_simplification(
        cp,
        unihan,
        all_variants,
        cedict,
        cedict_inverse,
        sources,
        gaps,
        conflicts,
    )
    variants = build_variants(unihan)
    radical = build_radical(unihan)
    stroke_variants = build_stroke_data(
        row["strokes"],
        unihan,
        cns_sequences,
        mmah_graphics_count,
        conflicts,
    )
    decomposition, components = build_decomposition(
        mmah_dictionary,
        selected_cps,
        radical_map,
        radical_mapping_sources,
        sources,
        gaps,
    )
    liushu = build_liushu(
        mmah_dictionary, radical_map, radical_mapping_sources, sources, gaps
    )
    readings = build_readings(
        unihan,
        cedict,
        cns_readings,
        bopomofo_to_pinyin,
        sources,
        gaps,
        conflicts,
    )
    definitions, definition_sources = build_definitions(unihan, cedict)
    if definitions:
        sources["definitions"] = definition_sources
    else:
        gaps.append(
            make_gap(
                "definitions",
                "not_attested",
                "Neither Unihan nor an exact one-character CC-CEDICT entry supplies an English definition.",
            )
        )

    radical_count, radical_count_sources = radical_stroke_counts[
        radical["kangxi_number"]
    ]
    structural_sum = radical_count + radical["residual_strokes"]
    if structural_sum != row["strokes"]:
        conflicts.append(
            make_conflict(
                "radical.total_strokes_equation",
                "recorded_no_value_change",
                [
                    {
                        "value": {
                            "radical_strokes": radical_count,
                            "residual_strokes": radical["residual_strokes"],
                            "sum": structural_sum,
                        },
                        "source_ids": unique([UNIHAN_ID] + radical_count_sources),
                    },
                    {"value": row["strokes"], "source_ids": [MOE_ID]},
                ],
                "The Unihan radical assignment and delivered radical count do not add to the Taiwan MOE total; both values are retained for review.",
            )
        )

    kangxi_values = unique(
        [unihan.get("kIRGKangXi", ""), unihan.get("kKangXi", "")]
    )
    kangxi_citation = kangxi_values[0] if kangxi_values else None
    if kangxi_citation:
        sources["kangxi_citation"] = [UNIHAN_ID]
    else:
        gaps.append(
            make_gap(
                "kangxi_citation",
                "not_attested",
                "Unihan supplies neither kIRGKangXi nor kKangXi for this character.",
            )
        )
    if len(kangxi_values) > 1:
        conflicts.append(
            make_conflict(
                "kangxi_citation",
                "unresolved",
                [
                    {"value": value, "source_ids": [UNIHAN_ID]}
                    for value in kangxi_values
                ],
                "Unihan's two Kangxi citation properties disagree; the first value is displayed and both remain recorded.",
            )
        )

    gaps.extend(
        [
            make_gap(
                "grading.hsk",
                "source_unavailable",
                "No versioned redistribution-approved HSK character-level source passed the Phase 0 audit.",
            ),
            make_gap(
                "grading.tocfl",
                "source_unavailable",
                "No versioned redistribution-approved TOCFL character-level source passed the Phase 0 audit.",
            ),
            make_gap(
                "confusable_with",
                "source_unavailable",
                "No approved curated visual-confusables source passed the Phase 0 audit.",
            ),
        ]
    )

    record = {
        "codepoint": codepoint(cp),
        "traditional": char,
        "simplified": simplified,
        "simplification_note": simplification_note,
        "variants_異體字": variants,
        "radical": radical,
        "total_strokes": row["strokes"],
        "total_strokes_standard": "TW-MOE-1996",
        "stroke_count_variants": stroke_variants,
        "ids_decomposition": decomposition,
        "components": components,
        "liushu_六書": liushu,
        "readings": readings,
        "definitions": definitions,
        "frequency": {
            "rank": row["rank"],
            "selection_rank": selection_rank,
            "corpus_id": MOE_ID,
            "count": row["count"],
            "cumulative_count": row["cumulative_count"],
            "cumulative_percentage": row["cumulative_percentage"],
            "per_million": round(row["count"] / corpus_total * 1_000_000, 6),
            "corpus_total_count": corpus_total,
        },
        "grading": {"hsk": None, "tocfl": None},
        "confusable_with": None,
        "kangxi_citation": kangxi_citation,
        "sources": sources,
        "gaps": gaps,
        "conflicts": conflicts,
    }
    return normalize_tree(record)


def deterministic_record_digest(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    registry = load_registry()
    moe_path = acquired_path(registry, MOE_ID)
    unihan_path = acquired_path(registry, UNIHAN_ID)
    cjk_path = acquired_path(registry, CJK_RADICALS_ID)
    equivalent_path = acquired_path(registry, EQUIVALENT_IDEOGRAPH_ID)
    cns_path = acquired_path(registry, CNS_ID)
    mmah_dictionary_path = acquired_path(registry, MMAH_DICTIONARY_ID)
    mmah_graphics_path = acquired_path(registry, MMAH_GRAPHICS_ID)
    cedict_path = acquired_path(registry, CC_CEDICT_ID)

    selected_rows, corpus_total, exclusions = read_moe_frequency(
        registry, moe_path
    )
    selected_cps = {ord(row["character"]) for row in selected_rows}
    if len(selected_cps) != 2000:
        raise RuntimeError("selected character codepoints are not unique")
    radical_map, _ = parse_cjk_radicals(cjk_path)
    radical_mapping_sources = {cp: CJK_RADICALS_ID for cp in radical_map}
    equivalent_map = parse_equivalent_ideographs(equivalent_path)
    radical_map.update(equivalent_map)
    radical_mapping_sources.update(
        {cp: EQUIVALENT_IDEOGRAPH_ID for cp in equivalent_map}
    )
    unihan, all_variants = parse_unihan(unihan_path, selected_cps)
    missing_unihan = selected_cps - set(unihan)
    if missing_unihan:
        raise RuntimeError(
            "selected characters absent from parsed Unihan: "
            + ", ".join(codepoint(cp) for cp in sorted(missing_unihan))
        )
    cns_readings, bopomofo_to_pinyin, cns_sequences = parse_cns(
        registry, cns_path
    )
    mmah_dictionary = parse_mmah_dictionary(mmah_dictionary_path, selected_cps)
    mmah_graphics = parse_mmah_graphics(mmah_graphics_path, selected_cps)
    cedict, cedict_inverse = parse_cc_cedict(registry, cedict_path, selected_cps)

    radical_stroke_counts: dict[int, tuple[int, list[str]]] = {}
    for number in range(1, 215):
        record = json.loads((ROOT / "radicals" / f"{number}.json").read_text(encoding="utf-8"))
        radical_stroke_counts[number] = (
            record["stroke_count"],
            record["sources"]["stroke_count"],
        )

    CHARACTERS_PATH.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for selection_rank, row in enumerate(selected_rows, start=1):
        cp = ord(row["character"])
        record = build_record(
            selection_rank,
            row,
            corpus_total,
            unihan[cp],
            all_variants,
            cedict.get(cp, {}),
            cedict_inverse,
            mmah_dictionary.get(cp),
            mmah_graphics.get(cp),
            radical_map,
            radical_mapping_sources,
            selected_cps,
            radical_stroke_counts,
            cns_readings,
            bopomofo_to_pinyin,
            cns_sequences,
        )
        output = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        if not unicodedata.is_normalized("NFC", output):
            raise RuntimeError(f"record is not NFC: {record['codepoint']}")
        (CHARACTERS_PATH / f"{record['codepoint']}.json").write_text(
            output, encoding="utf-8"
        )
        records.append(record)

    source_ids = [
        MOE_ID,
        UNIHAN_ID,
        CJK_RADICALS_ID,
        EQUIVALENT_IDEOGRAPH_ID,
        CNS_ID,
        MMAH_DICTIONARY_ID,
        MMAH_GRAPHICS_ID,
        CC_CEDICT_ID,
    ]
    manifest = {
        "phase": 3,
        "generated_at": utc_now(),
        "record_count": len(records),
        "selection_policy": "First 2,000 valid unified Han ideographs in Taiwan MOE 1996 source rank; Traditional primary; no Simplified-corpus backfill.",
        "source_rank_range": [
            records[0]["frequency"]["rank"],
            records[-1]["frequency"]["rank"],
        ],
        "excluded_rows_before_selection_completed": exclusions,
        "corpus_total_count": corpus_total,
        "record_digest_sha256": deterministic_record_digest(records),
        "records_with_conflicts": sum(bool(record["conflicts"]) for record in records),
        "conflict_count": sum(len(record["conflicts"]) for record in records),
        "gap_count": sum(len(record["gaps"]) for record in records),
        "source_acquisitions": {
            source_id: registry["sources"][source_id]["acquisition"]
            for source_id in source_ids
        },
        "builder": "scripts/build_phase3.py",
        "schema": "schema/character.schema.json",
    }
    MANIFEST_PATH.write_text(
        json.dumps(normalize_tree(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"built {len(records)} character records; "
        f"source ranks {manifest['source_rank_range'][0]}–{manifest['source_rank_range'][1]}; "
        f"{manifest['records_with_conflicts']} records flagged"
    )


if __name__ == "__main__":
    main()
