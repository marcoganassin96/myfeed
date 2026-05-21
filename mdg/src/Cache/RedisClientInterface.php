<?php
namespace App\Cache;

interface RedisClientInterface
{
    public function get(string $key): ?string;
    public function setex(string $key, int $ttl, string $value): void;
    public function del(array $keys): void;
}
