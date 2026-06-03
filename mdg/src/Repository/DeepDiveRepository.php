<?php
namespace App\Repository;

use App\Entity\DeepDive;
use Doctrine\ORM\EntityManagerInterface;

class DeepDiveRepository
{
    public function __construct(private EntityManagerInterface $em) {}

    public function findByEventId(string $eventId): ?DeepDive
    {
        return $this->em->find(DeepDive::class, $eventId);
    }

    /** @param list<string> $chunks */
    public function save(string $eventId, array $chunks): DeepDive
    {
        $deepDive = $this->em->find(DeepDive::class, $eventId) ?? new DeepDive();
        $deepDive->setEventId($eventId);
        $deepDive->setChunks($chunks);
        $deepDive->setCreatedAt(new \DateTimeImmutable());
        $this->em->persist($deepDive);
        $this->em->flush();
        return $deepDive;
    }
}
