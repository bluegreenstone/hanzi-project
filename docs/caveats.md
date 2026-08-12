# Corpus caveats through Phase 6

## Script and regional precedence

Traditional forms are primary and Simplified forms are secondary. All 2,000
character Pinyin/Zhuyin inventories are canonicalized to exact Taiwan MOE
evidence: 1,964 Revised Dictionary matches and 36 exact-codepoint Dictionary of
Variants adjudications. Exact prioritized Taiwan MOE readings cover 11,891 of
13,368 words. The other 1,477 are absent from both pinned official downloads;
their earlier CC-CEDICT/CNS readings remain provisional and carry exact Taiwan
verification gaps.
Phase 3 character stroke counts use the Taiwan MOE 1996 frequency table's published `筆畫` field;
the Phase 1 radical spine retains its separately validated CNS-first count.
PRC, CNS, Unicode IRG, and Japanese differences are retained as variants or
conflicts rather than discarded.

All 2,000 characters expose a dedicated `english_translation`. It is the
unchanged Unihan `kDefinition` gloss, which may contain several comma- or
semicolon-separated senses rather than one context-specific translation.
CC-CEDICT senses remain separately available in `definitions[]`.

`definitions_zh_TW` is a separate verbatim Taiwan layer. It covers all 2,000
characters and 11,891 words, retaining the complete decoded workbook cell and
source entry ID. The 1,477 dual-dictionary word absences remain null. Because
the MOE workbooks are CC BY-ND, consumers must not silently summarize, split,
reorder, or Unicode-normalize this field. One source string (`串聯`, word record
`moe1996-09926`) intentionally retains compatibility ideographs and is therefore
not NFC; every non-verbatim record field remains NFC-validated.

All 214 radicals also expose a single `english_definition` for compact display.
It is the same unchanged Unihan gloss already retained in the radical's
`definitions[]`; “single” describes the JSON string, not a claim that the
radical has only one possible sense.

Phase 5 uses PRC GF 0023-2020 as a provisional baseline, independent of the
Traditional-first display policy. The ordered paths come from Make Me a Hanzi,
which declares PRC convention but does not claim formal per-character GF
conformance. Every record therefore says `formal_conformance: not_verified`.
Taiwan-first stroke *count* precedence does not silently assert identical stroke
*order*; 6 radicals and 235 characters retain explicit Taiwan/PRC path-count
conflicts.

The generated library contains 2,097 unique SVGs: full 214-radical coverage and
2,000/2,000 character visual coverage. Of these, 2,096 preserve an exact
Make Me a Hanzi row. 汙 (U+6C59), the sole exact-codepoint gap in the pinned path
source, uses an explicitly labeled component reconstruction: strokes 1–3 reuse
the left-side 氵 geometry from the exact 污 row; strokes 4–6 reuse the exact 于
paths with the disclosed transform `matrix(0.65 0 0 0.9 320 0)`. Their order
follows the exact Taiwan CNS11643 sequence `444115`. This fallback is not an
attested or official U+6C59 glyph. A pinned official KanjiVG index audit likewise
contains no exact U+6C59 entry.

Make Me a Hanzi does not provide authoritative per-path stroke-type names.
`stroke_types` is therefore null with a gap on every populated stroke-order
record. Taiwan CNS does publish five general stroke types, but its sequences are
kept separately and are not assigned to PRC path indices without evidence that
the two regional orders align.

## Radical-block characters are display symbols

Each record's primary key is a CJK Unified Ideograph. Characters in the Kangxi
Radicals block (U+2F00–U+2FD5) are compatibility/display symbols and occur only
in `radical_block.char`. They must never be used as character-record keys or
substituted for unified ideographs in joins.

## Han unification and fonts

One unified codepoint may have different Taiwan, Mainland China, Hong Kong, or
Japanese glyph shapes. The public site should set an appropriate HTML `lang`
attribute and use region-specific Noto CJK fonts. A codepoint match does not
guarantee that every regional font renders the preferred Taiwan form.

