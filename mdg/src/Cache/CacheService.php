<?php
namespace App\Cache;

use Predis\Client;

class CacheService
{
    private Client $redis;

    public function __construct(string $redisUrl, private int $cacheTtl)
    {
        $this->redis = new Client($redisUrl);
    }

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
