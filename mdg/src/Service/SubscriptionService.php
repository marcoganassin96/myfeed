<?php
namespace App\Service;

use App\Cache\CacheService;
use App\Repository\SubscriptionRepository;

class SubscriptionService
{
    public function __construct(
        private CacheService $cache,
        private SubscriptionRepository $repo,
    ) {}

    public function listForUser(string $userId): array
    {
        $key = "subscription:list:{$userId}";
        $cached = $this->cache->get($key);
        if ($cached !== null) {
            return $cached;
        }
        $rows = $this->repo->findByUser($userId);
        $this->cache->set($key, $rows);
        return $rows;
    }

    public function subscribe(string $userId, string $topicId): array
    {
        $this->cache->delete("subscription:list:{$userId}");
        return $this->repo->upsert($userId, $topicId);
    }

    public function unsubscribe(string $userId, string $topicId): void
    {
        $this->cache->delete("subscription:list:{$userId}");
        $this->repo->delete($userId, $topicId);
    }
}
