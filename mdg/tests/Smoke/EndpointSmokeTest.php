<?php
namespace App\Tests\Smoke;

use PHPUnit\Framework\Attributes\Depends;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpClient\HttpClient;
use Symfony\Contracts\HttpClient\HttpClientInterface;

/**
 * Smoke suite: real HTTP calls against localhost:9000 after migration + fixtures.
 * Skips cleanly when the server is not reachable.
 *
 * Run: ADMIN_TOKEN=dev-admin-secret composer smoke
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
    private HttpClientInterface $adminClient;

    /** @var list<\Closure> Deferred cleanup callbacks run in tearDown. */
    private array $tearDownCallbacks = [];

    private static function baseUrl(): string
    {
        return $_ENV['MDG_SMOKE_BASE_URL'] ?? (string) getenv('MDG_SMOKE_BASE_URL') ?: 'http://localhost:9000';
    }

    private static function adminToken(): string
    {
        return $_ENV['ADMIN_TOKEN'] ?? (string) getenv('ADMIN_TOKEN') ?: 'dev-admin-secret';
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
        $this->adminClient = HttpClient::create([
            'headers' => ['X-Admin-Token' => self::adminToken()],
        ]);
        $this->tearDownCallbacks = [];
    }

    protected function tearDown(): void
    {
        foreach ($this->tearDownCallbacks as $callback) {
            $callback();
        }
        parent::tearDown();
    }

    /**
     * Root of the dependency chain — fetches newsletters for the seeded user.
     *
     * @return array{newsletterId: string, topicId: string}
     *
     * curl http://localhost:9000/master-data/newsletters -H "X-User-Id: mock-user-0001"
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
     * @param array{newsletterId: string, topicId: string} $ids
     * @return array{newsletterId: string, topicId: string, eventId: string}
     *
     * curl http://localhost:9000/master-data/newsletters/{id} -H "X-User-Id: mock-user-0001"
     */
    #[Depends('testNewslettersListReturns200')]
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

    /**
     * curl http://localhost:9000/master-data/subscriptions -H "X-User-Id: mock-user-0001"
     */
    public function testSubscriptionsListReturns200(): void
    {
        $response = $this->client->request('GET', self::baseUrl() . '/master-data/subscriptions');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }

    /**
     * @param array{newsletterId: string, topicId: string} $ids
     *
     * curl -X POST http://localhost:9000/master-data/subscriptions -H "X-User-Id: smoke-test-user" -H "Content-Type: application/json" -d '{"topic_id": "<uuid>"}'
     */
    #[Depends('testNewslettersListReturns200')]
    public function testSubscribeReturns201(array $ids): void
    {
        $topicId    = $ids['topicId'];
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

        $this->tearDownCallbacks[] = function () use ($topicId, $smokeClient): void {
            $status = $smokeClient->request(
                'DELETE',
                self::baseUrl() . '/master-data/subscriptions/' . $topicId
            )->getStatusCode();
            if (!in_array($status, [200, 204, 404], true)) {
                fwrite(STDERR, "Smoke teardown: DELETE /master-data/subscriptions/$topicId returned $status\n");
            }
        };
    }

    /**
     * @param array{newsletterId: string, topicId: string, eventId: string} $ids
     *
     * curl -X POST http://localhost:9000/master-data/interactions -H "X-User-Id: mock-user-0001" -H "Content-Type: application/json" -d '{"event_id": "<uuid>", "type": "view"}'
     */
    #[Depends('testNewsletterGetByIdReturns200')]
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
     * @param array{newsletterId: string, topicId: string, eventId: string} $ids
     *
     * curl http://localhost:9000/master-data/deep-dive/{eventId} -H "X-User-Id: mock-user-0001"
     */
    #[Depends('testNewsletterGetByIdReturns200')]
    public function testDeepDiveReturns200(array $ids): void
    {
        $response = $this->client->request(
            'GET',
            self::baseUrl() . '/master-data/deep-dive/' . $ids['eventId']
        );
        $this->assertSame(200, $response->getStatusCode());
    }

    /**
     * Topics list is public — no auth header needed.
     *
     * curl http://localhost:9000/master-data/topics
     */
    public function testTopicsListReturns200(): void
    {
        $plainClient = HttpClient::create();
        $response    = $plainClient->request('GET', self::baseUrl() . '/master-data/topics');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }

    /**
     * Topic CRUD round-trip via admin endpoints.
     *
     * curl -X POST http://localhost:9000/master-data/admin/topics -H "X-Admin-Token: dev-admin-secret" -H "Content-Type: application/json" -d '{"name":"Smoke Topic"}'
     * curl http://localhost:9000/master-data/topics/{id}
     * curl -X PUT http://localhost:9000/master-data/admin/topics/{id} -H "X-Admin-Token: dev-admin-secret" -H "Content-Type: application/json" -d '{"name":"Updated"}'
     * curl -X DELETE http://localhost:9000/master-data/admin/topics/{id} -H "X-Admin-Token: dev-admin-secret"
     */
    public function testTopicCrudRoundTrip(): void
    {
        $jsonAdmin = HttpClient::create(['headers' => [
            'Content-Type'  => 'application/json',
            'X-Admin-Token' => self::adminToken(),
        ]]);
        $base = self::baseUrl();

        $res = $jsonAdmin->request('POST', "{$base}/master-data/admin/topics",
            ['json' => ['name' => 'Smoke Topic', 'description' => 'auto']]);
        $this->assertSame(201, $res->getStatusCode(), 'POST /admin/topics failed');
        /** @var array<string, mixed> $created */
        $created = $res->toArray();
        $topicId = (string) $created['topic_id'];

        $this->tearDownCallbacks[] = static function () use ($topicId, $jsonAdmin, $base): void {
            $jsonAdmin->request('DELETE', "{$base}/master-data/admin/topics/{$topicId}")->getStatusCode();
        };

        // GET is public
        $plainClient = HttpClient::create();
        $res = $plainClient->request('GET', "{$base}/master-data/topics/{$topicId}");
        $this->assertSame(200, $res->getStatusCode());
        $this->assertSame('Smoke Topic', $res->toArray()['name']);

        $res = $jsonAdmin->request('PUT', "{$base}/master-data/admin/topics/{$topicId}",
            ['json' => ['name' => 'Updated Topic']]);
        $this->assertSame(200, $res->getStatusCode());
        $this->assertSame('Updated Topic', $res->toArray()['name']);

        $res = $jsonAdmin->request('DELETE', "{$base}/master-data/admin/topics/{$topicId}");
        $this->assertSame(204, $res->getStatusCode());

        $res = $plainClient->request('GET', "{$base}/master-data/topics/{$topicId}");
        $this->assertSame(404, $res->getStatusCode(), 'GET after DELETE should 404');
    }

    /**
     * Tests that admin token is required — no token → 401.
     * GET /master-data/admin/topics does not exist (admin reads via public /master-data/topics).
     * POST without token is the correct way to verify the listener fires on admin/topics.
     *
     * curl -X POST http://localhost:9000/master-data/admin/topics  (no token — expect 401)
     */
    public function testAdminTopicsWithoutTokenReturns401(): void
    {
        $plainClient = HttpClient::create();
        $response    = $plainClient->request('POST', self::baseUrl() . '/master-data/admin/topics');
        $this->assertSame(401, $response->getStatusCode());
    }

    /**
     * News events list is user-scoped; $this->client sends X-User-Id.
     *
     * curl http://localhost:9000/master-data/news-events -H "X-User-Id: mock-user-0001"
     */
    public function testNewsEventsListReturns200(): void
    {
        $response = $this->client->request('GET', self::baseUrl() . '/master-data/news-events');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }

    /**
     * NewsEvent CRUD round-trip via admin endpoints.
     *
     * curl -X POST http://localhost:9000/master-data/admin/news-events -H "X-Admin-Token: dev-admin-secret" -H "Content-Type: application/json" -d '{"headline":"Smoke Event","summary":"Test summary","date":"2026-01-15"}'
     */
    public function testNewsEventCrudRoundTrip(): void
    {
        $jsonAdmin = HttpClient::create(['headers' => [
            'Content-Type'  => 'application/json',
            'X-Admin-Token' => self::adminToken(),
        ]]);
        $base = self::baseUrl();

        $res = $jsonAdmin->request('POST', "{$base}/master-data/admin/news-events", [
            'json' => ['headline' => 'Smoke Event', 'summary' => 'Test summary', 'date' => '2026-01-15'],
        ]);
        $this->assertSame(201, $res->getStatusCode(), 'POST /admin/news-events failed');
        /** @var array<string, mixed> $created */
        $created = $res->toArray();
        $eventId = (string) $created['event_id'];

        $this->tearDownCallbacks[] = static function () use ($eventId, $jsonAdmin, $base): void {
            $jsonAdmin->request('DELETE', "{$base}/master-data/admin/news-events/{$eventId}")->getStatusCode();
        };

        $res = $jsonAdmin->request('GET', "{$base}/master-data/admin/news-events/{$eventId}");
        $this->assertSame(200, $res->getStatusCode());
        $this->assertSame('Smoke Event', $res->toArray()['headline']);

        $res = $jsonAdmin->request('PUT', "{$base}/master-data/admin/news-events/{$eventId}", [
            'json' => ['headline' => 'Updated Event', 'summary' => 'Updated summary', 'date' => '2026-01-20'],
        ]);
        $this->assertSame(200, $res->getStatusCode());
        $this->assertSame('Updated Event', $res->toArray()['headline']);

        $res = $jsonAdmin->request('DELETE', "{$base}/master-data/admin/news-events/{$eventId}");
        $this->assertSame(204, $res->getStatusCode());

        $res = $jsonAdmin->request('GET', "{$base}/master-data/admin/news-events/{$eventId}");
        $this->assertSame(404, $res->getStatusCode(), 'GET after DELETE should 404');
    }

    /**
     * Newsletter mutations via admin endpoints; GET (admin) verifies 404 after delete.
     *
     * curl -X POST http://localhost:9000/master-data/admin/newsletters -H "X-Admin-Token: dev-admin-secret" -H "Content-Type: application/json" -d '{"topic_id":"<uuid>","date":"2026-06-09","title":"Smoke Newsletter","narrative":"Body"}'
     */
    public function testNewsletterMutationsRoundTrip(): void
    {
        $jsonAdmin = HttpClient::create(['headers' => [
            'Content-Type'  => 'application/json',
            'X-Admin-Token' => self::adminToken(),
        ]]);
        $base = self::baseUrl();

        // Get a topic_id from the public topics list
        $topicsRes = HttpClient::create()->request('GET', "{$base}/master-data/topics");
        $this->assertSame(200, $topicsRes->getStatusCode(), 'Topics list failed');
        /** @var list<array<string, mixed>> $topics */
        $topics  = $topicsRes->toArray();
        $this->assertNotEmpty($topics, 'Topics list empty — run fixtures');
        $topicId = (string) $topics[0]['topic_id'];

        $res = $jsonAdmin->request('POST', "{$base}/master-data/admin/newsletters", [
            'json' => ['topic_id' => $topicId, 'date' => '2026-06-09',
                       'title' => 'Smoke Newsletter', 'narrative' => 'Test narrative'],
        ]);
        $this->assertSame(201, $res->getStatusCode(), 'POST /admin/newsletters failed');
        /** @var array<string, mixed> $created */
        $created      = $res->toArray();
        $newsletterId = (string) $created['newsletter_id'];

        $this->tearDownCallbacks[] = static function () use ($newsletterId, $jsonAdmin, $base): void {
            $jsonAdmin->request('DELETE', "{$base}/master-data/admin/newsletters/{$newsletterId}")->getStatusCode();
        };

        $res = $jsonAdmin->request('PUT', "{$base}/master-data/admin/newsletters/{$newsletterId}", [
            'json' => ['title' => 'Updated Newsletter', 'narrative' => 'Updated narrative'],
        ]);
        $this->assertSame(200, $res->getStatusCode(), 'PUT /admin/newsletters/{id} failed');
        $this->assertSame('Updated Newsletter', $res->toArray()['title']);

        $res = $jsonAdmin->request('DELETE', "{$base}/master-data/admin/newsletters/{$newsletterId}");
        $this->assertSame(204, $res->getStatusCode(), 'DELETE /admin/newsletters/{id} failed');

        // Verify deletion via admin GET
        $res = $jsonAdmin->request('GET', "{$base}/master-data/admin/newsletters/{$newsletterId}");
        $this->assertSame(404, $res->getStatusCode(), 'GET after DELETE should 404');
    }

    /**
     * Admin interactions list via admin endpoint.
     *
     * curl http://localhost:9000/master-data/admin/interactions -H "X-Admin-Token: dev-admin-secret"
     */
    public function testAdminInteractionsListReturns200(): void
    {
        $response = $this->adminClient->request('GET', self::baseUrl() . '/master-data/admin/interactions');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }

    /**
     * Admin subscriptions list via admin endpoint.
     *
     * curl http://localhost:9000/master-data/admin/subscriptions -H "X-Admin-Token: dev-admin-secret"
     */
    public function testAdminSubscriptionsListReturns200(): void
    {
        $response = $this->adminClient->request('GET', self::baseUrl() . '/master-data/admin/subscriptions');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }
}
