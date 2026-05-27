# Doctrine Migrations + Fixtures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw SQL schema files and Python mock-data seeding with Doctrine Migrations (schema) and DoctrineFixturesBundle (data) in the mdg Symfony service, plus a new Python orchestrator `00_seed_doctrine.py`.

**Architecture:** Install `doctrine-migrations-bundle` and `doctrine-fixtures-bundle` in `mdg/`. Add 6 missing entity classes so Doctrine can generate the full schema via `doctrine:migrations:diff`. Manually patch the generated migration with `gen_random_uuid()` defaults and a `pgcrypto` extension. Port mock data insertion from Python to a `LoadMockData` PHP fixture class using batch raw SQL. Create `00_seed_doctrine.py` that calls Doctrine commands then queries the DB for IDs and saves `seed_result.json`.

**Tech Stack:** PHP 8.4, Symfony 7, Doctrine ORM 3, doctrine/doctrine-migrations-bundle ^3.3, doctrine/doctrine-fixtures-bundle ^3.6, Python 3.12, psycopg2, Docker Compose.

**Worktree:** `.worktrees/feat/doctrine-migrations-fixtures/`
All shell commands run from that directory unless stated otherwise.

---

## File Map

| Action | File |
|---|---|
| Modify | `mdg/composer.json` |
| Modify | `mdg/config/bundles.php` |
| Create | `mdg/config/packages/doctrine_migrations.yaml` |
| Create | `mdg/src/Entity/Topic.php` |
| Create | `mdg/src/Entity/Thread.php` |
| Create | `mdg/src/Entity/NewsEvent.php` |
| Create | `mdg/src/Entity/EventThreadMembership.php` |
| Create | `mdg/src/Entity/NewsletterEvent.php` |
| Create | `mdg/src/Entity/NewsletterContextLink.php` |
| Create | `mdg/migrations/Version<timestamp>.php` (generated then edited) |
| Create | `mdg/src/DataFixtures/LoadMockData.php` |
| Create | `mdg/tests/DataFixtures/LoadMockDataTest.php` |
| Create | `newsletter/scripts/00_seed_doctrine.py` |

---

## Task 1: Install doctrine-migrations-bundle

**Files:**
- Modify: `mdg/composer.json`
- Modify: `mdg/config/bundles.php`
- Create: `mdg/config/packages/doctrine_migrations.yaml`

- [ ] **Step 1: Add dependency to composer.json**

In `mdg/composer.json`, add to `"require"`:
```json
"doctrine/doctrine-migrations-bundle": "^3.3"
```

Full `require` block after edit:
```json
"require": {
    "php": ">=8.4",
    "symfony/framework-bundle": "^7.0",
    "symfony/http-kernel": "^7.0",
    "symfony/runtime": "^7.0",
    "symfony/var-exporter": "^7.0",
    "symfony/console": "^7.0",
    "symfony/yaml": "^7.0",
    "doctrine/orm": "^3.0",
    "doctrine/doctrine-bundle": "^2.12",
    "doctrine/doctrine-migrations-bundle": "^3.3",
    "predis/predis": "^2.2"
}
```

- [ ] **Step 2: Run composer install inside mdg container**

```bash
docker compose exec mdg composer require doctrine/doctrine-migrations-bundle:^3.3 --no-interaction
```

Expected: `Package operations: N installs ...` — success.

- [ ] **Step 3: Register bundle in bundles.php**

Replace `mdg/config/bundles.php` content:
```php
<?php
return [
    Symfony\Bundle\FrameworkBundle\FrameworkBundle::class => ['all' => true],
    Doctrine\Bundle\DoctrineBundle\DoctrineBundle::class => ['all' => true],
    Doctrine\Bundle\MigrationsBundle\DoctrineMigrationsBundle::class => ['all' => true],
];
```

- [ ] **Step 4: Create doctrine_migrations.yaml**

Create `mdg/config/packages/doctrine_migrations.yaml`:
```yaml
doctrine_migrations:
    migrations_paths:
        'DoctrineMigrations': '%kernel.project_dir%/migrations'
    storage:
        table_storage:
            table_name: 'doctrine_migration_versions'
```

- [ ] **Step 5: Verify bundle loads**

```bash
docker compose exec mdg php bin/console doctrine:migrations:status
```

