<?php
namespace App\Service;

use App\Repository\TopicRepository;

class TopicService
{
    /** No cache — admin reads are low-frequency and bypass user-personalised TTLs. */
    public function __construct(private TopicRepository $repo) {}

    /**
     * Lists all topics; thin pass-through — no cache, admin reads are infrequent.
     *
     * @return list<array<string, mixed>>
     */
    public function list(): array
    {
        return $this->repo->findAll();
    }

    /**
     * Returns null when not found so the controller can decide the 404 response.
     *
     * @return array<string, mixed>|null
     */
    public function getById(string $id): ?array
    {
        return $this->repo->findById($id);
    }

    /**
     * Delegates creation to the repository; returns the inserted row via RETURNING.
     *
     * @return array<string, mixed>
     */
    public function create(string $name, ?string $description): array
    {
        return $this->repo->create($name, $description);
    }

    /**
     * Returns null when the topic_id does not exist so callers control the 404 response.
     *
     * @return array<string, mixed>|null
     */
    public function update(string $id, string $name, ?string $description): ?array
    {
        return $this->repo->update($id, $name, $description);
    }

    /** Returns true if deleted, false if topic did not exist. */
    public function delete(string $id): bool
    {
        return $this->repo->delete($id);
    }
}
