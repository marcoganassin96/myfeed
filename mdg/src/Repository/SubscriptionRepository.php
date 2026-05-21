<?php
namespace App\Repository;

use App\Entity\Subscription;
use Doctrine\ORM\EntityManagerInterface;

class SubscriptionRepository
{
    public function __construct(private EntityManagerInterface $em) {}

    public function findByUser(string $userId): array
    {
        $conn = $this->em->getConnection();
        return $conn->fetchAllAssociative(
            'SELECT s.topic_id, t.name, s.subscribed_at
             FROM subscriptions s
             JOIN topics t ON t.topic_id = s.topic_id
             WHERE s.user_id = :userId
             ORDER BY s.subscribed_at DESC',
            ['userId' => $userId]
        );
    }

    public function upsert(string $userId, string $topicId): array
    {
        $conn = $this->em->getConnection();
        return $conn->fetchAssociative(
            'INSERT INTO subscriptions (user_id, topic_id) VALUES (:uid, :tid)
             ON CONFLICT (user_id, topic_id) DO NOTHING
             RETURNING topic_id,
                 (SELECT name FROM topics WHERE topic_id = :tid) AS name,
                 subscribed_at',
            ['uid' => $userId, 'tid' => $topicId]
        ) ?: [];
    }

    public function delete(string $userId, string $topicId): void
    {
        $this->em->getConnection()->executeStatement(
            'DELETE FROM subscriptions WHERE user_id = :uid AND topic_id = :tid',
            ['uid' => $userId, 'tid' => $topicId]
        );
    }
}
