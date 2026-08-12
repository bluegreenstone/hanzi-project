# Phase 0 source audit

Audit date: 2026-08-10; acquisition registry updated 2026-08-11  
Status: **Phase 0 accepted; Phases 1–6 and high-risk content audits validated**

This memo audits coverage, provenance, access, and redistribution rights for the
Kangxi radical and character corpus. At the Phase 0 checkpoint, no third-party
dataset or image had been downloaded into the project; later pinned acquisitions
are recorded in the appended phase notes. The machine-readable registry is
[`sources.json`](../sources.json).

## Decisions made at the `[DECIDE]` markers

These are judgment calls made during Phase 0 and must remain visible:

1. **Script priority: Traditional-primary.** This is the user's explicit project
   decision. Traditional forms are the canonical character identities and word
   forms. Simplified forms are secondary mappings from Unihan and CC-CEDICT. All
   one-to-many mappings remain reviewable, and no Traditional rank is synthesized
   by converting or splitting a Simplified-only frequency list.
2. **Frequency corpus: Taiwan MOE 1996 Common Terms Survey (八十五年常用語詞調查).**
   Its open-data release supplies Traditional character- and word-frequency CSVs
   under Taiwan OGDL 1.0. The resulting rank is explicitly a historical,
   Taiwan-oriented usage rank based on roughly 1.5 million sampled characters,
   not a timeless or global-Chinese rank. SUBTLEX-CH remains approved only for a
   separately labeled Simplified comparison and cannot select canonical records.
3. **Words per character: 10.** Select the ten highest-frequency Traditional word
   forms in the MOE table that contain the character, then join to CC-CEDICT.
   Fewer than ten is valid when fewer licensed, attested entries survive
   validation.
4. **Segmentation: reuse the MOE-published word-frequency rows.** No local corpus
   segmentation is performed. The source does not disclose a named segmentation
   tool, so `segmentation_tool` must be `null` with a `source_unavailable` gap;
   it must not be guessed. The released word rows and source ranks make selection
   reproducible without resegmenting source texts.
5. **Stroke-order baseline: current PRC GF 0023-2020, provisionally.** It took
   effect on 2021-03-01 and superseded the 1997 standard named in the objective.
   Make Me a Hanzi supplies openly licensed PRC-order paths; differences from
   GF 0023-2020, the 1997 legacy standard, Taiwan MOE/CNS data, or Japanese order
   become `standard_conflicts` rather than silent substitutions. The official
   standard PDF is reference-only because no open redistribution license was
   identified.
6. **Top-2,000 rule:** take the first 2,000 valid Han unified ideographs in the
   MOE source-published character rank. Exclude non-Han rows, compatibility
   ideographs, the Kangxi Radicals block, and the CJK Radicals Supplement; do not
   backfill exclusions from SUBTLEX-CH. Preserve source count, source rank, and
   cumulative percentage. Any duplicate or malformed source rank is a validation
   failure, not a cue to invent a tie-break.
7. **Pinyin and stroke-count conflict precedence: Taiwan first.** Exact Taiwan
   MOE dictionary readings are canonical; CNS11643 remains Taiwan comparison
   evidence. Phase 3 character stroke counts
   use the MOE 1996 table's published `筆畫` value; the Phase 1 radical spine
   retains its separately validated CNS-first count. CNS sequence length, PRC
   path counts from Make Me a Hanzi, Unicode IRG values, and Japanese values
   remain explicit variants. This resolves display precedence without discarding
   source evidence.

Revision note: the script-priority and frequency-source decisions above replace
the initial Simplified-primary/SUBTLEX selection after the user's 2026-08-10
direction that Traditional is primary and Simplified secondary. Decision 7
records the user's subsequent direction that Taiwan MOE-aligned pronunciation
and stroke counts win source conflicts while PRC alternatives remain visible.

## Material specification corrections

- Unicode removed `kRSKangXi` in Unicode 15.1. Current Unihan 17.0 uses
  `kRSUnicode` for radical/residual-stroke assignments. Phase 1 should use
  `kRSUnicode`; resurrecting the removed property from an older release would mix
  incompatible Unihan versions.
- `CJKRadicals.txt`, not Unihan, is the authoritative machine-readable map from
  radical number to the Kangxi Radicals block codepoint and corresponding unified
  ideograph. This is a narrow, documented exception to “structural fields from
  Unihan only.” All three files are Unicode data under the same Unicode-3.0
  license family.
- The objective's PRC 1997 stroke-order option is no longer current. The audit
  recommends GF 0023-2020 while retaining the 1997 publication as a named legacy
  comparison source.
