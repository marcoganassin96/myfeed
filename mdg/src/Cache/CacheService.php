<?php
namespace App\Cache;

class CacheService
{
    public function __construct(
        private RedisClientInterface $redis,
        private int $cacheTtl,
    ) {}

    /** @return array<string, mixed>|null */
    public function get(string $key): ?array
    {
        $val = $this->redis->get($key);
        return $val !== null ? json_decode($val, true) : null;
    }

    /** @param array<array-key, mixed> $data */
    public function set(string $key, array $data): void
    {
        $this->redis->setex($key, $this->cacheTtl, json_encode($data, JSON_THROW_ON_ERROR));
    }

    public function delete(string ...$keys): void
    {
        if ($keys) {
            $this->redis->del(...$keys);
        }
    }

    /** Flushes all cached data — call after fixture reload to prevent stale reads. */
    public function flush(): void
    {
        $this->redis->flush();
    }
}
