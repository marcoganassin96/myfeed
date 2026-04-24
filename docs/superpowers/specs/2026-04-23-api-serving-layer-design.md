# API / Serving Layer — Design Spec

**Date:** 2026-04-23
**Scope:** API / Serving Layer with mocked data for load testing. Real data integration (NLP pipeline, LLM generation) is out of scope for this phase.

---

## 1. Goal

Build and load-test the API / Serving Layer before any real data pipeline exists. All data is seeded via a mock script. The layer must sustain **1,000 requests per second** with **p95 < 200ms** on the mixed-realistic scenario, while remaining cost-efficient at off-peak hours (near-zero idle cost).

---

## 2. Architecture

### Stack

| Component | Choice | Reason |
|---|---|---|
| Cloud | AWS | Managed scaling, native Lambda integrations |
| API runtime | Lambda + API Gateway (REST) | Serverless, scales to zero at idle, no cluster ops |
| Auth | AWS Cognito User Pool | Native API Gateway authorizer, zero auth code |
| Cache | ElastiCache Serverless (Redis) | Sub-10ms newsletter reads, TTL-based invalidation |
| Database | Aurora Serverless v2 (PostgreSQL) | Relational schema fits thread/event/newsletter relationships; scales to 0 ACUs at idle |
| Connection pooling | RDS Proxy | Manages Lambda→Aurora connection bursts |
| Deep-dive delivery | Lambda Response Streaming (SSE) | Streams mock chunks to client; no polling needed |

### Component Diagram

```
Client (Web / Mobile)
       │ HTTPS
       ▼
AWS Cognito  ◄── JWT issuance / token refresh
       │ Bearer token on every request
       ▼
API Gateway (REST)
  Cognito Authorizer · throttle 1,000 req/s
       │ routes per domain
       ├──► λ newsletters      GET /newsletters, GET /newsletters/{id}
       ├──► λ subscriptions    GET/POST/DELETE /subscriptions
       ├──► λ interactions     POST /interactions
       └──► λ deep-dive        POST /deep-dive/{event_id}  [Response Streaming]

┌─ VPC ──────────────────────────────────────────────────┐
│  ElastiCache Serverless (Redis)   Aurora Serverless v2  │
│  Newsletter read cache · TTL 1h   PostgreSQL · RDS Proxy│
└────────────────────────────────────────────────────────┘
```

### Lambda functions

| Function | Trigger | Notes |
|---|---|---|
| `newsletters` | API Gateway | Checks Redis first; falls back to Aurora on miss |
| `subscriptions` | API Gateway | Direct Aurora reads/writes; no cache |
| `interactions` | API Gateway | Append-only Aurora write |
| `deep-dive` | API Gateway (streaming) | Streams synthetic SSE chunks with artificial delay (mock phase) |

---

## 3. API Endpoints

All endpoints require `Authorization: Bearer <cognito_jwt>`. The `user_id` is extracted from the JWT `sub` claim — never passed as a request parameter.

### Newsletters

| Method | Path | Description | Cache |
|---|---|---|---|
| GET | `/newsletters` | Latest newsletter per subscribed topic for the calling user | Redis · TTL 1h |
| GET | `/newsletters/{newsletter_id}` | Full newsletter by ID | Redis · TTL 1h |

### Subscriptions

| Method | Path | Description | Cache |
|---|---|---|---|
| GET | `/subscriptions` | List user's topic subscriptions | No cache |
| POST | `/subscriptions` | Subscribe to a topic `{ topic_id }` | No cache |
| DELETE | `/subscriptions/{topic_id}` | Unsubscribe from a topic | No cache |

### Interactions

| Method | Path | Description | Cache |
|---|---|---|---|
| POST | `/interactions` | Record interaction `{ event_id, type: "view"\|"click"\|"deep_dive" }` | No cache |

### Deep-dive

| Method | Path | Description | Cache |
|---|---|---|---|
| POST | `/deep-dive/{event_id}` | Open SSE stream for on-demand report | No cache |

**SSE event format:**
```
data: {"chunk": "GPT-5.8 was released today...", "done": false}
data: {"chunk": " marking a major leap in reasoning...", "done": false}
data: {"chunk": "", "done": true}
```

