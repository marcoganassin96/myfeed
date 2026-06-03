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

    /**
     * Persists a deep-dive analysis and primes the cache for subsequent reads.
     *
     * Called once after the LLM pipeline finishes generating a deep-dive for a news event.
     * Chunks are the ordered SSE frames produced by the stream; storing them allows the
     * endpoint to replay the stream on demand without re-invoking the LLM.
     *
     * @param string      $eventId Identifier of the news event this deep-dive belongs to.
     * @param list<string> $chunks  Ordered sequence of text pieces that form the full analysis,
     *                              each corresponding to one SSE data frame when replayed.
     */
    public function store(string $eventId, array $chunks): void
    {
        $this->repo->save($eventId, $chunks);
        $this->cache->set("deep-dive:{$eventId}", ['chunks' => $chunks]);
    }
}
