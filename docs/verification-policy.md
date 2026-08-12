# Corpus content-verification policy

Status: **high-risk audit complete; explicit gaps remain**
Effective date: 2026-08-11

This policy separates structural validity from factual verification. A record
can be schema-valid, internally consistent, licensed, and hash-correct while
still containing the wrong pronunciation, historical identity, definition, or
classification.

## Evidence hierarchy

Use sources in this order unless a field-specific rule below is stricter:

1. Taiwan government or Taiwanese scholarly primary/curated evidence: Taiwan
   MOE dictionaries and standard-character resources, CNS11643, Academia Sinica
   小學堂, National Central Library scans, and similarly accountable catalogues.
2. Another independent primary or scholarly source with a stable record,
   edition, entry ID, glyph code, or page/region locator.
3. Unicode/Unihan for encoding, variants, cross-regional attestations, and fields
   for which Unicode is the named authority; not as a substitute for Taiwan
   learner-facing lexical priority.
4. Community dictionaries or derivative image collections only as discovery or
   secondary cross-checks. They cannot independently establish a canonical
   Taiwan pronunciation or historical-glyph identity.

No field is considered verified merely because two sources copied the same
upstream dataset. Cross-references must be independent at the claim level.

## Pronunciation rules

- Taiwan MOE is canonical for learner-facing word Pinyin and Zhuyin when an
  exact Traditional headword is available.
- Preserve the MOE value verbatim with dictionary version and entry ID.
- Regional, historical, literary, surname, tone-change, and other readings may
  be retained, but must be separately labeled rather than mixed into an
  unqualified canonical array.
- A character-level MOE omission does not invalidate a CNS11643 reading. Review
  its class and context before deciding whether it is canonical or additional.
- A word absent from the MOE Concised Dictionary requires the MOE Revised
  Dictionary or another Taiwan authority plus an independent cross-check.
- Mechanical Pinyin-to-Zhuyin conversion verifies encoding consistency only; it
  does not verify that the lexical reading itself is correct.

The current reproducible comparison is
`scripts/audit_moe_pronunciations.py`. Its output is
`../metadata/audits/pronunciation-moe-concised-20260626.json`.

## Historical-image rules

Every published historical asset must have all of the following:

1. exact target character or explicitly documented historical equivalence;
2. exact script/form classification;
3. scholarly source identity;
4. stable source glyph code or edition/page/region locator;
5. local file hash and license/redistribution evidence;
6. an independent identity check when the immediate source is a community
   derivative or modern vector transcription.

Filename, category, visual similarity, license metadata, and file integrity are
not identity evidence by themselves. Assets that fail the identity gate remain
available only as quarantine candidates; an empty published form array means
“not yet verified,” not “historically unattested.”

Exact duplicate bytes count once for visual coverage. A hash assigned to more
than one radical must record the scholarly cross-identification or be corrected.
The current reproducible check is `scripts/audit_historical_images.py`, with
results in `../metadata/audits/historical-images.json`.

## Other field rules

- Definitions must distinguish unchanged source glosses from locally composed
  summaries. A source gloss is not assumed complete or context-specific.
- Taiwan MOE definition cells are copied only as exact-headword, verbatim
  `definitions_zh_TW` entries with workbook entry IDs. OOXML character-escape
  decoding is permitted; editorial or Unicode-compatibility normalization is
  not. Exact dual-dictionary misses remain null gaps.
- Stroke counts and orders must retain regional standard labels; equal counts do
  not prove equal stroke order.
- 六書 and component claims require a source that actually makes that claim.
  Broad modern etymology categories must not be silently narrowed.
- Simplification mappings, variants, and radical assignments retain conflicts.
  The official PRC 2013 table may select a context-independent Mainland
  correspondence, but sense-, name-, surname-, reading-, or usage-dependent
  relationships remain null. Taiwan CNS is canonical for character radical
  assignment; displaced Unihan assignments remain conflict evidence.
- Frequency values are verified against their named historical corpus only and
  must not be generalized to contemporary or global usage.

## Verification states

Each auditable claim or asset should ultimately have one of these states:

- `verified`: meets the applicable source and independent-check requirements;
- `verified_with_conflict`: authoritative evidence conflicts and all values are
  preserved with a documented display decision;
- `review_required`: evidence exists but classification or source agreement is
  unresolved;
- `source_unavailable`: no acceptable source has been found;
- `quarantined`: evidence is too weak or contradictory for release-facing use.

## Release gate

The corpus may be described as content-verified only when:

- every populated claim and published asset has a verification state and
  field-level evidence;
- no `review_required` or `quarantined` item is presented as canonical;
- all automated audit queues are empty or contain only explicitly accepted,
  documented conflicts;
- a second pass confirms that build scripts reproduce the corrected records;
- structural validators and content audits both pass on the same snapshot.

This snapshot has completed the defined high-risk audits. Release documentation
must still distinguish fully reproduced populated claims from 1,477 provisional
word-reading/definition gaps, accepted regional or structural conflicts,
secondary-source Kangxi counts, and release-excluded quarantine evidence. The
corpus as a whole must not be represented as uniformly claim-level verified.
