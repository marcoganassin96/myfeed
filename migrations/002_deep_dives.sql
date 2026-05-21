CREATE TABLE deep_dives (
    event_id   UUID        PRIMARY KEY REFERENCES news_events ON DELETE CASCADE,
    chunks     JSONB       NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
