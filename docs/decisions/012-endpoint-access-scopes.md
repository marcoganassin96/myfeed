# ADR-012: MDG Endpoint Access Scopes (Public / User / Admin)

## Context

MDG exposes ~25 endpoints across Topics, NewsEvents, Newsletters, Subscriptions, and Interactions.
Currently there is zero authorization — any caller can hit any endpoint.
Before building the Laravel admin panel we need a stable, documented contract for which
endpoints each caller type is allowed to reach.

Three caller types exist:
- **Public** — unauthenticated (browser, any client)
- **User** — authenticated end-user, identified by `X-User-Id` header
- **Admin** — Laravel admin panel, identified by `X-Admin-Token` shared secret

A fourth caller (FastAPI newsletter-serving layer) is equivalent to "user" for read
endpoints and is out of scope here.

---

## Options Considered

### Option A — Single controller per resource, route-level guards
Keep one `NewsletterController` etc.; annotate each method with a guard attribute.

**Rejected:** Guard annotations are easy to forget on new methods; mixing user-context
code and admin code in the same class increases cognitive load and risk of scope leak.

### Option B — Split controllers by role per resource (chosen)
`UserNewsletterController` owns user-scoped routes; `AdminNewsletterController` owns
admin-scoped routes. Public routes live in the user controller (no guard needed).

**Chosen:** Role is visible at the file level; admin controllers can be protected by a
single route-prefix listener without per-method configuration; each class has one
responsibility.

---

## Decision

### Access scope per endpoint

| Method | Path | Scope | Auth mechanism | Notes |
|--------|------|-------|----------------|-------|
| GET | /master-data/topics | **Public** | none | User browses topics before subscribing |
| GET | /master-data/topics/{id} | **Public** | none | |
| POST | /master-data/admin/topics | **Admin** | X-Admin-Token | |
| PUT | /master-data/admin/topics/{id} | **Admin** | X-Admin-Token | |
| DELETE | /master-data/admin/topics/{id} | **Admin** | X-Admin-Token | |
| GET | /master-data/news-events | **User** | X-User-Id | Filtered to user's subscribed topics only |
| GET | /master-data/news-events/{id} | **User** | X-User-Id | 403 if user not subscribed to event's topic |
| GET | /master-data/admin/news-events | **Admin** | X-Admin-Token | Unfiltered — all events |
| GET | /master-data/admin/news-events/{id} | **Admin** | X-Admin-Token | Unrestricted |
| POST | /master-data/admin/news-events | **Admin** | X-Admin-Token | |
| PUT | /master-data/admin/news-events/{id} | **Admin** | X-Admin-Token | |
| DELETE | /master-data/admin/news-events/{id} | **Admin** | X-Admin-Token | |
| GET | /master-data/newsletters | **User** | X-User-Id | Filtered to user's subscribed topics only |
| GET | /master-data/newsletters/{id} | **User** | X-User-Id | 403 if user not subscribed to newsletter's topic |
| GET | /master-data/admin/newsletters | **Admin** | X-Admin-Token | Unfiltered — all newsletters |
| GET | /master-data/admin/newsletters/{id} | **Admin** | X-Admin-Token | Unrestricted |
| POST | /master-data/admin/newsletters | **Admin** | X-Admin-Token | |
| PUT | /master-data/admin/newsletters/{id} | **Admin** | X-Admin-Token | |
| DELETE | /master-data/admin/newsletters/{id} | **Admin** | X-Admin-Token | |
| POST | /master-data/subscriptions | **User** | X-User-Id | User subscribes to a topic |
| GET | /master-data/subscriptions | **User** | X-User-Id | User's own subscriptions only |
| DELETE | /master-data/subscriptions/{topicId} | **User** | X-User-Id | User removes own subscription |
| GET | /master-data/admin/subscriptions | **Admin** | X-Admin-Token | All subscriptions across all users |
| DELETE | /master-data/admin/subscriptions/{userId}/{topicId} | **Admin** | X-Admin-Token | Force-delete any subscription |
| POST | /master-data/interactions | **User** | X-User-Id | User records own interaction |
| GET | /master-data/admin/interactions | **Admin** | X-Admin-Token | All interactions — renamed from /interactions |

### Auth mechanisms

**X-User-Id:** Header injected by the upstream gateway (FastAPI or future API gateway).
MDG trusts it — no signature verification at MDG layer (network isolation per ADR-005).

**X-Admin-Token:** Shared secret stored in MDG env var `ADMIN_TOKEN`.
Checked by a Symfony `KernelEvents::REQUEST` listener on every request whose path
contains `/admin/`. Returns 401 JSON on mismatch or absence.
Laravel panel sends it as `X-Admin-Token: <secret>` on every request to MDG.

### What is NOT decided here

- Signature/JWT validation for X-User-Id (deferred — ADR-005 network isolation is the current guarantee)
- Per-user rate limiting
- Audit logging of admin mutations

---

## Usage

```bash
# Public — no header needed
curl http://localhost:9000/master-data/topics

# User — X-User-Id required
curl http://localhost:9000/master-data/newsletters \
  -H "X-User-Id: user-abc"

# Admin — X-Admin-Token required
curl -X POST http://localhost:9000/master-data/admin/newsletters \
  -H "X-Admin-Token: supersecret" \
  -H "Content-Type: application/json" \
  -d '{"topic_id":"...","date":"2026-06-09","title":"T","narrative":"N"}'
```

---

## Consequences

- Admin routes must be migrated to `/admin/` prefix before Laravel panel is built (stable contract)
- User read endpoints (news-events, newsletters) currently return unfiltered data — subscription filtering is a Phase 2 backlog item
- One `KernelEvents::REQUEST` listener covers all admin protection with zero per-route config
- Controller split (`User*Controller` / `Admin*Controller`) enforces scope at class level, not annotation level
