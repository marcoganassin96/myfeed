<?php
namespace App\Service;

use App\Repository\InteractionRepository;

class InteractionService
{
    public function __construct(private InteractionRepository $repo) {}

    public function record(string $userId, string $eventId, string $type): array
    {
        return $this->repo->save($userId, $eventId, $type);
    }
}
