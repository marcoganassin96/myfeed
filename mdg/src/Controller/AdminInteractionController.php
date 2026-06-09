<?php
namespace App\Controller;

use App\Service\InteractionService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Admin Interactions')]
class AdminInteractionController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private InteractionService $service) {}

    /** Lists all interactions across all users for admin review; no user context required. */
    #[OA\Get(summary: 'List all interactions (admin)')]
    #[OA\Response(response: 200, description: 'Array of interaction objects')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/interactions', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return new JsonResponse($this->service->listAll());
    }
}
