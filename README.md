# Hanzi Project

A Traditional-first Chinese character corpus with structured radical, character,
word, pronunciation, stroke-order, and historical-form data. It is intended for
dictionaries, learning tools, research interfaces, and other projects that need
traceable data rather than a single opaque lookup table.

This 2026-08-11 snapshot passes the structural release suite and the completed
Taiwan-source-first audits for character readings, prioritized word readings,
definitions, simplification conflicts, radical assignments, and published
historical-asset identity gates. Remaining source absences and accepted regional
or structural conflicts are explicit data, not silently filled values. Do not
describe an individual gap or reviewed conflict as independently verified.

## Content verification status

The completed high-risk audit pass established:

- All 2,000 character reading sets are canonicalized to exact Taiwan MOE
  evidence: 1,964 Revised Dictionary matches and 36 exact-codepoint Dictionary
  of Variants adjudications. No character-reading item remains unresolved.
- 11,891 of 13,368 words reproduce exact prioritized Taiwan MOE Pinyin, Zhuyin,
  definitions, and entry IDs. The other 1,477 are absent from both pinned
  official downloads and retain explicit Taiwan-verification/definition gaps.
- All 37 formerly unresolved character simplification conflicts were reviewed
  against the official PRC 2013 table: 21 mappings were selected and 16 remain
  null because the official relationship is sense-, name-, surname-, reading-,
  or usage-dependent.
- Five character radical assignments were corrected to Taiwan CNS values;
  differing Unihan assignments remain visible conflict evidence.
- The 455 weakly identified Commons historical assets are quarantined and 214
  superseded community seal vectors are release-excluded. All 23 cross-radical
  duplicate-hash groups are explicitly annotated.

See [`docs/verification-policy.md`](docs/verification-policy.md) and the
machine-readable evidence under [`metadata/audits/`](metadata/audits/). The
source-level checks are reproducible with the corresponding `scripts/audit_*.py`
programs.

## What is included

| Resource | Coverage |
|---|---:|
| Kangxi radicals | 214 |
| Traditional-primary characters | 2,000 |
| Taiwan MOE-ranked words | 13,368 |
| Release-facing visual assets | 4,421 |
| Stroke-order SVGs | 2,097 |
| Query formats | SQLite, JSONL, Parquet |

The radical records contain 2,000 `example_characters` references: every
top-2,000 character with an eligible ranked `common_words` link, grouped under
its Taiwan CNS radical and ordered by character-frequency rank. This gives
common-character examples for 202 radicals; the other 12 remain explicitly
empty rather than being padded with obscure forms.

The stroke-order library covers all 214 radicals and all 2,000 characters.
There are 2,096 exact source SVGs and one disclosed component reconstruction for
汙 (U+6C59), whose exact codepoint is absent from the pinned source library.

The deterministic release archive is `dist/hanzi-corpus-2026-08-11.zip`; its
current byte length and SHA-256 are recorded outside the payload in
`dist/release-metadata.json` and `dist/SHA256SUMS`. Raw acquisitions, quarantine
files, duplicate aliases, retired vectors, Finder metadata, and Python bytecode
are excluded. The archive includes the canonical JSON plus a query-ready SQLite
database and equivalent relational JSONL and Parquet tables.

## Query-ready distributions

The generated query layer is organized into three physical license profiles:

- `core` — entities, normalized relationships, readings, non-Taiwan-verbatim
  definitions, provenance, and indexed search;
- `verbatim-tw-definitions` — exact Taiwan MOE definition strings isolated from
  ordinary editable definition fields;
- `visual-assets` — asset metadata and the separately manifested image/SVG
  payload.