- A historical-form “glyph asset” cannot be a cropped derivative because the
  asset rules prohibit cropping. Store the original full-resolution page plus
  page number and a non-destructive bounding-box locator in manifest metadata.
  The later JSON Schema must allow that locator.

## Approved source set

| Source ID | What it can populate | License gate and important limits |
|---|---|---|
| `unicode-unihan-17.0.0` | Radical assignment, residual and total strokes, readings, definitions, variants, Kangxi citations | Approved, Unicode-3.0. Properties are incomplete; preserve dual Hans/Hant stroke counts and all conflicts. |
| `unicode-cjk-radicals-17.0.0` | Radical number, radical-block codepoint, unified primary ideograph | Approved, Unicode-3.0. Identity mapping only; no colloquial names or positions. |
| `unicode-equivalent-unified-ideograph-17.0.0` | Explicit equivalent-unified mappings for residual CJK radical-form characters in IDS | Approved, Unicode-3.0. Normalize only exact `Equivalent_Unified_Ideograph` mappings. |
| `unicode-cldr-48.2` | Reproducible Pinyin-to-Bopomofo conversion and validation | Approved, Unicode-3.0. Conversion does not invent lexical readings or tone sandhi. |
| `cc-cedict-editor-2026-08-11` | Trad/simp headwords, pinyin, English definitions, word records | Approved, CC BY-SA 4.0. Pinned editor snapshot; publish attribution/ShareAlike notices. |
| `moe-tw-common-terms-1996` | Canonical top-2,000 selection, Traditional character frequency, Traditional word frequency, common-word ranking | Approved, Taiwan OGDL 1.0. Historical and Taiwan-specific; preserve the published ranks and attribution. |
| `moe-tw-concised-dictionary-2014-20260626` | First-priority Taiwan word readings and definitions; character definitions | Approved for verbatim Pinyin/Zhuyin/definition-cell evidence under CC BY-ND 3.0 Taiwan. Exact Traditional headwords only; decoded cells remain otherwise unchanged, entry IDs and attribution are retained, and differing CC-CEDICT/CNS readings remain labeled comparison evidence. |
| `moe-tw-revised-dictionary-2015-20260625` | Character readings and second-priority exact word readings/definitions | Approved for verbatim Pinyin/Zhuyin/definition-cell evidence under CC BY-ND 3.0 Taiwan. Used for words only after an exact Concised miss. |
| `prc-standard-characters-2013` | Official adjudication of conflicting Simplified mappings | Approved as verification-only evidence under the PRC MOE site terms. The page, ZIP, PDF, page images, and derived glyphs are excluded from release artifacts. |
| `subtlex-ch-2010` | Separately labeled Simplified character/word frequency comparison | Approved, CC BY 4.0. Simplified, subtitle-based, and dated; never populate or alter the canonical Traditional rank. |
| `makemeahanzi-dictionary-master-audit` | IDS-like decompositions, components, radical, partial etymology/semantic/phonetic components | Approved, LGPL-3.0-or-later. Pin a commit; unknown IDS markers become gaps; do not over-map its three etymology classes to 六書. |
| `makemeahanzi-graphics-master-audit` | Ordered SVG paths and medians under PRC conventions | Approved, Arphic Public License. Generated/modified SVGs need notices and same-license source availability; formal GF 0023 conformance is not guaranteed. |
| `cns11643-attributes-2026-08-05` | Taiwan Zhuyin/Pinyin comparisons, canonical character radical assignments, and stroke-sequence counts; later components and stroke-order attributes | Approved, Taiwan OGDL 1.0. A clean reacquisition passes full-archive CRC; all four used members and the documentation member are independently hashed. |
| `kanji-alive-radicals-master-audit` | Japanese radical names, meanings, readings, variants, and positions | Approved, CC BY 4.0. Enrichment only, never PRC structural authority. |
| `zhwikisource-shuowen-2026-08-10` | 說文 entry text and its 540 radical headings | Approved, CC BY-SA 4.0. Pin revisions; do not conflate later editorial material with the original work. |
| `commons-shuowen-ncl-00915` | Full-page Shuowen seal-form images | Approved public-domain scan. Preserve original pages and dimensions; no crop or lossy re-encode. |
| `commons-liushutong-harvard-1795` | Full-page 六書通 forms | Approved public-domain scans. This is Min Qiji's 六書通, not Yang Huan's 六書統. |
| `commons-kangxi-dictionary-1716` | Original Kangxi pages, citation audits, evidence for per-radical counts | Approved only for individually verified public-domain scan files. Use one complete edition for counts. |
| `enwiki-kangxi-radicals-2026-08-10` | Learner glosses/names, variants, and secondary count claims | Approved, CC BY-SA 4.0. Pin a revision and cross-check structure/counts against primary sources. |

