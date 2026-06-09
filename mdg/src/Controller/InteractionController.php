<?php
namespace App\Controller;

use App\Service\InteractionService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: '👤 User / Interactions')]
class InteractionController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private InteractionService $service) {}

    /** Validates required fields here; service assumes valid input and owns persistence. */
    #[OA\Post(summary: 'Record a user interaction with a news event')]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream by UserContextListener; not validated here',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['event_id', 'type'],
            properties: [
                new OA\Property(property: 'event_id', type: 'string', format: 'uuid'),
                new OA\Property(property: 'type', type: 'string', example: 'read'),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Interaction recorded')]
    #[OA\Response(response: 400, description: 'event_id or type missing')]
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
