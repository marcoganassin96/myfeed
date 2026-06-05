# MDG Smoke Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PHPUnit smoke suite that makes real HTTP calls to the running MDG stack and verifies every public endpoint returns the expected status code with real fixture data.

**Architecture:** Three tasks in order — wire the named test suites + scripts, install `symfony/http-client`, write the single chained test class. Unit tests continue to run via `composer test`; smoke tests run via `composer smoke`; both run via `composer test:all`.

**Tech Stack:** PHPUnit 11, symfony/http-client ^7.0, Symfony HttpClient, PHP 8.4

---

## File Map

| File | Change |
|---|---|
| `mdg/phpunit.xml.dist` | Split single `<directory>tests</directory>` into `unit` and `smoke` named suites |
| `mdg/composer.json` | Change `test` script to `--testsuite unit`; add `smoke` and `test:all` scripts |
| `mdg/composer.lock` | Updated by `composer require` |
| `mdg/tests/Smoke/EndpointSmokeTest.php` | New — chained smoke test class |

---

### Task 1: Wire named PHPUnit suites and composer scripts

**Files:**
- Modify: `mdg/phpunit.xml.dist`
- Modify: `mdg/composer.json`

- [ ] **Step 1: Replace the single test directory with two named suites in `phpunit.xml.dist`**

Replace the entire `<testsuites>` block (currently one suite with `<directory>tests</directory>`) with:

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

- [ ] **Step 2: Update `composer.json` scripts**

Replace the `"scripts"` block:

```json
"scripts": {
    "test":     "phpunit --testsuite unit",
    "smoke":    "phpunit --testsuite smoke",
    "test:all": "phpunit",
    "phpstan":  "phpstan analyse"
}
```

- [ ] **Step 3: Run unit suite to confirm nothing broke**

```bash
cd mdg && composer test
```

Expected output (last two lines):
```
Tests: 32, Assertions: 80, PHPUnit Deprecations: 1, Skipped: 1.
```
All 32 tests must pass. If count differs, a test file was not listed in the unit suite directories — add the missing directory to `phpunit.xml.dist`.

- [ ] **Step 4: Run smoke suite to confirm it's empty (not an error)**

```bash
cd mdg && composer smoke
```

Expected output:
```
No tests executed!
```
`tests/Smoke/` does not exist yet — PHPUnit reports "No tests executed!" which is correct.

- [ ] **Step 5: Commit**

```bash
cd mdg && git add phpunit.xml.dist composer.json
git commit -m "test(smoke): wire unit and smoke named PHPUnit suites"
```

---

### Task 2: Add symfony/http-client dependency

**Files:**
- Modify: `mdg/composer.json` (updated by composer)
- Modify: `mdg/composer.lock` (updated by composer)

- [ ] **Step 1: Install the package**

```bash
cd mdg && composer require --dev "symfony/http-client:^7.0"
```

Expected: composer resolves and installs the package, updates `composer.lock`. No errors.

- [ ] **Step 2: Verify it installed**

```bash
cd mdg && php -r "require 'vendor/autoload.php'; echo Symfony\Component\HttpClient\HttpClient::class . PHP_EOL;"
```

Expected output:
```
Symfony\Component\HttpClient\HttpClient
```

- [ ] **Step 3: Confirm unit suite still passes**

```bash
cd mdg && composer test
```

Expected: same 32 tests, 0 failures.

- [ ] **Step 4: Commit**

```bash
cd mdg && git add composer.json composer.lock
git commit -m "chore(deps): add symfony/http-client to mdg require-dev"
```

---

### Task 3: Write EndpointSmokeTest

**Files:**
- Create: `mdg/tests/Smoke/EndpointSmokeTest.php`

- [ ] **Step 1: Create the file**

Create `mdg/tests/Smoke/EndpointSmokeTest.php` with the following content:

```php
<?php
namespace App\Tests\Smoke;

use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpClient\HttpClient;
use Symfony\Contracts\HttpClient\HttpClientInterface;

/**
 * Smoke suite: real HTTP calls against localhost:9000 after migration + fixtures.
 * Skips cleanly when the server is not reachable.
 *
 * Run: composer smoke
 * Requires: docker-compose up -d && doctrine:migrations:migrate && doctrine:fixtures:load
 */
class EndpointSmokeTest extends TestCase
{
    private static bool $serverAvailable = true;

    /** Fixture user subscribed to 2 topics — provides real newsletter/event IDs. */
    private const SEEDED_USER = 'mock-user-0001';

    /** Clean user with no subscriptions — used for the POST /subscriptions write test. */
    private const SMOKE_USER = 'smoke-test-user';

    private HttpClientInterface $client;

    private static function baseUrl(): string
    {
        return $_ENV['MDG_SMOKE_BASE_URL'] ?? (string) getenv('MDG_SMOKE_BASE_URL') ?: 'http://localhost:9000';
    }

    public static function setUpBeforeClass(): void
    {
        try {
            HttpClient::create()
                ->request('GET', self::baseUrl() . '/master-data/newsletters', [
                    'headers' => ['X-User-Id' => self::SEEDED_USER],
                    'timeout' => 2.0,
                ])
                ->getStatusCode();
        } catch (\Throwable) {
            self::$serverAvailable = false;
        }
    }

    protected function setUp(): void
    {
        if (!self::$serverAvailable) {
            $this->markTestSkipped('MDG server not reachable at ' . self::baseUrl());
        }
        $this->client = HttpClient::create([
            'headers' => ['X-User-Id' => self::SEEDED_USER],
        ]);
    }

    /**
     * Root of the chain — fetches newsletters for a seeded user and extracts IDs
     * needed by all downstream tests.
     *
     * @return array{newsletterId: string, topicId: string}
     */
    public function testNewslettersListReturns200(): array
    {
        $response = $this->client->request('GET', self::baseUrl() . '/master-data/newsletters');
        $this->assertSame(200, $response->getStatusCode());
        /** @var list<array<string, mixed>> $body */
        $body = $response->toArray();
        $this->assertNotEmpty($body, 'Newsletters list is empty — run fixtures first');
        $this->assertArrayHasKey('newsletterId', $body[0]);
        $this->assertArrayHasKey('topicId', $body[0]);

        return [
            'newsletterId' => (string) $body[0]['newsletterId'],
            'topicId'      => (string) $body[0]['topicId'],
        ];
    }

    /**
     * Verifies the detail endpoint and extracts eventId for interaction + deep-dive tests.
     *
     * @depends testNewslettersListReturns200
     * @param array{newsletterId: string, topicId: string} $ids
     * @return array{newsletterId: string, topicId: string, eventId: string}
     */
    public function testNewsletterGetByIdReturns200(array $ids): array
    {
        $response = $this->client->request(
            'GET',
            self::baseUrl() . '/master-data/newsletters/' . $ids['newsletterId']
        );
        $this->assertSame(200, $response->getStatusCode());
        /** @var array<string, mixed> $body */
        $body = $response->toArray();
        $this->assertSame($ids['newsletterId'], $body['newsletter_id']);
        $this->assertNotEmpty($body['events'], 'Newsletter has no events — check fixtures');

        return [
            ...$ids,
            'eventId' => (string) $body['events'][0]['event_id'],
        ];
    }

    /** Subscriptions list for the seeded user — independent of the newsletter chain. */
    public function testSubscriptionsListReturns200(): void
    {
        $response = $this->client->request('GET', self::baseUrl() . '/master-data/subscriptions');
        $this->assertSame(200, $response->getStatusCode());
        $this->assertIsArray($response->toArray());
    }

    /**
     * Uses the clean smoke user (no pre-existing subscriptions) to avoid duplicate-key
     * errors on repeated runs. Teardown deletes the created row even on failure.
     *
     * @depends testNewslettersListReturns200
     * @param array{newsletterId: string, topicId: string} $ids
     */
    public function testSubscribeReturns201(array $ids): void
    {
        $topicId = $ids['topicId'];
        $smokeClient = HttpClient::create([
            'headers' => [
                'X-User-Id'    => self::SMOKE_USER,
                'Content-Type' => 'application/json',
            ],
        ]);

        $response = $smokeClient->request(
            'POST',
            self::baseUrl() . '/master-data/subscriptions',
            ['json' => ['topic_id' => $topicId]]
        );
        $this->assertSame(201, $response->getStatusCode());
        /** @var array<string, mixed> $body */
        $body = $response->toArray();
        $this->assertSame($topicId, $body['topic_id']);

        $this->addTearDownCallback(function () use ($topicId, $smokeClient): void {
            $smokeClient->request(
                'DELETE',
                self::baseUrl() . '/master-data/subscriptions/' . $topicId
            )->getStatusCode();
        });
    }

    /**
     * @depends testNewsletterGetByIdReturns200
     * @param array{newsletterId: string, topicId: string, eventId: string} $ids
     */
    public function testInteractionRecordReturns201(array $ids): void
    {
        $response = $this->client->request(
            'POST',
            self::baseUrl() . '/master-data/interactions',
            [
                'headers' => ['Content-Type' => 'application/json'],
                'json'    => ['event_id' => $ids['eventId'], 'type' => 'view'],
            ]
        );
        $this->assertSame(201, $response->getStatusCode());
    }

    /**
     * Fixtures do not seed deep_dive rows, so 404 is valid.
     * The test guards against unexpected 4xx/5xx (e.g. 500 from a broken query).
     *
     * @depends testNewsletterGetByIdReturns200
     * @param array{newsletterId: string, topicId: string, eventId: string} $ids
     */
    public function testDeepDiveReturns200or404(array $ids): void
    {
        $response = $this->client->request(
            'GET',
            self::baseUrl() . '/master-data/deep-dive/' . $ids['eventId']
        );
        $status = $response->getStatusCode();
        $this->assertContains(
            $status,
            [200, 404],
            "Deep-dive returned unexpected status $status for event {$ids['eventId']}"
        );
    }
}
```

