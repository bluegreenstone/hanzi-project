PRAGMA application_id = 1212242505;
PRAGMA user_version = 10000;
PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    version TEXT,
    status TEXT NOT NULL,
    source_url TEXT,
    documentation_url TEXT,
    license_id TEXT NOT NULL,
    license_name TEXT,
    license_url TEXT,
    obligation_class TEXT NOT NULL,
    source_json TEXT NOT NULL CHECK (json_valid(source_json))
) WITHOUT ROWID;

CREATE TABLE license_obligations (
    obligation_class TEXT NOT NULL,
    license_id TEXT NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (obligation_class, license_id)
) WITHOUT ROWID;

CREATE TABLE license_profiles (
    profile_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    jsonl_path TEXT NOT NULL,
    parquet_path TEXT NOT NULL,
    profile_json TEXT NOT NULL CHECK (json_valid(profile_json))
) WITHOUT ROWID;

CREATE TABLE license_profile_tables (
    profile_id TEXT NOT NULL REFERENCES license_profiles(profile_id),
    table_name TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    PRIMARY KEY (profile_id, table_name),
    UNIQUE (profile_id, ordinal)
) WITHOUT ROWID;

CREATE TABLE character_nodes (
    codepoint TEXT PRIMARY KEY,
    character TEXT NOT NULL UNIQUE,
    in_top_2000 INTEGER NOT NULL CHECK (in_top_2000 IN (0, 1))
) WITHOUT ROWID;

CREATE TABLE radicals (
    kangxi_number INTEGER PRIMARY KEY CHECK (kangxi_number BETWEEN 1 AND 214),
    primary_char TEXT NOT NULL,
    codepoint TEXT NOT NULL UNIQUE,
    radical_char TEXT NOT NULL,
    stroke_count INTEGER NOT NULL,
    english_definition TEXT,
    semantic_field TEXT,
    character_count_in_kangxi INTEGER,
    character_count_status TEXT,
    example_count INTEGER NOT NULL,
    record_json TEXT NOT NULL CHECK (json_valid(record_json))
);

CREATE TABLE characters (
    codepoint TEXT PRIMARY KEY REFERENCES character_nodes(codepoint),
    traditional TEXT NOT NULL UNIQUE,
    simplified TEXT,
    radical_number INTEGER NOT NULL REFERENCES radicals(kangxi_number),
    residual_strokes INTEGER NOT NULL,
    total_strokes INTEGER NOT NULL,
    frequency_rank INTEGER NOT NULL,
    selection_rank INTEGER NOT NULL UNIQUE,
    frequency_count INTEGER NOT NULL,
    per_million REAL NOT NULL,
    english_translation TEXT,
    kangxi_citation TEXT,
    ids_decomposition TEXT,
    common_word_count INTEGER NOT NULL,
    record_json TEXT NOT NULL CHECK (json_valid(record_json))
) WITHOUT ROWID;

CREATE TABLE words (
    word_id TEXT PRIMARY KEY,
    traditional TEXT NOT NULL,
    simplified TEXT,
    frequency_rank INTEGER NOT NULL UNIQUE,
    frequency_count INTEGER NOT NULL,
    per_million REAL NOT NULL,
    pinyin_text TEXT,
    zhuyin_text TEXT,
    english_definition_text TEXT,
    constituent_count INTEGER NOT NULL,
    record_json TEXT NOT NULL CHECK (json_valid(record_json))
) WITHOUT ROWID;

CREATE TABLE radical_examples (
    kangxi_number INTEGER NOT NULL REFERENCES radicals(kangxi_number),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    codepoint TEXT NOT NULL REFERENCES characters(codepoint),
    PRIMARY KEY (kangxi_number, ordinal),
    UNIQUE (kangxi_number, codepoint)
) WITHOUT ROWID;

CREATE TABLE character_components (
    codepoint TEXT NOT NULL REFERENCES characters(codepoint),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    component_codepoint TEXT NOT NULL REFERENCES characters(codepoint),
    PRIMARY KEY (codepoint, ordinal),
    UNIQUE (codepoint, component_codepoint)
) WITHOUT ROWID;

CREATE TABLE character_common_words (
    codepoint TEXT NOT NULL REFERENCES characters(codepoint),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    word_id TEXT NOT NULL REFERENCES words(word_id),
    PRIMARY KEY (codepoint, ordinal),
    UNIQUE (codepoint, word_id)
) WITHOUT ROWID;

