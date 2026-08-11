# Phase 5 report — stroke order

Status: **PASS**

## Completed

- Unique target unified ideographs: **2,097**.
- Generated, licensed ordered SVGs: **2,097**.
- Exact-source SVGs: **2,096**; explicitly reconstructed SVGs: **1**.
- Radical coverage: **214 / 214**.
- Character coverage: **2,000 / 2,000**.
- Taiwan CNS comparison sequences: **211 radicals** and **2,000 characters**.
- Taiwan/PRC path-count conflicts: **6 radicals** and **235 characters**.

## Explicit limitations

- 汙 (U+6C59) is the sole character without an exact Make Me a Hanzi row. Its delivered fallback is explicitly marked `reconstructed`: strokes 1-3 reuse the left-side 氵 geometry from 污, strokes 4-6 reuse 于 with a disclosed affine placement, and order metadata follows the exact Taiwan CNS sequence 444115. The official KanjiVG index also has no exact U+6C59 entry.
- Make Me a Hanzi declares PRC stroke-order convention but does not claim formal per-character GF 0023-2020 conformance. The standard is therefore a provisional baseline and `formal_conformance` is `not_verified`.
- Make Me a Hanzi supplies ordered paths but no per-path PRC stroke-type names. All 2,214 populated record references keep `stroke_types` null with a source gap; 汙 retains its Taiwan CNS types separately.
- CNS publishes Taiwan stroke types as 1=橫, 2=豎, 3=撇, 4=點, 5=折. These sequences are retained separately and never assigned to PRC path indices without proof that the regional orders align.

## Implementation decisions introduced in this phase

1. One SVG is generated per unique unified ideograph and reused when a radical also appears in the top-2,000 character set.
2. Exact-source SVGs preserve source Bézier path strings and order byte-for-value. The single 汙 reconstruction also preserves its selected component path strings, but applies a disclosed affine placement to 于 and must not be presented as attested source geometry.
3. Stroke-count differences against the canonical Taiwan record values are preserved in `stroke_order.standard_conflicts`; no path is added, removed, or reassigned to force agreement.
4. The reference-only GF publication supplies the standard identifier, not redistributable path data. All path content comes from the Arphic-licensed Make Me a Hanzi snapshot.

## Phase boundary

Phase 6 validation and packaging has not started.
