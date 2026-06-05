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

    /** @var list<\Closure> Deferred cleanup callbacks run in tearDown. */
    private array $tearDownCallbacks = [];

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
            // Intentional: any failure (network error, wrong URL, PHP error) means the
            // server is unavailable. Suite will skip cleanly via setUp().
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
        $this->tearDownCallbacks = [];
    }

    /** Runs deferred cleanup closures registered during the test. */
    protected function tearDown(): void
    {
        foreach ($this->tearDownCallbacks as $callback) {
            $callback();
        }
        parent::tearDown();
    }

    /**
     * Root of the dependency chain — fetches newsletters for the seeded user and extracts IDs needed by all downstream tests.
     *
     * @return array{newsletterId: string, topicId: string}
     * 
     * Equivalent curl command:
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
     * Verifies the detail endpoint and extracts eventId for interaction + deep-dive tests.
     *
     * @param array{newsletterId: string, topicId: string} $ids
     * @return array{newsletterId: string, topicId: string, eventId: string}
     *
     * Equivalent curl command:
     * curl http://localhost:9000/master-data/newsletters/{newsletterId} -H "X-User-Id: mock-user-0001"
     * eg: curl http://localhost:9000/master-data/newsletters/33a520e3-6a7c-4224-9033-6b2d27beadae -H "X-User-Id: mock-user-0001"
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
     * Runs independently of the newsletter chain so subscriptions are verified even when newsletters fail.
     * 
     * Equivalent curl command:
     * curl http://localhost:9000/master-data/subscriptions -H "X-User-Id: mock-user-0001"
    */
    public function testSubscriptionsListReturns200(): void
    {
        $response = $this->client->request('GET', self::baseUrl() . '/master-data/subscriptions');
        $this->assertSame(200, $response->getStatusCode());
        // toArray() throws on non-array JSON; calling it validates the response shape.
        $response->toArray();
    }

    /**
     * Uses the clean smoke user (no pre-existing subscriptions) to avoid duplicate-key errors on repeated runs. Teardown deletes the created row even on failure.
     *
     * @param array{newsletterId: string, topicId: string} $ids
     *
     * Equivalent curl command:
     * curl -X POST http://localhost:9000/master-data/subscriptions -H "X-User-Id: smoke-test-user" -H "Content-Type: application/json" -d '{"topic_id": {topicId}}'
     * eg: topicId=b83747d8-48f1-4b8c-a66c-f8c9bebad597 | sports
     * curl -X POST http://localhost:9000/master-data/subscriptions -H "X-User-Id: smoke-test-user" -H "Content-Type: application/json" -d '{"topic_id": "b83747d8-48f1-4b8c-a66c-f8c9bebad597"}'
     */
    #[Depends('testNewslettersListReturns200')]
    public function testSubscribeReturns201(array $ids): void
    {
        $topicId = $ids['topicId'];
        $smokeClient = HttpClient::create([
            'headers' => [
                'X-User-Id'    => self::SMOKE_USER,
                'Content-Type' => 'application/json',
            ],
        ]);
        // Note 1: The execution creates a real subscription row in the database, so we use a dedicated smoke user and delete the row in tearDown.
        // Note 2: the endpoint returns 201 on success, but some errors (e.g. topic not found) also return 201 with an error message in the body. The test verifies the status code and response shape to catch these cases.
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
     * Verifies the interaction endpoint accepts the eventId extracted from the newsletter detail.
     *
     * @param array{newsletterId: string, topicId: string, eventId: string} $ids
     *
     * Equivalent curl command:
     * curl -X POST http://localhost:9000/master-data/interactions -H "X-User-Id: mock-user-0001" -H "Content-Type: application/json" -d '{"event_id": {eventId}, "type": "view"}'
     * eg: eventId=3c983933-9e1c-44f5-af9d-b7fd6cd613cc
     * curl -X POST http://localhost:9000/master-data/interactions -H "X-User-Id: mock-user-0001" -H "Content-Type: application/json" -d '{"event_id": "3c983933-9e1c-44f5-af9d-b7fd6cd613cc", "type": "view"}'
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
     * Fixtures seed deep_dive rows for every event, so 200 is expected.
     *
     * @param array{newsletterId: string, topicId: string, eventId: string} $ids
     *
     * Equivalent curl command:
     * curl http://localhost:9000/master-data/deep-dive/{eventId} -H "X-User-Id: mock-user-0001"
     * eg: eventId=3c983933-9e1c-44f5-af9d-b7fd6cd613cc
     * curl http://localhost:9000/master-data/deep-dive/3c983933-9e1c-44f5-af9d-b7fd6cd613cc -H "X-User-Id: mock-user-0001"
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
}
