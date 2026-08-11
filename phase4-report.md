# Phase 4 report — common-word layer

Status: **PASS**

## Completed

- Word records: **13,368**.
- Character-to-word references: **17,616**.
- Characters with a dedicated English translation: **2,000 / 2,000**.
- Characters with 10 words: **1,423 / 2,000**.
- Single-character published MOE word rows retained: **1,818**.
- Word records flagged by mapping conflicts: **18**.
- Explicit word gaps: **28,058**.

## Words per character

| Words | Characters |
|---:|---:|
| 1 | 25 |
| 2 | 40 |
| 3 | 46 |
| 4 | 57 |
| 5 | 73 |
| 6 | 75 |
| 7 | 78 |
| 8 | 93 |
| 9 | 90 |
| 10 | 1,423 |

## Conflicts and gaps

| Category | Count |
|---|---:|
| conflict: `simplified` | 18 |
| gap: `conflicting_sources` | 18 |
| gap: `not_attested` | 216 |
| gap: `source_unavailable` | 27,824 |

## Implementation decisions introduced in this phase

1. The corpus's 46,721 published `85rest02.csv` rows are the word-boundary authority. The release names no segmentation software, so `segmentation_tool` remains null with a `source_unavailable` gap.
2. One-character rows are retained because the source publishes them as word rows and no approved rule excludes them.
3. Eligibility requires an exact NFC Traditional headword match in the pinned CC-CEDICT snapshot. No local segmentation, script conversion, substring lookup, or approximate matching is used.
4. Each character receives the first 10 distinct eligible Traditional forms in ascending MOE rank. A shared word is stored once and joined by its rank-derived ID.
5. Multiple exact CC-CEDICT Simplified mappings remain null and are preserved in `conflicts[]`; dictionary pronunciations are all retained rather than ranked as a Taiwan primary reading.
6. Word Zhuyin is a deterministic conversion through the pinned Taiwan CNS syllable table. A non-unique or incomplete conversion remains a gap.

## Source limitations

- **20,421** MOE rows had no exact CC-CEDICT Traditional headword and were ineligible.
- No approved HSK word-level source passed the source audit; `grading.hsk` remains null.
- Phase 5 stroke-order SVG work has not started.
