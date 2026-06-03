<?php
namespace App\Cache;

use Predis\Client;

class PredisAdapter implements RedisClientInterface
{
    private Client $client;

    public function __construct(string $redisUrl)
    {
        $this->client = new Client($redisUrl);
    }

    public function get(string $key): ?string
    {
        return $this->client->get($key);
    }

    public function setex(string $key, int $ttl, string $value): void
    {
        $this->client->setex($key, $ttl, $value);
    }

    public function del(string ...$keys): void
    {
        $this->client->del($keys);
    }
}
