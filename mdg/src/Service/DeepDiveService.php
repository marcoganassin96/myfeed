<?php
namespace App\Service;

use App\Cache\CacheService;
use App\Repository\DeepDiveRepository;

class DeepDiveService
{
    public function __construct(
        private CacheService $cache,
        private DeepDiveRepository $repo,
    ) {}

    /** @return array<string, mixed>|null */
    public function get(string $eventId): ?array
    {
        $key = "deep-dive:{$eventId}";
        $cached = $this->cache->get($key);
        if ($cached !== null) {
            return $cached;
        }
        $entity = $this->repo->findByEventId($eventId);
        if ($entity === null) {
            return null;
        }
        $data = ['chunks' => $entity->getChunks()];
        $this->cache->set($key, $data);
        return $data;
    }

    /** @param list<string> $chunks */
    public function store(string $eventId, array $chunks): void
    {
        $this->repo->save($eventId, $chunks);
        $this->cache->set("deep-dive:{$eventId}", ['chunks' => $chunks]);
    }
}
