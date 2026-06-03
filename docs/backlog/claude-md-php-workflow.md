# Backlog: CLAUDE.md PHP Workflow Improvements

**Area:** Developer workflow / CLAUDE.md  
**Status:** Open  
**Raised:** 2026-06-03

---

## Context

CLAUDE.md currently covers Python/FastAPI patterns well but lacks guidance for PHP/MDG work. As PHPStan integration matures (now at level 7 on branch `feat/phpstan`) and the MDG codebase grows, the following standards should be codified in CLAUDE.md so Claude Code enforces them automatically on every PHP task.

---

## Items

### 9.1 — PHP_CodeSniffer integration

Add to CLAUDE.md:

- Run `composer phpcs` (or equivalent) after every PHP file change.
- Standard: PSR-12.
- Zero violations before committing.

**Why not now:** PHP CS Fixer is tracked in [php-code-quality.md](php-code-quality.md) (item 4.2). Resolve tooling choice (PHPCS vs CS Fixer) there first, then document winner in CLAUDE.md.

---

### 9.2 — PHPStan in validation checklist

Add to CLAUDE.md `## Validation — Run After Every Code Change`:

```bash
# PHP static analysis (run from repo root or mdg/)
cd mdg && composer phpstan
```

Target level: 7 (current branch goal). Bump to 8+ tracked in [php-code-quality.md](php-code-quality.md).

---

### 9.3 — Pre-commit hook: tests + linting

Add to CLAUDE.md:

Before every commit, Claude Code must run:

1. `cd newsletter && pytest tests/ -v` — Python unit tests
2. `cd mdg && composer phpstan` — PHP static analysis
3. `cd mdg && composer phpcs` (once tooling is settled) — PHP coding standards

Block the commit if any step fails. Document this as a non-negotiable gate, same as the existing Python checklist.

---

### 9.4 — Exception handling standard

Add to CLAUDE.md PHP Coding Standards section:

- Always handle exceptions explicitly. Never silently swallow `\Throwable`.
- Acceptable patterns: re-throw as domain exception, log + return error response, or bubble up with added context.
- PHPStan level 7 enforces unchecked throws — use it as a first-pass guard.

---

### 9.5 — Explicit typing over PHPDoc

Add to CLAUDE.md PHP Coding Standards section:

- Always use native PHP 8.x type declarations (parameter types, return types, property types) instead of `@param`/`@return` PHPDoc where the language supports it.
- PHPDoc is permitted only for generics/templates (`@var list<Foo>`, `@template`) where native types are insufficient.
- Rationale: PHPStan reads both, but native types are enforced by the runtime and easier for reviewers to read.

---

### 9.6 — Docstrings on public API

Add to CLAUDE.md PHP Coding Standards section:

- All public methods on Services, Repositories, Controllers, and DTOs require a one-line docblock describing **what** the method does (not **how**).
- Private/internal helpers: docblock only when the intent is non-obvious.
- Format: `/** One sentence. */` — no `@param`/`@return` unless type cannot be expressed natively.

---

### 9.7 — Two-path solution evaluation

Add to CLAUDE.md `## Development Workflow` or a new `## Decision Process` section:

For every non-trivial PHP (or Python) task, evaluate two approaches before writing code:

| Path | Description |
|------|-------------|
| **Ideal Design** | Best possible architecture ignoring current implementation. |
| **Pragmatic Implementation** | Smallest change to current code that minimises regression risk. |

Steps:

1. Write a short pros/cons table for both paths.
2. Present to user and ask which to pursue.
3. If **Pragmatic** is chosen: implement it, then immediately create a backlog entry in `docs/backlog/` documenting the ideal design and the deferred technical debt.
4. If **Ideal** is chosen: implement it directly; no backlog entry needed.

This mirrors the existing brainstorming skill workflow but makes the trade-off explicit for every task, not just new features.

---

## Implementation Notes

- Items 9.1–9.3 depend on settling the PHPCS vs CS Fixer choice (see [php-code-quality.md](php-code-quality.md) item 4.2).
- Items 9.4–9.6 can be added to CLAUDE.md immediately once PHPStan level 7 lands on `main`.
- Item 9.7 is workflow-only — no tooling dependency; can be added any time.
- All changes land in a single `docs(claude-md): add PHP workflow standards` commit once the items above are ready.
