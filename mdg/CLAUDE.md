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

> Full standards to be added after `docs/backlog/claude-md-php-workflow.md` items 9.2–9.7 are implemented.
> See backlog for: PHPStan gate, explicit typing, mandatory docblocks, exception handling, two-path evaluation.

### What is settled now

- PHP 8.4 minimum — use all available native type declarations
- PHPStan level 7 is the static analysis gate; never lower it
- PSR-4 autoloading: `App\` → `src/`, `App\Tests\` → `tests/`

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
