<?php
namespace App\Tests\Cache;

use App\Cache\CacheService;
use PHPUnit\Framework\TestCase;
use Predis\Client;

class CacheServiceTest extends TestCase
{
    private Client $redis;
    private CacheService $cache;

    protected function setUp(): void
    {
        $this->redis = $this->createMock(Client::class);
        $this->cache = new CacheService('redis://localhost', 3600);
        $ref = new \ReflectionProperty(CacheService::class, 'redis');
        $ref->setValue($this->cache, $this->redis);
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
