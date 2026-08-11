# Phase 2 report

Status: **complete and validated**

## Outcome

- Radical records enriched: **214 / 214**
- Definitions populated: **214 / 214**
- Single English display definitions: **214 / 214**
- Defensible Shuowen mappings: **204 / 214**
- License-verified seal-form references: **214 / 214**
- Oracle-bone radical coverage: **169 / 214** (300 original references)
- Bronze radical coverage: **180 / 214** (316 original references)
- 六書通 radical coverage: **204 / 214** (3627 original references)
- Historical originals integrated: **4243**
- Total logical assets, including 214 Shuowen/seal assets: **4457**
- Distinct unchanged physical originals, including the supplemental composite: **4458**
- Kangxi character counts populated and review-flagged: **214 / 214**
- Automated validation: **PASS**

## Completed records and flagged records

- All 214 records carry the pinned Unihan English definition and the pinned English-Wikipedia Kangxi count.
- Counts remain `secondary_source_unverified`; none is presented as verified against an original 1716 scan.
- Wikisource maps 200 radicals by exact heading and four by Unihan `kSemanticVariant` (尢→尣, 巛→川, 彐→彑, 歹→歺).
- Ten radicals have no defensible pinned Shuowen heading mapping: 8, 15, 55–56, 71, 88, 90, 138, 170, 174.
- Those ten records still carry exact-character public-domain seal SVGs, but the images do not change their null Shuowen-heading status.
- No record is missing a seal image. This is image coverage, not a claim that every Kangxi radical is one of Shuowen's 540 section headings.
- Oracle-bone source gaps remain for: 2–4, 6, 8, 13, 16, 28, 41, 52–54, 58, 60, 64–65, 71, 80, 82, 91–92, 95, 97–98, 105, 107, 110, 114, 116, 127, 134, 136, 138–140, 146, 157, 162, 166–167, 171, 174, 179–180, 200.
- Bronze source gaps remain for: 2, 4, 6, 8, 16–17, 35, 54, 58–59, 65, 76, 78, 90–91, 98, 105, 114, 116, 134, 136, 140–141, 146, 162, 170, 174, 176, 179, 183, 188, 191, 208–209.
- 六書通 source gaps remain for: 6, 8, 14, 47, 58, 90, 105, 114, 134, 160.
- Every historical empty array uses `source_unavailable`; none is relabeled `not_attested` without affirmative scholarly evidence that the form did not exist.

## Image-library composition

- Academia Sinica 小學堂 CC0 representatives: **325**.
- Wikimedia Commons public-domain Oracle/bronze/六書通 SVG revisions: **455**.
- CODH 偏類六書通 TE00010 CC BY-SA glyph JPEGs: **125**.
- CODH 偏類六書通 TE00008–21 series CC BY-SA glyph JPEGs: **3338**.
- Existing Shuowen/seal logical assets: **214**; supplemental library assets: **1**.
- Exact-hash historical transport routes: Wayback **34**, plexus/analects-data **398**, earlier seal mirror **197**.
- Commons SVGs are modern vector transcriptions; 小學堂 PNGs are database-rendered palaeographic glyphs; CODH JPEGs are source-published glyph extracts. Each representation type is labeled in its manifest entry.

## New gaps

- `not_attested`: 30
- `source_unavailable`: 517

Historical-form gaps are source/mapping/transport gaps, not assertions that a form never existed. The semantic taxonomy and primary-scan verification gaps remain unchanged.

## Failed or limited source access

