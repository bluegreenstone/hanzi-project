# Validation report

Phase 6 status: **PASS**

Release: `hanzi-corpus-2026-08-11`

| Check | Result | Detail |
|---|---:|---|
| P6-01 | PASS | Exactly 214 radical records, numbered 1-214, with unique unified primaries. |
| P6-02 | PASS | Radical counts match Unihan except 5 reviewed Taiwan-precedence variants. |
| P6-03 | PASS | Every character equation matches or has exactly one preserved review conflict; 459 reviewed positional-form exceptions. |
| P6-04 | PASS | All scoped character/component/confusable/word joins resolve, and word constituents reproduce their headword codepoints. |
| P6-05 | PASS | Every non-null record field has registered provenance and every record/stroke-asset schema validates. |
| P6-06 | PASS | Every asset reference resolves to one uniquely manifested, licensed, hash-verified file. |
| P6-07 | PASS | Every SVG path count matches its asset and stroke-order object; 241 Taiwan/PRC record-count differences are preserved. |
| P6-08 | PASS | Pinyin syntax, Zhuyin codepoints, and all character/word conversion-table joins match. |
| P6-09 | PASS | Every delivered many-Traditional-to-one-Simplified mapping is explicitly flagged for round-trip review. |
| P6-10 | PASS | Kangxi Radical and CJK Radical Supplement characters occur only in radical_block.char. |
| P6-11 | PASS | Record counts, NFC normalization, unique IDs, and a non-BMP JSON sentinel all pass. |
| P6-12 | PASS | The deterministic release payload contains every final record, schema, report, script, and manifested asset, excluding raw acquisitions and quarantine. |

## Reviewed exceptions (not validation failures)

- Taiwan radical count versus Unihan: **5**
- Radical-plus-residual equation: **459**
- Taiwan canonical count versus PRC-convention SVG paths: **241**

Every item is serialized in `phase6-review-exceptions.json`; an unflagged mismatch fails its check.