Expected output contains: `>> Executed Migrations: 0` (no error).

- [ ] **Step 6: Commit**

```bash
git add mdg/composer.json mdg/composer.lock mdg/config/bundles.php mdg/config/packages/doctrine_migrations.yaml
git commit -m "chore(mdg): install doctrine-migrations-bundle"
```

---

## Task 2: Install doctrine-fixtures-bundle

**Files:**
- Modify: `mdg/composer.json`
- Modify: `mdg/config/bundles.php`

- [ ] **Step 1: Add dev dependency**

```bash
docker compose exec mdg composer require --dev doctrine/doctrine-fixtures-bundle:^3.6 --no-interaction
```

Expected: success.

- [ ] **Step 2: Register bundle for dev only in bundles.php**

Replace `mdg/config/bundles.php`:
```php
<?php
return [
    Symfony\Bundle\FrameworkBundle\FrameworkBundle::class => ['all' => true],
    Doctrine\Bundle\DoctrineBundle\DoctrineBundle::class => ['all' => true],
    Doctrine\Bundle\MigrationsBundle\DoctrineMigrationsBundle::class => ['all' => true],
    Doctrine\Bundle\FixturesBundle\DoctrineFixturesBundle::class => ['dev' => true],
];
```

- [ ] **Step 3: Verify command exists**

```bash
docker compose exec mdg php bin/console doctrine:fixtures:load --help
```

Expected: help output with `--append` and `--no-interaction` options listed.

- [ ] **Step 4: Commit**

```bash
git add mdg/composer.json mdg/composer.lock mdg/config/bundles.php
git commit -m "chore(mdg): install doctrine-fixtures-bundle (dev)"
```

---

## Task 3: Add Topic entity

**Files:**
- Create: `mdg/src/Entity/Topic.php`

- [ ] **Step 1: Create the entity**

Create `mdg/src/Entity/Topic.php`:
```php
<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'topics')]
#[ORM\UniqueConstraint(name: 'uniq_topics_name', columns: ['name'])]
class Topic
{
    #[ORM\Id]
    #[ORM\Column(name: 'topic_id', type: 'guid')]
    private string $topicId;

    #[ORM\Column(type: 'string', length: 100)]
    private string $name;

    #[ORM\Column(type: 'text', nullable: true)]
    private ?string $description;

    public function getTopicId(): string { return $this->topicId; }
    public function getName(): string { return $this->name; }
    public function getDescription(): ?string { return $this->description; }
}
```

- [ ] **Step 2: Validate mapping syntax**

```bash
docker compose exec mdg php bin/console doctrine:mapping:info
```

Expected: `App\Entity\Topic` listed with no errors.

- [ ] **Step 3: Commit**

```bash
git add mdg/src/Entity/Topic.php
git commit -m "feat(mdg): add Topic entity"
```

---

## Task 4: Add Thread entity

**Files:**
- Create: `mdg/src/Entity/Thread.php`

- [ ] **Step 1: Create the entity**

Create `mdg/src/Entity/Thread.php`:
```php
<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'threads')]
#[ORM\Index(name: 'idx_threads_topic_id', columns: ['topic_id'])]
class Thread
{
    #[ORM\Id]
    #[ORM\Column(name: 'thread_id', type: 'guid')]
    private string $threadId;

    #[ORM\Column(name: 'topic_id', type: 'guid')]
    private string $topicId;

    #[ORM\Column(type: 'string', length: 200)]
    private string $name;

    #[ORM\Column(name: 'created_at', type: 'datetimetz_immutable')]
    private \DateTimeImmutable $createdAt;

    public function getThreadId(): string { return $this->threadId; }
    public function getTopicId(): string { return $this->topicId; }
    public function getName(): string { return $this->name; }
    public function getCreatedAt(): \DateTimeImmutable { return $this->createdAt; }
}
```

- [ ] **Step 2: Validate mapping**

```bash
docker compose exec mdg php bin/console doctrine:mapping:info
```

Expected: both `Topic` and `Thread` listed, no errors.

- [ ] **Step 3: Commit**

```bash
git add mdg/src/Entity/Thread.php
git commit -m "feat(mdg): add Thread entity"
```

---

## Task 5: Add NewsEvent entity

**Files:**
- Create: `mdg/src/Entity/NewsEvent.php`

