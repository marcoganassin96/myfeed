<?php
/*
This file was entirely created by Claude Code
While it is technically a "fixture" in the sense that it loads data, it completely bypasses the Doctrine ORM in favor of DBAL (Database Abstraction Layer).
It's writing raw SQL instead of letting the EntityManager do its job.
Committed as it is for didactic purposes - next step: manually refactor the file in order to:

1. Leverege the Identity Map: Transition from manual ID tracking (RETURNING clauses)
   to Doctrine's Unit of Work, allowing the EntityManager to manage object
   lifecycles and relationships automatically.

2. Implement Managed Batching: Replace raw SQL batching with a Persist-Flush-Clear
   cycle. This maintains high performance and low memory consumption while
   ensuring data integrity through Entity validation.

3. Establish Object Graph Links: Replace foreign key arrays with ReferenceRepository
   calls ($this->addReference / $this->getReference), enabling clean,
   type-safe associations between Topics, Threads, and Events.

4. Enhance Observability: Enable full SQL logging and "trackable" fixture
   execution, moving away from a "black box" script toward a standard
   Symfony/Doctrine development workflow.
*/

namespace App\DataFixtures;

use App\Cache\CacheService;
use Doctrine\Bundle\FixturesBundle\Fixture;
use Doctrine\DBAL\Connection;
use Doctrine\ORM\EntityManagerInterface;
use Doctrine\Persistence\ObjectManager;
use Symfony\Component\Uid\Uuid;

class LoadMockData extends Fixture
{
    public function __construct(private CacheService $cache) {}

    private const TOPICS = [
        ['name' => 'technology', 'description' => 'AI, software, and hardware news'],
        ['name' => 'politics',   'description' => 'Global political developments'],
        ['name' => 'sports',     'description' => 'Sports events and results'],
    ];
    private const THREADS_PER_TOPIC     = 5;
    private const EVENTS_PER_THREAD     = 20;
    private const EVENTS_PER_NEWSLETTER = 5;
    private const DAYS                  = 30;
    private const MOCK_USERS            = 1000;

