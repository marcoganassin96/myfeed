<?php
namespace App\Controller;

use App\Service\InteractionService;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

class InteractionController
{
    public function __construct(private InteractionService $service) {}

    #[Route('/master-data/interactions', methods: ['POST'])]
    public function record(Request $request): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['event_id']) || empty($body['type'])) {
            return new JsonResponse(['error' => 'event_id and type required'], 400);
        }
        $userId = $request->attributes->get('user_id', '');
        $result = $this->service->record($userId, $body['event_id'], $body['type']);
        return new JsonResponse($result, 201);
    }
}
