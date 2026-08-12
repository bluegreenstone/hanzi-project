# Query distributions

Release archives include the corpus in three query formats:

- `hanzi.sqlite3` — the complete normalized query database, including indexed
  joins, source/license metadata, and full-text search;
- `jsonl/<profile>/<table>.jsonl` — one canonical JSON object per relational
  row;
- `parquet/<profile>/<table>.parquet` — the same rows in compressed Parquet.

Generated data files are intentionally ignored by Git. Build them from the
canonical records with:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-release.txt
.venv/bin/python scripts/build_query_distributions.py
.venv/bin/python scripts/validate_query_distributions.py --rebuild-check
```

## SQLite quick start

```sh
sqlite3 -readonly query/hanzi.sqlite3
```

Within SQLite:

```sql
SELECT codepoint, traditional, simplified, total_strokes
FROM characters
WHERE traditional = '水';

SELECT traditional, frequency_rank
FROM v_radical_characters
WHERE kangxi_number = 187
ORDER BY ordinal;

SELECT d.entity_type, d.entity_id, d.traditional, d.frequency_rank
FROM search_fts
JOIN search_documents AS d ON d.search_id = search_fts.rowid
WHERE search_fts MATCH '馬'
ORDER BY d.frequency_rank IS NULL, d.frequency_rank;
```

More examples are in [`examples.sql`](examples.sql).

## Main tables

| Table | Purpose |
|---|---|
| `radicals` | One row per Kangxi radical |
| `character_nodes` | Every codepoint needed by word joins, including nodes outside the top 2,000 |
| `characters` | The 2,000 selected character records |
| `words` | The 13,368 ranked word records |
| `radical_examples` | Ordered radical-to-common-character links |
| `character_components` | In-corpus component links |
| `character_common_words` | Ordered character-to-word links |
| `word_constituents` | Ordered word-to-character-node links |
| `readings` | Normalized reading rows by scheme |
| `definitions` | English and other non-Taiwan-verbatim definitions |
| `taiwan_definitions` | Exact Taiwan MOE definition strings, isolated under their own profile |
| `record_field_sources` | Field-to-source, license, and obligation mappings |
| `assets` | Per-file visual asset provenance and licenses |
| `search_documents` / `search_fts` | Searchable core records and the FTS5 index |

The `record_json` column in each entity table preserves the canonical nested
record except for `definitions_zh_TW`, which is deliberately isolated in
`taiwan_definitions`. The complete original JSON records remain in `radicals/`,
`characters/`, and `words/`.

## License profiles

`core`, `verbatim-tw-definitions`, and `visual-assets` are physical JSONL and
Parquet directories and logical SQLite table groups. Query their membership
through `license_profiles` and `license_profile_tables`.

The core profile is not a claim that every source is permissively licensed. Use
`record_field_sources`, `sources`, and `license_obligations` to inspect the
requirements attached to a field. Read `licenses/profiles.json` and
`docs/attribution.md` before redistribution.

## Schema and determinism

`migrations/0001_initial.sql` defines query schema `1.0.0`. The database stores
that as `PRAGMA user_version = 10000`. The builder writes a manifest containing
input, database, JSONL, and Parquet SHA-256 digests. The validator checks row
equivalence, foreign keys, SQLite integrity, profile separation, example
lookups, and byte-for-byte deterministic rebuilds.