In the mock phase the deep-dive Lambda emits pre-written chunks with a configurable inter-chunk delay (default 50ms) to simulate LLM streaming latency.

---

## 4. Data Model (PostgreSQL)

### Entity Relationships

```
topics ──< threads ──< event_thread_memberships >── news_events
topics ──< newsletters ──< newsletter_events >── news_events
newsletters ──< newsletter_context_links >── newsletters
topics ──< subscriptions  (user_id + topic_id)
news_events ──< interactions  (user_id + event_id)
```

### Tables

#### `topics`
```sql
topic_id    UUID        PRIMARY KEY
name        VARCHAR(100) UNIQUE NOT NULL
description TEXT
```

#### `threads`
```sql
thread_id  UUID         PRIMARY KEY
topic_id   UUID         NOT NULL REFERENCES topics
name       VARCHAR(200) NOT NULL
created_at TIMESTAMPTZ  DEFAULT now()

INDEX (topic_id)
```

#### `news_events`
```sql
event_id   UUID         PRIMARY KEY
headline   VARCHAR(300) NOT NULL
summary    TEXT         NOT NULL
date       DATE         NOT NULL
source_url TEXT

-- no thread_id column: membership expressed via event_thread_memberships
```

#### `event_thread_memberships`
```sql
event_id          UUID NOT NULL REFERENCES news_events
thread_id         UUID NOT NULL REFERENCES threads
position          INT  NOT NULL   -- ordinal rank within the thread (1, 2, 3…)
previous_event_id UUID REFERENCES news_events  -- nullable; predecessor in this thread

PRIMARY KEY (event_id, thread_id)
INDEX (thread_id, position)
```

`previous_event_id` is thread-scoped: the same news event can have different predecessors in different threads.

#### `newsletters`
```sql
newsletter_id UUID         PRIMARY KEY
topic_id      UUID         NOT NULL REFERENCES topics
date          DATE         NOT NULL
title         VARCHAR(200) NOT NULL
narrative     TEXT         NOT NULL  -- LLM-generated daily narrative

UNIQUE (topic_id, date)
INDEX  (topic_id, date DESC)
```

#### `newsletter_events`
```sql
newsletter_id  UUID NOT NULL REFERENCES newsletters
event_id       UUID NOT NULL REFERENCES news_events
thread_id      UUID NOT NULL REFERENCES threads  -- which thread context to display for this event in this newsletter
position       INT  NOT NULL                     -- display order within newsletter

PRIMARY KEY (newsletter_id, event_id)
INDEX (newsletter_id, position)
```

`thread_id` is set by the NLP pipeline at newsletter-generation time. It picks the most relevant thread for each event given the newsletter's topic. Without it, the render query would fan out into multiple rows for events that belong to more than one thread.

#### `newsletter_context_links`
```sql
id                  UUID PRIMARY KEY
newsletter_id       UUID NOT NULL REFERENCES newsletters   -- current newsletter
linked_newsletter_id UUID NOT NULL REFERENCES newsletters  -- past newsletter to read
reason              TEXT NOT NULL  -- LLM-generated: why this past edition is relevant
position            INT  NOT NULL  -- display order

INDEX (newsletter_id)
```

#### `subscriptions`
```sql
user_id       VARCHAR NOT NULL   -- Cognito sub claim
topic_id      UUID    NOT NULL REFERENCES topics
subscribed_at TIMESTAMPTZ DEFAULT now()

PRIMARY KEY (user_id, topic_id)
INDEX (user_id)
```

#### `interactions`
```sql
interaction_id UUID        PRIMARY KEY
user_id        VARCHAR     NOT NULL   -- Cognito sub claim
event_id       UUID        NOT NULL REFERENCES news_events
type           VARCHAR     NOT NULL CHECK (type IN ('view', 'click', 'deep_dive'))
created_at     TIMESTAMPTZ DEFAULT now()

INDEX (user_id, created_at DESC)
```

### Key query — full newsletter render