The two PRC stroke-order publications are registered as `reference_only`. Their
standard identifiers and supersession relationship can be cited, but their PDFs
or extracted tables cannot be redistributed under the present audit.

## Field coverage

### Radical records

| Field group | Planned source(s) | Coverage assessment |
|---|---|---|
| Identity and codepoints | Unicode CJKRadicals 17.0 | Complete for 1–214. |
| Structural radical/strokes | CNS11643 stroke sequences; Unihan 17.0 `kRSUnicode` and `kTotalStrokes`; Make Me a Hanzi comparison | CNS sequence length is canonical under the Taiwan-first policy. Unicode IRG and PRC-convention path-count differences remain explicit variants. |
| Variants and positions | CJKRadicals, Kanji alive, pinned Wikipedia revision | Partial; roles/positions need source agreement. |
| Names and readings | CNS11643, Unihan (including PRC `kTGHZ2013`), Kanji Alive, CLDR, Wikipedia | CNS Pinyin is canonical; PRC and other Unihan attestations remain explicit variants. Jyutping/fanqie and Japanese are viable where attested; Korean colloquial labels remain weak. |
| Definitions | Unihan and CC-CEDICT | Partial but licensed; null where absent. |
| Shuowen text and seal form | Chinese Wikisource plus NCL public-domain scan | Viable with page/revision-level provenance; the 540→214 mapping is not assumed. |
| 六書通 forms | Harvard-Yenching 1795 public-domain scans on Commons | Viable, with full-page assets and page locators. |
| Oracle-bone and bronze forms | Phase 0 found no approved systematic source | Historical finding superseded by the Phase 2 Oracle/bronze/六書通 acquisition addendum below. |
| Kangxi character count | One selected 1716 Kangxi scan, with Wikipedia only as a cross-check | Possible but review-heavy; OCR alone is not authoritative. |
| Example characters | Derived from the MOE Traditional rank joined to Unihan radical assignments | Viable and reproducible. |
| Stroke order | Make Me a Hanzi graphics, audited against GF 0023-2020; CNS as regional conflict source | Good for covered characters; formal-standard and rare-radical gaps remain possible. |

### Character records

| Field group | Planned source(s) | Coverage assessment |
|---|---|---|
| Trad/simp and variants | Unihan plus CC-CEDICT; official PRC 2013 table for conflict adjudication | Strong; all 37 conflicting candidates reviewed, with 21 selected and 16 context-dependent nulls. |
| Radical and residual strokes; total strokes | CNS radical canonical; Unihan residual and comparison assignment; MOE 1996 `筆畫` canonical; CNS sequence length, Unihan `kTotalStrokes`, and Make Me a Hanzi comparison | Complete for the selected set. Never use the removed `kRSKangXi`; retain all assignment/count disagreements. |
| IDS and components | Make Me a Hanzi dictionary; CJKVI remains quarantined | Good for common characters, but unknown markers become gaps. |
| 六書 type and semantic/phonetic components | Make Me a Hanzi etymology fields | Partial; do not claim a precise traditional category when the source is broader. |
| Pinyin, Jyutping, Korean/Japanese readings | Taiwan MOE Revised/Variants canonical for Mandarin; Unihan and CC-CEDICT for labeled comparisons/other languages | All 2,000 Mandarin inventories adjudicated; preserve displaced readings as conflicts. |
| Zhuyin | Taiwan MOE Revised/Variants canonical; CNS11643 comparison | Complete and paired to the same exact MOE evidence as Pinyin. |
| Definitions | Verbatim Taiwan MOE Concised definitions plus Unihan/CC-CEDICT English glosses | Exact Taiwan definitions cover all 2,000 characters. |
| Frequency | Taiwan MOE 1996 Common Terms Survey | Complete for the selected top 2,000 by construction; historical and Taiwan-specific. |
| Grading | No approved HSK/TOCFL source | Blocked. |
| Confusables | No approved curated source | Blocked. |
| Common words | MOE Traditional word-frequency ranking joined to CC-CEDICT | Viable; N=10 maximum, not a promise of ten. |
| Stroke order | Make Me a Hanzi graphics | Likely high coverage; validate path count and standard conflicts. |
| Kangxi citation | Unihan `kIRGKangXi`/`kKangXi`, audited against a public-domain scan | Viable where Unihan supplies a citation. |

