-- wirecache schema
-- Applied via: wirecache init (or automatically on first DB command)

CREATE TABLE IF NOT EXISTS stories (
    id            SERIAL          PRIMARY KEY,
    url           TEXT            UNIQUE NOT NULL,
    title         TEXT,
    summary       TEXT,
    source        TEXT,
    categories    TEXT[],
    published     TIMESTAMPTZ,
    fetched_at    TIMESTAMPTZ     DEFAULT NOW(),

    search_vector TSVECTOR        GENERATED ALWAYS AS (
        to_tsvector(
            'english',
            coalesce(title,   '') || ' ' ||
            coalesce(summary, '')
        )
    ) STORED
);

CREATE INDEX IF NOT EXISTS stories_search_idx
    ON stories USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS stories_published_idx
    ON stories (published DESC);

CREATE INDEX IF NOT EXISTS stories_categories_idx
    ON stories USING GIN (categories);

CREATE INDEX IF NOT EXISTS stories_fetched_idx
    ON stories (fetched_at);
