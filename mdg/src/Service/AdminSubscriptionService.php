<?php
namespace App\Service;

use App\Repository\AdminSubscriptionRepository;

class AdminSubscriptionService
{
    /** Separate from SubscriptionService — admin scope bypasses user context and cache. */
    public function __construct(private AdminSubscriptionRepository $repo) {}

    /**
     * Returns all subscriptions for admin overview; bypasses per-user cache TTLs.
     * @return list<array<string, mixed>>
     */
    public function listAll(): array
    {
        return $this->repo->findAll();
    }

    /** Returns true if deleted, false if subscription did not exist. */
    public function delete(string $userId, string $topicId): bool
    {
        return $this->repo->delete($userId, $topicId);
    }
}