Start with [`query/README.md`](query/README.md) and
[`query/examples.sql`](query/examples.sql). Build and validate all query formats
with:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-release.txt
.venv/bin/python scripts/build_query_distributions.py
.venv/bin/python scripts/validate_query_distributions.py --rebuild-check
```

Generated databases, columnar files, and release archives are ignored by Git;
they are reproducible release products rather than source files.

Historical radical coverage includes only release-facing source-verified
mappings. Exact duplicate aliases, quarantined files, and retired vectors are
not counted here.

| Form | Radicals represented | Asset files referenced by records |
|---|---:|---:|
| Oracle bone (甲骨文) | 159 / 214 | 159 |
| Bronze script (金文) | 166 / 214 | 166 |
| Shuowen seal script (說文解字) | 211 / 214 | 211 |
| Liushutong (六書通) | 196 / 214 | 1,787 |

An empty historical-form array means that this release did not acquire an
approved matching source asset. It does not mean that the form never existed.

## Data policy

- Traditional characters are primary; Simplified forms are secondary mappings.
- Taiwan evidence has precedence for canonical Pinyin, Zhuyin, and character
  stroke counts. PRC and other regional readings or counts are retained as
  variants or conflicts.
- Many-to-one mappings are flagged. Context-independent conflicts use the
  official PRC 2013 correspondence; context-dependent relationships remain null
  with exact page evidence.
- Every character has an `english_translation`, and every radical has an
  `english_definition`. These are unchanged Unihan `kDefinition` strings, so a
  single string can contain several comma- or semicolon-separated glosses.
- Every character and 11,891 words also expose `definitions_zh_TW`, copied
  verbatim from exact-headword Taiwan MOE dictionary cells with source entry IDs.
- Missing information is explicit. Each record has a `gaps` array explaining
  whether a value was not attested, lacked an approved source, or had conflicting
  evidence.

The 2,000-character selection is based on the Taiwan Ministry of Education's
1996 common-terms survey. It is a historical Taiwan frequency list, not a claim
about contemporary worldwide Chinese usage.

## Repository layout

| Path | Contents |
|---|---|
| `radicals/` | One JSON record per Kangxi radical, named by radical number |
| `characters/` | One JSON record per character, named by Unicode codepoint |
| `words/` | Taiwan MOE word-frequency records, ordered by published rank |
| `assets/stroke-order/` | Ordered-path SVGs for radicals and characters |
| `assets/oracle/` | Oracle-bone reference glyphs |
| `assets/bronze/` | Bronze-script reference glyphs |
| `assets/shuowen_seal/` | Shuowen seal-script vectors and supplemental evidence |
| `assets/liushutong/` | Liushutong reference glyphs |
| `schema/` | JSON Schemas for radicals, characters, words, and stroke assets |
| `query/` | Query schema, examples, migrations, and generated distribution paths |
| `licenses/` | Machine-readable payload profiles and obligation classes |
| `docs/` | User-facing caveats, attribution, validation, and schema policy |
| `metadata/manifests/` | Machine-readable build and release manifests |
| `metadata/audits/` | Detailed source and review evidence |
| `scripts/` | Acquisition, build, integration, and validation scripts |
| `sources.json` | Versioned source registry, constraints, and license metadata |
| `assets/manifest.json` | Asset paths, hashes, provenance, and per-file licenses |

Character filenames use uppercase Unicode notation, such as
`characters/U+6C34.json` for 水. Radical filenames use the Kangxi number, such as
`radicals/85.json`. Word filenames use stable MOE row IDs, such as
`words/moe1996-00001.json`.

References between records use those stable identifiers. For example, a word's
`constituent_chars` contains character codepoints, while a character's
`common_words` contains MOE word IDs and a radical's `example_characters`
contains character codepoints. Asset paths should be read from the record or
`assets/manifest.json`, not inferred from filenames.

## Quick examples

Inspect a character:

```sh
jq '{traditional, simplified, english_translation, definitions_zh_TW, readings, total_strokes}' \
  characters/U+6C34.json
```

Inspect a radical, its common characters, and its historical forms:

```sh
jq '{primary, english_definition, example_characters, stroke_count, historical_forms}' \
  radicals/85.json
```

Inspect the highest-ranked word:

```sh
jq '{traditional, simplified, pinyin, zhuyin, definitions, definitions_zh_TW, frequency}' \
  words/moe1996-00001.json
```

See why a field is missing or unresolved:

```sh
jq '.gaps' characters/U+6C59.json
```

Query the generated SQLite database:

```sh
sqlite3 -readonly query/hanzi.sqlite3 < query/examples.sql
```

Validate a record against its schema with any JSON Schema 2020-12 validator;
the canonical schemas are in `schema/`.

## Documentation

- [`docs/gaps.md`](docs/gaps.md) summarizes known missing and conflicting
  data. Exact explanations remain in each record's `gaps` array.
- [`docs/caveats.md`](docs/caveats.md) explains regional conventions, frequency scope,
  historical assets, stroke order, and other interpretation limits.
- [`docs/validation.md`](docs/validation.md) records the release checks and
  reviewed structural exceptions; field-level audit JSON remains the content
  evidence.
- [`docs/verification-policy.md`](docs/verification-policy.md) defines the content-evidence
  standard and the distinction between verified claims, explicit gaps, and
  accepted conflicts.
- [`docs/source-audit.md`](docs/source-audit.md) explains source acceptance and rejection.
- [`docs/attribution.md`](docs/attribution.md) contains required source attribution and
  redistribution notices.
- [`docs/licensing.md`](docs/licensing.md) explains the query payload profiles.
- [`docs/schema-versioning.md`](docs/schema-versioning.md) defines compatibility
  and migration policy.

## Provenance and licensing

Licensing is source-specific; this repository does not imply one blanket license
for every record and asset. Before redistributing or adapting the corpus:

1. Read [`docs/attribution.md`](docs/attribution.md) and
   [`docs/licensing.md`](docs/licensing.md).
2. Check [`sources.json`](sources.json) for the data source and license.
3. Check [`assets/manifest.json`](assets/manifest.json) for each visual asset's
   creator, source, license, and SHA-256 digest.
4. Use [`licenses/profiles.json`](licenses/profiles.json) and the query database's
   `record_field_sources` table to identify layer- and field-level obligations.

The corpus includes material under the Unicode License v3, CC BY-SA 4.0,
LGPL-3.0-or-later, Taiwan Open Government Data License 1.0, CC0, public-domain
terms, and other asset-specific licenses. Preserve the attribution and
ShareAlike notices that apply to the material you reuse.