## Simplification mappings

Traditional-to-Simplified mappings are not always one-to-one. Phase 3 flags 541
records with an attested many-Traditional-to-one-Simplified relationship. All 37
records that had multiple or disagreeing candidates were reviewed against the
official PRC 2013 table: 21 context-independent correspondences are selected,
while 16 sense-, name-, surname-, reading-, or usage-dependent cases keep
`simplified` null. A round trip through a Simplified form must not be assumed to
recover a unique Traditional character.

## Frequency scope

The top 2,000 are historical Taiwan usage ranks from the MOE's 1996 Common Terms
Survey, not a contemporary global-Chinese list. Seven source rows before the
selection cutoff were skipped because they were not single unified Han
ideographs, so delivered source ranks span 1–2007. No Simplified corpus was used
to backfill them.

`radicals.*.example_characters` is a complete grouping within that selected
top-2,000 universe, not a claim to list every character indexed under a radical
in the Kangxi Dictionary. Eligibility also requires at least one exact ranked
`common_words` link. Lists are ordered by character-frequency rank and are not
artificially capped. Twelve radicals have empty lists because no character in
the selected common-use universe qualifies; no rare substitute is inserted.

## IDS, components, and 六書 labels

Make Me a Hanzi supplies 1,840 usable normalized IDS strings and 1,868 etymology
rows for the selected set. Only 485 `components` arrays are emitted because the
referential-integrity rule prohibits dangling component codepoints outside the
top-2,000 corpus; the IDS remains available when valid. Unicode's explicit
equivalent-unified mappings normalize CJK radical-form characters. An IDS with
an unknown marker or an unmapped forbidden radical form is null, never guessed.

The source label `pictophonetic` is normalized to `形聲`. The broader
`pictographic` and `ideographic` labels are preserved as source categories but
are not forced into a narrower traditional 六書 class.

Phase 6 also normalizes CJK Radical Supplement symbols embedded in 29 sourced
六書 hint records through Unicode's pinned equivalent-unified mapping. The one
unmapped symbol, U+2E80, is represented losslessly as the literal ASCII token
`[U+2E80]`; no replacement character is guessed.

## Historical-image identity

Licensing, file hashes, filenames, and source categories do not establish that
an image depicts the claimed character in the claimed historical script. The
content audit therefore distinguishes source integrity from identity
verification. The 455 images from the Commons Ancient Chinese Characters
project that have only community project-table, filename, and category evidence
are quarantined, removed from release-facing records, and excluded from the
package. Another 214 community seal vectors are retained only as retired audit
evidence after exact Academia Sinica replacements or explicit source-query gaps.

Exact duplicate historical files are modeled as 1,676 release-excluded
provenance aliases rather than independent forms. The 23 hash groups reused
across different radicals all carry explicit scholarly cross-identification
annotations. The published historical set has no unannotated duplicate-hash
group and no same-radical duplicate group.

## Release package

`dist/hanzi-corpus-2026-08-11.zip` is the redistributable corpus package. It
contains final records, assets, schemas, provenance, attribution, reports,
manifests, audits, and build scripts. Raw `source-data/`, `quarantine/`, Finder
metadata, and Python bytecode caches are excluded. Rebuilding from raw inputs
therefore requires reacquiring the versions recorded in `sources.json` rather
than relying on the release ZIP alone.

## Radical and total-stroke arithmetic

For 458 characters, the delivered radical's primary stroke count plus the
attested residual count does not equal the MOE total. A common cause is a positional form
such as three-stroke 氵 being indexed under the four-stroke 水 radical. The
records preserve and flag both source values instead of altering the residual or
total to make the equation pass. Separately, 277 characters retain explicit
Taiwan CNS, Unicode IRG, and/or PRC path-count variants.

Taiwan CNS radical assignments are canonical. Five characters differ from the
first Unihan `kRSUnicode` radical; the CNS assignment is delivered and the
Unihan assignment remains in `radical.additional_assignments` and `conflicts[]`.