```sql
SELECT
  n.newsletter_id, n.date, n.title, n.narrative,
  ne.position,
  e.event_id, e.headline, e.summary, e.date AS event_date,
  etm.thread_id, t.name AS thread_name,
  etm.previous_event_id
FROM newsletters n
JOIN newsletter_events ne  ON ne.newsletter_id = n.newsletter_id
JOIN news_events e          ON e.event_id = ne.event_id
JOIN event_thread_memberships etm ON etm.event_id = e.event_id AND etm.thread_id = ne.thread_id
JOIN threads t              ON t.thread_id = ne.thread_id
WHERE n.topic_id = $1
  AND n.date     = $2
ORDER BY ne.position, etm.thread_id;
```

Context links fetched in a separate query (small list, always < 5 rows):
```sql
SELECT ncl.reason, ncl.position, n.newsletter_id, n.date, n.title
FROM newsletter_context_links ncl
JOIN newsletters n ON n.newsletter_id = ncl.linked_newsletter_id
WHERE ncl.newsletter_id = $1
ORDER BY ncl.position;
```

---

## 5. Caching Strategy

**Redis key scheme:**
```
newsletter:{newsletter_id}          → full newsletter JSON (TTL 1h)
newsletters:user:{user_id}:latest   → list of newsletter_ids for user's topics (TTL 1h)
```

**Read path:**
1. Check Redis — return immediately on hit
2. On miss: query Aurora, write result to Redis, return

**Invalidation:** TTL-based only. Newsletters are immutable once generated — no explicit cache busting needed.

---

## 6. Mock Data

Seeded by `seed.py` before each load test run. Idempotent (truncates all tables, re-inserts).

| Table | Rows |
|---|---|
| topics | 3 |
| threads | 15 (5 per topic) |
| news_events | 300 (~20 per thread) |
| event_thread_memberships | ~450 (some events span 2 threads) |
| newsletters | 90 (30 days × 3 topics) |
| newsletter_events | 450 (5 events × 90 newsletters) |
| newsletter_context_links | ~180 (2 links per newsletter) |
| subscriptions | ~2,000 (1,000 mock users × avg 2 topics) |
| interactions | 10,000 (historical) |

Redis pre-warmed with the 3 latest newsletters (one per topic) at TTL 1h.

Cognito: 100 real test-user tokens issued at seed time, rotated across k6 virtual users. Auth overhead is included in all latency measurements.

---

## 7. Load Testing Plan

**Tool:** k6

| Scenario | Endpoint mix | VUs | Pass criteria |
|---|---|---|---|
| Newsletter read (cached) | 80% GET /newsletters/{id} | 500 | p99 < 50ms · 0% errors |
| Newsletter read (cache miss) | GET /newsletters/{id} cold | 200 | p99 < 300ms · 0% errors |
| Mixed realistic | 60% newsletter · 30% interactions · 10% subscriptions | 1,000 | 1,000 req/s · p95 < 200ms |
| Deep-dive SSE burst | POST /deep-dive | 50 | First chunk < 500ms · stream completes |
| Cold start stress | Spike 0 → 1,000 VUs in 10s | 1,000 | Error rate < 1% during ramp |

All scenarios must pass before real data integration begins.

The cold start stress test determines whether Lambda **provisioned concurrency** is required. If error rate exceeds 1% during the spike, provisioned concurrency is enabled for the `newsletters` and `deep-dive` functions.

Metrics exported to CloudWatch: p50, p95, p99 latency per endpoint, error rate, Lambda cold start count, Redis hit rate, Aurora ACU utilisation.

---

## 8. Error Handling

| Error | Handling |
|---|---|
| Cognito token expired | API Gateway returns 401; client refreshes token |
| Lambda cold start timeout | API Gateway 504; k6 counts as error; informs provisioned concurrency decision |
| Aurora connection pool exhausted | RDS Proxy queues request up to 30s; Lambda returns 503 if exceeded |
| Redis unavailable | Lambda falls through to Aurora; no error surfaced to client |
| Deep-dive stream interrupted | Client receives partial SSE; `done: true` never arrives; client shows retry prompt |

---

## 9. Out of Scope (this phase)

- NLP/clustering pipeline (assigns events to threads)
- LLM newsletter generation (narrative, context link reasons)
- Real web scraping / source monitoring
- Email delivery
- Frontend / client application
- User & Subscription Service management UI