CREATE TABLE word_constituents (
    word_id TEXT NOT NULL REFERENCES words(word_id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    codepoint TEXT NOT NULL REFERENCES character_nodes(codepoint),
    PRIMARY KEY (word_id, ordinal)
) WITHOUT ROWID;

CREATE TABLE readings (
    entity_type TEXT NOT NULL CHECK (entity_type IN ('radical', 'character', 'word')),
    entity_id TEXT NOT NULL,
    scheme TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    reading TEXT NOT NULL,
    context TEXT,
    region TEXT,
    standard TEXT,
    source_entry_ids_json TEXT CHECK (
        source_entry_ids_json IS NULL OR json_valid(source_entry_ids_json)
    ),
    PRIMARY KEY (entity_type, entity_id, scheme, ordinal)
) WITHOUT ROWID;

CREATE TABLE definitions (
    entity_type TEXT NOT NULL CHECK (entity_type IN ('radical', 'character', 'word')),
    entity_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    language TEXT NOT NULL,
    register TEXT,
    definition_text TEXT NOT NULL,
    source_id TEXT,
    source_entry_id TEXT,
    source_entry_indices_json TEXT CHECK (
        source_entry_indices_json IS NULL OR json_valid(source_entry_indices_json)
    ),
    PRIMARY KEY (entity_type, entity_id, ordinal)
) WITHOUT ROWID;

CREATE TABLE taiwan_definitions (
    entity_type TEXT NOT NULL CHECK (entity_type IN ('character', 'word')),
    entity_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    language TEXT NOT NULL,
    register TEXT,
    definition_text TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    source_entry_id TEXT NOT NULL,
    license_id TEXT NOT NULL,
    verbatim INTEGER NOT NULL CHECK (verbatim = 1),
    PRIMARY KEY (entity_type, entity_id, ordinal)
) WITHOUT ROWID;

CREATE TABLE record_field_sources (
    entity_type TEXT NOT NULL CHECK (entity_type IN ('radical', 'character', 'word')),
    entity_id TEXT NOT NULL,
    field_path TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    license_id TEXT NOT NULL,
    obligation_class TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_id, field_path, source_id)
) WITHOUT ROWID;

CREATE TABLE assets (
    asset_id TEXT PRIMARY KEY,
    asset_kind TEXT NOT NULL,
    local_path TEXT NOT NULL UNIQUE,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    license_id TEXT NOT NULL,
    obligation_class TEXT NOT NULL,
    mime_type TEXT,
    sha256 TEXT NOT NULL,
    byte_length INTEGER NOT NULL,
    kangxi_number INTEGER,
    codepoint TEXT,
    asset_json TEXT NOT NULL CHECK (json_valid(asset_json))
) WITHOUT ROWID;

CREATE TABLE search_documents (
    search_id INTEGER PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES license_profiles(profile_id),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('radical', 'character', 'word')),
    entity_id TEXT NOT NULL,
    frequency_rank INTEGER,
    traditional TEXT,
    simplified TEXT,
    pinyin TEXT,
    zhuyin TEXT,
    english TEXT,
    search_text TEXT NOT NULL,
    UNIQUE (profile_id, entity_type, entity_id)
);

CREATE INDEX characters_radical_idx
    ON characters(radical_number, frequency_rank);
CREATE INDEX characters_simplified_idx
    ON characters(simplified);
CREATE INDEX words_traditional_idx
    ON words(traditional, frequency_rank);
CREATE INDEX words_simplified_idx
    ON words(simplified, frequency_rank);
CREATE INDEX radical_examples_codepoint_idx
    ON radical_examples(codepoint);
CREATE INDEX character_common_words_word_idx
    ON character_common_words(word_id);
CREATE INDEX word_constituents_codepoint_idx
    ON word_constituents(codepoint, word_id);
CREATE INDEX character_nodes_scope_idx
    ON character_nodes(in_top_2000, codepoint);
CREATE INDEX readings_lookup_idx
    ON readings(reading, scheme, entity_type);
CREATE INDEX definitions_source_idx
    ON definitions(source_id, entity_type);
CREATE INDEX taiwan_definitions_source_idx
    ON taiwan_definitions(source_id, entity_type);
CREATE INDEX record_field_sources_license_idx
    ON record_field_sources(obligation_class, license_id, entity_type);
CREATE INDEX assets_license_idx
    ON assets(obligation_class, license_id, asset_kind);
CREATE INDEX search_documents_entity_idx
    ON search_documents(entity_type, entity_id, profile_id);

CREATE VIRTUAL TABLE search_fts USING fts5(
    profile_id UNINDEXED,
    entity_type UNINDEXED,
    entity_id UNINDEXED,
    traditional,
    simplified,
    pinyin,
    zhuyin,
    english,
    search_text,
    content = 'search_documents',
    content_rowid = 'search_id',
    tokenize = 'unicode61 remove_diacritics 0'
);

CREATE VIEW v_radical_characters AS
SELECT
    r.kangxi_number,
    r.primary_char AS radical,
    e.ordinal,
    c.codepoint,
    c.traditional,
    c.frequency_rank
FROM radical_examples AS e
JOIN radicals AS r USING (kangxi_number)
JOIN characters AS c USING (codepoint);

CREATE VIEW v_character_words AS
SELECT
    c.codepoint,
    c.traditional AS character,
    cw.ordinal,
    w.word_id,
    w.traditional AS word,
    w.pinyin_text,
    w.frequency_rank
FROM character_common_words AS cw
JOIN characters AS c USING (codepoint)
JOIN words AS w USING (word_id);

CREATE VIEW v_field_license_counts AS
SELECT
    obligation_class,
    license_id,
    entity_type,
    COUNT(*) AS field_source_references
FROM record_field_sources
GROUP BY obligation_class, license_id, entity_type;

CREATE VIEW v_asset_license_counts AS
SELECT
    obligation_class,
    license_id,
    asset_kind,
    COUNT(*) AS asset_count,
    SUM(byte_length) AS total_bytes
FROM assets
GROUP BY obligation_class, license_id, asset_kind;
