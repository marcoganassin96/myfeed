<?php
namespace App\Cache;

interface RedisClientInterface
{
    public function get(string $key): ?string;
    public function setex(string $key, int $ttl, string $value): void;

    /*
    * Redis DEL cares only about values (the key strings), not array indices.
    * So best type would be string[], which is equal to array<int|string, string>, that accepts both indexed and associative arrays, as long as the values are strings.
    * But since I prefer to simply allow client to call delete with both collection or single keys, I will use variadic string parameters, which allow:
    * - `delete('key')`
    * - `delete(...['key1', 'key2'])`
    Why not string[]|string: because it would forces every implementation to handle both cases internally in two distinct code paths
    */
    public function del(string ...$keys): void;
}