### Word records

| Field group | Planned source(s) | Coverage assessment |
|---|---|---|
| Trad/simp and definitions | CC-CEDICT English/mappings; Taiwan MOE Concised then Revised for verbatim Traditional definitions | Taiwan definitions cover 11,891 records; 1,477 exact dual-source misses are explicit null gaps. |
| Pinyin and Zhuyin | Taiwan MOE Concised Dictionary, then Revised Dictionary; CC-CEDICT/CNS as regional cross-check | 11,891 exact prioritized matches; 1,477 dual-source misses retain provisional readings and exact gaps. |
| Frequency and rank | Taiwan MOE 1996 Common Terms Survey | Viable for Traditional word forms; reuse published rows and preserve source rank. |
| HSK/TOCFL grading | No approved source | Blocked. |

## Fields no approved source can currently fill reliably

Use `null` (or omit an optional field) and a `gaps[]` entry rather than inference:

- systematic oracle-bone and bronze historical-form assets for the top 2,000
  characters (radical-level coverage is superseded by the Phase 2 addendum;
  character historical forms are not a Phase 3 character-schema field);
- Korean learner-style radical names such as meaning-plus-sound labels, as
  distinct from a bare Unihan Korean reading;
- a curated `semantic_field` taxonomy with external provenance;
- complete, precise traditional 六書 classification for every in-scope character;
- reading-level `frequency_share` values;
- HSK and TOCFL grades under an explicitly versioned, redistribution-compatible
  source;
- a curated `confusable_with` set;
- authoritative stroke-type names aligned one-for-one with every Make Me a Hanzi
  SVG path;
- exact 1716 Kangxi per-radical counts until one complete edition has passed a
  page-level extraction and review workflow.

## Sources that failed the license gate

- **Academia Sinica Balanced Corpus 4.0 — rejected.** Its contract limits use to
  academic research, prohibits commercial activity, and prohibits transfer to
  third parties. It cannot back a redistributable public corpus.
- **Taiwan MOE public dictionary datasets — revised to reference-only for
  verification.** The current versioned Concised Dictionary workbook is CC
  BY-ND 3.0 Taiwan and is now the primary exact-headword pronunciation
  cross-check. Any integrated Pinyin/Zhuyin must remain verbatim, retain entry
  IDs and attribution, and keep independently sourced variants separate.
- **Taiwan MOE stroke-order learning data — rejected.** The cited XML/animation
  data is CC BY-NC-ND 3.0 Taiwan, incompatible with transformed SVG assets and a
  potentially commercial public website. CNS11643 open data is the allowed
  MOE-aligned source for canonical Taiwan readings and stroke-sequence counts,
  and the allowed Taiwan cross-check for later stroke-order assets.
- **CJKVI/CHISE IDS — quarantined.** The repository has mixed file-level terms;
  the principal `ids.txt` delegates to CHISE terms that were not sufficiently
  explicit in the audited pages. Make Me a Hanzi is the approved decomposition
  route for now.
- **Academia Sinica 小學堂 and CUHK 漢語多功能字庫 — quarantined at Phase 0.**
  This original finding remains applicable to CUHK. It is superseded for
  小學堂 by the later official CC0 license evidence and Phase 2 acquisition
  addendum below.
- **TOCFL lists and the PRC international Chinese level standard — quarantined.**
  Download availability is not a redistribution license, and the schema does not
  identify which evolving HSK model its numeric field means.
- **zi.tools and hanziyuan.net — not approved.** No sufficiently explicit bulk
  redistribution and asset license was established during this audit, so no
  content from them may be written to disk.

## Acquisition controls for the next phase

Before Phase 1 downloads any third-party file:

1. pin an immutable version or revision and record SHA-256, retrieval time, and
   the exact license text/version;
2. write the source and license entry before the data or image file;
3. use bulk downloads, not page scraping, when available;
4. throttle every host to at most one request per second and obey `robots.txt`;
5. send unresolved-license files only to `quarantine/`, never to delivered
   records or `assets/manifest.json` references;
6. normalize parsed text to UTF-8 NFC and verify non-BMP values by numeric
   codepoint round-trip tests;
7. preserve every source disagreement in `conflicts[]` or an explicit regional
   variant field. Apply the user-approved Taiwan precedence for Pinyin and
   stroke count, and never discard the losing PRC, Unicode IRG, or Japanese
   value.

## Phase 0 validation

