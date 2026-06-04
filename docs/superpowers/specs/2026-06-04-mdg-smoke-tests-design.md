# MDG Smoke Test Suite — Design

**Date:** 2026-06-04  
**Branch:** feat/mdg-smoke-tests  
**Scope:** PHP/Symfony MDG app only

---

## Context

All existing MDG controller tests use mocked services (`PHPUnit\Framework\TestCase` + `createMock`). They verify logic in isolation but cannot detect integration failures: wrong routes, missing middleware, broken DB queries, or fixture data issues.

This spec adds a **smoke test suite** that makes real HTTP calls to the running local stack after `doctrine:migrations:migrate` + `doctrine:fixtures:load`. It confirms every public endpoint returns an expected status code with real data.

---

## Goals

- Verify all public MDG endpoints respond correctly against a live DB + fixtures
- Run independently from unit tests (no server required for `composer test`)
- Skip cleanly if server is unreachable (no false failures in CI)
- Leave DB state unchanged after every run, even on failure

---

## Suite Wiring

### `phpunit.xml.dist` — split into two named suites

Current single `<directory>tests</directory>` becomes explicit per-directory entries:

```xml
<testsuites>
  <testsuite name="unit">
    <directory>tests/Cache</directory>
    <directory>tests/Controller</directory>
    <directory>tests/DataFixtures</directory>
    <directory>tests/Service</directory>
  </testsuite>
  <testsuite name="smoke">
    <directory>tests/Smoke</directory>
  </testsuite>
</testsuites>
```

### `composer.json` — three scripts

| Command | Runs |
|---|---|
| `composer test` | `phpunit --testsuite unit` — unit only, pre-commit gate unchanged |
| `composer smoke` | `phpunit --testsuite smoke` — smoke only, requires running stack |
| `composer test:all` | `phpunit` — both suites |

---

## New Dependency

Add to `require-dev`:

```
symfony/http-client: ^7.0
```

Used inside the test class via `Symfony\Component\HttpClient\HttpClient::create()`. No Guzzle, no curl wrappers.

---

## Test Class

**File:** `tests/Smoke/EndpointSmokeTest.php`  
**Extends:** `PHPUnit\Framework\TestCase`

### Constants

```php
private const BASE_URL = ''; // resolved from MDG_SMOKE_BASE_URL env, fallback http://localhost:9000
private const USER_ID  = 'smoke-test-user';
```

### Server reachability guard

`setUpBeforeClass` attempts `GET /master-data/newsletters` with a 2-second timeout. On any `\Throwable`, sets `static $serverAvailable = false`.

`setUp` checks the flag — calls `$this->markTestSkipped(...)` if false. Entire suite skips without error output.

### Test chain

All tests except `testDiscoverIds` carry `@depends testDiscoverIds`. PHPUnit passes the return value of the depended-upon test as the argument.

```
testDiscoverIds(): array
  Calls GET /master-data/newsletters
  Asserts: 200, non-empty array
  Extracts: newsletterId = body[0]['newsletter_id']
            topicId      = body[0]['topic_id']
            eventId      = body[0]['events'][0]['event_id']
  Returns: ['newsletterId' => …, 'topicId' => …, 'eventId' => …]

testNewsletterGetByIdReturns200(array $ids)   @depends testDiscoverIds
  Calls GET /master-data/newsletters/{newsletterId}
  Asserts: 200, response['newsletter_id'] === $ids['newsletterId']

testSubscriptionsListReturns200(array $ids)   @depends testDiscoverIds
  Calls GET /master-data/subscriptions
  Asserts: 200, body is array

testSubscribeReturns201(array $ids)           @depends testDiscoverIds
  Calls POST /master-data/subscriptions  {"topic_id": topicId}
  Asserts: 201, response['topic_id'] === $ids['topicId']
  Registers teardown: DELETE /master-data/subscriptions/{topicId}
    (addTearDownCallback — fires even on later test failure)

testInteractionRecordReturns201(array $ids)   @depends testDiscoverIds
  Calls POST /master-data/interactions  {"event_id": eventId, "type": "view"}
  Asserts: 201

testDeepDiveReturns200or404(array $ids)       @depends testDiscoverIds
  Calls GET /master-data/deep-dive/{eventId}
  Asserts: status is 200 or 404
  (fixtures do not seed deep_dive rows — 404 is valid)
```

### Headers on every request

```
X-User-Id: smoke-test-user
Content-Type: application/json  (POST only)
```

---

## Cleanup Strategy

Only `POST /master-data/subscriptions` writes durable state. Cleanup registered inside the test body via `addTearDownCallback`:

```php
$this->addTearDownCallback(function () use ($topicId): void {
    $this->client->request('DELETE', self::baseUrl() . "/master-data/subscriptions/{$topicId}", [
        'headers' => ['X-User-Id' => self::USER_ID],
    ]);
});
```

`POST /master-data/interactions` writes an interaction row. Interactions are append-only with no unique constraint per user+event+type, so re-runs accumulate rows but do not fail. No cleanup needed.

---

## Edge Cases

| Scenario | Behaviour |
|---|---|
| Server not running | Entire suite skipped, `composer test` unaffected |
| Fixtures not loaded | `testDiscoverIds` fails (empty newsletters) — chain stops, descriptive failure |
| Subscribe already exists (duplicate run without cleanup) | DELETE in teardown removes the row; second run POST succeeds |
| Deep-dive 404 | Accepted — fixtures omit deep_dive rows by design |

---

## Files Changed

| File | Change |
|---|---|
| `mdg/phpunit.xml.dist` | Split into `unit` + `smoke` named suites |
| `mdg/composer.json` | Add `symfony/http-client` to require-dev; add `smoke` + `test:all` scripts |
| `mdg/tests/Smoke/EndpointSmokeTest.php` | New — chained smoke test class |