    public function load(ObjectManager $manager): void
    {
        $this->cache->flush();

        assert($manager instanceof EntityManagerInterface);
        $conn = $manager->getConnection();

        $conn->executeStatement(
            'TRUNCATE interactions, newsletter_context_links, newsletter_events,
             newsletters, event_thread_memberships, deep_dives, news_events, threads, subscriptions, topics CASCADE'
        );

        $now = (new \DateTimeImmutable())->format('Y-m-d H:i:sP');

        // --- topics ---
        $topicIds = [];
        foreach (self::TOPICS as $t) {
            $topicId = Uuid::v4()->toRfc4122();
            $conn->executeStatement(
                'INSERT INTO topics (topic_id, name, description) VALUES (?, ?, ?)',
                [$topicId, $t['name'], $t['description']]
            );
            $topicIds[] = $topicId;
        }

        // --- threads ---
        $threadsByTopic = [];
        $threadToTopic  = [];
        foreach ($topicIds as $topicId) {
            for ($i = 0; $i < self::THREADS_PER_TOPIC; $i++) {
                $tid = Uuid::v4()->toRfc4122();
                $conn->executeStatement(
                    'INSERT INTO threads (thread_id, topic_id, name, created_at) VALUES (?, ?, ?, ?)',
                    [$tid, $topicId, "Thread $i ($topicId)", $now]
                );
                $threadsByTopic[$topicId][] = $tid;
                $threadToTopic[$tid]        = $topicId;
            }
        }

        // --- news_events + event_thread_memberships ---
        $allEvents      = [];
        $membershipRows = [];
        $start          = new \DateTimeImmutable('-' . self::DAYS . ' days midnight');
        $daysPerEvent   = (int)(self::DAYS / self::EVENTS_PER_THREAD);

        // To iterate key-value pairs in a dict (associative array) we use: ($dict as $key => $vaue)
        // Here $threadsByTopic is a dict where keys are topic IDs and values are arrays of thread IDs.
        foreach ($threadsByTopic as $topicId => $threadIds) {
            // To iterate values in an array we use: ($dict as $key => $value)
            foreach ($threadIds as $threadId) {
                $prevEventId = null;
                for ($pos = 1; $pos <= self::EVENTS_PER_THREAD; $pos++) {
                    $evDate  = $start->modify('+' . (($pos - 1) * $daysPerEvent) . ' days')->format('Y-m-d');
                    $eventId = Uuid::v4()->toRfc4122();
                    $conn->executeStatement(
                        'INSERT INTO news_events (event_id, headline, summary, date, source_url)
                         VALUES (?, ?, ?, ?, ?)',
                        [
                            $eventId,
                            "Headline $pos / thread $threadId",
                            "Summary of event $pos.",
                            $evDate,
                            'https://example.com/' . bin2hex(random_bytes(8)),
                        ]
                    );
                    $allEvents[]      = [$eventId, $topicId, $threadId];
                    $membershipRows[] = [$eventId, $threadId, $pos, $prevEventId];
                    $prevEventId      = $eventId;
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
                $nlId = Uuid::v4()->toRfc4122();
                $conn->executeStatement(
                    'INSERT INTO newsletters (newsletter_id, topic_id, date, title, narrative) VALUES (?, ?, ?, ?, ?)',
                    [
                        $nlId,
                        $topicId,
                        $nlDate,
                        "Newsletter $nlDate — $topicId",
                        "Narrative for $topicId on $nlDate.",
                    ]
                );
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
                $ctxRows[] = [Uuid::v4()->toRfc4122(), $nlId, $linkedId, 'Background context (link ' . ($p + 1) . ')', $p + 1];
            }
        }
        $this->batchInsert($conn, 'newsletter_context_links',
            ['id', 'newsletter_id', 'linked_newsletter_id', 'reason', 'position'],
            $ctxRows, 500
        );

        // --- subscriptions ---
        $subRows = [];
        for ($u = 0; $u < self::MOCK_USERS; $u++) {
            foreach (array_slice($topicIds, 0, 2) as $topicId) {
                $subRows[] = [sprintf('mock-user-%04d', $u), $topicId, $now];
            }
        }
        $this->batchInsert($conn, 'subscriptions', ['user_id', 'topic_id', 'subscribed_at'], $subRows, 1000);

        // --- deep_dives ---
        $deepDiveRows = [];
        foreach ($allEvents as $event) {
            $deepDiveRows[] = [
                $event[0],
                json_encode(['Mock deep-dive chunk 1.', 'Mock deep-dive chunk 2.']),
                $now,
            ];
        }
        $this->batchInsert($conn, 'deep_dives', ['event_id', 'chunks', 'created_at'], $deepDiveRows, 300);

        // --- interactions ---
        $evIds   = array_column(array_slice($allEvents, 0, 100), 0);
        $types   = ['view', 'click', 'deep_dive'];
        $intRows = [];
        for ($i = 0; $i < 10000; $i++) {
            $intRows[] = [
                Uuid::v4()->toRfc4122(),
                sprintf('mock-user-%04d', $i % self::MOCK_USERS),
                $evIds[$i % count($evIds)],
                $types[$i % 3],
                $now,
            ];
        }
        $this->batchInsert($conn, 'interactions', ['interaction_id', 'user_id', 'event_id', 'type', 'created_at'], $intRows, 1000);
    }

    /**
     * @param array<int, string> $cols
     * @param list<array<int, mixed>> $rows
     */
    private function batchInsert(Connection $conn, string $table, array $cols, array $rows, int $pageSize): void
    {
        if ($pageSize < 1) {
            throw new \InvalidArgumentException('pageSize must be >= 1');
        }
        if (empty($rows)) {
            return;
        }
        $colList        = implode(', ', $cols);
        $rowPlaceholder = '(' . implode(', ', array_fill(0, count($cols), '?')) . ')';
        foreach (array_chunk($rows, $pageSize) as $batch) {
            $placeholders = implode(', ', array_fill(0, count($batch), $rowPlaceholder));
            $params       = [];
            foreach ($batch as $row) {
                foreach ($row as $val) {
                    $params[] = $val;
                }
            }
            $conn->executeStatement("INSERT INTO $table ($colList) VALUES $placeholders", $params);
        }
    }
}