- **PASS:** `sources.json` records an ID, full name, URL, access date, license
  status, redistribution statement, coverage, schema fields, and constraints for
  every audited source.
- **PASS:** approved, reference-only, quarantined, and rejected sources are
  distinguished mechanically.
- **PASS:** no third-party image or dataset has been written to disk.
- **PASS:** fields lacking an approved source are listed explicitly.
- **PASS:** the superseded Unihan property and stroke-order standard are recorded
  rather than silently accepted.
- **CHECKPOINT SATISFIED:** the user accepted the revised audit and project
  decisions on 2026-08-10, authorizing Phase 1.

## Phase 2 acquisition addendum

Phase 2 used only registry-approved sources and pinned every admitted source
snapshot before extraction:

- Chinese Wikisource `說文解字`: the main page plus all 15 volume pages were
  acquired through the MediaWiki revisions API. Page and revision IDs,
  timestamps, byte length, and snapshot SHA-256 are recorded in `sources.json`.
  The parser found 540 unique headings in volumes 1–14. Of the 214 Kangxi
  primary ideographs, 200 map by exact normalized heading and four only through
  a direct Unihan `kSemanticVariant` relationship (`尢→尣`, `巛→川`, `彐→彑`,
  `歹→歺`). Ten remain unmapped rather than inferred.
- English Wikipedia `Kangxi radicals`: revision 1362962863 was acquired through
  the revisions API and yielded 214 published count claims. These remain
  `secondary_source_unverified` until one internally complete 1716 Kangxi scan
  is selected and independently counted.
- Wikimedia Commons embedded seal files: metadata resolved for 101 exact file
  candidates. The per-file gate found 100 public-domain files and one CC BY-SA
  3.0 file. The CC BY-SA original (`齒-seal.svg`) was acquired unchanged and its
  attribution, license, dimensions, MIME type, timestamps, original URL, and
  hashes are in `assets/manifest.json`.
- The Wikimedia upload host returned HTTP 429 for the remaining 100 originals
  after bounded, rate-limited retries and directed bulk clients to thumbnails.
  Because this project requires the original file and prohibits replacement by
  an altered derivative, no thumbnail was substituted. All 100 are recorded as
  source-access failures rather than license failures.
- The approved NCL Shuowen and Harvard 六書通 scans were not assigned to records
  without verified per-radical full-page locators. The approved Kangxi scan
  category was not used to claim primary verification without one selected,
  internally complete edition.

The cumulative Phase 1+2 validator passed all 17 checks at that checkpoint. Its
radical and asset inventory remains covered by the Phase 3 regression check.

## Phase 2 image-library recovery addendum

The user requested a complete historical seal-image library where a form exists,
including one-at-a-time retries and alternative Taiwan-oriented routes. The
revised acquisition preserved the original license and integrity gate:

- Wikimedia Commons exposes a complete numbered series of 540 Shuowen radical
  SVGs and an unchanged numbered composite. API metadata resolved all 204
  Shuowen radical numbers used by the Kangxi mappings and verified the series as
  CC BY-SA 3.0. Two hundred individual numbered originals plus four originals
  from the embedded route (二, 人, 儿, and 齒) passed their own hash and license
  gates. The composite is retained unchanged as a supplemental library asset;
  no record now depends on a composite locator.
- The ten Kangxi radicals without a defensible Shuowen heading mapping each have
  an exact-character Commons seal SVG with public-domain metadata. These images
  populate `historical_forms` but do not change `shuowen: null` or manufacture a
  relationship to the 540-heading system.
- The Commons upload edge continued to return HTTP 429. An Internet Archive
  capture supplied the unchanged numbered composite and some individual files.
  A commit-pinned copy in `lbm364dl/hanzi-etymology-dict` supplied the last three
  exact-character files (爿, 阜, and 靑/青) and 194 numbered originals. Every
  mirrored file was admitted only after a
  byte-for-byte SHA-1 match to a Commons `imageinfo` revision; Commons remains
  the substantive source and per-file license authority.
- The National Central Library rare-book portal was audited as a Taiwan
  alternative but was not copied from directly. Its portal-specific image-use,
  authorization, and fee conditions do not provide a straightforward grant for
  this public redistributable corpus. The separately public-domain NCL Shuowen
  scan hosted by Commons remains approved, but no unverified page crop or
  per-radical locator was inferred from it.
- The remaining 97 `source_access_failed` entries stay in the asset manifest as
  audit history for the first embedded-candidate route. They no longer
  represented delivered coverage gaps at that checkpoint: all 214 radical records resolved to a
  distinct, license-verified individual seal SVG. The library stores those 214
  originals plus the unchanged supplemental composite, for 215 original files.

