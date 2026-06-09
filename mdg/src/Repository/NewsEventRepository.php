<?php
namespace App\Repository;

use Doctrine\ORM\EntityManagerInterface;

class NewsEventRepository
{
    /** Injected by Symfony DI; EntityManager provides DBAL connection for raw SQL. */
    public function __construct(private EntityManagerInterface $em) {}

    /** @return list<array<string, mixed>> */
    public function findAll(): array
    {
        return $this->em->getConnection()->fetchAllAssociative(
            'SELECT event_id, headline, summary, date, source_url
             FROM news_events ORDER BY date DESC'
        );
    }

    /**
     * Returns null when not found; caller decides 404 response.
     *
     * @return array<string, mixed>|null
     */
    public function findById(string $id): ?array
    {
        $row = $this->em->getConnection()->fetchAssociative(
            'SELECT event_id, headline, summary, date, source_url
             FROM news_events WHERE event_id = :id',
            ['id' => $id]
        );
        return $row !== false ? $row : null;
    }

    /**
     * Uses RETURNING to return inserted row without a second query.
     *
     * @return array<string, mixed>
     */
    public function create(string $headline, string $summary, string $date, ?string $sourceUrl): array
    {
        $row = $this->em->getConnection()->fetchAssociative(
            'INSERT INTO news_events (event_id, headline, summary, date, source_url)
             VALUES (gen_random_uuid(), :headline, :summary, :date, :source_url)
             RETURNING event_id, headline, summary, date, source_url',
            ['headline' => $headline, 'summary' => $summary, 'date' => $date, 'source_url' => $sourceUrl]
        );
        if ($row === false) {
            throw new \RuntimeException('INSERT INTO news_events returned no row');
        }
        return $row;
    }

    /**
     * Uses RETURNING; returns null when event_id not found.
     *
     * @return array<string, mixed>|null
     */
    public function update(
        string $id,
        string $headline,
        string $summary,
        string $date,
        ?string $sourceUrl
    ): ?array {
        $row = $this->em->getConnection()->fetchAssociative(
            'UPDATE news_events
             SET headline = :headline, summary = :summary, date = :date, source_url = :source_url
             WHERE event_id = :id
             RETURNING event_id, headline, summary, date, source_url',
            ['id' => $id, 'headline' => $headline, 'summary' => $summary,
             'date' => $date, 'source_url' => $sourceUrl]
        );
        return $row !== false ? $row : null;
    }

    /** Returns true when a row was deleted; false when event did not exist. */
    public function delete(string $id): bool
    {
        return $this->em->getConnection()->executeStatement(
            'DELETE FROM news_events WHERE event_id = :id',
            ['id' => $id]
        ) > 0;
    }
}
