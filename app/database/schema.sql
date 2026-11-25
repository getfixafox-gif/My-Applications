-- My Applications schema, version 1.
-- Every user object is identified by a UUID string.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    id          TEXT PRIMARY KEY NOT NULL,
    name        TEXT NOT NULL,
    name_key    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_name_key
    ON categories (name_key);

CREATE TABLE IF NOT EXISTS tags (
    id          TEXT PRIMARY KEY NOT NULL,
    name        TEXT NOT NULL,
    name_key    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_name_key
    ON tags (name_key);

CREATE TABLE IF NOT EXISTS entries (
    id           TEXT PRIMARY KEY NOT NULL,
    title        TEXT NOT NULL,
    title_key    TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    type         TEXT NOT NULL DEFAULT '',
    category_id  TEXT REFERENCES categories (id) ON DELETE SET NULL,
    image_path   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_title_key ON entries (title_key);
CREATE INDEX IF NOT EXISTS idx_entries_updated_at ON entries (updated_at);
CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries (created_at);
CREATE INDEX IF NOT EXISTS idx_entries_category ON entries (category_id);

CREATE TABLE IF NOT EXISTS links (
    id          TEXT PRIMARY KEY NOT NULL,
    entry_id    TEXT NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_links_entry_position ON links (entry_id, position);

CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id  TEXT NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    tag_id    TEXT NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    PRIMARY KEY (entry_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_entry_tags_tag ON entry_tags (tag_id);

CREATE TABLE IF NOT EXISTS app_meta (
    key    TEXT PRIMARY KEY NOT NULL,
    value  TEXT NOT NULL
);
