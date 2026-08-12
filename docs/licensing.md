# License profiles and redistribution

The corpus is assembled from independently licensed sources. There is no single
blanket data or asset license. The machine-readable registry is `sources.json`,
per-file visual terms are in `assets/manifest.json`, and required notices are in
`docs/attribution.md`.

`licenses/profiles.json` separates the distributed query payload into three
profiles:

| Profile | Contents | Important handling |
|---|---|---|
| `core` | Radical, character, word, join, reading, definition, provenance, and search tables | Still contains material with source-specific attribution, ShareAlike, copyleft, and reference constraints; inspect field provenance |
| `verbatim-tw-definitions` | Exact Taiwan MOE definition cells | Preserve verbatim; CC BY-ND 3.0 Taiwan and attribution apply |
| `visual-assets` | Asset metadata plus manifested images and stroke-order SVGs | Apply each file's recorded license and attribution |

The profiles are practical payload boundaries, not legal conclusions. In
particular, `core` means “the normal query layer,” not “public domain” or
“unrestricted commercial use.”

## Querying obligations

The SQLite database exposes the same metadata as the JSON files:

```sql
SELECT obligation_class, license_id, entity_type, field_source_references
FROM v_field_license_counts
ORDER BY obligation_class, license_id, entity_type;
```

For individual fields:

```sql
SELECT field_path, source_id, license_id, obligation_class
FROM record_field_sources
WHERE entity_type = 'character' AND entity_id = 'U+99AC'
ORDER BY field_path, source_id;
```

For visual files:

```sql
SELECT asset_id, local_path, source_id, license_id, obligation_class
FROM assets
WHERE codepoint = 'U+99AC'
ORDER BY asset_kind, asset_id;
```

The obligation classes are descriptive groupings:

- `public-domain`
- `attribution`
- `share-alike`
- `no-derivatives`
- `copyleft`
- `conditional`
- `restricted`

Always consult the source's exact license and constraints. A field may cite
multiple sources and therefore carry multiple rows and obligations.

## Taiwan dictionary text

`definitions_zh_TW` remains present in the canonical per-record JSON, but the
query formats remove it from entity `record_json` and publish it only in
`taiwan_definitions`. That physical separation prevents consumers from
accidentally treating verbatim CC BY-ND text as an ordinary editable definition
field. Do not summarize, split, reorder, or normalize those strings when
redistributing them.

This document and the machine-readable profiles are informational and are not
legal advice.