The revised cumulative Phase 1+2 validator passes all 17 checks. The historical
form conclusion in this seal-recovery addendum was subsequently superseded by
the licensed-source acquisition below. Phase 3 was subsequently authorized.

## Phase 2 Oracle, bronze, and 六書通 acquisition addendum

This addendum supersedes the Phase 0 statements that no approved systematic
Oracle/bronze source existed, that 小學堂 lacked a redistribution grant, and
that those historical-form arrays remained empty. Chinese-language searches
and Taiwan/Japan institutional sources established the following licensed
routes before any new image was admitted:

- Academia Sinica's official 小學堂 license page expressly applies CC0 1.0 to
  every-resolution glyph image returned by its query interface and to glyph
  attributes. Exact Traditional-primary queries across all 214 radicals and
  the 甲骨文/金文 interfaces yielded 9,487 radical-to-glyph mappings for 9,331
  distinct glyph codes. The complete mapping and source-reference index is
  pinned. Phase 2 acquired one deterministic source-ordered, highest-size
  representative for each covered radical/form query: 159 Oracle and 166
  bronze PNGs. The index, not the 325-file subset, is the complete discovery
  record; acquiring all 9,331 variant images is a separately disclosed
  expansion.
- The Wikimedia Commons Ancient Chinese Characters Oracle, bronze, and
  large-seal/六書通 indexes yielded 511 licensed radical candidates. All were
  public-domain files on their pinned metadata revisions. Four hundred
  fifty-five exact current or uniquely pinned historical SVG originals were
  recovered through direct, one-at-a-time, Wayback, and commit-pinned mirror
  passes; 56 candidate transports remain unavailable and 131 source-table positions
  were empty. These are recorded as route/table gaps, even where 小學堂 or CODH
  independently supplies record coverage.
- Chinese filename searches located `plexus/analects-data` at commit
  `c1efa0bbd30d3a74acad756efe401977edc501ce`. Because the repository has no
  repository-wide license, it is transport only: each admitted file had to
  match a separately license-verified current or uniquely identified historical
  Commons SHA-1. The mirror matched 401 candidates and is never used as content
  or license provenance.
- The ROIS-DS CODH catalog identifies all fourteen 偏類六書通 volumes
  TE00008–TE00021 as CC BY-SA 4.0. TE00010 supplied 125 unchanged JPEGs for 14
  exact Traditional-primary radicals. The other thirteen pinned volumes supply
  3,338/3,338 unchanged JPEGs with zero failures and exact matches spanning 196
  radicals. All 3,463 assets retain their exact volume, locator, DOI, and
  required attribution. 偏類六書通 is labeled as a later reorganization of the
  閔齊伋/畢弘述 六書通 tradition, not conflated with the Harvard 1795 edition.

After identity quarantine, exact-duplicate aliasing, and scholarly-source
replacement, the release-facing historical set contains 2,323 mapped assets.
Final radical coverage is 159/214 Oracle, 166/214 bronze, 196/214 六書通, and
211/214 seal. Every remaining empty historical array is a
`source_unavailable` gap rather than `not_attested`. The cumulative validator
passed all 17 checks at that checkpoint.

## Phase 3 character-set acquisition and build addendum

Phase 3 pinned and used the following licensed bulk inputs before parsing:

- The MOE 1996 survey bulk ZIP, SHA-256
  `aae5a194644bea6f47491aa80076133afe666a7099af4fe2ecb55c696d970765`.
  Its separately hashed `85rest01.csv` member selects the characters; the
  separately hashed `85rest02.csv` word table was reserved for Phase 4.
- Make Me a Hanzi `dictionary.txt` at commit
  `bddc96d41bef78427ed0e034e9f7e31d71fd1b92`, SHA-256
  `744bb05d5b0742e9ee35c37791f94d56a173349b3367569e7ca11e510364d203`.
- The CC-CEDICT project's own editor export dated
  `2026-08-11T14:10:23Z`, with 124,816 entries and compressed SHA-256
  `73af18e207d9ae969e8f5d6b13c777bed64246268efb218e8df6d2f20563618f`.
  The separately advertised stable MDBG route was not automated because its
  page prohibits scripted access.
- Unicode 17.0.0 `EquivalentUnifiedIdeograph.txt`, SHA-256
  `38619c05a17e771554000fe604afee92e10eb49e0616ecf0c87af3c1eb0f4320`,
  used only to normalize explicitly mapped CJK radical-form characters in IDS
  and component evidence.