- [ ] **Step 1: Create the entity**

Create `mdg/src/Entity/NewsEvent.php`:
```php
<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'news_events')]
class NewsEvent
{
    #[ORM\Id]
    #[ORM\Column(name: 'event_id', type: 'guid')]
    private string $eventId;

    #[ORM\Column(type: 'string', length: 300)]
    private string $headline;

    #[ORM\Column(type: 'text')]
    private string $summary;

    #[ORM\Column(type: 'date_immutable')]
    private \DateTimeImmutable $date;

    #[ORM\Column(name: 'source_url', type: 'text', nullable: true)]
    private ?string $sourceUrl;

    public function getEventId(): string { return $this->eventId; }
    public function getHeadline(): string { return $this->headline; }
    public function getSummary(): string { return $this->summary; }
    public function getDate(): \DateTimeImmutable { return $this->date; }
    public function getSourceUrl(): ?string { return $this->sourceUrl; }
}
```

- [ ] **Step 2: Validate mapping**

```bash
docker compose exec mdg php bin/console doctrine:mapping:info
```

Expected: `NewsEvent` listed, no errors.

- [ ] **Step 3: Commit**

```bash
git add mdg/src/Entity/NewsEvent.php
git commit -m "feat(mdg): add NewsEvent entity"
```

---

## Task 6: Add EventThreadMembership entity

**Files:**
- Create: `mdg/src/Entity/EventThreadMembership.php`

- [ ] **Step 1: Create the entity**

Create `mdg/src/Entity/EventThreadMembership.php`:
```php
<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'event_thread_memberships')]
#[ORM\Index(name: 'idx_etm_thread_position', columns: ['thread_id', 'position'])]
class EventThreadMembership
{
    #[ORM\Id]
    #[ORM\Column(name: 'event_id', type: 'guid')]
    private string $eventId;

    #[ORM\Id]
    #[ORM\Column(name: 'thread_id', type: 'guid')]
    private string $threadId;

    #[ORM\Column(type: 'integer')]
    private int $position;

    #[ORM\Column(name: 'previous_event_id', type: 'guid', nullable: true)]
    private ?string $previousEventId;

    public function getEventId(): string { return $this->eventId; }
    public function getThreadId(): string { return $this->threadId; }
    public function getPosition(): int { return $this->position; }
    public function getPreviousEventId(): ?string { return $this->previousEventId; }
}
```

- [ ] **Step 2: Validate mapping**

```bash
docker compose exec mdg php bin/console doctrine:mapping:info
```

Expected: `EventThreadMembership` listed, no errors.

- [ ] **Step 3: Commit**

```bash
git add mdg/src/Entity/EventThreadMembership.php
git commit -m "feat(mdg): add EventThreadMembership entity"
```

---

## Task 7: Add NewsletterEvent entity

**Files:**
- Create: `mdg/src/Entity/NewsletterEvent.php`

- [ ] **Step 1: Create the entity**

Create `mdg/src/Entity/NewsletterEvent.php`:
```php
<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'newsletter_events')]
#[ORM\Index(name: 'idx_newsletter_events_nl_pos', columns: ['newsletter_id', 'position'])]
class NewsletterEvent
{
    #[ORM\Id]
    #[ORM\Column(name: 'newsletter_id', type: 'guid')]
    private string $newsletterId;

    #[ORM\Id]
    #[ORM\Column(name: 'event_id', type: 'guid')]
    private string $eventId;

    #[ORM\Column(name: 'thread_id', type: 'guid')]
    private string $threadId;

    #[ORM\Column(type: 'integer')]
    private int $position;

    public function getNewsletterId(): string { return $this->newsletterId; }
    public function getEventId(): string { return $this->eventId; }
    public function getThreadId(): string { return $this->threadId; }
    public function getPosition(): int { return $this->position; }
}
```

- [ ] **Step 2: Validate mapping**

```bash
docker compose exec mdg php bin/console doctrine:mapping:info
```

Expected: `NewsletterEvent` listed, no errors.

- [ ] **Step 3: Commit**

```bash
git add mdg/src/Entity/NewsletterEvent.php
git commit -m "feat(mdg): add NewsletterEvent entity"
```

---

## Task 8: Add NewsletterContextLink entity

**Files:**
- Create: `mdg/src/Entity/NewsletterContextLink.php`

