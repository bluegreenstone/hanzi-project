# Hanzi Project

A Traditional-first Chinese character corpus with structured radical, character,
word, pronunciation, stroke-order, and historical-form data. It is intended for
dictionaries, learning tools, research interfaces, and other projects that need
traceable data rather than a single opaque lookup table.

This snapshot was released on 2026-08-11 and passed all release validation
checks.

## What is included

| Resource | Coverage |
|---|---:|
| Kangxi radicals | 214 |
| Traditional-primary characters | 2,000 |
| Taiwan MOE-ranked words | 13,368 |
| Manifested visual assets | 6,555 |
| Stroke-order SVGs | 2,097 |

The stroke-order library covers all 214 radicals and all 2,000 characters.
There are 2,096 exact source SVGs and one disclosed component reconstruction for
汙 (U+6C59), whose exact codepoint is absent from the pinned source library.

Historical radical coverage includes:

| Form | Radicals represented | Asset files referenced by records |
|---|---:|---:|
| Oracle bone (甲骨文) | 169 / 214 | 300 |
| Bronze script (金文) | 180 / 214 | 316 |
| Shuowen seal script (說文解字) | 214 / 214 | 214 |
| Liushutong (六書通) | 204 / 214 | 3,627 |

An empty historical-form array means that this release did not acquire an
approved matching source asset. It does not mean that the form never existed.

## Data policy

- Traditional characters are primary; Simplified forms are secondary mappings.
- Taiwan evidence has precedence for canonical Pinyin, Zhuyin, and character
  stroke counts. PRC and other regional readings or counts are retained as
  variants or conflicts.
- Ambiguous many-to-one and conflicting simplifications are flagged instead of
  being silently resolved.
- Every character has an `english_translation`, and every radical has an
  `english_definition`. These are unchanged Unihan `kDefinition` strings, so a
  single string can contain several comma- or semicolon-separated glosses.
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
| `scripts/` | Acquisition, build, integration, and validation scripts |
| `sources.json` | Versioned source registry, constraints, and license metadata |
| `assets/manifest.json` | Asset paths, hashes, provenance, and per-file licenses |
| `phase*-manifest.json` | Machine-readable build and archival release manifests |

Character filenames use uppercase Unicode notation, such as
`characters/U+6C34.json` for 水. Radical filenames use the Kangxi number, such as
`radicals/85.json`. Word filenames use stable MOE row IDs, such as
`words/moe1996-00001.json`.

References between records use those stable identifiers. For example, a word's
`constituent_chars` contains character codepoints, while a character's
`common_words` contains MOE word IDs. Asset paths should be read from the record
or `assets/manifest.json`, not inferred from filenames.

## Quick examples

Inspect a character:

```sh
jq '{traditional, simplified, english_translation, readings, total_strokes}' \
  characters/U+6C34.json
```

Inspect a radical and its historical forms:

```sh
jq '{primary, english_definition, stroke_count, historical_forms}' \
  radicals/85.json
```

Inspect the highest-ranked word:

```sh
jq '{traditional, simplified, pinyin, zhuyin, definitions, frequency}' \
  words/moe1996-00001.json
```

See why a field is missing or unresolved:

```sh
jq '.gaps' characters/U+6C59.json
```

Validate a record against its schema with any JSON Schema 2020-12 validator;
the canonical schemas are in `schema/`.

## Documentation

- [`gaps-report.md`](gaps-report.md) summarizes known missing and conflicting
  data. Exact explanations remain in each record's `gaps` array.
- [`caveats.md`](caveats.md) explains regional conventions, frequency scope,
  historical assets, stroke order, and other interpretation limits.
- [`validation-report.md`](validation-report.md) records the release checks and
  reviewed exceptions.
- [`source-audit.md`](source-audit.md) explains source acceptance and rejection.
- [`attribution.md`](attribution.md) contains required source attribution and
  redistribution notices.

## Provenance and licensing

Licensing is source-specific; this repository does not imply one blanket license
for every record and asset. Before redistributing or adapting the corpus:

1. Read [`attribution.md`](attribution.md).
2. Check [`sources.json`](sources.json) for the data source and license.
3. Check [`assets/manifest.json`](assets/manifest.json) for each visual asset's
   creator, source, license, and SHA-256 digest.

The corpus includes material under the Unicode License v3, CC BY-SA 4.0,
LGPL-3.0-or-later, Taiwan Open Government Data License 1.0, CC0, public-domain
terms, and other asset-specific licenses. Preserve the attribution and
ShareAlike notices that apply to the material you reuse.
