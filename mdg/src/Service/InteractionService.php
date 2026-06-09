<?php
namespace App\Service;

use App\Repository\InteractionRepository;

class InteractionService
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private InteractionRepository $repo) {}

    /** @return array<string, mixed> */
    public function record(string $userId, string $eventId, string $type): array
    {
        return $this->repo->save($userId, $eventId, $type);
    }

    /**
     * Returns all interactions for admin review; no cache — admin reads bypass user TTLs.
     * @return list<array<string, mixed>>
     */
    public function listAll(): array
    {
        return $this->repo->findAll();
    }
}
