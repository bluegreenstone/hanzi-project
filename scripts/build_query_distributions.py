#!/usr/bin/env python3
"""Build deterministic SQLite, JSONL, and Parquet query distributions."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import platform
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
QUERY_ROOT = ROOT / "query"
DATABASE_PATH = QUERY_ROOT / "hanzi.sqlite3"
JSONL_ROOT = QUERY_ROOT / "jsonl"
PARQUET_ROOT = QUERY_ROOT / "parquet"
MANIFEST_PATH = QUERY_ROOT / "manifest.json"
MIGRATIONS_ROOT = QUERY_ROOT / "migrations"
PROFILES_PATH = ROOT / "licenses" / "profiles.json"
SOURCES_PATH = ROOT / "sources.json"
ASSET_MANIFEST_PATH = ROOT / "assets" / "manifest.json"
RELEASE_ID = "hanzi-corpus-2026-08-11"
GENERATED_AT = "2026-08-11T00:00:00Z"

TABLE_ORDER = (
    "metadata",
    "sources",
    "license_obligations",
    "license_profiles",
    "license_profile_tables",
    "character_nodes",
    "radicals",
    "characters",
    "words",
    "radical_examples",
    "character_components",
    "character_common_words",
    "word_constituents",
    "readings",
    "definitions",
    "taiwan_definitions",
    "record_field_sources",
    "assets",
    "search_documents",
)

SORT_KEYS = {
    "metadata": ("key",),
    "sources": ("source_id",),
    "license_obligations": ("obligation_class", "license_id"),
    "license_profiles": ("profile_id",),
    "license_profile_tables": ("profile_id", "ordinal"),
    "character_nodes": ("codepoint",),
    "radicals": ("kangxi_number",),
    "characters": ("selection_rank",),
    "words": ("frequency_rank",),
    "radical_examples": ("kangxi_number", "ordinal"),
    "character_components": ("codepoint", "ordinal"),
    "character_common_words": ("codepoint", "ordinal"),
    "word_constituents": ("word_id", "ordinal"),
    "readings": ("entity_type", "entity_id", "scheme", "ordinal"),
    "definitions": ("entity_type", "entity_id", "ordinal"),
    "taiwan_definitions": ("entity_type", "entity_id", "ordinal"),
    "record_field_sources": (
        "entity_type",
        "entity_id",
        "field_path",
        "source_id",
    ),
    "assets": ("asset_id",),
    "search_documents": ("search_id",),
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_records(directory: str, sort_key: Any) -> list[dict[str, Any]]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / directory).glob("*.json"))
    ]
    return sorted(records, key=sort_key)


def core_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a query copy without the separately packaged Taiwan definitions."""
    result = copy.deepcopy(record)
    result.pop("definitions_zh_TW", None)
    sources = result.get("sources")
    if isinstance(sources, dict):
        for field_path in list(sources):
            if field_path == "definitions_zh_TW" or field_path.startswith(
                "definitions_zh_TW."
            ):
                sources.pop(field_path)
    for collection in ("gaps", "conflicts"):
        values = result.get(collection)
        if isinstance(values, list):
            result[collection] = [
                item
                for item in values
                if not str(item.get("field", "")).startswith("definitions_zh_TW")
            ]
    return result


def join_readings(values: Iterable[Any]) -> str | None:
    readings: list[str] = []
    for value in values:
        if isinstance(value, str):
            reading = value
        elif isinstance(value, dict):
            reading = value.get("reading") or value.get("text")
        else:
            reading = None
        if reading and reading not in readings:
            readings.append(reading)
    return " ".join(readings) or None


def split_characters(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value)


