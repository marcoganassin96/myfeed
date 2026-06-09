# Laravel Admin Panel — Design Spec

**Date:** 2026-06-08
**Scope:** Add a Laravel + Filament v3 admin panel service (`admin/`) to the monorepo. Didactic goal: learn Laravel-native auth, Eloquent, Filament CRUD, and HTTP client patterns. No real user data — all seeded mock data.

**Related ADRs:** ADR-010 (Breeze auth), ADR-011 (dual data access pattern), ADR-012 (endpoint access scopes)

---

## 1. Goal

Provide a browser-based admin UI for content editors to view and manage all newsletter domain entities (Topics, NewsEvents, Newsletters, Subscriptions, Interactions). Auth is handled natively by Laravel Breeze. Domain data is owned exclusively by MDG and accessed via HTTP.

---

## 2. Architecture

### Bounded Contexts

| Context | Owner | Access |
|---|---|---|
| Admin identity (`admins` table) | Laravel | Direct Eloquent |
| Domain data (all other tables) | MDG / Doctrine | `MdgApiClient` → HTTP |

### Component Diagram

```
Browser → admin:8080
               │
    ┌──────────▼──────────────────────────┐
    │  Laravel Admin (admin/)             │
    │  PHP 8.4 · Laravel 11 · Filament v3 │
    │  Breeze auth (sessions/cookies)     │
    │                                     │
    │  Eloquent ──────► admins table      │
    │  MdgApiClient ──► mdg:9000 (HTTP)   │
    └──────────────────────────────────────┘
                    │
           ┌────────▼────────┐
           │   mdg:9000      │
           │ Symfony / MDG   │
           │ Doctrine ORM    │
           └────────┬────────┘
                    │
           ┌────────▼────────┐
           │  postgres:5432  │
           │  admins         │ ← Laravel migrations
           │  domain tables  │ ← Doctrine migrations
           └─────────────────┘
```

### Repo Location

`admin/` at monorepo root — sibling to `newsletter/`, `mdg/`, `load_tests/`.

---

## 3. MDG Changes (prerequisite)

Nelmio API doc bundle already installed. All new endpoints follow existing OA annotation pattern.

**Access scope model (ADR-012):** Three caller types — Public (no auth), User (X-User-Id header), Admin (X-Admin-Token header). All `/master-data/admin/*` paths are guarded by `AdminTokenListener` which returns 401 JSON when the header is absent or wrong.

### Controller Split by Role

Controllers are split by access scope. Each class has one responsibility.

#### `TopicController` — Public reads

| Method | Path | Scope |
|---|---|---|
| GET | `/master-data/topics` | Public |
| GET | `/master-data/topics/{id}` | Public |

#### `AdminTopicController` — Admin mutations

| Method | Path | Scope |
|---|---|---|
| POST | `/master-data/admin/topics` | Admin |
| PUT | `/master-data/admin/topics/{id}` | Admin |
| DELETE | `/master-data/admin/topics/{id}` | Admin |

#### `NewsEventController` — User reads

| Method | Path | Scope |
|---|---|---|
| GET | `/master-data/news-events` | User |
| GET | `/master-data/news-events/{id}` | User |

#### `AdminNewsEventController` — Admin full CRUD

| Method | Path | Scope |
|---|---|---|
| GET | `/master-data/admin/news-events` | Admin |
| GET | `/master-data/admin/news-events/{id}` | Admin |
| POST | `/master-data/admin/news-events` | Admin |
| PUT | `/master-data/admin/news-events/{id}` | Admin |
| DELETE | `/master-data/admin/news-events/{id}` | Admin |

#### `NewsletterController` — User reads (unchanged)

| Method | Path | Scope |
|---|---|---|
| GET | `/master-data/newsletters` | User |
| GET | `/master-data/newsletters/{id}` | User |

#### `AdminNewsletterController` — Admin full CRUD

| Method | Path | Scope |
|---|---|---|
| GET | `/master-data/admin/newsletters` | Admin |
| GET | `/master-data/admin/newsletters/{id}` | Admin |
| POST | `/master-data/admin/newsletters` | Admin |
| PUT | `/master-data/admin/newsletters/{id}` | Admin |
| DELETE | `/master-data/admin/newsletters/{id}` | Admin |

#### `InteractionController` — User write (unchanged)

| Method | Path | Scope |
|---|---|---|
| POST | `/master-data/interactions` | User |

