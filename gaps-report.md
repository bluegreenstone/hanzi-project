# Known data gaps

This report explains where the corpus is incomplete or deliberately leaves a
value unresolved. A gap is not automatically an error: it often means that a
source was checked but did not attest a value, that no redistribution-approved
source was available, or that sources disagreed.

The exact, authoritative explanation is stored beside the affected data in each
record's `gaps` array. This document summarizes those record-level entries so
people can quickly judge whether the corpus fits their use case.

## How gap reasons work

| Reason | Meaning |
|---|---|
| `not_attested` | An approved source was checked but did not supply the value. |
| `source_unavailable` | No approved, versioned, redistributable source was available for the field or record. |
| `conflicting_sources` | Sources supplied incompatible values, so the corpus preserves the conflict instead of choosing silently. |

## Overall totals

| Record type | Records | Records with one or more gaps | Gap entries | Source unavailable | Not attested | Conflicting sources |
|---|---:|---:|---:|---:|---:|---:|
| Radicals | 214 | 214 | 1,489 | 1,381 | 108 | 0 |
| Characters | 2,000 | 2,000 | 16,279 | 12,066 | 4,139 | 74 |
| Words | 13,368 | 13,368 | 28,058 | 27,824 | 216 | 18 |

Every record has at least one gap because several optional fields lack a single
approved source across the entire corpus. This does not mean that every record
is missing its core identity, reading, definition, or frequency data.

## Systematic gaps

These release-wide gaps account for most entries in the totals above.

| Scope | Field | Affected records | Why it is absent |
|---|---|---:|---|
| Characters | `grading.hsk` | 2,000 | No versioned, redistribution-approved character-level HSK source passed the source audit. |
| Characters | `grading.tocfl` | 2,000 | No versioned, redistribution-approved character-level TOCFL source passed the source audit. |
| Characters | `confusable_with` | 2,000 | No approved curated visual-confusables source was available. |
| Characters | `stroke_order.stroke_types` | 2,000 | Ordered paths are available, but the source does not authoritatively name each path's stroke type. |
| Characters | `stroke_order.formal_standard_verification` | 2,000 | The paths follow a PRC convention source, but formal per-character GF 0023-2020 conformance was not established. |
| Radicals | `names.zh` | 214 | No approved source supplied systematic Traditional-Chinese colloquial radical names. |
| Radicals | `names.ko` | 214 | No approved source supplied systematic Korean learner-style radical names. |
| Radicals | `semantic_field` | 214 | No approved source supplied a complete semantic-field taxonomy. |
| Radicals | `character_count_in_kangxi.primary_scan_verification` | 214 | Published counts have not been independently verified against one complete 1716 Kangxi scan. |
| Radicals | Stroke types and formal verification | 214 | The same path-level limitations described for characters apply. |
| Words | `grading.hsk` | 13,368 | No versioned, redistribution-approved word-level HSK source passed the source audit. |
| Words | `segmentation_tool` | 13,368 | The MOE table publishes word rows but does not name a segmentation tool. |

## Radical coverage

Historical-form arrays contain only assets acquired from approved sources. An
empty array is an acquisition gap, not evidence that the historical form never
existed.

| Historical form | Covered radicals | Missing radicals | Referenced assets |
|---|---:|---:|---:|
| Oracle bone (甲骨文) | 169 / 214 (79.0%) | 45 | 300 |
| Bronze script (金文) | 180 / 214 (84.1%) | 34 | 316 |
| Shuowen seal script (說文解字) | 214 / 214 (100%) | 0 | 214 |
| Liushutong (六書通) | 204 / 214 (95.3%) | 10 | 3,627 |

Other radical gaps:

- Ten radicals have exact-character seal images but cannot be proven to map to
  one of the 540 Shuowen section headings; their Shuowen section metadata is
  therefore null.
- Taiwan CNS does not attest Pinyin, Zhuyin, stroke count, or stroke sequence for
  three radicals.
- A small number of Japanese, Korean, Cantonese, and fanqie readings are not
  attested by the approved sources.
- English and Japanese learner names are missing for four radicals each.

## Character coverage

| Field or issue | Affected records | Interpretation |
|---|---:|---|
| `components` | 1,515 | 160 lack an approved decomposition; 1,355 would require components outside the closed 2,000-character set or otherwise cannot satisfy referential integrity. |
| `ids_decomposition` | 160 | The source decomposition is unknown, absent, or contains an unmapped radical-form symbol. |
| Fewer than ten `common_words` | 577 | Only exact Traditional headword matches shared by the MOE ranking and pinned CC-CEDICT snapshot are included. |
| No usable `liushu_六書` classification | 132 | Make Me a Hanzi supplies no usable etymology category for these records. |
| Source category cannot be narrowed to a traditional 六書 type | 710 | The broader source label is preserved without inventing a narrower class. |
| No separate phonetic component attested | 739 | The source category supplies none or does not resolve to one component. |
| No separate semantic component attested | 723 | The source category supplies none or does not resolve to one component. |
| `simplification_note` not attested | 1,441 | Most do not need a special simplification note; absence is recorded explicitly. |
| Conflicting `simplified` mapping | 37 | `simplified` is left null and the candidates are preserved in `conflicts`. |
| Exact source stroke-order SVG unavailable | 1 | 汙 (U+6C59) uses the explicitly labeled six-stroke component reconstruction described below. |

Reading gaps are comparatively small: Hangul is unattested for 65 characters,
fanqie for 48, Japanese kun and Korean readings for 37 each, and Japanese on for
5.

### The 汙 stroke-order exception

汙 (U+6C59) is the only character without an exact codepoint match in the pinned
stroke-path source. Its SVG is openly labeled as a reconstruction: strokes 1–3
reuse the 氵 geometry from 污, and strokes 4–6 reuse the exact 于 paths with a
documented transform. The order follows the Taiwan CNS sequence `444115`. It is
not represented as an attested or official U+6C59 source glyph.

## Word coverage

| Field or issue | Affected records | Interpretation |
|---|---:|---|
| `constituent_chars.local_records` | 1,088 | One or more constituent characters fall outside the closed top-2,000 character set; the word text remains intact. |
| Complete Zhuyin unavailable | 183 | The pinned conversion evidence does not establish a unique complete reading. |
| Partially converted Zhuyin | 33 | At least one syllable lacks unique conversion evidence; the partial result and explanation are retained. |
| Conflicting Simplified form | 18 | Multiple exact CC-CEDICT entries disagree, so no single mapping is selected. |

The word list contains only exact NFC Traditional headword matches between the
Taiwan MOE frequency table and the pinned CC-CEDICT snapshot. It does not infer
matches by converting scripts, segmenting text, or using approximate spelling.

## Finding exact affected records

Inspect every gap on one record:

```sh
jq '.gaps' characters/U+6C59.json
```

List characters with an unresolved Simplified mapping:

```sh
jq -r 'select(any(.gaps[]?; .field == "simplified")) | .traditional' \
  characters/*.json
```

Print a radical's gaps as tab-separated reason, field, and explanation:

```sh
jq -r '.gaps[] | [.reason, .field, .detail] | @tsv' radicals/85.json
```

For visual assets, `assets/manifest.json` also records historical source gaps,
transport failures, rejected candidates, and unacquired files. See
`caveats.md` for interpretation guidance and `source-audit.md` for why candidate
sources were accepted or rejected.
