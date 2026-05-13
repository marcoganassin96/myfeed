-- migrations/001_initial_schema.sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE topics (
    topic_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE threads (
    thread_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id   UUID         NOT NULL REFERENCES topics ON DELETE CASCADE,
    name       VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_threads_topic_id ON threads (topic_id);

CREATE TABLE news_events (
    event_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    headline   VARCHAR(300) NOT NULL,
    summary    TEXT         NOT NULL,
    date       DATE         NOT NULL,
    source_url TEXT
);

CREATE TABLE event_thread_memberships (
    event_id          UUID NOT NULL REFERENCES news_events ON DELETE CASCADE,
    thread_id         UUID NOT NULL REFERENCES threads ON DELETE CASCADE,
    position          INT  NOT NULL,
    previous_event_id UUID REFERENCES news_events ON DELETE SET NULL,
    PRIMARY KEY (event_id, thread_id)
);
CREATE INDEX idx_etm_thread_position ON event_thread_memberships (thread_id, position);

CREATE TABLE newsletters (
    newsletter_id UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id      UUID         NOT NULL REFERENCES topics ON DELETE CASCADE,
    date          DATE         NOT NULL,
    title         VARCHAR(200) NOT NULL,
    narrative     TEXT         NOT NULL,
    UNIQUE (topic_id, date)
);
CREATE INDEX idx_newsletters_topic_date ON newsletters (topic_id, date DESC);

CREATE TABLE newsletter_events (
    newsletter_id UUID NOT NULL REFERENCES newsletters ON DELETE CASCADE,
    event_id      UUID NOT NULL REFERENCES news_events ON DELETE CASCADE,
    thread_id     UUID NOT NULL REFERENCES threads ON DELETE CASCADE,
    position      INT  NOT NULL,
    PRIMARY KEY (newsletter_id, event_id)
);
CREATE INDEX idx_newsletter_events_nl_pos ON newsletter_events (newsletter_id, position);

CREATE TABLE newsletter_context_links (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    newsletter_id        UUID NOT NULL REFERENCES newsletters ON DELETE CASCADE,
    linked_newsletter_id UUID NOT NULL REFERENCES newsletters ON DELETE CASCADE,
    reason               TEXT NOT NULL,
    position             INT  NOT NULL
);
CREATE INDEX idx_ncl_newsletter_id ON newsletter_context_links (newsletter_id);

CREATE TABLE subscriptions (
    user_id       VARCHAR     NOT NULL,
    topic_id      UUID        NOT NULL REFERENCES topics ON DELETE CASCADE,
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, topic_id)
);
CREATE INDEX idx_subscriptions_user_id ON subscriptions (user_id);

CREATE TABLE interactions (
    interaction_id UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        VARCHAR     NOT NULL,
    event_id       UUID        NOT NULL REFERENCES news_events ON DELETE CASCADE,
    type           VARCHAR(20) NOT NULL CHECK (type IN ('view', 'click', 'deep_dive')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_interactions_user_date ON interactions (user_id, created_at DESC);
