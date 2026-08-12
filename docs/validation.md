# Validation report

Phase 6 status: **PASS**

Release: `hanzi-corpus-2026-08-11`

| Check | Result | Detail |
|---|---:|---|
| P6-01 | PASS | Exactly 214 radical records, numbered 1-214, with unique unified primaries. |
| P6-02 | PASS | Radical counts match Unihan except 5 reviewed Taiwan-precedence variants. |
| P6-03 | PASS | Every character equation matches or has exactly one preserved review conflict; 458 reviewed positional-form exceptions. |
| P6-04 | PASS | All scoped character/component/confusable/word joins resolve, and word constituents reproduce their headword codepoints. |
| P6-05 | PASS | Every non-null record field has registered provenance; schemas validate; official simplification adjudications and verbatim Taiwan definitions exactly reproduce pinned sources. |
| P6-06 | PASS | Every asset reference resolves to one uniquely manifested, licensed, hash-verified file. |
| P6-07 | PASS | Every SVG path count matches its asset and stroke-order object; 241 Taiwan/PRC record-count differences are preserved. |
| P6-08 | PASS | Pinyin syntax and Zhuyin codepoints pass; MOE-covered records reproduce exact official readings/entry IDs, including 1 exact MOE pair outside the CNS conversion table; uncovered words reproduce the declared CNS conversion. |
| P6-09 | PASS | Every delivered many-Traditional-to-one-Simplified mapping is flagged, and all 37 formerly conflicting candidates reproduce the official PRC-table adjudication. |
| P6-10 | PASS | Kangxi Radical and CJK Radical Supplement characters occur only in radical_block.char. |
| P6-11 | PASS | Record counts, unique IDs, NFC outside explicitly verbatim source cells, and a non-BMP JSON sentinel all pass. |
| P6-12 | PASS | The deterministic release payload contains every final record, user document, query distribution, schema, manifest, and released asset while excluding internal build/audit material. |
| P6-13 | PASS | SQLite integrity, relational counts, indexed lookups, profile isolation, JSONL/Parquet equivalence, and query-file hashes all pass. |

## Reviewed exceptions (not validation failures)

- Taiwan radical count versus Unihan: **5**
- Radical-plus-residual equation: **458**
- Taiwan canonical count versus PRC-convention SVG paths: **241**
- Exact MOE Pinyin/Zhuyin pair absent from CNS conversion table: **1**

Every item is serialized in `metadata/audits/phase6-review-exceptions.json`; an unflagged mismatch fails its check.
