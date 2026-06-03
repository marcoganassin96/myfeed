# MDG — Replace `mixed` array shapes with typed DTOs

## Motivation

PHPStan work on `feat/phpstan` revealed several places where `array<string, mixed>` and
`list<array<string, mixed>>` are used as return types. These are not truly generic — each
one represents a well-defined data shape (a feed card, a subscription row, an interaction
receipt, etc.) that is implicit rather than named.

Keeping `mixed` as the value type:
- Loses PHPStan's ability to verify field access on callers.
- Forces `@var` assertions at every cache boundary to re-declare the type.
- Makes the data contract readable only by reading the SQL, not the PHP signature.

A typed DTO (readonly class) makes the contract explicit, eliminates `@var` annotations
in service layers, and lets PHPStan verify field access end-to-end.

---

## Implicit DTOs found (`feat/phpstan` snapshot)

| DTO name | Fields | Current type | Used in |
|---|---|---|---|
| `NewsletterSummary` | `newsletterId`, `topicId`, `date`, `title` | `array{...}` (improved) | `NewsletterRepository::findLatestPerTopicForUser`, `NewsletterService::listForUser` |
| `SubscriptionRow` | `topic_id`, `name`, `subscribed_at` | `array<string, mixed>` | `SubscriptionRepository::findByUser`, `SubscriptionRepository::upsert`, `SubscriptionService::listForUser`, `SubscriptionService::subscribe` |
| `InteractionResult` | `interaction_id`, `created_at` | `array<string, mixed>` | `InteractionRepository::save`, `InteractionService::record` |
| `DeepDiveData` | `chunks: list<string>` | `array<string, mixed>` | `DeepDiveService::get` |
| `NewsletterDetail` | `newsletter_id`, `date`, `title`, `narrative`, `events: list<NewsletterEvent>`, `context_links: list<ContextLink>` | `array<string, mixed>` | `NewsletterService::getById` |
| `NewsletterEvent` | `position`, `event_id`, `headline`, `summary`, `event_date`, `thread_id`, `thread_name`, `previous_event_id` | `array<string, mixed>` (nested) | inside `NewsletterDetail` |
| `ContextLink` | `reason`, `position`, `newsletter_id`, `date`, `title` | `array<string, mixed>` (nested) | inside `NewsletterDetail` |

**Not in scope:** `CacheService::get()` / `set()` stay as `array<string, mixed>` — the cache
layer is intentionally generic. DTOs live above it, in the service layer.

---

## Implementation plan

Work bottom-up: simple, self-contained DTOs first. Each DTO resolves its `TODO` and the
`@var` assertion in the service layer that re-declares the type after cache retrieval.

### 8.1 — `NewsletterSummary` *(resolves `TODO` in `NewsletterRepository`)*

```php
// src/Dto/NewsletterSummary.php
final readonly class NewsletterSummary {
    public function __construct(
        public string $newsletterId,
        public string $topicId,
        public string $date,
        public string $title,
    ) {}
}
```

Changes:
- `NewsletterRepository::findLatestPerTopicForUser` — map `getArrayResult()` rows to `list<NewsletterSummary>`.
- `NewsletterService::listForUser` — return type `list<NewsletterSummary>`; drop `@var` assertion on cached value.
- Update cache `@var` in service to `list<NewsletterSummary>|null`.

### 8.2 — `SubscriptionRow`

```php
final readonly class SubscriptionRow {
    public function __construct(
        public string $topicId,
        public string $name,
        public string $subscribedAt,
    ) {}
}
```

Changes:
- `SubscriptionRepository::findByUser` — map DBAL rows; return `list<SubscriptionRow>`.
- `SubscriptionRepository::upsert` — map single row; return `SubscriptionRow`.
- `SubscriptionService::listForUser`, `subscribe` — propagate new types.

### 8.3 — `InteractionResult`

```php
final readonly class InteractionResult {
    public function __construct(
        public string $interactionId,
        public string $createdAt,
    ) {}
}
```

Changes:
- `InteractionRepository::save` — map DBAL row; return `InteractionResult`.
- `InteractionService::record` — propagate.

### 8.4 — `DeepDiveData`

```php
final readonly class DeepDiveData {
    /** @param list<string> $chunks */
    public function __construct(
        public array $chunks,
    ) {}
}
```

Changes:
- `DeepDiveService::get` — wrap `['chunks' => ...]` in `DeepDiveData`; return `DeepDiveData|null`.
- Update cache `@var` accordingly.

### 8.5 — `NewsletterDetail` (+ `NewsletterEvent`, `ContextLink`) *(complex, do last)*

Three DTOs. `NewsletterService::getById` builds the result from raw DBAL rows; the
mapping logic moves into a private method or a dedicated assembler.

```php
final readonly class NewsletterEvent { ... }   // 8 fields
final readonly class ContextLink { ... }       // 5 fields
final readonly class NewsletterDetail { ... }  // newsletter_id, date, title, narrative,
                                               // list<NewsletterEvent>, list<ContextLink>
```

Changes:
- `NewsletterRepository::findByIdWithEvents` — keep raw DBAL return (intermediate shape), or
  map to typed arrays and let the service assemble `NewsletterDetail`.
- `NewsletterService::getById` — assemble and return `NewsletterDetail|null`.

---

## Propagation note

Each DTO replacement also touches controllers that consume the service return value.
Check controller `JsonResponse` serialisation: `json_encode` on a `readonly` class
requires `(array)` cast or a `toArray()` method, since `json_encode` does not read
public readonly properties by default in all PHP versions. Verify behaviour with
`JsonResponse` before closing each item.
