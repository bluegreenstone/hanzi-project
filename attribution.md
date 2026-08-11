# Attribution

This is the cumulative website attribution block for corpus material admitted
through Phase 5. Asset-level file pages, creators, license URLs, revision dates,
dimensions, and hashes remain authoritative in `assets/manifest.json`.

## Unicode data

Radical identity, structural mappings, IDS radical normalization, definitions,
readings, variants, and comparison stroke counts include data from [Unicode CJK Radicals
17.0.0](https://www.unicode.org/Public/17.0.0/ucd/CJKRadicals.txt) and [Unihan
17.0.0](https://www.unicode.org/Public/17.0.0/ucd/Unihan.zip), plus the
[Equivalent Unified Ideograph data
file](https://www.unicode.org/Public/17.0.0/ucd/EquivalentUnifiedIdeograph.txt).
Copyright ©
1991–2026 Unicode, Inc. Distributed under the [Unicode License
v3](https://www.unicode.org/license.txt); the Unicode copyright and permission
notice must accompany redistribution.

Each Phase 4 character's dedicated `english_translation` is the unchanged
English `kDefinition` value from this pinned Unihan release. The fuller
`definitions[]` array remains available for CC-CEDICT senses and other lexical
detail; the dedicated field does not contain an inferred or machine-generated
translation.

Each of the 214 radical records likewise exposes the unchanged Unihan
`kDefinition` as a single `english_definition` display string. Its existing
structured `definitions[]` entry remains unchanged.

## Taiwan MOE character frequency and canonical character stroke counts

The Phase 3 character set, ranks, counts, cumulative statistics, and canonical
character stroke counts come from the Taiwan Ministry of Education's [85年常用語詞調查報告之各項統計表](https://data.gov.tw/dataset/45518), specifically the
1996 survey's `85rest01.csv` character-frequency table. The data is supplied by
the Government of the Republic of China (Taiwan) under the [Taiwan Open
Government Data License 1.0](https://data.gov.tw/license). Changes: the legacy
Big5 table was decoded to UTF-8, valid unified Han rows were selected in source
rank without Simplified-corpus backfill, and per-million values were calculated
from the published counts.

## Taiwan MOE word frequency

Phase 4 word ranks, counts, cumulative statistics, and character common-word
ordering come from the same Taiwan MOE 1996 survey, specifically its separately
hashed `85rest02.csv` word-frequency table, under the [Taiwan Open Government
Data License 1.0](https://data.gov.tw/license). Changes: the legacy Big5 table
was decoded to UTF-8 and NFC-normalized, per-million values were calculated from
the published corpus total of 617,306, and source-published rows were joined by
exact Traditional headword to the pinned CC-CEDICT snapshot. No local word
segmentation was performed.

## Taiwan canonical readings and comparison stroke counts

Taiwan-first Pinyin, Zhuyin, and stroke-sequence counts use the [CNS11643
Chinese Standard Interchange Code Full Character Library attribute
dataset](https://data.gov.tw/dataset/5961), supplied by the Government of the
Republic of China (Taiwan) under the [Taiwan Open Government Data License
1.0](https://data.gov.tw/license). The corpus restructures selected fields and
records PRC or other regional differences as variants or conflicts. For Phase 3
characters, the MOE table's `筆畫` value above is canonical and CNS sequence
length is retained as comparison evidence when it differs.

## CC-CEDICT character and word entries

Exact Traditional/Simplified mappings, dictionary Pinyin comparisons, and
English definitions use the [CC-CEDICT project editor
export](https://cc-cedict.org/editor/editor.php?handler=Download), snapshot
`2026-08-11T14:10:23Z` with 124,816 entries, under [CC BY-SA
4.0](https://creativecommons.org/licenses/by-sa/4.0/). Changes: entries were
restricted to exact Traditional headwords. Phase 3 uses the one-character
subset; Phase 4 joins eligible MOE word rows to all exact matching entries.
Numeric Pinyin was converted to NFC tone marks, definitions were grouped with
their source entry indices, and ambiguous Simplified mappings were preserved as
conflicts. Adapted CC-CEDICT-derived material must retain attribution and be
shared under compatible ShareAlike terms.

## Make Me a Hanzi dictionary data

IDS-like decompositions, component evidence, and etymology categories use [Make Me a Hanzi
`dictionary.txt`](https://github.com/skishore/makemeahanzi/blob/bddc96d41bef78427ed0e034e9f7e31d71fd1b92/dictionary.txt), commit
`bddc96d41bef78427ed0e034e9f7e31d71fd1b92`, under
[LGPL-3.0-or-later](https://github.com/skishore/makemeahanzi/blob/bddc96d41bef78427ed0e034e9f7e31d71fd1b92/LGPL).
Changes: text was NFC-normalized; explicit Unicode mappings replaced radical-form
characters in IDS strings; unknown or dangling components became gaps; only
`pictophonetic` was normalized to the traditional label `形聲`.

## Japanese radical names

Japanese names use `japanese-radicals.csv` from [Kanji alive's
kanji-data-media](https://github.com/kanjialive/kanji-data-media), commit
`2d2a4931eec6e0cb532d5102766273c2323f96db`, under [CC BY
4.0](https://creativecommons.org/licenses/by/4.0/). Changes: the selected rows
were normalized to NFC and incorporated into per-radical JSON records.

## Stroke-order paths and stroke-count comparison data

Comparison stroke-path counts use [Make Me a Hanzi
`graphics.txt`](https://github.com/skishore/makemeahanzi/blob/master/graphics.txt),
commit `bddc96d41bef78427ed0e034e9f7e31d71fd1b92`, under the [Arphic Public
License](https://github.com/skishore/makemeahanzi/blob/master/APL/english/ARPHICPL.TXT).
Phase 5 generates 2,097 SVG wrappers under the same Arphic Public License.
Of these, 2,096 preserve an exact source row's Bézier path strings and order,
adding only the documented source-coordinate transform, stable one-based path
indices, and source/license metadata. The 汙 U+6C59 fallback is prominently
marked `reconstructed`: it composes source paths from 污 and 于, applies a
disclosed affine placement to 于, and uses the pinned Taiwan CNS11643 sequence
`444115` for its order metadata. It must not be described as an exact Make Me a
Hanzi glyph. The website must display the Make Me a Hanzi attribution and keep
all modified SVG source freely available under the applicable Arphic terms.

The source declares PRC stroke-order convention but does not claim formal
per-character GF 0023-2020 conformance. The government standard supplies only a
reference-only provisional baseline identifier and no copied standard tables or
PDF content is redistributed.

## Taiwan CNS stroke-sequence comparison

Taiwan comparison sequences use the pinned CNS11643
`CNS_strokes_sequence.txt` table and its exact documentation member under the
[Taiwan Open Government Data License 1.0](https://data.gov.tw/license). The
published mapping is 1=橫, 2=豎, 3=撇, 4=點, and 5=折. These Taiwan sequences are
stored separately from the PRC-order SVG paths and are not assigned to path
indices unless regional-order alignment can be proven.

## 說文解字 transcription

Entry text and headings come from pinned revisions of the [Chinese Wikisource
`說文解字`](https://zh.wikisource.org/wiki/說文解字) transcription. Wikisource
contributions are available under [CC BY-SA
4.0](https://creativecommons.org/licenses/by-sa/4.0/); the original classical
text is public domain. The exact page and revision IDs used are recorded in
`sources.json`. Changes: wiki markup was removed, text was NFC-normalized, and
editorial notes were separated from entry text.

## Kangxi count claims

Per-radical count claims come from [English Wikipedia, “Kangxi
radicals,” revision
1362962863](https://en.wikipedia.org/w/index.php?title=Kangxi_radicals&oldid=1362962863),
under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). They are
redistributed as extracted numeric claims and explicitly marked
`secondary_source_unverified`.

## Shuowen numbered SVGs

The individual `Shuowen Seal Radical NNN.svg` files, including the 齒 file
resolved through the embedded-candidate route, are by [LiliCharlie on Wikimedia
Commons](https://commons.wikimedia.org/wiki/User:LiliCharlie), sourced from the
[numbered 540-radical Commons
category](https://commons.wikimedia.org/wiki/Category:Shuowen_seal_script_radicals_(SVG))
and licensed [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
The files are stored unchanged.

The unchanged supplemental [numbered 540-radical composite
SVG](https://commons.wikimedia.org/wiki/File:The_540_Shuowen_Seal_Radicals_-_numbered.svg)
is also by LiliCharlie and is licensed [CC BY-SA
4.0](https://creativecommons.org/licenses/by-sa/4.0/). The corpus stores it
once as a supplemental original after acquiring individual record-level SVGs;
it does not crop or re-encode the image.

## Academia Sinica 小學堂 historical glyphs

Oracle-bone and bronze glyph images and their displayed glyph attributes come
from the [Academia Sinica 小學堂文字學資料庫](https://xiaoxue.iis.sinica.edu.tw/guide/).
The database's [official license page](https://xiaoxue.iis.sinica.edu.tw/License/License)
applies the [CC0 1.0 Universal Public Domain
Dedication](https://creativecommons.org/publicdomain/zero/1.0/) to glyph images
at every resolution returned through the query interface and to the associated
glyph attributes. Attribution is not legally required, but the corpus retains
the source glyph code, displayed bibliographic reference, query mapping, and
retrieval provenance for every indexed candidate. The admitted PNG files are
unchanged responses from the source's highest-size 300-point option.

## Commons Oracle, bronze, and 六書通 forms

Historical Oracle, bronze, and 六書通 SVGs come from the Wikimedia Commons
[Oracle](https://commons.wikimedia.org/wiki/Commons:Ancient_Chinese_characters/oracle),
[bronze](https://commons.wikimedia.org/wiki/Commons:Ancient_Chinese_characters/bronze),
and [large-seal/六書通](https://commons.wikimedia.org/wiki/Commons:Ancient_Chinese_characters/bigseal)
Ancient Chinese Characters indexes. Each admitted file was marked public domain
on its pinned Commons file revision. Attribution is not required, but the
manifest preserves the filename, file page, original URL, content hash, author
or source statement, and exact current or uniquely identified historical
revision. Files recovered from mirrors were admitted only when their bytes
matched that pinned Commons revision.

## CODH 偏類六書通 glyphs

The corpus includes source-published glyph images from all fourteen
[偏類六書通 TE00008–TE00021 volumes in the ROIS-DS CODH
篆書字体データセット](https://codh.rois.ac.jp/tensho/book/), licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
The required attribution is:

> 『篆書字体データセット』（国文学研究資料館が複数の機関から収集／ROIS-DS人文学オープンデータ共同利用センター・一般財団法人人文情報学研究所加工）, doi:10.20676/00000390, CC BY-SA 4.0.

The 3,463 unchanged JPEGs retain their exact TE volume label, source URL, and
page/canvas locator. 偏類六書通 is treated as a later reorganization of the
閔齊伋/畢弘述 六書通 tradition, not silently identified with the Harvard 1795
edition.

## Exact-character seal SVGs

The following Wikimedia Commons Ancient Chinese Characters project files are
marked public domain; attribution is not required but their file histories are
preserved here: [二](https://commons.wikimedia.org/wiki/File:%E4%BA%8C-seal.svg),
[人](https://commons.wikimedia.org/wiki/File:%E4%BA%BA-seal.svg),
[儿](https://commons.wikimedia.org/wiki/File:%E5%84%BF-seal.svg),
[亠](https://commons.wikimedia.org/wiki/File:%E4%BA%A0-seal.svg),
[冫](https://commons.wikimedia.org/wiki/File:%E4%BB%8C-seal.svg),
[廾](https://commons.wikimedia.org/wiki/File:%E5%BB%BE-seal.svg),
[弋](https://commons.wikimedia.org/wiki/File:%E5%BC%8B-seal.svg),
[无](https://commons.wikimedia.org/wiki/File:%E7%84%A1-seal.svg),
[父](https://commons.wikimedia.org/wiki/File:%E7%88%B6-seal.svg),
[爿](https://commons.wikimedia.org/wiki/File:%E7%88%BF-seal.svg),
[艮](https://commons.wikimedia.org/wiki/File:%E8%89%AE-seal.svg),
[阜](https://commons.wikimedia.org/wiki/File:%E9%98%9C-seal.svg), and
[靑/青](https://commons.wikimedia.org/wiki/File:%E9%9D%92-seal.svg).

## Byte-transport mirrors

The [Internet Archive Wayback Machine](https://web.archive.org/) and pinned
[Hanzi / Kanji Etymology Dictionary commit
`caada9c8…`](https://github.com/lbm364dl/hanzi-etymology-dict/commit/caada9c8ec6f51e59158e9633598230d9e23a9c8)
and [plexus/analects-data commit
`c1efa0bb…`](https://github.com/plexus/analects-data/tree/c1efa0bbd30d3a74acad756efe401977edc501ce/commons_ancient_characters)
were used only to transport files whose bytes exactly match a separately
license-verified current or uniquely pinned historical Commons SHA-1. Neither
GitHub repository is substituted as content or license provenance; the
originating Commons attribution and license above remain in force.
