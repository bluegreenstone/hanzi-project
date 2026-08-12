-- Exact character lookup.
SELECT
    codepoint,
    traditional,
    simplified,
    total_strokes,
    frequency_rank,
    english_translation
FROM characters
WHERE traditional = '水';

-- Common characters using Kangxi radical 馬, ordered by corpus frequency.
SELECT
    kangxi_number,
    radical,
    codepoint,
    traditional,
    frequency_rank
FROM v_radical_characters
WHERE kangxi_number = 187
ORDER BY ordinal;

-- Ranked words associated with a character.
SELECT
    word_id,
    word,
    pinyin_text,
    frequency_rank
FROM v_character_words
WHERE codepoint = 'U+99AC'
ORDER BY ordinal;

-- Full-text lookup across characters, words, readings, and English definitions.
SELECT
    d.entity_type,
    d.entity_id,
    d.traditional,
    d.simplified,
    d.pinyin,
    d.frequency_rank
FROM search_fts
JOIN search_documents AS d ON d.search_id = search_fts.rowid
WHERE search_fts MATCH '馬'
ORDER BY d.frequency_rank IS NULL, d.frequency_rank
LIMIT 25;

-- Inspect the tables assigned to each redistribution profile.
SELECT
    profile_id,
    ordinal,
    table_name
FROM license_profile_tables
ORDER BY profile_id, ordinal;

-- Read exact Taiwan definitions from their isolated CC BY-ND layer.
SELECT
    entity_type,
    entity_id,
    definition_text,
    source_id,
    source_entry_id,
    license_id
FROM taiwan_definitions
WHERE entity_type = 'character' AND entity_id = 'U+99AC'
ORDER BY ordinal;

-- Audit source-license obligations attached to canonical record fields.
SELECT
    obligation_class,
    license_id,
    entity_type,
    field_source_references
FROM v_field_license_counts
ORDER BY obligation_class, license_id, entity_type;

-- Audit visual assets by license and asset family.
SELECT
    obligation_class,
    license_id,
    asset_kind,
    asset_count,
    total_bytes
FROM v_asset_license_counts
ORDER BY obligation_class, license_id, asset_kind;

-- Find word constituents that are valid Unicode nodes but outside the top 2,000.
SELECT
    wc.word_id,
    w.traditional AS word,
    wc.ordinal,
    n.codepoint,
    n.character
FROM word_constituents AS wc
JOIN words AS w USING (word_id)
JOIN character_nodes AS n USING (codepoint)
WHERE n.in_top_2000 = 0
ORDER BY w.frequency_rank, wc.ordinal
LIMIT 50;
