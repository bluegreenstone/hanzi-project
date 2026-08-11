# Phase 3 report — Character set

Status: **complete and validated**

## Outcome

- Records: **2000** Traditional-primary character files.
- MOE source ranks consumed: **1–2007**.
- Excluded source rows before selection completed: **7**.
- Records with reviewable conflicts: **656**.
- Total conflicts: **864**.
- Total explicit gaps: **16279**.

## Coverage

| Field | Populated | Coverage |
|---|---:|---:|
| Simplified mapping | 1963 | 98.2% |
| many-to-one simplification note | 522 | 26.1% |
| IDS decomposition | 1840 | 92.0% |
| locally resolvable component list | 485 | 24.2% |
| Make Me a Hanzi etymology | 1868 | 93.4% |
| Taiwan CNS Pinyin | 2000 | 100.0% |
| Zhuyin | 2000 | 100.0% |
| English definition | 2000 | 100.0% |
| Kangxi citation | 2000 | 100.0% |

## Conflicts by field

| Field | Count |
|---|---:|
| `radical.total_strokes_equation` | 459 |
| `total_strokes` | 277 |
| `readings.pinyin` | 90 |
| `simplified` | 37 |
| `kangxi_citation` | 1 |

## Gaps by reason

| Reason | Count |
|---|---:|
| `conflicting_sources` | 74 |
| `not_attested` | 4139 |
| `source_unavailable` | 12066 |

## Implementation decisions introduced in this phase

1. The stable MDBG CC-CEDICT page forbids scripted access. The build therefore uses and pins the CC-CEDICT project's own dated editor-export snapshot (`2026-08-11T14:10:23Z`) and labels it as such; it is not represented as the stable 2026-08-10 MDBG release.
2. The MOE CSV's published `筆畫` value is the canonical Taiwan MOE stroke count. CNS sequence length, Unicode IRG values, and Make Me a Hanzi PRC path counts are retained as variants whenever they differ.
3. Components outside the selected top-2,000 set are not emitted as dangling references. The full normalized IDS remains available, while `components` is null with a gap until the character set expands.
4. Make Me a Hanzi `pictophonetic` is normalized to `形聲`. Its broader `pictographic` and `ideographic` labels are preserved without forcing a narrower 六書 classification.
5. Only exact one-character CC-CEDICT headwords populate character mappings and definitions. Word entries remain Phase 4 work.

## Deferred by phase boundary

- Common-word joins and word records remain Phase 4.
- Stroke-order SVG assets remain Phase 5; Phase 3 uses only path counts as explicit PRC comparison evidence.
- HSK, TOCFL, and curated confusable fields remain null because no approved versioned sources passed the audit.