The deterministic selection consumed MOE source ranks 1–2007 to obtain exactly
2,000 valid unified Han ideographs. Seven earlier non-Han or parenthesized rows
were excluded and logged; no Simplified corpus supplied replacements. The Phase
3 validator passes all 12 checks, including an exact source rebuild, per-field
provenance, explicit null/gap pairing, Taiwan-first reading and stroke-count
precedence, one-to-many simplification flags, Unicode-block isolation, component
referential integrity, and Phase 2 regression integrity.

## Phase 4 common-word acquisition and build addendum

Phase 4 parsed the pinned MOE `85rest02.csv` member without acquiring a new or
unversioned source. The table has 46,721 consecutive published rows and a final
cumulative frequency of 617,306. Its SHA-256 is
`8ade7cd812e50ed9d0acc396f5b493d40014e00571b6cd424ae9d812bd1042de`.
The build reused the Phase 3 CC-CEDICT snapshot and Taiwan CNS attribute table;
all three inputs already had approved, redistribution-compatible licenses.

For each selected character, the builder walks MOE rows in ascending source rank
and admits the first ten distinct forms that contain the character and have an
exact NFC Traditional CC-CEDICT headword. It performs no local segmentation,
script conversion, substring substitution, or approximate dictionary lookup.
One-character MOE rows are retained because they are published in the source's
word table. Words shared across characters are stored once under a stable
rank-derived ID and joined from each character record.

The resulting library contains 13,368 word records and 17,616 character-word
references. A total of 1,423 characters receive ten words; the other 577 have
one to nine and carry an explicit `common_words` gap. The exact join excludes
20,421 MOE rows with no CC-CEDICT Traditional headword. Eighteen word records
retain conflicting Simplified mappings. HSK remains unavailable under the
approved source set, and the unnamed MOE segmentation process is recorded as a
null rather than guessed.

The same Phase 4 evidence now supplies `radicals.*.example_characters`. Every
top-2,000 character with at least one eligible ranked-word link is grouped under
its canonical Taiwan CNS radical and ordered by MOE character-frequency rank.
This distributes exactly 2,000 references across 202 radicals. The other 12
radicals retain empty arrays and exact `not_attested` gaps; the build never pads
them with lower-frequency or unranked forms. The Phase 4 validator passes all 14 checks, including
deterministic rebuilding, schemas, source licensing/provenance, exact ranked
joins, reading syntax, Unicode-block isolation, manifest digests, and Phase 2/3
regression integrity.

After the Phase 4 checkpoint, the character schema was extended with a required
`english_translation` field. All 2,000 selected characters already had an
English Unihan `kDefinition`, so the build exposes that unchanged value with
`unicode-unihan-17.0.0` provenance while retaining all existing
`definitions[]` entries. Coverage is 2,000/2,000 and no guessed or generated
translation was introduced.

The radical schema was also extended with a required single-value
`english_definition` intended for compact display beneath each radical. All
214 values exactly reproduce the already pinned Unihan `kDefinition`, retain
`unicode-unihan-17.0.0` provenance, and coexist with the structured
`definitions[]` array. Coverage is 214/214 with no semantic shortening or
unsourced choice among senses.

## Phase 5 stroke-order acquisition and build addendum

Phase 5 reused the pinned Make Me a Hanzi `graphics.txt` snapshot at commit
`bddc96d41bef78427ed0e034e9f7e31d71fd1b92`, SHA-256
`a28c478b5178e98f67f510b2d52fde08a69dc664654ef43498253b9b764d46ee`.
Its 9,574 exact character rows cover all 214 radicals and 1,999 of the 2,000
Traditional-primary characters. After deduplicating characters shared between
the two sets, the build generates 2,096 exact-source ordered SVGs for 2,097
target unified ideographs.

The sole missing exact character is 汙 (U+6C59). As an alternative-source audit,
the official KanjiVG index was pinned at commit
`61e39cfc29724132a6f8823b166296932985a0ff`; the index contains neither 汙 nor
U+6C59, so it supports the explicit exact-source gap but supplies no asset. The
delivered fallback is instead marked `reconstructed`: strokes 1–3 preserve the
left-side 氵 paths from 污, strokes 4–6 preserve the 于 paths with the disclosed
affine placement `matrix(0.65 0 0 0.9 320 0)`, and order metadata follows the
exact Taiwan CNS sequence `444115`. This produces 2,097 visual assets and
2,000/2,000 character coverage without presenting the reconstruction as an
attested Make Me a Hanzi or KanjiVG row.

