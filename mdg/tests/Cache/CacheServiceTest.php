<?php
namespace App\Tests\Cache;

use App\Cache\CacheService;
use App\Cache\RedisClientInterface;
use PHPUnit\Framework\TestCase;

class CacheServiceTest extends TestCase
{
    private RedisClientInterface $redis;
    private CacheService $cache;

    protected function setUp(): void
    {
        $this->redis = $this->createMock(RedisClientInterface::class);
        $this->cache = new CacheService($this->redis, 3600);
    }

    public function testGetReturnsParsedArrayOnHit(): void
    {
        $this->redis->method('get')->with('mykey')->willReturn('{"a":1}');
        $result = $this->cache->get('mykey');
        $this->assertSame(['a' => 1], $result);
    }

    public function testGetReturnsNullOnMiss(): void
    {
        $this->redis->method('get')->with('mykey')->willReturn(null);
        $this->assertNull($this->cache->get('mykey'));
    }

    public function testSetCallsSetexWithTtlAndJson(): void
    {
        $this->redis->expects($this->once())
            ->method('setex')
            ->with('mykey', 3600, '{"x":2}');
        $this->cache->set('mykey', ['x' => 2]);
    }

    public function testDeleteCallsDel(): void
    {
        $this->redis->expects($this->once())
            ->method('del')
            ->with(['k1', 'k2']);
        $this->cache->delete('k1', 'k2');
    }

    public function testDeleteWithNoKeysDoesNotCallDel(): void
    {
        $this->redis->expects($this->never())->method('del');
        $this->cache->delete();
    }
}
