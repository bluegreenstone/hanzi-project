#!/usr/bin/env python3
"""Validate query distributions against the canonical corpus records."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_query_distributions as builder  # noqa: E402


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_records(directory: str) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / directory).glob("*.json"))
    ]


def count_lines(path: Path) -> int:
    with path.open("rb") as stream:
        return sum(
            chunk.count(b"\n")
            for chunk in iter(lambda: stream.read(1024 * 1024), b"")
        )


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def expected_counts() -> dict[str, int]:
    radicals = load_records("radicals")
    characters = load_records("characters")
    words = load_records("words")
    source_registry = json.loads(builder.SOURCES_PATH.read_text(encoding="utf-8"))
    profiles = json.loads(builder.PROFILES_PATH.read_text(encoding="utf-8"))
    assets = json.loads(builder.ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
    all_nodes = {
        item["codepoint"] for item in characters
    } | {
        codepoint
        for word in words
        for codepoint in word["constituent_chars"]
    }
    return {
        "sources": len(source_registry["sources"]),
        "license_profiles": len(profiles["profiles"]),
        "character_nodes": len(all_nodes),
        "radicals": len(radicals),
        "characters": len(characters),
        "words": len(words),
        "radical_examples": sum(
            len(item.get("example_characters") or []) for item in radicals
        ),
        "character_components": sum(
            len(item.get("components") or []) for item in characters
        ),
        "character_common_words": sum(
            len(item.get("common_words") or []) for item in characters
        ),
        "word_constituents": sum(len(item["constituent_chars"]) for item in words),
        "taiwan_definitions": sum(
            len(item.get("definitions_zh_TW") or [])
            for item in [*characters, *words]
        ),
        "assets": sum(
            len(assets.get(key, []))
            for key in ("assets", "library_assets", "stroke_order_assets")
        ),
        "search_documents": len(radicals) + len(characters) + len(words),
    }


def validate_sqlite(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    database_path = ROOT / manifest["database"]["path"]
    if not database_path.is_file():
        return [f"missing SQLite database: {database_path.relative_to(ROOT)}"]
    if database_path.stat().st_size != manifest["database"]["bytes"]:
        errors.append("SQLite byte length differs from the query manifest")
    if sha256_path(database_path) != manifest["database"]["sha256"]:
        errors.append("SQLite SHA-256 differs from the query manifest")

    expected = expected_counts()
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            errors.append(f"SQLite integrity_check failed: {integrity}")
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            errors.append(f"SQLite foreign_key_check returned {len(foreign_keys)} rows")
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if user_version != manifest["database"]["sqlite_user_version"]:
            errors.append("SQLite user_version differs from the query manifest")
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]
        if application_id != 1212242505:
            errors.append(f"unexpected SQLite application_id: {application_id}")

        for table_name, expected_count in expected.items():
            actual = connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
            if actual != expected_count:
                errors.append(
                    f"{table_name}: {actual} rows, expected {expected_count}"
                )
        for table_name, expected_count in manifest["row_counts"].items():
            actual = connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
            if actual != expected_count:
                errors.append(
                    f"{table_name}: SQLite count {actual} differs from manifest {expected_count}"
                )

        top_nodes = connection.execute(
            "SELECT COUNT(*) FROM character_nodes WHERE in_top_2000 = 1"
        ).fetchone()[0]
        if top_nodes != 2000:
            errors.append(f"character_nodes has {top_nodes} top-2,000 rows")
        dangling = connection.execute(
            "SELECT COUNT(*) FROM word_constituents AS wc "
            "LEFT JOIN character_nodes AS n USING (codepoint) "
            "WHERE n.codepoint IS NULL"
        ).fetchone()[0]
        if dangling:
            errors.append(f"word_constituents has {dangling} unresolved nodes")

        core_definition_leaks = sum(
            connection.execute(
                f"SELECT COUNT(*) FROM {table_name} "
                "WHERE json_type(record_json, '$.definitions_zh_TW') IS NOT NULL"
            ).fetchone()[0]
            for table_name in ("characters", "words")
        )
        if core_definition_leaks:
            errors.append(
                f"core record_json contains {core_definition_leaks} Taiwan-definition fields"
            )
        provenance_leaks = connection.execute(
            "SELECT COUNT(*) FROM record_field_sources "
            "WHERE field_path = 'definitions_zh_TW' "
            "OR field_path LIKE 'definitions_zh_TW.%'"
        ).fetchone()[0]
        if provenance_leaks:
            errors.append(
                f"core record_field_sources contains {provenance_leaks} Taiwan-definition rows"
            )
        wrong_tw_license = connection.execute(
            "SELECT COUNT(*) FROM taiwan_definitions "
            "WHERE license_id <> 'CC-BY-ND-3.0-TW' OR verbatim <> 1"
        ).fetchone()[0]
        if wrong_tw_license:
            errors.append(
                f"taiwan_definitions has {wrong_tw_license} non-verbatim or mislicensed rows"
            )

        profile_tables = connection.execute(
            "SELECT profile_id, table_name FROM license_profile_tables"
        ).fetchall()
        table_occurrences: dict[str, list[str]] = {}
        for profile_id, table_name in profile_tables:
            table_occurrences.setdefault(table_name, []).append(profile_id)
        expected_tables = set(builder.TABLE_ORDER)
        if set(table_occurrences) != expected_tables:
            errors.append("license profiles do not cover exactly the exported query tables")
        duplicates = {
            table: values
            for table, values in table_occurrences.items()
            if len(values) != 1
        }
        if duplicates:
            errors.append(f"query tables appear in multiple profiles: {duplicates}")

        horse_examples = connection.execute(
            "SELECT traditional FROM v_radical_characters "
            "WHERE kangxi_number = 187 ORDER BY ordinal"
        ).fetchall()
        expected_horse_examples = [
            ("馬",), ("驗",), ("驚",), ("駕",), ("駐",),
            ("駛",), ("驅",), ("騎",), ("馳",),
        ]
        if horse_examples != expected_horse_examples:
            errors.append(f"radical 187 query returned {horse_examples!r}")
        search_rows = connection.execute(
            "SELECT d.entity_type, d.entity_id "
            "FROM search_fts "
            "JOIN search_documents AS d ON d.search_id = search_fts.rowid "
            "WHERE search_fts MATCH '馬'"
        ).fetchall()
        if ("character", "U+99AC") not in search_rows:
            errors.append("FTS lookup for 馬 does not return U+99AC")
    finally:
        connection.close()
    return errors


def validate_columnar(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        import duckdb
    except ImportError:
        return [
            "Parquet validation requires: python -m pip install -r requirements-release.txt"
        ]

    listed = {item["path"]: item for item in manifest["files"]}
    expected_paths: set[str] = set()
    connection = duckdb.connect(":memory:")
    try:
        for table_name, row_count in manifest["row_counts"].items():
            profile_id = next(
                profile_id
                for profile_id, profile in manifest["profiles"].items()
                if table_name in profile["sqlite_tables"]
            )
            jsonl = ROOT / "query" / "jsonl" / profile_id / f"{table_name}.jsonl"
            parquet = ROOT / "query" / "parquet" / profile_id / f"{table_name}.parquet"
            for format_name, path in (("jsonl", jsonl), ("parquet", parquet)):
                relative = str(path.relative_to(ROOT))
                expected_paths.add(relative)
                item = listed.get(relative)
                if item is None:
                    errors.append(f"query manifest omits {relative}")
                    continue
                if not path.is_file():
                    errors.append(f"missing {format_name} file: {relative}")
                    continue
                if path.stat().st_size != item["bytes"]:
                    errors.append(f"{relative}: byte length differs from manifest")
                if sha256_path(path) != item["sha256"]:
                    errors.append(f"{relative}: SHA-256 differs from manifest")
                if item["rows"] != row_count:
                    errors.append(f"{relative}: manifest row count differs")
            if jsonl.is_file() and count_lines(jsonl) != row_count:
                errors.append(f"{jsonl.relative_to(ROOT)}: JSONL line count differs")
            if parquet.is_file():
                actual = connection.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{sql_path(parquet)}')"
                ).fetchone()[0]
                if actual != row_count:
                    errors.append(
                        f"{parquet.relative_to(ROOT)}: {actual} rows, expected {row_count}"
                    )
                if jsonl.is_file() and row_count:
                    first = json.loads(
                        jsonl.open("r", encoding="utf-8").readline()
                    )
                    columns = [
                        row[0]
                        for row in connection.execute(
                            f"DESCRIBE SELECT * FROM read_parquet('{sql_path(parquet)}')"
                        ).fetchall()
                    ]
                    if columns != list(first):
                        errors.append(
                            f"{parquet.relative_to(ROOT)}: columns differ from JSONL"
                        )
    finally:
        connection.close()
    if set(listed) != expected_paths:
        errors.append(
            "query manifest file set differs from the expected JSONL/Parquet table set"
        )
    return errors


def validate(rebuild_check: bool = False) -> list[str]:
    if not builder.MANIFEST_PATH.is_file():
        return ["query/manifest.json is missing; run scripts/build_query_distributions.py"]
    manifest = json.loads(builder.MANIFEST_PATH.read_text(encoding="utf-8"))
    errors = [*validate_sqlite(manifest), *validate_columnar(manifest)]
    if rebuild_check and not errors:
        before = {
            "database": manifest["database"]["sha256"],
            "files": {
                item["path"]: item["sha256"] for item in manifest["files"]
            },
        }
        rebuilt = builder.build()
        after = {
            "database": rebuilt["database"]["sha256"],
            "files": {
                item["path"]: item["sha256"] for item in rebuilt["files"]
            },
        }
        if before != after:
            errors.append("query distributions are not byte-deterministic across rebuilds")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rebuild-check",
        action="store_true",
        help="rebuild all query files and compare their SHA-256 digests",
    )
    args = parser.parse_args()
    errors = validate(rebuild_check=args.rebuild_check)
    if errors:
        print(f"Query distribution validation: FAIL ({len(errors)} errors)")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("Query distribution validation: PASS")


if __name__ == "__main__":
    main()