- The first Wikisource-embedded Commons route still records 97 HTTP-429 failures as immutable audit history. They are superseded for coverage by the complete numbered series/composite and exact-character routes; no thumbnail or transformed derivative was substituted.
- The Commons index supplied 511 licensed candidates; 455 exact current or historical originals were recovered. The manifest retains 56 still-unrecovered candidate routes and 131 empty index positions.
- Two superseded 500×500 seal PNG previews from the first acquisition attempt are retained only under `quarantine/legacy-unmanifested-seal-previews/`; no radical or manifest entry references them.
- Wikimedia's upload edge rate-limited original downloads. Internet Archive and the pinned plexus/analects-data Git commit were transport only; a file was admitted only on an exact current or uniquely pinned historical Commons SHA-1 match.
- Taiwan's National Central Library rare-book portal was not copied from directly because its image-use and authorization terms do not provide a straightforward public-corpus redistribution grant. The separately public-domain NCL scan on Commons remains approved, but it has no verified per-radical full-page locators in this phase.
- CODH supplies exact-codepoint locators for 196 radicals across 偏類六書通 TE00008–TE00021. The exact volume label and CC BY-SA attribution remain on all 3463 images.
- No single internally complete 1716 Kangxi edition has yet been selected and independently counted, so all secondary counts remain explicitly unverified.

## Judgment calls made in Phase 2

1. Unihan `kDefinition` strings are retained as modern English glosses without semantic rewriting.
2. Shuowen mappings are admitted only for an exact normalized heading or a direct Unihan `kSemanticVariant`; no visual-similarity inference is used.
3. Wikisource editorial/fanqie notes are kept separately in `edition_notes`, rather than merged into the Shuowen entry text.
4. No unsourced semantic-field taxonomy is invented; `semantic_field` is null with an explicit gap in all records.
5. Every Kangxi count is stored with `secondary_source_unverified` and a primary-scan-verification gap.
6. A historical image is admitted only when a free license, unchanged original bytes, immutable hashes, and a record-level mapping all resolve.
7. Exact-character seal images for the ten unmapped Kangxi radicals are kept in `historical_forms` while `shuowen` stays null; visual presence never manufactures a Shuowen-heading mapping.
8. Taiwan 小學堂 is listed first within overlapping Oracle/bronze arrays because the project is Traditional-primary and the source is a Taiwan scholarly database; Commons variants remain alongside it.
9. The complete 小學堂 candidate index preserves all 9,487 radical-to-glyph mappings, while this phase acquires one deterministic source-ordered maximum-size representative for each of the 325 covered radical/form queries. Downloading all 9,331 distinct source glyph images would be a separate multi-hour expansion, not silently implied by the 325 representative files.
10. A mirror file matching an older Commons revision is admitted only when that SHA-1 occurs uniquely in the pinned Commons file history; an already-acquired current revision is never overwritten.
11. 偏類六書通 is kept as a labeled later reorganization of the 閔齊伋/畢弘述 六書通 tradition, not silently identified with the Harvard 1795 edition.

## Sources used

- Unicode Unihan 17.0.0: 214 definitions and four explicit semantic-variant mapping relationships.
- Chinese Wikisource 說文解字: the pinned main page plus 15 volume revisions, 540 parsed headings, and entry text for 204 mapped Kangxi radicals.
- English Wikipedia revision 1362962863: 214 published Kangxi count claims, all retained as secondary and unverified.
- Academia Sinica 小學堂: 9,487 exact-query Oracle/bronze mappings indexed and 325 unchanged maximum-size representative PNGs acquired under CC0.
- Wikimedia Commons Ancient Chinese Characters project: 511 licensed radical candidates audited and 455 exact SVG originals acquired, including exact historical revisions where necessary.
- CODH 篆書字体データセット TE00010: 125 unchanged glyph JPEGs for 14 exact Traditional-primary radicals under CC BY-SA 4.0.
- CODH 篆書字体データセット TE00008–TE00009 and TE00011–TE00021: 3338 unchanged glyph JPEGs covering 196 exact Traditional-primary radicals under CC BY-SA 4.0.
- Internet Archive Wayback Machine, the pinned plexus/analects-data commit, and the earlier seal mirror: byte transport only under exact Commons hash gates.

## Stop boundary

Phase 3 has not begun. Review Phase 2 before any character-level expansion.