def obligation_index(profiles: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    by_license: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    for obligation_class, definition in profiles["obligation_classes"].items():
        for license_id in definition["license_ids"]:
            key = license_id.casefold()
            if key in by_license:
                raise RuntimeError(f"license appears in multiple classes: {license_id}")
            by_license[key] = obligation_class
            rows.append(
                {
                    "obligation_class": obligation_class,
                    "license_id": license_id,
                    "description": definition["description"],
                }
            )
    return by_license, rows


def classify_license(license_id: str | None, index: dict[str, str]) -> tuple[str, str]:
    canonical = license_id or "NOASSERTION"
    obligation_class = index.get(canonical.casefold())
    if obligation_class is None:
        raise RuntimeError(f"unclassified license: {canonical}")
    return canonical, obligation_class


def reading_rows(
    entity_type: str,
    entity_id: str,
    schemes: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scheme, raw_values in schemes.items():
        values = raw_values if isinstance(raw_values, list) else []
        for ordinal, value in enumerate(values):
            if isinstance(value, str):
                reading = value
                context = region = standard = source_entry_ids = None
            elif isinstance(value, dict):
                reading = value.get("reading") or value.get("text")
                context = value.get("context")
                region = value.get("region")
                standard = value.get("standard")
                source_entry_ids = value.get("source_entry_ids")
            else:
                continue
            if not reading:
                continue
            rows.append(
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "scheme": scheme,
                    "ordinal": ordinal,
                    "reading": reading,
                    "context": context,
                    "region": region,
                    "standard": standard,
                    "source_entry_ids_json": (
                        canonical_json(source_entry_ids)
                        if source_entry_ids is not None
                        else None
                    ),
                }
            )
    return rows


def definition_rows(
    entity_type: str,
    entity_id: str,
    definitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ordinal, definition in enumerate(definitions):
        text = definition.get("gloss") or definition.get("text")
        if not text:
            continue
        indices = definition.get("source_entry_indices")
        rows.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "ordinal": ordinal,
                "language": definition.get("lang") or "und",
                "register": definition.get("register"),
                "definition_text": text,
                "source_id": definition.get("source_id"),
                "source_entry_id": definition.get("source_entry_id"),
                "source_entry_indices_json": (
                    canonical_json(indices) if indices is not None else None
                ),
            }
        )
    return rows


def taiwan_definition_rows(
    entity_type: str,
    entity_id: str,
    definitions: list[dict[str, Any]],
    source_licenses: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ordinal, definition in enumerate(definitions):
        source_id = definition["source_id"]
        rows.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "ordinal": ordinal,
                "language": definition["lang"],
                "register": definition.get("register"),
                "definition_text": definition["text"],
                "source_id": source_id,
                "source_entry_id": str(definition["source_entry_id"]),
                "license_id": source_licenses[source_id],
                "verbatim": 1,
            }
        )
    return rows


def field_source_rows(
    entity_type: str,
    entity_id: str,
    sources: dict[str, list[str]],
    source_licenses: dict[str, str],
    source_obligations: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field_path, source_ids in sorted(sources.items()):
        if field_path == "definitions_zh_TW" or field_path.startswith(
            "definitions_zh_TW."
        ):
            continue
        for source_id in source_ids:
            rows.append(
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "field_path": field_path,
                    "source_id": source_id,
                    "license_id": source_licenses[source_id],
                    "obligation_class": source_obligations[source_id],
                }
            )
    return rows