- [ ] **Step 1: Create the entity**

Create `mdg/src/Entity/NewsletterContextLink.php`:
```php
<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'newsletter_context_links')]
#[ORM\Index(name: 'idx_ncl_newsletter_id', columns: ['newsletter_id'])]
class NewsletterContextLink
{
    #[ORM\Id]
    #[ORM\Column(type: 'guid')]
    private string $id;

    #[ORM\Column(name: 'newsletter_id', type: 'guid')]
    private string $newsletterId;

    #[ORM\Column(name: 'linked_newsletter_id', type: 'guid')]
    private string $linkedNewsletterId;

    #[ORM\Column(type: 'text')]
    private string $reason;

    #[ORM\Column(type: 'integer')]
    private int $position;

    public function getId(): string { return $this->id; }
    public function getNewsletterId(): string { return $this->newsletterId; }
    public function getLinkedNewsletterId(): string { return $this->linkedNewsletterId; }
    public function getReason(): string { return $this->reason; }
    public function getPosition(): int { return $this->position; }
}
```

- [ ] **Step 2: Validate all 10 entities**

```bash
docker compose exec mdg php bin/console doctrine:mapping:info
```

Expected: all 10 entity classes listed (Topic, Thread, NewsEvent, EventThreadMembership, NewsletterEvent, NewsletterContextLink, Newsletter, Subscription, Interaction, DeepDive), no errors.

- [ ] **Step 3: Commit**

```bash
git add mdg/src/Entity/NewsletterContextLink.php
git commit -m "feat(mdg): add NewsletterContextLink entity — all entities complete"
```

---

## Task 9: Generate schema migration

**Files:**
- Create: `mdg/migrations/Version<timestamp>.php` (auto-generated)

Prerequisite: Docker Compose is up (`docker compose up -d`). DB must be reachable.

- [ ] **Step 1: Run diff to generate migration**

```bash
docker compose exec mdg php bin/console doctrine:migrations:diff
```

Expected: `Generated new migration class to "migrations/VersionYYYYMMDDHHMMSS.php"`.
Note the exact filename — it will be `mdg/migrations/Version<timestamp>.php`.

- [ ] **Step 2: Inspect the generated file**

```bash
docker compose exec mdg cat migrations/Version<timestamp>.php
```

Verify the `up()` method contains `CREATE TABLE` statements for all 10 tables.

---

## Task 10: Edit generated migration

**Files:**
- Modify: `mdg/migrations/Version<timestamp>.php`

This task adds everything Doctrine's diff cannot auto-detect: the `pgcrypto` extension, UUID defaults via `gen_random_uuid()`, timestamp column defaults, and the check constraint on interactions.

- [ ] **Step 1: Open the generated migration file**

Open `mdg/migrations/Version<timestamp>.php`. Locate the `up()` method.

- [ ] **Step 2: Add pgcrypto extension as the first statement**

At the very top of the `up()` method body, before any CREATE TABLE, add:
```php
$this->addSql("CREATE EXTENSION IF NOT EXISTS pgcrypto");
```

- [ ] **Step 3: Add gen_random_uuid() defaults for all UUID PKs**

At the end of `up()`, after all CREATE TABLE statements, add:
```php
$this->addSql("ALTER TABLE topics ALTER COLUMN topic_id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE threads ALTER COLUMN thread_id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE news_events ALTER COLUMN event_id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE newsletters ALTER COLUMN newsletter_id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE newsletter_context_links ALTER COLUMN id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE interactions ALTER COLUMN interaction_id SET DEFAULT gen_random_uuid()");
```

Do NOT add this for `deep_dives.event_id` — it is a FK to `news_events.event_id`, not auto-generated.

- [ ] **Step 4: Add NOW() defaults for timestamp columns**

Still at the end of `up()`, add:
```php
$this->addSql("ALTER TABLE threads ALTER COLUMN created_at SET DEFAULT NOW()");
$this->addSql("ALTER TABLE subscriptions ALTER COLUMN subscribed_at SET DEFAULT NOW()");
$this->addSql("ALTER TABLE interactions ALTER COLUMN created_at SET DEFAULT NOW()");
$this->addSql("ALTER TABLE deep_dives ALTER COLUMN created_at SET DEFAULT NOW()");
```

- [ ] **Step 5: Add check constraint for interactions.type**

