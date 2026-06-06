<?php
namespace App\Tests\Cache;

use App\Cache\NullCacheAdapter;
use PHPUnit\Framework\TestCase;

class NullCacheAdapterTest extends TestCase
{
    private NullCacheAdapter $adapter;

    protected function setUp(): void
    {
        $this->adapter = new NullCacheAdapter();
    }

    public function testGetAlwaysReturnsNull(): void
    {
        $this->assertNull($this->adapter->get('any-key'));
    }

    public function testSetexDoesNotPersistValue(): void
    {
        $this->adapter->setex('key', 60, 'value');
        $this->assertNull($this->adapter->get('key'));
    }

    public function testDelDoesNotThrow(): void
    {
        $this->expectNotToPerformAssertions();
        $this->adapter->del('key1', 'key2');
    }

    public function testFlushDoesNotThrow(): void
    {
        $this->expectNotToPerformAssertions();
        $this->adapter->flush();
    }
}
