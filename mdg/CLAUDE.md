# CLAUDE.md — mdg (PHP/Symfony)

App-specific guidance. Repo-wide rules in root `CLAUDE.md`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | PHP 8.4, Docker |
| Framework | Symfony 7 |
| ORM | Doctrine ORM 3 + Migrations |
| Cache | predis/predis 2 |
| Testing | PHPUnit 11, symfony/test-pack |
| Static analysis | PHPStan (phpstan/phpstan + symfony + doctrine extensions) |

---

## File Structure

```
mdg/
  src/
    Controller/              # Symfony controllers — one per resource
    Service/                 # Business logic — one per resource
    Repository/              # Doctrine repositories — one per entity
    Entity/                  # Doctrine entities
    Cache/                   # CacheService wrapper
    EventListener/           # Symfony event listeners
    DataFixtures/            # Doctrine fixtures (test + local envs)
    Kernel.php
  tests/
    Controller/              # Controller integration tests
    Service/                 # Service unit tests (mocked deps)
    Cache/                   # Cache unit tests
    DataFixtures/            # Fixture tests
  composer.json
  phpunit.xml.dist
  phpstan.neon               # PHPStan config — level 7, targets src/ and tests/
  Dockerfile
```

---

## Validation — Run After Every Code Change

```bash
# Unit + integration tests
cd mdg && composer test

# Static analysis (level 7)
cd mdg && composer phpstan
```

All tests must pass and PHPStan must report zero errors before committing.

---

## PHP Coding Standards

### Static analysis gate

PHPStan level 7 is the floor — never lower it. Zero errors required before committing.

### Explicit types over PHPDoc (9.5)

Always use native PHP 8.x type declarations for parameters, return types, and property types. PHPDoc (`@param`, `@return`) is permitted **only** where native types are insufficient:

```php
// CORRECT — native types
public function getById(string $id): ?array { ... }

// CORRECT — PHPDoc only for generics (native can't express list<Foo>)
/** @return list<array<string, mixed>> */
public function listForUser(string $userId): array { ... }

// WRONG — PHPDoc where native type works
/** @param string $id */
/** @return array|null */
public function getById($id) { ... }
```

### Mandatory docblocks on public API (9.6)

Every public method on Services, Repositories, Controllers, and DTOs requires a one-line docblock. The docblock must explain **why** the pattern exists — not restate the method name.

Focus on: DI injection rationale, Symfony conventions, variadic args, design patterns (factory, decorator), non-obvious constraints.

```php
// CORRECT — explains the DI pattern and why nullable
/** Fetches newsletter by ID; returns null when not found so callers control the 404 response. */
public function getById(string $id): ?array { ... }

// CORRECT — explains why CacheService is injected (not Symfony cache directly)
/** Wraps predis with domain-level TTL defaults; injected so tests can mock without a Redis server. */
public function __construct(
    private readonly CacheService $cache,
    private readonly NewsletterRepository $repo,
) {}

// WRONG — restates the name
/** Gets newsletter by ID. */
public function getById(string $id): ?array { ... }

// WRONG — missing docblock on public Service method
public function listForUser(string $userId): array { ... }
```

Private and internal helpers: docblock only when intent is non-obvious.

### Exception handling (9.4)

Never silently swallow `\Throwable`. Every catch block must do one of:

1. **Re-throw as domain exception** — add context, preserve original as `$previous`
2. **Log + return error response** — for controller boundaries only
3. **Bubble up with context** — wrap and rethrow with additional message

```php
// CORRECT — re-throw with context
try {
    $this->repo->save($entity);
} catch (\Throwable $e) {
    throw new PersistenceException('Failed to save newsletter', previous: $e);
}

// CORRECT — controller boundary: log + respond
try {
    $result = $this->service->getById($id);
} catch (\Throwable $e) {
    $this->logger->error('getById failed', ['id' => $id, 'error' => $e->getMessage()]);
    return $this->json(['error' => 'Internal error'], 500);
}

// WRONG — silent swallow
try {
    $this->cache->set($key, $data);
} catch (\Throwable $e) {
    // ignore
}
```

PHPStan level 7 enforces unchecked throws — use it as first-pass guard.

### PSR-4 autoloading

`App\` → `src/`, `App\Tests\` → `tests/`

---

## Testing Standards

### TDD — test before implementation

1. Write the failing test
2. Run it — confirm it fails with the expected error
3. Write minimal implementation
4. Run again — confirm it passes
5. Commit

### Test structure

Tests live in `tests/` mirroring `src/` structure. Use `PHPUnit\Framework\TestCase` for unit tests, `Symfony\Bundle\FrameworkBundle\Test\WebTestCase` for controller integration tests.

Mock dependencies with `$this->createMock(ClassName::class)` — never instantiate real services with real DB/cache connections in unit tests.

### What to test per service

- Cache hit → repository not called
- Cache miss → repository called, result cached
- Repository returns empty → `null` returned
- Happy path → correct data shape returned