## Dictionary snapshot and exact word joins

The stable MDBG download page prohibits scripted access, so Phase 3 pins the
CC-CEDICT project's own editor-export snapshot from 2026-08-11 rather than
mislabeling it as the stable 2026-08-10 MDBG release. Phase 3 character fields
use exact one-character headwords. Phase 4 requires an exact NFC Traditional
headword match between a published MOE word row and CC-CEDICT; it does not
convert scripts, segment text, or use approximate matching. This produced
13,368 shared word records and 17,616 character-to-word references. Of the
2,000 characters, 1,423 reached ten eligible words; all shorter lists carry an
explicit gap.

The MOE table contains one-character rows and publishes them as word-frequency
rows. They are retained because the approved selection rule provides no basis
for discarding them. The MOE release does not identify a segmentation tool, so
every word record keeps `segmentation_tool` null with a `source_unavailable`
gap. Exact Concised Dictionary Pinyin, Zhuyin, definitions, and entry IDs are
canonical; the Revised Dictionary fills exact-headword Concised omissions.
Earlier CC-CEDICT/CNS values remain conflict evidence when they differ. The
1,477 words absent from both official downloads retain explicit provisional
reading and definition gaps rather than inferred matches.

## Shuowen 540 versus Kangxi 214

The 540 Shuowen section headings and the 214 Kangxi radicals are different
indexing systems. Phase 2 maps 204 Kangxi primary ideographs to Shuowen headings:
200 exact and four through direct Unihan semantic variants. The other ten remain
unmapped even though exact-character seal images exist for them. An image is not
evidence that the character is a Shuowen section heading.

The superseded seal SVGs are modern vector renderings of historical glyphs, not
facsimile scans, and are release-excluded. Release-facing seal records use 211
exact Traditional-primary Academia Sinica 小學堂 query results; radicals 8, 90,
and 174 carry hashed exact-query gaps. The full unchanged numbered composite is
retained separately as supplemental evidence; no record depends on a crop or
composite locator.

Two superseded 500×500 PNG previews from the first seal attempt are retained
only in `quarantine/legacy-unmanifested-seal-previews/`. They are not delivered
assets and are not referenced by any radical or manifest entry.

## Historical-form coverage and representation

Release-facing seal-image coverage is 211/214. Oracle-bone coverage is 159/214
radicals, bronze coverage is 166/214, and 六書通 coverage is 196/214. Empty arrays are
`source_unavailable` gaps, not scholarly claims that a historical form never
existed. The source tables and transport audit remain visible even when an
alternative source supplies coverage for the same radical.

These are reference glyph assets rather than one uniform facsimile series.
Commons assets are modern vector transcriptions, 小學堂 PNGs are
database-rendered palaeographic glyphs, and CODH JPEGs are source-published
glyph extracts. Their representation type and edition are recorded per asset;
they must not be presented as equivalent photographic evidence.

The 小學堂 candidate index preserves all 9,487 exact-query radical-to-glyph
mappings and 9,331 distinct source glyph codes. Phase 2 stores one deterministic
source-ordered, highest-size representative for each of the 325 covered
radical/form queries, not all 9,331 image files. Thus the delivered library has
full indexed candidate discovery but only representative 小學堂 image-byte
coverage. Acquiring every indexed variant is a separate expansion and must not
be inferred from the representative count.

CODH's fourteen 偏類六書通 volumes TE00008–TE00021 are later radical/stroke
reorganizations of the 閔齊伋/畢弘述 六書通 tradition. All 3,463 admitted
images retain their exact TE volume label and are not silently identified with
the Harvard 1795 edition. The 3,338-image expanded series includes every
source-published glyph for every exact Traditional-primary radical match in the
thirteen newly pinned volumes; TE00010's 125 images are retained separately.

## Kangxi character counts

All 214 count claims come from a pinned English-Wikipedia revision and are
marked `secondary_source_unverified`. They have not yet been independently
counted against one internally complete 1716 Kangxi edition and should not be
presented as primary-source-verified totals.
