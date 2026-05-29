<?php
namespace App\Tests\Service;

use App\Cache\CacheService;
use App\Repository\SubscriptionRepository;
use App\Service\SubscriptionService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;

class SubscriptionServiceTest extends TestCase
{
    private CacheService&MockObject $cache;
    private SubscriptionRepository&MockObject $repo;
    private SubscriptionService $service;

    protected function setUp(): void
    {
        $this->cache = $this->createMock(CacheService::class);
        $this->repo = $this->createMock(SubscriptionRepository::class);
        $this->service = new SubscriptionService($this->cache, $this->repo);
    }

    public function testListReturnsFromCacheOnHit(): void
    {
        $cached = [['topic_id' => 't-1', 'name' => 'tech']];
        $this->cache->method('get')->with('subscription:list:user-1')->willReturn($cached);
        $this->repo->expects($this->never())->method('findByUser');

        $this->assertSame($cached, $this->service->listForUser('user-1'));
    }

    public function testListQueriesRepoOnMissAndCaches(): void
    {
        $rows = [['topic_id' => 't-1', 'name' => 'tech', 'subscribed_at' => '2026-01-01']];
        $this->cache->method('get')->willReturn(null);
        $this->repo->method('findByUser')->willReturn($rows);
        $this->cache->expects($this->once())->method('set')->with('subscription:list:user-1', $rows);

        $this->assertSame($rows, $this->service->listForUser('user-1'));
    }

    public function testSubscribeInvalidatesCacheAndReturnsRow(): void
    {
        $row = ['topic_id' => 't-1', 'name' => 'tech', 'subscribed_at' => '2026-01-01'];
        $this->repo->method('upsert')->willReturn($row);
        $this->cache->expects($this->once())->method('delete')->with('subscription:list:user-1');

        $result = $this->service->subscribe('user-1', 't-1');
        $this->assertSame($row, $result);
    }

    public function testUnsubscribeInvalidatesCache(): void
    {
        $this->cache->expects($this->once())->method('delete')->with('subscription:list:user-1');
        $this->repo->expects($this->once())->method('delete')->with('user-1', 't-1');

        $this->service->unsubscribe('user-1', 't-1');
    }
}