- [ ] **Step 2: Run PHPStan against the new file**

```bash
cd mdg && composer phpstan
```

Expected: `[OK] No errors`. If PHPStan reports errors, fix them before continuing.

- [ ] **Step 3: Run unit suite to confirm no regressions**

```bash
cd mdg && composer test
```

Expected: 32 tests, 0 failures (smoke class is in `tests/Smoke/` which is excluded from `unit` suite).

- [ ] **Step 4: Run smoke suite with server down to verify skip behaviour**

Stop the MDG server if running (`docker-compose stop mdg`), then:

```bash
cd mdg && composer smoke
```

Expected output contains:
```
S  (skipped)
Tests: 6, Skipped: 6.
```
All 6 tests must be marked skipped — not failed.

- [ ] **Step 5: Run smoke suite with server up to verify passing behaviour**

Start the full stack and load fixtures:

```bash
docker-compose up -d
cd mdg && php bin/console doctrine:migrations:migrate --no-interaction
cd mdg && php bin/console doctrine:fixtures:load --no-interaction
```

Then run:

```bash
cd mdg && composer smoke
```

Expected: 6 tests, 0 failures, 0 skipped. If any test fails, the error message will indicate which endpoint failed and what was returned.

- [ ] **Step 6: Run `test:all` to confirm both suites together**

```bash
cd mdg && composer test:all
```

Expected: 38 tests total (32 unit + 6 smoke), 0 failures.

- [ ] **Step 7: Commit**

```bash
cd mdg && git add tests/Smoke/EndpointSmokeTest.php
git commit -m "test(smoke): add EndpointSmokeTest for all public MDG endpoints"
```
