<?php
namespace App\Cache;

/** No-op cache adapter for environments without a Redis instance. All reads return null; writes are discarded. */
class NullCacheAdapter implements RedisClientInterface
{
    /** Always returns null — no backing store. */
    public function get(string $key): ?string
    {
        return null;
    }

    /** No-op — value is discarded. */
    public function setex(string $key, int $ttl, string $value): void
    {
    }

    /** No-op — nothing to delete. */
    public function del(string ...$keys): void
    {
    }

    /** No-op — nothing to flush. */
    public function flush(): void
    {
    }
}
