<?php
namespace App\Service;

use App\Repository\NewsEventRepository;

class NewsEventService
{
    /** No cache — admin reads are low-frequency and bypass user-personalised TTLs. */
    public function __construct(private NewsEventRepository $repo) {}

    /**
     * Lists all news events; thin pass-through — no cache, admin reads are infrequent.
     * @return list<array<string, mixed>>
     */
    public function list(): array
    {
        return $this->repo->findAll();
    }

    /**
     * Returns null when not found so the controller can decide the 404 response.
     * @return array<string, mixed>|null
     */
    public function getById(string $id): ?array
    {
        return $this->repo->findById($id);
    }

    /**
     * Delegates creation to the repository; returns the inserted row via RETURNING.
     * @return array<string, mixed>
     */
    public function create(string $headline, string $summary, string $date, ?string $sourceUrl): array
    {
        return $this->repo->create($headline, $summary, $date, $sourceUrl);
    }

    /**
     * Returns null when the event_id does not exist so callers control the 404 response.
     * @return array<string, mixed>|null
     */
    public function update(
        string $id,
        string $headline,
        string $summary,
        string $date,
        ?string $sourceUrl
    ): ?array {
        return $this->repo->update($id, $headline, $summary, $date, $sourceUrl);
    }

    /** Returns true if deleted, false if event did not exist. */
    public function delete(string $id): bool
    {
        return $this->repo->delete($id);
    }
}
