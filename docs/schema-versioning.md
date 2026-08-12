# Schema versioning

The canonical JSON records and the query distribution are versioned separately.
This lets query consumers receive a stable relational interface while corpus
records continue to gain source-backed fields.

## Query database

The current query schema is `1.0.0`, stored as:

```sql
PRAGMA user_version; -- 10000
```

The integer encoding is `major * 10000 + minor * 100 + patch`. SQL migrations
live under `query/migrations/` and are applied in filename order when the
database is built.

- Patch releases may add indexes or correct metadata without changing query
  results.
- Minor releases may add nullable columns, tables, or views.
- Major releases may rename or remove columns, change keys, or alter field
  semantics.

Published migrations are append-only. A release rebuild always starts with a
new database so its contents remain deterministic and fully derivable from the
canonical JSON.

## Stable identifiers

- radicals: integer `kangxi_number`
- characters: uppercase Unicode identifiers such as `U+99AC`
- words: stable source row identifiers such as `moe1996-00001`
- assets: the `asset_id` recorded in `assets/manifest.json`

These identifiers are the supported join keys. Filenames and display strings
must not be substituted for them.

## Manifests

`query/manifest.json` records the relational schema version, input digest, row
counts, output paths, byte lengths, and SHA-256 digests. It is generated rather
than tracked. Release-level payload metadata is stored in
`metadata/manifests/phase6.json` and alongside the release archive under
`dist/`.

Consumers should validate a downloaded archive against `dist/SHA256SUMS`, then
use `query/manifest.json` to validate individual query files.
