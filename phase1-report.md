# Phase 1 report

Status: **complete and validated**

## Outcome

- Radical records completed: **214 / 214**
- Unresolved conflict records: **0**
- Automated validation: **PASS**

## Taiwan precedence and retained variants

- Taiwan CNS Pinyin is canonical for **211** records; radicals 8, 15, and 20 use a documented Unicode fallback because CNS has no phonetic row.
- Noncanonical Unihan Pinyin evidence is retained for **74** records.
- Explicit PRC `kTGHZ2013`/regional Pinyin variants occur in **11** records (10, 25, 27, 36, 51, 53, 68, 90, 144, 153, 171).
- Noncanonical stroke counts occur in **10** records (54, 97–98, 114, 131, 178, 188, 194, 206, 213).
- Explicit Make Me a Hanzi PRC-convention counts occur in **6** records (54, 98, 188, 194, 206, 213).
- Unicode IRG and Japanese counts remain separately labeled when they differ; no losing value is discarded.

## New gaps

- `not_attested`: 108
- `source_unavailable`: 1381

The dominant gaps are systematic Traditional-Chinese and Korean learner-style radical names. Four radicals also lack a Unicode-mappable Kanji Alive row for English/Japanese labels.

## Sources used

- Unicode 17.0.0 `CJKRadicals.txt`: radical number, unified primary, and radical-block identity.
- Unicode 17.0.0 Unihan: structural cross-check, Unicode IRG counts, variants, general readings, and PRC `kTGHZ2013` readings.
- Kanji Alive commit `2d2a4931eec6e0cb532d5102766273c2323f96db`: English meanings used as radical labels and Japanese radical names.
- CNS11643 server snapshot dated 2026-08-05: canonical Taiwan Zhuyin/Pinyin and stroke-sequence counts, using three independently hashed members that pass ZIP CRC checks.
- Make Me a Hanzi commit `bddc96d41bef78427ed0e034e9f7e31d71fd1b92`: PRC-convention ordered-path counts for all 214 primary radical ideographs.

## Failed or limited access

- The CNS11643 `Properties.zip` snapshot has a valid central directory and exact advertised byte length, but full-archive testing fails on unrelated members. `CNS_phonetic.txt`, `CNS_pinyin_2.txt`, and `CNS_strokes_sequence.txt` independently pass CRC and SHA-256 checks and are admitted; damaged `CNS_source.txt` and `CNS_stroke.txt` remain excluded.
- Kanji Alive has no Unicode-mappable primary radical row for Kangxi numbers 43, 52, 92, and 168; their English/Japanese labels remain gaps.
- No source refused access during this phase.

## Judgment calls made in Phase 1

1. Kanji Alive's `Meaning` cell is represented as an English radical label, while `Reading-J` is represented as a Japanese radical name. Source strings are preserved without semantic rewriting.
2. The radical schema extends the example with Unihan Japanese on/kun, Korean romanization, and Hangul readings so available sourced readings are not discarded.
3. Taiwan CNS readings are canonical. PRC dictionary readings and other Unihan attestations are separate variants, so display precedence is resolved without erasing evidence.
4. Taiwan stroke-sequence length is canonical when present. Make Me a Hanzi PRC-convention, Unicode IRG, and Kanji Alive Japanese disagreements are separate variants.
5. Direct extraction from Taiwan MOE dictionary/stroke-learning datasets remains disallowed by their no-derivatives terms; CNS11643 is the open-data, MOE-aligned implementation source.
6. Future Phase 2–5 fields are omitted rather than mislabeled as Phase 1 gaps.

## Stop boundary

Phase 2 has not begun. Review this revised Phase 1 precedence before radical enrichment.
