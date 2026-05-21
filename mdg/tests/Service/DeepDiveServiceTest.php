<?php
namespace App\Tests\Service;

use App\Cache\CacheService;
use App\Repository\DeepDiveRepository;
use App\Service\DeepDiveService;
use PHPUnit\Framework\TestCase;

class DeepDiveServiceTest extends TestCase
{
    private CacheService $cache;
    private DeepDiveRepository $repo;
    private DeepDiveService $service;

    protected function setUp(): void
    {
        $this->cache = $this->createMock(CacheService::class);
        $this->repo = $this->createMock(DeepDiveRepository::class);
        $this->service = new DeepDiveService($this->cache, $this->repo);
    }

    public function testGetReturnsFromCacheOnHit(): void
    {
        $cached = ['chunks' => ['chunk one']];
        $this->cache->method('get')->with('deep-dive:ev-1')->willReturn($cached);
        $this->repo->expects($this->never())->method('findByEventId');

        $this->assertSame($cached, $this->service->get('ev-1'));
    }

    public function testGetReturnsNullOnMiss(): void
    {
        $this->cache->method('get')->willReturn(null);
        $this->repo->method('findByEventId')->willReturn(null);

        $this->assertNull($this->service->get('ev-1'));
    }

    public function testStoreWritesToRepoAndCache(): void
    {
        $chunks = ['chunk one', 'chunk two'];
        $this->repo->expects($this->once())->method('save')->with('ev-1', $chunks);
        $this->cache->expects($this->once())->method('set')->with(
            'deep-dive:ev-1',
            ['chunks' => $chunks]
        );

        $this->service->store('ev-1', $chunks);
    }
}
