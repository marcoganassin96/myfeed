<?php
namespace App\Repository;

use Doctrine\ORM\EntityManagerInterface;

class InteractionRepository
{
    public function __construct(private EntityManagerInterface $em) {}

    public function save(string $userId, string $eventId, string $type): array
    {
        $conn = $this->em->getConnection();
        return $conn->fetchAssociative(
            'INSERT INTO interactions (user_id, event_id, type)
             VALUES (:uid, :eid, :type)
             RETURNING interaction_id, created_at',
            ['uid' => $userId, 'eid' => $eventId, 'type' => $type]
        ) ?: [];
    }
}
