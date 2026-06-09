<?php
namespace App\Repository;

use Doctrine\ORM\EntityManagerInterface;

class AdminSubscriptionRepository
{
    /** Injected by Symfony DI; provides DBAL connection for admin-scope subscription queries. */
    public function __construct(private EntityManagerInterface $em) {}

    /**
     * Returns all subscriptions across all users for admin listing.
     * @return list<array<string, mixed>>
     */
    public function findAll(): array
    {
        return $this->em->getConnection()->fetchAllAssociative(
            'SELECT s.user_id, s.topic_id, t.name AS topic_name, s.subscribed_at
             FROM subscriptions s
             JOIN topics t ON t.topic_id = s.topic_id
             ORDER BY s.subscribed_at DESC'
        );
    }

    /** Returns true when row deleted; false when subscription did not exist. */
    public function delete(string $userId, string $topicId): bool
    {
        return $this->em->getConnection()->executeStatement(
            'DELETE FROM subscriptions WHERE user_id = :uid AND topic_id = :tid',
            ['uid' => $userId, 'tid' => $topicId]
        ) > 0;
    }
}