Every exact-source SVG preserves the Make Me a Hanzi Bézier path strings and
their source order. The generated wrapper adds only a 1024×1024 SVG container,
the documented `scale(1,-1) translate(0,-900)` display transform, stable
one-based path IDs, and source/license metadata. The 汙 reconstruction preserves
the selected component path strings but additionally places 于 with the disclosed
affine transform. These are disclosed modifications under the Arphic Public
License. The source's PRC convention is labeled against a provisional GF
0023-2020 baseline; formal conformance is not claimed because the official
standard is reference-only and no redistributable per-character verification
table was available.

Taiwan comparison data comes from the already pinned CNS11643
`CNS_strokes_sequence.txt` and its separately hashed UTF-8 documentation member,
which defines 1=橫, 2=豎, 3=撇, 4=點, and 5=折. The build retains 211 radical and
2,000 character CNS sequences. It records 6 radical and 235 character path-count
conflicts without changing either source. Because Make Me a Hanzi supplies no
authoritative per-path type names and Taiwan/PRC order alignment is unproven,
CNS types remain a separate regional sequence; all populated `stroke_types`
fields remain null with explicit gaps.

The Phase 5 validator passes all 10 checks: source integrity, record and asset
schemas, exact-source and reconstructed SVG geometry/order and hashes, record
joins, explicit type/count gap modeling, Arphic attribution/modification notices,
manifest digests, and Phase 2/4 regression projections.

## Phase 6 validation and packaging addendum

Phase 6 applies the ten requested corpus-wide checks plus record/Unicode and
release-payload checks. It emits 705 machine-readable reviewed exceptions: five
Taiwan radical counts that differ from Unihan, 458 positional-radical arithmetic
differences, and 241 Taiwan-count versus PRC-convention SVG path-count
differences. Each is already represented by a source variant or conflict; an
unflagged mismatch fails validation.

The radical-block isolation pass found 30 CJK Radical Supplement occurrences in
29 Make Me a Hanzi 六書 hint records. The Phase 3 builder now replaces each with
its pinned Unicode `EquivalentUnifiedIdeograph.txt` mapping. U+2E80, for which
Unicode publishes no equivalent unified ideograph, is preserved losslessly as
the ASCII token `[U+2E80]` instead of being assigned a guessed character.

The final deterministic ZIP contains all delivered records, manifested assets,
schemas, source and license metadata, reports, manifests, audit files, and build
scripts. Raw acquisitions and quarantined files are excluded from the
redistributable package; their URLs, versions, integrity hashes, and license
decisions remain in `sources.json` and the phase manifests. The Phase 6 validator
passes all 12 checks, and the archive is verified by CRC, exact entry set,
uncompressed byte length, and per-file SHA-256.

## 2026-08-11 high-risk content-audit addendum

The deep audit subsequently replaced the remaining provisional high-risk fields:

- All 2,000 character reading inventories reproduce exact Taiwan MOE evidence.
  The Revised Dictionary covers 1,964 records; exact-codepoint 正字 pages from the
  Dictionary of Variants adjudicate the remaining 36. Displaced CNS/Unihan values
  remain explicit conflicts.
- Prioritized exact-headword Concised/Revised evidence covers 11,891 word
  readings and definitions. The 1,477 dual-source misses remain explicit Taiwan
  verification and `definitions_zh_TW` gaps.
- All 2,000 characters have exact Concised Dictionary `definitions_zh_TW` cells
  and entry IDs. Definition text is verbatim after OOXML escape decoding; the
  single source compatibility-form string is deliberately not NFC-normalized.
- All 37 conflicting character simplification mappings were visually adjudicated
  against the official PRC 2013 table. Twenty-one context-independent targets
  are selected; sixteen context-dependent relationships remain null.
- Taiwan CNS radical assignments corrected five character records. The differing
  first Unihan assignments remain visible as additional assignments and conflict
  evidence.
- Historical identity mitigation quarantines 455 weak community mappings,
  release-excludes 214 superseded seal vectors and 1,676 exact-duplicate aliases,
  and annotates all 23 cross-radical duplicate hashes.

The current validators pass Phase 3 at 14/14, Phase 4 at 14/14, Phase 5 at
10/10, and Phase 6 at 12/12. The deterministic archive's current byte length and
SHA-256 are written outside the payload in `dist/release-metadata.json` and
`dist/SHA256SUMS`, avoiding a self-referential checksum inside the archive.
