# Phase 6 report — validation and packaging

Status: **PASS**

## Outcome

- Radical records: **214**
- Character records: **2,000**
- Word records: **13,368**
- Manifested assets: **6,555**
- Validation checks: **12 / 12 passed**
- Release archive: `dist/hanzi-corpus-2026-08-11.zip`

## Packaging profile

The archive contains the final records, assets, schemas, provenance registry, attribution, caveats, reports, manifests, audit files, and Python build/validation scripts. ZIP entry order, timestamps, permissions, and compression settings are fixed for deterministic output.

Raw `source-data/` acquisitions and `quarantine/` are intentionally excluded from the redistributable corpus. Their acquisition URLs, versions, hashes, and license decisions remain recorded in `sources.json` and the phase manifests.

The package checksum is written beside the archive in `dist/SHA256SUMS`; `dist/release-metadata.json` records its byte length and SHA-256.
