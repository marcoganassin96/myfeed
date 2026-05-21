<?php
namespace App\Cache;

class CacheService
{
    public function __construct(
        private RedisClientInterface $redis,
        private int $cacheTtl,
    ) {}

    public function get(string $key): ?array
    {
        $val = $this->redis->get($key);
        return $val !== null ? json_decode($val, true) : null;
    }

    public function set(string $key, array $data): void
    {
        $this->redis->setex($key, $this->cacheTtl, json_encode($data));
    }

    public function delete(string ...$keys): void
    {
        if ($keys) {
            $this->redis->del($keys);
        }
    }
}