```php
$this->addSql("ALTER TABLE interactions ADD CONSTRAINT chk_interaction_type CHECK (type IN ('view', 'click', 'deep_dive'))");
```

- [ ] **Step 6: Commit the edited migration**

```bash
git add mdg/migrations/
git commit -m "feat(mdg): add schema migration with UUID defaults and constraints"
```

---

## Task 11: Run migration and validate schema

Prerequisite: Docker Compose up, fresh DB (no existing tables — if tables exist from old seed, drop and recreate the DB or truncate all tables first).

- [ ] **Step 1: Run migration**

```bash
docker compose exec mdg php bin/console doctrine:migrations:migrate --no-interaction
```

Expected:
```
++ migrating DoctrineMigrations\Version<timestamp>
   -> CREATE EXTENSION IF NOT EXISTS pgcrypto
   ...
++ migrated (took Xms, used YMiB memory)
```

- [ ] **Step 2: Verify migration version recorded**

```bash
docker compose exec mdg php bin/console doctrine:migrations:status
```

Expected: `>> Executed Migrations: 1` and `>> Available Migrations: 1`.

- [ ] **Step 3: Verify tables exist**

```bash
docker compose exec postgres psql -U postgres -d newsletter -c "\dt"
```

Expected: 10 tables listed: `topics`, `threads`, `news_events`, `event_thread_memberships`, `newsletters`, `newsletter_events`, `newsletter_context_links`, `subscriptions`, `interactions`, `deep_dives`, plus `doctrine_migration_versions`.

- [ ] **Step 4: Commit (no new files — migration already committed)**

No commit needed for this step.

---

## Task 12: Write failing integration test for LoadMockData

**Files:**
- Create: `mdg/tests/DataFixtures/LoadMockDataTest.php`

Prerequisite: Docker Compose up with DB after migration.

- [ ] **Step 1: Create the test directory and file**

Create `mdg/tests/DataFixtures/LoadMockDataTest.php`:
```php
<?php
namespace App\Tests\DataFixtures;

use App\DataFixtures\LoadMockData;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;

class LoadMockDataTest extends KernelTestCase
{
    private EntityManagerInterface $em;

    protected function setUp(): void
    {
        self::bootKernel(['environment' => 'dev']);
        $this->em = static::getContainer()->get(EntityManagerInterface::class);
    }

    public function testRowCountsAfterLoad(): void
    {
        $fixture = new LoadMockData();
        $fixture->load($this->em);

        $conn = $this->em->getConnection();

        $this->assertSame('3', $conn->fetchOne('SELECT COUNT(*)::text FROM topics'));
        $this->assertSame('15', $conn->fetchOne('SELECT COUNT(*)::text FROM threads'));
        $this->assertSame('300', $conn->fetchOne('SELECT COUNT(*)::text FROM news_events'));
        $this->assertSame('300', $conn->fetchOne('SELECT COUNT(*)::text FROM event_thread_memberships'));
        $this->assertSame('90', $conn->fetchOne('SELECT COUNT(*)::text FROM newsletters'));
        $this->assertSame('450', $conn->fetchOne('SELECT COUNT(*)::text FROM newsletter_events'));
        $this->assertSame('176', $conn->fetchOne('SELECT COUNT(*)::text FROM newsletter_context_links'));
        $this->assertSame('2000', $conn->fetchOne('SELECT COUNT(*)::text FROM subscriptions'));
        $this->assertSame('10000', $conn->fetchOne('SELECT COUNT(*)::text FROM interactions'));
    }
}
```

- [ ] **Step 2: Run to verify it fails**

```bash
docker compose exec mdg vendor/bin/phpunit tests/DataFixtures/LoadMockDataTest.php --testdox
```

Expected: FAIL — `Class "App\DataFixtures\LoadMockData" not found` (or similar — LoadMockData does not exist yet).

- [ ] **Step 3: Commit the failing test**

```bash
git add mdg/tests/DataFixtures/LoadMockDataTest.php
git commit -m "test(mdg): add failing integration test for LoadMockData fixture"
```

---

## Task 13: Implement LoadMockData fixture

**Files:**
- Create: `mdg/src/DataFixtures/LoadMockData.php`

- [ ] **Step 1: Create the fixture class**