#### `AdminInteractionController` — Admin read

| Method | Path | Scope |
|---|---|---|
| GET | `/master-data/admin/interactions` | Admin |

#### `AdminSubscriptionController` — Admin (already correct)

| Method | Path | Scope |
|---|---|---|
| GET | `/master-data/admin/subscriptions` | Admin |
| DELETE | `/master-data/admin/subscriptions/{userId}/{topicId}` | Admin |

### New EventListener

`AdminTokenListener` — `KernelEvents::REQUEST` priority 20 (runs before `UserContextListener` at priority 10). Checks `X-Admin-Token` header against `ADMIN_TOKEN` env var on all paths containing `/admin/`. Returns `{"error":"Unauthorized"}` 401 JSON on mismatch.

### New / Modified MDG Services and Repositories

- `TopicService` + `TopicRepository` — already implemented ✓
- `NewsEventService` + `NewsEventRepository` — already implemented ✓
- `AdminSubscriptionService` + `AdminSubscriptionRepository` — already implemented ✓
- `InteractionService` + `InteractionRepository` — already implemented ✓
- `NewsletterService::listAll()` + `NewsletterRepository::findAll()` — **add**: admin needs unfiltered list

---

## 4. Laravel Admin App

### Stack

| Layer | Choice |
|---|---|
| Runtime | PHP 8.4, Docker |
| Framework | Laravel 11 |
| Admin UI | Filament v3 |
| Auth | Laravel Breeze (blade stack) |
| HTTP client | Laravel `Http` facade (built-in) |
| DB access | Eloquent (admins table only) |

### File Structure

```
admin/
  app/
    Http/
      Controllers/        # Breeze auth controllers only
    Models/
      Admin.php           # Eloquent model — admins table
    Services/
      MdgApiClient.php    # Http facade wrapper → MDG
    DTOs/
      TopicDto.php
      NewsletterDto.php
      NewsEventDto.php
      SubscriptionDto.php
      InteractionDto.php
    Filament/
      Resources/
        TopicResource.php
        NewsletterResource.php
        NewsEventResource.php
        SubscriptionResource.php
        InteractionResource.php
  database/
    migrations/
      xxxx_create_admins_table.php
  resources/views/         # Breeze blade views
  docker/
    Dockerfile
  .env.example
  CLAUDE.md
```

### Auth

- Laravel Breeze blade stack
- `users` table renamed to `admins` in migration; model is `Admin`; `config/auth.php` guard renamed from `web` to `admin`
- All Filament panel routes protected by `auth` middleware
- Seeded with one default admin via `AdminSeeder`: `admin@newsletter.local` / `password` (dev only)

### MdgApiClient

Single service class. Base URL from `MDG_URL` env var (default `http://mdg:9000`). All methods return typed DTOs, never `mixed`.

```php
class MdgApiClient
{
    // Base URL from MDG_URL env var (default http://mdg:9000)
    // Admin token from ADMIN_TOKEN env var — sent as X-Admin-Token header on all /admin/ calls
    public function __construct(private string $baseUrl, private string $adminToken) {}

    // --- Public (no auth) ---

    /** @return list<TopicDto> */
    public function getTopics(): array                                   // GET /master-data/topics

    public function getTopic(string $id): TopicDto                       // GET /master-data/topics/{id}

    // --- Admin topics (/admin/ prefix, X-Admin-Token header) ---

    public function createTopic(TopicDto $data): TopicDto                // POST /master-data/admin/topics
    public function updateTopic(string $id, TopicDto $data): TopicDto    // PUT  /master-data/admin/topics/{id}
    public function deleteTopic(string $id): void                        // DELETE /master-data/admin/topics/{id}

    // --- Admin newsletters ---

    /** @return list<NewsletterDto> */
    public function getNewsletters(): array                              // GET /master-data/admin/newsletters

    public function getNewsletter(string $id): NewsletterDto             // GET /master-data/admin/newsletters/{id}
    public function createNewsletter(NewsletterDto $data): NewsletterDto // POST /master-data/admin/newsletters
    public function updateNewsletter(string $id, NewsletterDto $data): NewsletterDto // PUT
    public function deleteNewsletter(string $id): void                   // DELETE /master-data/admin/newsletters/{id}

    // --- Admin news events ---

    /** @return list<NewsEventDto> */
    public function getNewsEvents(): array                               // GET /master-data/admin/news-events

    public function getNewsEvent(string $id): NewsEventDto               // GET /master-data/admin/news-events/{id}
    public function createNewsEvent(NewsEventDto $data): NewsEventDto    // POST /master-data/admin/news-events
    public function updateNewsEvent(string $id, NewsEventDto $data): NewsEventDto // PUT
    public function deleteNewsEvent(string $id): void                    // DELETE /master-data/admin/news-events/{id}

    // --- Admin subscriptions ---

    /** @return list<SubscriptionDto> */
    public function getSubscriptions(): array                            // GET /master-data/admin/subscriptions

    // Both userId and topicId required — admin delete bypasses user context
    public function deleteSubscription(string $userId, string $topicId): void  // DELETE /master-data/admin/subscriptions/{userId}/{topicId}

    // --- Admin interactions ---

    /** @return list<InteractionDto> */
    public function getInteractions(): array                             // GET /master-data/admin/interactions
}
```