def source_rows(
    registry: dict[str, Any],
    license_index: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    source_licenses: dict[str, str] = {}
    source_obligations: dict[str, str] = {}
    for source_id, source in sorted(registry["sources"].items()):
        license_data = source.get("license") or {}
        license_id, obligation_class = classify_license(
            license_data.get("id"), license_index
        )
        source_licenses[source_id] = license_id
        source_obligations[source_id] = obligation_class
        rows.append(
            {
                "source_id": source_id,
                "full_name": source.get("full_name") or source_id,
                "version": source.get("version"),
                "status": source.get("status") or "unknown",
                "source_url": source.get("url"),
                "documentation_url": source.get("documentation_url"),
                "license_id": license_id,
                "license_name": license_data.get("name"),
                "license_url": license_data.get("url"),
                "obligation_class": obligation_class,
                "source_json": canonical_json(source),
            }
        )
    return rows, source_licenses, source_obligations


def asset_rows(
    manifest: dict[str, Any],
    license_index: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    collections = (
        ("historical", manifest.get("assets", [])),
        ("library", manifest.get("library_assets", [])),
        ("stroke-order", manifest.get("stroke_order_assets", [])),
    )
    for default_kind, assets in collections:
        for asset in assets:
            license_id, obligation_class = classify_license(
                asset.get("license_id"), license_index
            )
            source_id = asset.get("source_id")
            if source_id is None:
                source_ids = asset.get("source_ids") or []
                if not source_ids:
                    raise RuntimeError(
                        f"asset has no source identifier: {asset.get('asset_id')}"
                    )
                source_id = source_ids[0]
            rows.append(
                {
                    "asset_id": asset["asset_id"],
                    "asset_kind": (
                        asset.get("asset_type")
                        or asset.get("historical_form")
                        or default_kind
                    ),
                    "local_path": asset["local_path"],
                    "source_id": source_id,
                    "license_id": license_id,
                    "obligation_class": obligation_class,
                    "mime_type": asset.get("mime_type"),
                    "sha256": asset["sha256"],
                    "byte_length": asset["bytes"],
                    "kangxi_number": asset.get("kangxi_number"),
                    "codepoint": asset.get("codepoint"),
                    "asset_json": canonical_json(asset),
                }
            )
    return sorted(rows, key=lambda item: item["asset_id"])


def build_rows() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    registry = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    asset_manifest = json.loads(ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
    radicals = load_records("radicals", lambda item: item["kangxi_number"])
    characters = load_records(
        "characters", lambda item: item["frequency"]["selection_rank"]
    )
    words = load_records("words", lambda item: item["frequency"]["rank"])

    license_index, obligation_rows = obligation_index(profiles)
    sources, source_licenses, source_obligations = source_rows(
        registry, license_index
    )

    rows: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLE_ORDER}
    rows["sources"] = sources
    rows["license_obligations"] = obligation_rows
    rows["metadata"] = [
        {"key": "release_id", "value": RELEASE_ID},
        {"key": "query_schema_version", "value": "1.0.0"},
        {"key": "profiles_schema_version", "value": str(profiles["schema_version"])},
        {"key": "radical_count", "value": str(len(radicals))},
        {"key": "character_count", "value": str(len(characters))},
        {"key": "word_count", "value": str(len(words))},
    ]

    for profile_id, profile in sorted(profiles["profiles"].items()):
        rows["license_profiles"].append(
            {
                "profile_id": profile_id,
                "description": profile["description"],
                "jsonl_path": profile["jsonl_path"],
                "parquet_path": profile["parquet_path"],
                "profile_json": canonical_json(profile),
            }
        )
        for ordinal, table_name in enumerate(profile["sqlite_tables"]):
            rows["license_profile_tables"].append(
                {
                    "profile_id": profile_id,
                    "table_name": table_name,
                    "ordinal": ordinal,
                }
            )

    top_character_ids = {item["codepoint"] for item in characters}
    character_node_ids = set(top_character_ids)
    for word in words:
        character_node_ids.update(word["constituent_chars"])
    rows["character_nodes"] = [
        {
            "codepoint": codepoint,
            "character": chr(int(codepoint[2:], 16)),
            "in_top_2000": int(codepoint in top_character_ids),
        }
        for codepoint in sorted(
            character_node_ids, key=lambda value: int(value[2:], 16)
        )
    ]

    for radical in radicals:
        entity_id = str(radical["kangxi_number"])
        rows["radicals"].append(
            {
                "kangxi_number": radical["kangxi_number"],
                "primary_char": radical["primary"]["char"],
                "codepoint": radical["primary"]["codepoint"],
                "radical_char": radical["radical_block"]["char"],
                "stroke_count": radical["stroke_count"],
                "english_definition": radical.get("english_definition"),
                "semantic_field": radical.get("semantic_field"),
                "character_count_in_kangxi": radical.get("character_count_in_kangxi"),
                "character_count_status": radical.get(
                    "character_count_in_kangxi_status"
                ),
                "example_count": len(radical.get("example_characters") or []),
                "record_json": canonical_json(core_record(radical)),
            }
        )
        for ordinal, codepoint in enumerate(radical.get("example_characters") or []):
            rows["radical_examples"].append(
                {
                    "kangxi_number": radical["kangxi_number"],
                    "ordinal": ordinal,
                    "codepoint": codepoint,
                }
            )
        rows["readings"].extend(
            reading_rows("radical", entity_id, radical.get("readings") or {})
        )
        rows["definitions"].extend(
            definition_rows("radical", entity_id, radical.get("definitions") or [])
        )
        rows["record_field_sources"].extend(
            field_source_rows(
                "radical",
                entity_id,
                radical.get("sources") or {},
                source_licenses,
                source_obligations,
            )
        )

    for character in characters:
        entity_id = character["codepoint"]
        frequency = character["frequency"]
        rows["characters"].append(
            {
                "codepoint": entity_id,
                "traditional": character["traditional"],
                "simplified": character.get("simplified"),
                "radical_number": character["radical"]["kangxi_number"],
                "residual_strokes": character["radical"]["residual_strokes"],
                "total_strokes": character["total_strokes"],
                "frequency_rank": frequency["rank"],
                "selection_rank": frequency["selection_rank"],
                "frequency_count": frequency["count"],
                "per_million": frequency["per_million"],
                "english_translation": character.get("english_translation"),
                "kangxi_citation": character.get("kangxi_citation"),
                "ids_decomposition": character.get("ids_decomposition"),
                "common_word_count": len(character.get("common_words") or []),
                "record_json": canonical_json(core_record(character)),
            }
        )
        for ordinal, component in enumerate(character.get("components") or []):
            rows["character_components"].append(
                {
                    "codepoint": entity_id,
                    "ordinal": ordinal,
                    "component_codepoint": component,
                }
            )
        for ordinal, word_id in enumerate(character.get("common_words") or []):
            rows["character_common_words"].append(
                {"codepoint": entity_id, "ordinal": ordinal, "word_id": word_id}
            )
        rows["readings"].extend(
            reading_rows("character", entity_id, character.get("readings") or {})
        )
        rows["definitions"].extend(
            definition_rows("character", entity_id, character.get("definitions") or [])
        )
        rows["taiwan_definitions"].extend(
            taiwan_definition_rows(
                "character",
                entity_id,
                character.get("definitions_zh_TW") or [],
                source_licenses,
            )
        )
        rows["record_field_sources"].extend(
            field_source_rows(
                "character",
                entity_id,
                character.get("sources") or {},
                source_licenses,
                source_obligations,
            )
        )

    for word in words:
        entity_id = word["id"]
        frequency = word["frequency"]
        pinyin = join_readings(word.get("pinyin") or [])
        zhuyin = join_readings(word.get("zhuyin") or [])
        english = " | ".join(
            item["gloss"] for item in word.get("definitions") or [] if item.get("gloss")
        ) or None
        rows["words"].append(
            {
                "word_id": entity_id,
                "traditional": word["traditional"],
                "simplified": word.get("simplified"),
                "frequency_rank": frequency["rank"],
                "frequency_count": frequency["count"],
                "per_million": frequency["per_million"],
                "pinyin_text": pinyin,
                "zhuyin_text": zhuyin,
                "english_definition_text": english,
                "constituent_count": len(word["constituent_chars"]),
                "record_json": canonical_json(core_record(word)),
            }
        )
        for ordinal, codepoint in enumerate(word["constituent_chars"]):
            rows["word_constituents"].append(
                {"word_id": entity_id, "ordinal": ordinal, "codepoint": codepoint}
            )
        rows["readings"].extend(
            reading_rows(
                "word",
                entity_id,
                {"pinyin": word.get("pinyin") or [], "zhuyin": word.get("zhuyin") or []},
            )
        )
        rows["definitions"].extend(
            definition_rows("word", entity_id, word.get("definitions") or [])
        )
        rows["taiwan_definitions"].extend(
            taiwan_definition_rows(
                "word",
                entity_id,
                word.get("definitions_zh_TW") or [],
                source_licenses,
            )
        )
        rows["record_field_sources"].extend(
            field_source_rows(
                "word",
                entity_id,
                word.get("sources") or {},
                source_licenses,
                source_obligations,
            )
        )

    rows["assets"] = asset_rows(asset_manifest, license_index)

    definition_texts: dict[tuple[str, str], list[str]] = defaultdict(list)
    for definition in rows["definitions"]:
        definition_texts[
            (definition["entity_type"], definition["entity_id"])
        ].append(definition["definition_text"])
    search_id = 1
    for radical in rows["radicals"]:
        text = " ".join(
            item
            for item in (
                radical["primary_char"],
                split_characters(radical["primary_char"]),
                radical.get("english_definition") or "",
            )
            if item
        )
        rows["search_documents"].append(
            {
                "search_id": search_id,
                "profile_id": "core",
                "entity_type": "radical",
                "entity_id": str(radical["kangxi_number"]),
                "frequency_rank": None,
                "traditional": radical["primary_char"],
                "simplified": None,
                "pinyin": None,
                "zhuyin": None,
                "english": radical.get("english_definition"),
                "search_text": text,
            }
        )
        search_id += 1
    for character, original in zip(rows["characters"], characters, strict=True):
        pinyin = join_readings((original.get("readings") or {}).get("pinyin") or [])
        zhuyin = join_readings((original.get("readings") or {}).get("zhuyin") or [])
        english_text = " | ".join(
            definition_texts[("character", character["codepoint"])]
        )
        text = " ".join(
            item
            for item in (
                character["traditional"],
                split_characters(character["traditional"]),
                character.get("simplified") or "",
                split_characters(character.get("simplified")),
                pinyin or "",
                zhuyin or "",
                english_text,
            )
            if item
        )
        rows["search_documents"].append(
            {
                "search_id": search_id,
                "profile_id": "core",
                "entity_type": "character",
                "entity_id": character["codepoint"],
                "frequency_rank": character["frequency_rank"],
                "traditional": character["traditional"],
                "simplified": character.get("simplified"),
                "pinyin": pinyin,
                "zhuyin": zhuyin,
                "english": english_text or None,
                "search_text": text,
            }
        )
        search_id += 1
    for word in rows["words"]:
        english_text = " | ".join(definition_texts[("word", word["word_id"])])
        text = " ".join(
            item
            for item in (
                word["traditional"],
                split_characters(word["traditional"]),
                word.get("simplified") or "",
                split_characters(word.get("simplified")),
                word.get("pinyin_text") or "",
                word.get("zhuyin_text") or "",
                english_text,
            )
            if item
        )
        rows["search_documents"].append(
            {
                "search_id": search_id,
                "profile_id": "core",
                "entity_type": "word",
                "entity_id": word["word_id"],
                "frequency_rank": word["frequency_rank"],
                "traditional": word["traditional"],
                "simplified": word.get("simplified"),
                "pinyin": word.get("pinyin_text"),
                "zhuyin": word.get("zhuyin_text"),
                "english": english_text or None,
                "search_text": text,
            }
        )
        search_id += 1

    for table_name in TABLE_ORDER:
        rows[table_name] = sorted(
            rows[table_name],
            key=lambda item, keys=SORT_KEYS[table_name]: tuple(
                item.get(key) if item.get(key) is not None else "" for key in keys
            ),
        )
    return rows, profiles


def apply_schema(connection: sqlite3.Connection) -> None:
    migrations = sorted(MIGRATIONS_ROOT.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not migrations:
        raise RuntimeError("no query schema migrations found")
    for migration in migrations:
        connection.executescript(migration.read_text(encoding="utf-8"))


def insert_rows(
    connection: sqlite3.Connection,
    table_name: str,
    values: list[dict[str, Any]],
) -> None:
    if not values:
        return
    columns = tuple(values[0])
    placeholders = ",".join("?" for _ in columns)
    names = ",".join(f'"{column}"' for column in columns)
    connection.executemany(
        f'INSERT INTO "{table_name}" ({names}) VALUES ({placeholders})',
        (tuple(row[column] for column in columns) for row in values),
    )


def build_sqlite(rows: dict[str, list[dict[str, Any]]]) -> None:
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA page_size = 4096")
        apply_schema(connection)
        for table_name in TABLE_ORDER:
            try:
                insert_rows(connection, table_name, rows[table_name])
            except sqlite3.IntegrityError as exc:
                raise RuntimeError(
                    f"failed to insert query table {table_name}: {exc}"
                ) from exc
        connection.execute("INSERT INTO search_fts(search_fts) VALUES ('rebuild')")
        connection.execute("ANALYZE")
        connection.commit()
        connection.execute("VACUUM")
        connection.commit()
    finally:
        connection.close()


def table_profiles(profiles: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for profile_id, profile in profiles["profiles"].items():
        for table_name in profile["sqlite_tables"]:
            if table_name in result:
                raise RuntimeError(
                    f"table {table_name} appears in profiles {result[table_name]} and {profile_id}"
                )
            result[table_name] = profile_id
    missing = sorted(set(TABLE_ORDER) - set(result))
    if missing:
        raise RuntimeError(f"query tables are absent from license profiles: {missing}")
    return result


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(canonical_json(row))
            stream.write("\n")


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def build_columnar(
    rows: dict[str, list[dict[str, Any]]],
    profiles: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError(
            "Parquet generation requires the pinned release dependencies: "
            "python -m pip install -r requirements-release.txt"
        ) from exc

    if JSONL_ROOT.exists():
        shutil.rmtree(JSONL_ROOT)
    if PARQUET_ROOT.exists():
        shutil.rmtree(PARQUET_ROOT)
    profile_by_table = table_profiles(profiles)
    files: list[dict[str, Any]] = []
    connection = duckdb.connect(":memory:")
    try:
        for table_name in TABLE_ORDER:
            profile_id = profile_by_table[table_name]
            jsonl_path = JSONL_ROOT / profile_id / f"{table_name}.jsonl"
            parquet_path = PARQUET_ROOT / profile_id / f"{table_name}.parquet"
            write_jsonl(rows[table_name], jsonl_path)
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            order = ", ".join(f'"{column}"' for column in SORT_KEYS[table_name])
            connection.execute(
                "COPY (SELECT * FROM read_json_auto('"
                + sql_path(jsonl_path)
                + "', format='newline_delimited') ORDER BY "
                + order
                + ") TO '"
                + sql_path(parquet_path)
                + "' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            for format_name, path in (
                ("jsonl", jsonl_path),
                ("parquet", parquet_path),
            ):
                files.append(
                    {
                        "profile": profile_id,
                        "table": table_name,
                        "format": format_name,
                        "path": str(path.relative_to(ROOT)),
                        "rows": len(rows[table_name]),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_path(path),
                    }
                )
    finally:
        connection.close()
    return files


def input_digest(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item.relative_to(ROOT))):
        relative = str(path.relative_to(ROOT)).encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def build() -> dict[str, Any]:
    QUERY_ROOT.mkdir(parents=True, exist_ok=True)
    rows, profiles = build_rows()
    build_sqlite(rows)
    files = build_columnar(rows, profiles)
    input_paths = [
        *sorted((ROOT / "radicals").glob("*.json")),
        *sorted((ROOT / "characters").glob("*.json")),
        *sorted((ROOT / "words").glob("*.json")),
        SOURCES_PATH,
        ASSET_MANIFEST_PATH,
        PROFILES_PATH,
        Path(__file__).resolve(),
        *sorted(MIGRATIONS_ROOT.glob("[0-9][0-9][0-9][0-9]_*.sql")),
    ]
    manifest = {
        "schema_version": 1,
        "query_schema_version": "1.0.0",
        "release_id": RELEASE_ID,
        "generated_at": GENERATED_AT,
        "builder": "scripts/build_query_distributions.py",
        "tool_versions": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "duckdb": importlib.metadata.version("duckdb"),
        },
        "input_digest_sha256": input_digest(input_paths),
        "database": {
            "path": str(DATABASE_PATH.relative_to(ROOT)),
            "bytes": DATABASE_PATH.stat().st_size,
            "sha256": sha256_path(DATABASE_PATH),
            "sqlite_user_version": 10000,
            "table_count": len(TABLE_ORDER),
        },
        "profiles": profiles["profiles"],
        "row_counts": {name: len(rows[name]) for name in TABLE_ORDER},
        "files": sorted(files, key=lambda item: item["path"]),
    }
    write_json(MANIFEST_PATH, manifest)
    return manifest


def main() -> None:
    manifest = build()
    print(
        "built query distributions: "
        f"{manifest['database']['bytes']:,} SQLite bytes, "
        f"{len(manifest['files'])} JSONL/Parquet files"
    )


if __name__ == "__main__":
    main()