Create `mdg/src/DataFixtures/LoadMockData.php`:
```php
<?php
namespace App\DataFixtures;

use Doctrine\Bundle\FixturesBundle\Fixture;
use Doctrine\DBAL\Connection;
use Doctrine\ORM\EntityManagerInterface;
use Doctrine\Persistence\ObjectManager;

class LoadMockData extends Fixture
{
    private const TOPICS = [
        ['name' => 'technology', 'description' => 'AI, software, and hardware news'],
        ['name' => 'politics',   'description' => 'Global political developments'],
        ['name' => 'sports',     'description' => 'Sports events and results'],
    ];
    private const THREADS_PER_TOPIC    = 5;
    private const EVENTS_PER_THREAD    = 20;
    private const EVENTS_PER_NEWSLETTER = 5;
    private const DAYS                 = 30;
    private const MOCK_USERS           = 1000;

    public function load(ObjectManager $manager): void
    {
        assert($manager instanceof EntityManagerInterface);
        $conn = $manager->getConnection();

        $conn->executeStatement(
            'TRUNCATE interactions, newsletter_context_links, newsletter_events,
             newsletters, event_thread_memberships, news_events, threads, subscriptions, topics CASCADE'
        );

        // --- topics ---
        $topicIds = [];
        foreach (self::TOPICS as $t) {
            $row = $conn->fetchAssociative(
                'INSERT INTO topics (name, description) VALUES (?, ?) RETURNING topic_id',
                [$t['name'], $t['description']]
            );
            $topicIds[] = $row['topic_id'];
        }

        // --- threads ---
        $threadsByTopic = [];
        $threadToTopic  = [];
        foreach ($topicIds as $topicId) {
            for ($i = 0; $i < self::THREADS_PER_TOPIC; $i++) {
                $row = $conn->fetchAssociative(
                    'INSERT INTO threads (topic_id, name) VALUES (?, ?) RETURNING thread_id',
                    [$topicId, "Thread $i ($topicId)"]
                );
                $tid = $row['thread_id'];
                $threadsByTopic[$topicId][] = $tid;
                $threadToTopic[$tid]        = $topicId;
            }
        }

        // --- news_events + event_thread_memberships ---
        $allEvents       = [];          // [[eventId, topicId, threadId], ...]
        $membershipRows  = [];          // [[eventId, threadId, pos, prevId|null], ...]
        $start           = new \DateTimeImmutable('-' . self::DAYS . ' days midnight');
        $daysPerEvent    = (int)(self::DAYS / self::EVENTS_PER_THREAD); // 1

        foreach ($threadsByTopic as $topicId => $threadIds) {
            foreach ($threadIds as $threadId) {
                $prevEventId = null;
                for ($pos = 1; $pos <= self::EVENTS_PER_THREAD; $pos++) {
                    $evDate = $start->modify('+' . (($pos - 1) * $daysPerEvent) . ' days')->format('Y-m-d');
                    $row = $conn->fetchAssociative(
                        'INSERT INTO news_events (headline, summary, date, source_url)
                         VALUES (?, ?, ?, ?) RETURNING event_id',
                        [
                            "Headline $pos / thread $threadId",
                            "Summary of event $pos.",
                            $evDate,
                            'https://example.com/' . bin2hex(random_bytes(8)),
                        ]
                    );
                    $eventId       = $row['event_id'];
                    $allEvents[]   = [$eventId, $topicId, $threadId];
                    $membershipRows[] = [$eventId, $threadId, $pos, $prevEventId];
                    $prevEventId   = $eventId;
                }
            }
        }

        $this->batchInsert($conn, 'event_thread_memberships',
            ['event_id', 'thread_id', 'position', 'previous_event_id'],
            $membershipRows, 300
        );

        // --- newsletters + newsletter_events ---
        $nlList = [];

        for ($day = 0; $day < self::DAYS; $day++) {
            $nlDate = $start->modify("+$day days")->format('Y-m-d');
            foreach ($topicIds as $topicId) {
                $row = $conn->fetchAssociative(
                    'INSERT INTO newsletters (topic_id, date, title, narrative)
                     VALUES (?, ?, ?, ?) RETURNING newsletter_id',
                    [
                        $topicId,
                        $nlDate,
                        "Newsletter $nlDate — $topicId",
                        "Narrative for $topicId on $nlDate.",
                    ]
                );
                $nlId     = $row['newsletter_id'];
                $nlList[] = $nlId;

                $chosen = array_filter($allEvents, static fn($e) => $e[1] === $topicId);
                $chosen = array_slice(array_values($chosen), 0, self::EVENTS_PER_NEWSLETTER);

                $nlEventRows = [];
                foreach ($chosen as $p => $e) {
                    $nlEventRows[] = [$nlId, $e[0], $e[2], $p + 1];
                }
                $this->batchInsert($conn, 'newsletter_events',
                    ['newsletter_id', 'event_id', 'thread_id', 'position'],
                    $nlEventRows, self::EVENTS_PER_NEWSLETTER
                );
            }
        }

        // --- newsletter_context_links ---
        $ctxRows = [];
        foreach ($nlList as $i => $nlId) {
            if ($i < 2) {
                continue;
            }
            $linked = array_slice($nlList, $i - 2, 2);
            foreach ($linked as $p => $linkedId) {
                $ctxRows[] = [$nlId, $linkedId, 'Background context (link ' . ($p + 1) . ')', $p + 1];
            }
        }
        $this->batchInsert($conn, 'newsletter_context_links',
            ['newsletter_id', 'linked_newsletter_id', 'reason', 'position'],
            $ctxRows, 500
        );

        // --- subscriptions ---
        $subRows = [];
        for ($u = 0; $u < self::MOCK_USERS; $u++) {
            foreach (array_slice($topicIds, 0, 2) as $topicId) {
                $subRows[] = [sprintf('mock-user-%04d', $u), $topicId];
            }
        }
        $this->batchInsert($conn, 'subscriptions', ['user_id', 'topic_id'], $subRows, 1000);

        // --- interactions ---
        $evIds  = array_column(array_slice($allEvents, 0, 100), 0);
        $types  = ['view', 'click', 'deep_dive'];
        $intRows = [];
        for ($i = 0; $i < 10000; $i++) {
            $intRows[] = [
                sprintf('mock-user-%04d', $i % self::MOCK_USERS),
                $evIds[$i % count($evIds)],
                $types[$i % 3],
            ];
        }
        $this->batchInsert($conn, 'interactions', ['user_id', 'event_id', 'type'], $intRows, 1000);
    }

    private function batchInsert(Connection $conn, string $table, array $cols, array $rows, int $pageSize): void
    {
        if (empty($rows)) {
            return;
        }
        $colList = implode(', ', $cols);
        $rowPlaceholder = '(' . implode(', ', array_fill(0, count($cols), '?')) . ')';
        foreach (array_chunk($rows, $pageSize) as $batch) {
            $placeholders = implode(', ', array_fill(0, count($batch), $rowPlaceholder));
            $params = [];
            foreach ($batch as $row) {
                foreach ($row as $val) {
                    $params[] = $val;
                }
            }
            $conn->executeStatement("INSERT INTO $table ($colList) VALUES $placeholders", $params);
        }
    }
}
```

