<?php
namespace App\Repository;

use Doctrine\ORM\EntityManagerInterface;

class InteractionRepository
{
    public function __construct(private EntityManagerInterface $em) {}

    /** @return array<string, mixed> */
    public function save(string $userId, string $eventId, string $type): array
    {
        $conn = $this->em->getConnection();
        return $conn->fetchAssociative(
            'INSERT INTO interactions (interaction_id, user_id, event_id, type, created_at)
             VALUES (gen_random_uuid(), :uid, :eid, :type, NOW())
             RETURNING interaction_id, created_at',
            ['uid' => $userId, 'eid' => $eventId, 'type' => $type]
        ) ?: [];
    }

    /**
     * Returns all interactions ordered newest-first for admin listing.
     * @return list<array<string, mixed>>
     */
    public function findAll(): array
    {
        return $this->em->getConnection()->fetchAllAssociative(
            'SELECT interaction_id, user_id, event_id, type, created_at
             FROM interactions ORDER BY created_at DESC'
        );
    }
}