### DTOs

PHP 8.2+ readonly classes. One per domain entity. Example:

```php
readonly class TopicDto
{
    public function __construct(
        public string $id,
        public string $name,
        public ?string $description,
    ) {}

    public static function fromArray(array $data): self
    {
        return new self(
            id: $data['id'],
            name: $data['name'],
            description: $data['description'] ?? null,
        );
    }

    public function toArray(): array
    {
        return ['name' => $this->name, 'description' => $this->description];
    }
}
```

### Filament Resources

All 5 resources follow the same pattern. Since MDG returns plain arrays (not Eloquent models), each resource uses Filament v3's `->records(fn() => ...)` table data source backed by `MdgApiClient`. Create/Edit forms call `MdgApiClient` mutations via `handleRecordCreation()` / `handleRecordUpdate()` / `handleRecordDeletion()` overrides on the page classes.

| Resource | Operations | Notes |
|---|---|---|
| `TopicResource` | List, Create, Edit, Delete | Full CRUD |
| `NewsletterResource` | List, View, Create, Edit, Delete | Full CRUD |
| `NewsEventResource` | List, Create, Edit, Delete | Full CRUD |
| `SubscriptionResource` | List, Delete | No create (users subscribe via app) |
| `InteractionResource` | List | Read-only; no mutations |

---

## 5. Local Development

### docker-compose additions

```yaml
admin:
  build: ./admin
  ports:
    - "8080:80"
  environment:
    APP_ENV: local
    APP_KEY: base64:...
    DB_HOST: postgres
    DB_DATABASE: newsletter
    DB_USERNAME: newsletter
    DB_PASSWORD: newsletter
    MDG_URL: http://mdg:9000
  depends_on:
    postgres:
      condition: service_healthy
    mdg:
      condition: service_started
```

### Startup sequence

```bash
docker-compose up -d
# MDG runs migrations (Doctrine) — domain tables
# Laravel runs migrations — admins table only
# Seed admin user: php artisan db:seed
# Access admin panel: http://localhost:8080/admin
```

---

## 6. Error Handling

| Scenario | Handling |
|---|---|
| MDG unreachable | `MdgApiClient` throws `MdgApiException`; Filament shows error notification |
| MDG returns 404 | `MdgApiClient` returns `null`; resource redirects to list with not-found notice |
| MDG returns 4xx | `MdgApiClient` throws `MdgApiException` with response body; Filament form shows validation errors |
| MDG returns 5xx | `MdgApiClient` throws `MdgApiException`; Filament shows generic error notification |
| Admin not authenticated | Laravel redirects to `/login` |

---

## 7. Testing

### Laravel admin

- Feature tests on `MdgApiClient` using `Http::fake()` — no real MDG needed
- Filament resource tests via `Livewire::test()` with mocked `MdgApiClient`
- No DB fixtures for domain data in Laravel tests — all mocked via `Http::fake()`

### MDG (new endpoints)

- Unit tests for `TopicService`, `NewsEventService` (mock repositories)
- Controller integration tests for all new endpoints
- PHPStan level 7 zero errors — required before commit

---

## 8. Out of Scope

- Terraform / Fargate deployment of admin service (local only for now)
- Role-based access control within Filament (single admin role)
- Newsletter scheduling / dispatch (future queue feature)
- Thread or NewsletterEvent management (join-table complexity deferred)
