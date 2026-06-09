<?php
namespace App\Repository;

use Doctrine\ORM\EntityManagerInterface;

class TopicRepository
{
    /** Injected by Symfony DI; EntityManager provides DBAL connection for raw SQL. */
    public function __construct(private EntityManagerInterface $em) {}

    /** @return list<array<string, mixed>> */
    public function findAll(): array
    {
        return $this->em->getConnection()->fetchAllAssociative(
            'SELECT topic_id, name, description FROM topics ORDER BY name'
        );
    }

    /** Returns null when not found; caller decides 404 response. */
    /** @return array<string, mixed>|null */
    public function findById(string $id): ?array
    {
        $row = $this->em->getConnection()->fetchAssociative(
            'SELECT topic_id, name, description FROM topics WHERE topic_id = :id',
            ['id' => $id]
        );
        return $row !== false ? $row : null;
    }

    /** Uses RETURNING to return inserted row without a second query. */
    /** @return array<string, mixed> */
    public function create(string $name, ?string $description): array
    {
        $row = $this->em->getConnection()->fetchAssociative(
            'INSERT INTO topics (topic_id, name, description)
             VALUES (gen_random_uuid(), :name, :description)
             RETURNING topic_id, name, description',
            ['name' => $name, 'description' => $description]
        );
        if ($row === false) {
            throw new \RuntimeException('INSERT INTO topics returned no row');
        }
        return $row;
    }

    /** Uses RETURNING; returns null when topic_id not found. */
    /** @return array<string, mixed>|null */
    public function update(string $id, string $name, ?string $description): ?array
    {
        $row = $this->em->getConnection()->fetchAssociative(
            'UPDATE topics SET name = :name, description = :description
             WHERE topic_id = :id
             RETURNING topic_id, name, description',
            ['id' => $id, 'name' => $name, 'description' => $description]
        );
        return $row !== false ? $row : null;
    }

    /** Returns true when a row was deleted; false when topic did not exist. */
    public function delete(string $id): bool
    {
        return $this->em->getConnection()->executeStatement(
            'DELETE FROM topics WHERE topic_id = :id',
            ['id' => $id]
        ) > 0;
    }
}
