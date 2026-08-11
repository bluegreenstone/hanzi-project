#!/usr/bin/env python3
"""Build the Phase 1 Kangxi radical spine from pinned source snapshots."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "sources.json"
RADICALS_PATH = ROOT / "radicals"
MANIFEST_PATH = ROOT / "phase1-manifest.json"

UNIHAN_ID = "unicode-unihan-17.0.0"
CJK_RADICALS_ID = "unicode-cjk-radicals-17.0.0"
KANJI_ALIVE_ID = "kanji-alive-radicals-master-audit"
CNS_ID = "cns11643-attributes-2026-08-05"
MMAH_GRAPHICS_ID = "makemeahanzi-graphics-master-audit"

CODEPOINT_RE = re.compile(r"U\+([0-9A-F]{4,6})")
UNIHAN_FIELDS = {
    "kTotalStrokes",
    "kRSUnicode",
    "kIRG_TSource",
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
    "kTraditionalVariant",
}


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
        value = unicodedata.normalize("NFC", value.strip())
        if value and value not in result:
            result.append(value)
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
    expected = acquisition["sha256"]
    if actual != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {source_id}: expected {expected}, got {actual}"
        )
    return path


def parse_cjk_radicals(path: Path) -> tuple[dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    bases: dict[int, dict[str, Any]] = {}
    variants: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        identifier, radical_text, unified_text = [part.strip() for part in line.split(";")]
        number = int(identifier.rstrip("'"))
        row = {
            "identifier": identifier,
            "number": number,
            "radical_cp": int(radical_text, 16) if radical_text else None,
            "unified_cp": int(unified_text, 16),
        }
        if identifier.endswith("'"):
            variants[number].append(row)
        elif number in bases:
            raise RuntimeError(f"duplicate base radical {number}")
        else:
            bases[number] = row
    if set(bases) != set(range(1, 215)):
        raise RuntimeError("CJKRadicals.txt does not contain exactly base radicals 1–214")
    return bases, variants


def parse_unihan(path: Path, wanted: set[int]) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = defaultdict(dict)
    files = (
        "Unihan_IRGSources.txt",
        "Unihan_Readings.txt",
        "Unihan_Variants.txt",
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
                    if cp in wanted and field in UNIHAN_FIELDS:
                        result[cp][field] = unicodedata.normalize("NFC", value)
    return result


def parse_kanji_alive(
    path: Path,
    cjk_bases: dict[int, dict[str, Any]],
    cjk_variants: dict[int, list[dict[str, Any]]],
) -> dict[int, list[dict[str, str]]]:
    radical_cp_to_number: dict[int, int] = {}
    for number, row in cjk_bases.items():
        radical_cp_to_number[row["radical_cp"]] = number
    for number, rows in cjk_variants.items():
        for row in rows:
            if row["radical_cp"] is not None:
                radical_cp_to_number[row["radical_cp"]] = number

    mapped: dict[int, list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            radical = row["Radical"]
            if len(radical) != 1:
                continue
            number = radical_cp_to_number.get(ord(radical))
            if number is not None:
                mapped[number].append(row)
    return mapped


def parse_cns_readings(
    path: Path,
    acquisition: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, str], dict[str, str]]:
    required_members = acquisition["used_members"]
    with zipfile.ZipFile(path) as archive:
        payloads: dict[str, bytes] = {}
        for member, metadata in required_members.items():
            payload = archive.read(member)
            actual = sha256_bytes(payload)
            if actual != metadata["sha256"]:
                raise RuntimeError(
                    f"CNS member SHA-256 mismatch for {member}: "
                    f"expected {metadata['sha256']}, got {actual}"
                )
            payloads[member] = payload

    readings: dict[str, list[str]] = defaultdict(list)
    for line in payloads["CNS_phonetic.txt"].decode("utf-8-sig").splitlines():
        cns_code, value = line.split("\t", 1)
        readings[cns_code].append(unicodedata.normalize("NFC", value))

    bopomofo_to_pinyin: dict[str, str] = {}
    for line in payloads["CNS_pinyin_2.txt"].decode("utf-8-sig").splitlines():
        columns = line.split("\t")
        if len(columns) < 2:
            raise RuntimeError("malformed CNS_pinyin_2.txt row")
        bopomofo_to_pinyin[unicodedata.normalize("NFC", columns[0])] = (
            unicodedata.normalize("NFC", columns[1])
        )

    stroke_sequences: dict[str, str] = {}
    for line in payloads["CNS_strokes_sequence.txt"].decode("utf-8-sig").splitlines():
        cns_code, sequence = line.split("\t", 1)
        if not sequence or any(stroke not in "12345" for stroke in sequence):
            raise RuntimeError("malformed CNS_strokes_sequence.txt row")
        stroke_sequences[cns_code] = sequence
    return readings, bopomofo_to_pinyin, stroke_sequences


def parse_mmah_stroke_counts(path: Path, wanted: set[int]) -> dict[int, int]:
    counts: dict[int, int] = {}
    with path.open(encoding="utf-8") as stream:
        for raw in stream:
            row = json.loads(raw)
            character = row.get("character", "")
            if len(character) != 1 or ord(character) not in wanted:
                continue
            strokes = row.get("strokes")
            medians = row.get("medians")
            if not isinstance(strokes, list) or not strokes:
                raise RuntimeError(f"invalid Make Me a Hanzi strokes for {character}")
            if not isinstance(medians, list) or len(medians) != len(strokes):
                raise RuntimeError(f"stroke/median mismatch for {character}")
            counts[ord(character)] = len(strokes)
    return counts


def parse_hanyu_pinyin(value: str | None) -> list[str]:
    if not value:
        return []
    readings: list[str] = []
    for group in value.split():
        if ":" not in group:
            continue
        readings.extend(group.split(":", 1)[1].split(","))
    return unique(readings)


def build_pinyin_variants(
    unihan: dict[str, str], canonical: list[str]
) -> list[dict[str, Any]]:
    canonical_set = set(canonical)
    evidence: dict[str, dict[str, Any]] = {}

    def add(reading: str, region: str, classification: str, source_property: str) -> None:
        if reading in canonical_set:
            return
        item = evidence.setdefault(
            reading,
            {
                "reading": reading,
                "region": region,
                "classification": classification,
                "source_properties": [],
            },
        )
        if region == "CN":
            item["region"] = "CN"
            item["classification"] = classification
        if source_property not in item["source_properties"]:
            item["source_properties"].append(source_property)

    tghz = parse_hanyu_pinyin(unihan.get("kTGHZ2013"))
    for reading in tghz:
        add(reading, "CN", "regional_attestation", "kTGHZ2013")

    mandarin = unique(unihan.get("kMandarin", "").split())
    for index, reading in enumerate(mandarin):
        is_cn_preference = len(mandarin) > 1 and index == 0
        add(
            reading,
            "CN" if is_cn_preference else "und",
            "regional_preference" if is_cn_preference else "unicode_attestation",
            "kMandarin",
        )
    for reading in parse_hanyu_pinyin(unihan.get("kHanyuPinyin")):
        add(reading, "und", "dictionary_attestation", "kHanyuPinyin")
    return list(evidence.values())


def unihan_variant_codepoints(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(match, 16) for match in CODEPOINT_RE.findall(value)]


def build_variant_rows(
    primary_cp: int,
    cjk_rows: list[dict[str, Any]],
    unihan: dict[str, str],
) -> tuple[list[dict[str, Any]], list[str]]:
    by_cp: dict[int, dict[str, Any]] = {}
    source_ids: list[str] = []

    for row in cjk_rows:
        cp = row["unified_cp"]
        if cp == primary_cp:
            continue
        by_cp[cp] = {
            "char": chr(cp),
            "codepoint": codepoint(cp),
            "role": "orthographic",
            "source_identifier": row["identifier"],
        }
        if CJK_RADICALS_ID not in source_ids:
            source_ids.append(CJK_RADICALS_ID)

    relationships = (
        ("kSimplifiedVariant", "simplified", "simplified"),
        ("kTraditionalVariant", "orthographic", "traditional"),
    )
    for field, role, script in relationships:
        for cp in unihan_variant_codepoints(unihan.get(field)):
            if cp == primary_cp:
                continue
            if cp in by_cp:
                if field == "kSimplifiedVariant":
                    by_cp[cp]["role"] = role
                    by_cp[cp]["script"] = script
                by_cp[cp]["source_identifier"] += f"; {field}"
            else:
                by_cp[cp] = {
                    "char": chr(cp),
                    "codepoint": codepoint(cp),
                    "role": role,
                    "script": script,
                    "source_identifier": field,
                }
            if UNIHAN_ID not in source_ids:
                source_ids.append(UNIHAN_ID)

    variants = [by_cp[cp] for cp in sorted(by_cp)]
    return variants, source_ids


def make_gap(field: str, reason: str, detail: str) -> dict[str, str]:
    return {"field": field, "reason": reason, "detail": detail}


def build_record(
    number: int,
    base: dict[str, Any],
    cjk_variants: list[dict[str, Any]],
    unihan: dict[str, str],
    kanji_rows: list[dict[str, str]],
    cns_readings: dict[str, list[str]],
    bopomofo_to_pinyin: dict[str, str],
    cns_stroke_sequences: dict[str, str],
    mmah_stroke_count: int,
) -> dict[str, Any]:
    primary_cp = base["unified_cp"]
    radical_cp = base["radical_cp"]
    if radical_cp is None:
        raise RuntimeError(f"base radical {number} has no radical-block codepoint")

    total_strokes_values = unihan.get("kTotalStrokes", "").split()
    if not total_strokes_values or not all(value.isdigit() for value in total_strokes_values):
        raise RuntimeError(f"invalid kTotalStrokes for radical {number}")
    unihan_stroke_count = int(total_strokes_values[-1])
    cns_code = unihan.get("kIRG_TSource", "")
    cns_code = cns_code[1:] if cns_code.startswith("T") else ""
    cns_stroke_sequence = cns_stroke_sequences.get(cns_code)
    if cns_stroke_sequence:
        stroke_count = len(cns_stroke_sequence)
        stroke_count_standard = "TW-CNS11643"
        stroke_count_sources = [CNS_ID, UNIHAN_ID]
    else:
        stroke_count = unihan_stroke_count
        stroke_count_standard = "Unicode-IRG-fallback"
        stroke_count_sources = [UNIHAN_ID]

    variants, variant_sources = build_variant_rows(primary_cp, cjk_variants, unihan)
    sources: dict[str, list[str]] = {
        "kangxi_number": [CJK_RADICALS_ID],
        "primary": [CJK_RADICALS_ID],
        "radical_block": [CJK_RADICALS_ID],
        "variants": variant_sources or [CJK_RADICALS_ID, UNIHAN_ID],
        "stroke_count": stroke_count_sources,
        "stroke_count_standard": stroke_count_sources,
    }
    gaps: list[dict[str, str]] = []
    conflicts: list[dict[str, Any]] = []
    if not cns_stroke_sequence:
        gaps.append(
            make_gap(
                "stroke_count.tw",
                "not_attested",
                "CNS11643 has no stroke-sequence row for the Unihan kIRG_TSource code; the canonical count falls back to Unicode IRG kTotalStrokes.",
            )
        )

    stroke_count_variants: list[dict[str, Any]] = []
    if mmah_stroke_count != stroke_count:
        stroke_count_variants.append(
            {
                "count": mmah_stroke_count,
                "region": "CN",
                "convention": "Make Me a Hanzi PRC stroke order",
                "source_id": MMAH_GRAPHICS_ID,
                "note": "Counted from ordered paths; the source does not claim formal GF 0023-2020 conformance.",
            }
        )
    if unihan_stroke_count != stroke_count:
        stroke_count_variants.append(
            {
                "count": unihan_stroke_count,
                "region": "und",
                "convention": "Unicode IRG kTotalStrokes",
                "source_id": UNIHAN_ID,
            }
        )

    names: dict[str, list[str]] = {}
    english_names = unique([row["Meaning"] for row in kanji_rows if row["Meaning"]])
    japanese_names = unique([row["Reading-J"] for row in kanji_rows if row["Reading-J"]])
    if english_names:
        names["en"] = english_names
        sources["names.en"] = [KANJI_ALIVE_ID]
    else:
        gaps.append(
            make_gap(
                "names.en",
                "source_unavailable",
                "No Kanji Alive row maps to this Kangxi radical's Unicode radical codepoint.",
            )
        )
    if japanese_names:
        names["ja"] = japanese_names
        sources["names.ja"] = [KANJI_ALIVE_ID]
    else:
        gaps.append(
            make_gap(
                "names.ja",
                "source_unavailable",
                "No Kanji Alive row maps to this Kangxi radical's Unicode radical codepoint.",
            )
        )
    gaps.extend(
        [
            make_gap(
                "names.zh",
                "source_unavailable",
                "No approved Phase 1 source supplies a systematic Traditional-Chinese colloquial radical name.",
            ),
            make_gap(
                "names.ko",
                "source_unavailable",
                "No approved Phase 1 source supplies a systematic Korean learner-style radical name.",
            ),
        ]
    )

    readings: dict[str, Any] = {}
    zhuyin = unique(cns_readings.get(cns_code, []))
    cns_pinyin = unique(
        [bopomofo_to_pinyin[value] for value in zhuyin if value in bopomofo_to_pinyin]
    )
    fallback_pinyin = unique(
        unihan.get("kMandarin", "").split()
        + parse_hanyu_pinyin(unihan.get("kHanyuPinyin"))
    )
    pinyin = cns_pinyin or fallback_pinyin
    if not pinyin:
        gaps.append(
            make_gap("readings.pinyin", "not_attested", "Neither Unihan nor CNS11643 attests a reading.")
        )
    else:
        readings["pinyin"] = [
            {
                "reading": value,
                "context": "primary" if index == 0 else "additional",
                "region": "TW" if cns_pinyin else "und",
                "standard": "TW-CNS11643" if cns_pinyin else "Unicode-kMandarin-fallback",
            }
            for index, value in enumerate(pinyin)
        ]
        sources["readings.pinyin"] = [CNS_ID, UNIHAN_ID] if cns_pinyin else [UNIHAN_ID]
        if not cns_pinyin:
            gaps.append(
                make_gap(
                    "readings.pinyin.tw",
                    "not_attested",
                    "CNS11643 has no Taiwan reading for this radical; the canonical field falls back to Unicode readings.",
                )
            )

    pinyin_variants = build_pinyin_variants(unihan, pinyin)
    if pinyin_variants:
        readings["pinyin_variants"] = pinyin_variants
        sources["readings.pinyin_variants"] = [UNIHAN_ID]

    if zhuyin:
        readings["zhuyin"] = zhuyin
        sources["readings.zhuyin"] = [CNS_ID, UNIHAN_ID]
    else:
        gaps.append(
            make_gap(
                "readings.zhuyin",
                "not_attested",
                "The CRC-validated CNS phonetic table has no row for the Unihan kIRG_TSource code.",
            )
        )

    simple_readings = (
        ("jyutping", "kCantonese"),
        ("japanese_on", "kJapaneseOn"),
        ("japanese_kun", "kJapaneseKun"),
        ("korean", "kKorean"),
    )
    for target, field in simple_readings:
        values = unique(unihan.get(field, "").split())
        if values:
            readings[target] = values
            sources[f"readings.{target}"] = [UNIHAN_ID]
        else:
            gaps.append(
                make_gap(
                    f"readings.{target}",
                    "not_attested",
                    f"Unihan 17.0.0 has no {field} value for the primary ideograph.",
                )
            )

    hangul = unique(
        [token.split(":", 1)[0] for token in unihan.get("kHangul", "").split()]
    )
    if hangul:
        readings["hangul"] = hangul
        sources["readings.hangul"] = [UNIHAN_ID]
    else:
        gaps.append(
            make_gap(
                "readings.hangul",
                "not_attested",
                "Unihan 17.0.0 has no kHangul value for the primary ideograph.",
            )
        )

    fanqie = unique(unihan.get("kFanqie", "").split())
    if fanqie:
        readings["fanqie"] = [{"text": value} for value in fanqie]
        sources["readings.fanqie"] = [UNIHAN_ID]
    else:
        gaps.append(
            make_gap(
                "readings.fanqie",
                "not_attested",
                "Unihan 17.0.0 has no kFanqie value for the primary ideograph.",
            )
        )

    primary_kanji_rows = [row for row in kanji_rows if row["Radical"] == chr(radical_cp)]
    for row in primary_kanji_rows:
        if row["Stroke#"].isdigit() and int(row["Stroke#"]) != stroke_count:
            stroke_count_variants.append(
                {
                    "count": int(row["Stroke#"]),
                    "region": "JP",
                    "convention": "Kanji Alive Japanese radical convention",
                    "source_id": KANJI_ALIVE_ID,
                }
            )

    sources["stroke_count_variants"] = [
        MMAH_GRAPHICS_ID,
        UNIHAN_ID,
        KANJI_ALIVE_ID,
    ]

    record = {
        "kangxi_number": number,
        "primary": {"char": chr(primary_cp), "codepoint": codepoint(primary_cp)},
        "radical_block": {"char": chr(radical_cp), "codepoint": codepoint(radical_cp)},
        "variants": variants,
        "stroke_count": stroke_count,
        "stroke_count_standard": stroke_count_standard,
        "stroke_count_variants": stroke_count_variants,
        "names": names,
        "readings": readings,
        "sources": sources,
        "gaps": gaps,
        "conflicts": conflicts,
    }
    return normalize_tree(record)


def main() -> None:
    registry = load_registry()
    unihan_path = acquired_path(registry, UNIHAN_ID)
    cjk_path = acquired_path(registry, CJK_RADICALS_ID)
    kanji_path = acquired_path(registry, KANJI_ALIVE_ID)
    cns_path = acquired_path(registry, CNS_ID)
    mmah_graphics_path = acquired_path(registry, MMAH_GRAPHICS_ID)

    cjk_bases, cjk_variants = parse_cjk_radicals(cjk_path)
    primary_cps = {row["unified_cp"] for row in cjk_bases.values()}
    unihan = parse_unihan(unihan_path, primary_cps)
    kanji = parse_kanji_alive(kanji_path, cjk_bases, cjk_variants)
    mmah_stroke_counts = parse_mmah_stroke_counts(mmah_graphics_path, primary_cps)
    if set(mmah_stroke_counts) != primary_cps:
        raise RuntimeError("Make Me a Hanzi does not cover all 214 primary radical ideographs")
    cns_acquisition = registry["sources"][CNS_ID]["acquisition"]
    cns_readings, bopomofo_to_pinyin, cns_stroke_sequences = parse_cns_readings(
        cns_path, cns_acquisition
    )

    records = []
    RADICALS_PATH.mkdir(parents=True, exist_ok=True)
    for number in range(1, 215):
        record = build_record(
            number,
            cjk_bases[number],
            cjk_variants.get(number, []),
            unihan[cjk_bases[number]["unified_cp"]],
            kanji.get(number, []),
            cns_readings,
            bopomofo_to_pinyin,
            cns_stroke_sequences,
            mmah_stroke_counts[cjk_bases[number]["unified_cp"]],
        )
        records.append(record)
        output = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        if not unicodedata.is_normalized("NFC", output):
            raise RuntimeError(f"record {number} is not NFC")
        (RADICALS_PATH / f"{number}.json").write_text(output, encoding="utf-8")

    source_ids = [
        UNIHAN_ID,
        CJK_RADICALS_ID,
        KANJI_ALIVE_ID,
        CNS_ID,
        MMAH_GRAPHICS_ID,
    ]
    manifest = {
        "phase": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "source_acquisitions": {
            source_id: registry["sources"][source_id]["acquisition"]
            for source_id in source_ids
        },
        "builder": "scripts/build_phase1.py",
        "schema": "schema/radical.schema.json",
    }
    MANIFEST_PATH.write_text(
        json.dumps(normalize_tree(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"built {len(records)} radical records")


if __name__ == "__main__":
    main()
