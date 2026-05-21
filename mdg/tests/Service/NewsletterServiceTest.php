<?php
namespace App\Tests\Service;

use App\Cache\CacheService;
use App\Repository\NewsletterRepository;
use App\Service\NewsletterService;
use PHPUnit\Framework\TestCase;

class NewsletterServiceTest extends TestCase
{
    private CacheService $cache;
    private NewsletterRepository $repo;
    private NewsletterService $service;

    protected function setUp(): void
    {
        $this->cache = $this->createMock(CacheService::class);
        $this->repo = $this->createMock(NewsletterRepository::class);
        $this->service = new NewsletterService($this->cache, $this->repo);
    }

    public function testListReturnsFromCacheOnHit(): void
    {
        $cached = [['newsletter_id' => 'nl-1', 'title' => 'Tech']];
        $this->cache->method('get')->with('newsletter:list:user-1')->willReturn($cached);
        $this->repo->expects($this->never())->method('findLatestPerTopicForUser');

        $result = $this->service->listForUser('user-1');
        $this->assertSame($cached, $result);
    }

    public function testListQueriesRepoOnCacheMissAndCachesResult(): void
    {
        $rows = [['newsletter_id' => 'nl-1', 'title' => 'Tech']];
        $this->cache->method('get')->willReturn(null);
        $this->repo->method('findLatestPerTopicForUser')->with('user-1')->willReturn($rows);
        $this->cache->expects($this->once())->method('set')->with('newsletter:list:user-1', $rows);

        $result = $this->service->listForUser('user-1');
        $this->assertSame($rows, $result);
    }

    public function testGetByIdReturnsFromCacheOnHit(): void
    {
        $cached = ['newsletter_id' => 'nl-1', 'title' => 'Tech', 'events' => []];
        $this->cache->method('get')->with('newsletter:nl-1')->willReturn($cached);
        $this->repo->expects($this->never())->method('findByIdWithEvents');

        $result = $this->service->getById('nl-1');
        $this->assertSame($cached, $result);
    }

    public function testGetByIdReturnsNullWhenNotFound(): void
    {
        $this->cache->method('get')->willReturn(null);
        $this->repo->method('findByIdWithEvents')->willReturn(['rows' => [], 'links' => []]);

        $result = $this->service->getById('nl-not-found');
        $this->assertNull($result);
    }

    public function testGetByIdAssemblesResponseAndCachesOnMiss(): void
    {
        $this->cache->method('get')->willReturn(null);
        $this->repo->method('findByIdWithEvents')->willReturn([
            'rows' => [[
                'newsletter_id' => 'nl-1', 'date' => '2026-01-01',
                'title' => 'Tech', 'narrative' => 'Story',
                'position' => 1, 'event_id' => 'ev-1',
                'headline' => 'H', 'summary' => 'S', 'event_date' => '2026-01-01',
                'thread_id' => 'th-1', 'thread_name' => 'Thread A',
                'previous_event_id' => null,
            ]],
            'links' => [],
        ]);
        $this->cache->expects($this->once())->method('set')->with(
            'newsletter:nl-1',
            $this->arrayHasKey('newsletter_id')
        );

        $result = $this->service->getById('nl-1');
        $this->assertSame('nl-1', $result['newsletter_id']);
        $this->assertCount(1, $result['events']);
        $this->assertSame([], $result['context_links']);
    }
}