- [ ] **Step 2: Commit the fixture**

```bash
git add mdg/src/DataFixtures/LoadMockData.php
git commit -m "feat(mdg): implement LoadMockData fixture"
```

---

## Task 14: Run integration test

- [ ] **Step 1: Run the test**

```bash
docker compose exec mdg vendor/bin/phpunit tests/DataFixtures/LoadMockDataTest.php --testdox
```

Expected:
```
App\Tests\DataFixtures\LoadMockData
 ✔ Row counts after load
```

- [ ] **Step 2: Run full test suite to check for regressions**

```bash
docker compose exec mdg vendor/bin/phpunit --testdox
```

Expected: all existing tests pass plus the new integration test.

- [ ] **Step 3: Verify fixtures:load command works standalone**

```bash
docker compose exec mdg php bin/console doctrine:fixtures:load --no-interaction
```

Expected: no errors, execution completes.

- [ ] **Step 4: Commit**

If any test fixes were needed, commit them now:
```bash
git add -p
git commit -m "test(mdg): LoadMockData integration test passes"
```

---

## Task 15: Write 00_seed_doctrine.py

**Files:**
- Create: `newsletter/scripts/00_seed_doctrine.py`

- [ ] **Step 1: Create the script**

Create `newsletter/scripts/00_seed_doctrine.py`:
```python
#!/usr/bin/env python3
"""
Runs Doctrine migrations + fixtures via Docker Compose, then queries IDs and
saves seed_result.json for use by 01_prewarm.py and 03_get_load_test_ids.py.

Usage:
  DB_PASSWORD=<secret> python scripts/00_seed_doctrine.py

Env vars:
  DB_PASSWORD  database password (required)
  CONFIG       path to YAML config (default: config/local.yaml)
"""
import os, sys, json, subprocess, pathlib
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import get_out_filepath, OutFile, ROOT_DIR
from models import SeedResult
import psycopg2, psycopg2.extras
from config import load as _cfg
from utils import timed


def _php_console(args: list[str]) -> None:
    cmd = ["docker", "compose", "exec", "-T", "mdg", "php", "bin/console"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT_DIR))
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(args)}")


def _db():
    cfg = _cfg()["database"]
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["name"],
        user=cfg["user"],
        password=os.environ["DB_PASSWORD"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def seed() -> SeedResult:
    with timed("doctrine:migrations:migrate"):
        _php_console(["doctrine:migrations:migrate", "--no-interaction"])

    with timed("doctrine:fixtures:load"):
        _php_console(["doctrine:fixtures:load", "--no-interaction"])

    conn = _db()
    try:
        with conn.cursor() as cur:
            # topic_ids in fixture insertion order: technology, politics, sports
            cur.execute(
                "SELECT topic_id FROM topics "
                "ORDER BY CASE name WHEN 'technology' THEN 1 WHEN 'politics' THEN 2 WHEN 'sports' THEN 3 END"
            )
            topic_ids = [r["topic_id"] for r in cur.fetchall()]

            cur.execute("SELECT newsletter_id, topic_id::text, date::text FROM newsletters ORDER BY date, topic_id")
            nl_ids = {f"{r['topic_id']}|{r['date']}": r["newsletter_id"] for r in cur.fetchall()}

            cur.execute("SELECT MIN(date) FROM newsletters")
            start: date = cur.fetchone()["min"]
    finally:
        conn.close()

    return SeedResult(topic_ids=topic_ids, nl_ids=nl_ids, start=start)


def _save(result: SeedResult, env: str) -> None:
    payload = {
        "topic_ids": [str(tid) for tid in result.topic_ids],
        "nl_ids": {k: str(v) for k, v in result.nl_ids.items()},
        "start": str(result.start),
    }
    out_path = get_out_filepath(env, OutFile.SEED_RESULT)
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"  Seed result saved → {out_path}")


if __name__ == "__main__":
    _env = os.environ.get("env", "local")
    if _env != "local":
        print(
            f"ERROR: env={_env} not supported by 00_seed_doctrine.py. "
            "Run migrations via ECS task override for non-local environments.",
            file=sys.stderr,
        )
        sys.exit(1)

    with timed("Total time:"):
        try:
            result = seed()
        except Exception as e:
            print(f"✗ {e}", file=sys.stderr)
            sys.exit(1)

        _save(result, _env)
        print("  next: python scripts/01_prewarm.py", file=sys.stderr)
```

- [ ] **Step 2: Run the script end-to-end**

```bash
cd newsletter && DB_PASSWORD=<your-local-password> python scripts/00_seed_doctrine.py
```

Expected output:
```
  doctrine:migrations:migrate: ...
  doctrine:fixtures:load: ...
  Seed result saved → newsletter/scripts/out/local/00_seed_result.json
```

- [ ] **Step 3: Verify seed result is parseable by 01_prewarm.py**

```bash
cd newsletter && CONFIG=config/local.yaml python scripts/01_prewarm.py
```

Expected: Redis pre-warm completes with no errors.

- [ ] **Step 4: Commit**

```bash
git add newsletter/scripts/00_seed_doctrine.py
git commit -m "feat(seed): add 00_seed_doctrine.py — Doctrine-based seed orchestrator"
```

---

## Final Verification

- [ ] Run full phpunit suite: `docker compose exec mdg vendor/bin/phpunit --testdox` — all pass
- [ ] Run Python tests: `cd newsletter && pytest tests/ -v` — 67 passed
- [ ] Confirm `doctrine:migrations:status` shows 1 executed migration
- [ ] Confirm `00_seed_doctrine.py` produces valid `seed_result.json`
