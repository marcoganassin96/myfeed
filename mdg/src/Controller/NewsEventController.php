<?php
namespace App\Controller;

use App\Service\NewsEventService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: '👤 User / NewsEvents')]
class NewsEventController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private NewsEventService $service) {}

    /** Lists news events for authenticated user; user_id set by UserContextListener for future filtering. */
    #[OA\Get(summary: 'List news events (user)')]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream; stored in request attributes by UserContextListener',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\Response(response: 200, description: 'Array of news event objects')]
    #[Route('/master-data/news-events', methods: ['GET'])]
    public function list(Request $request): JsonResponse
    {
        // user_id available via $request->attributes->get('user_id') for future per-user filtering
        return new JsonResponse($this->service->list());
    }

    /** Service returns null on miss; controller owns the 404 decision. */
    #[OA\Get(summary: 'Get news event by ID (user)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\Response(response: 200, description: 'Event found')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/news-events/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $event = $this->service->getById($id);
        if ($event === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($event);
    }
}
