<?php
namespace App\Controller;

use App\Service\TopicService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Topics')]
class TopicController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private TopicService $service) {}

    /** Lists all topics; public — no auth required; used by client apps to show subscription choices. */
    #[OA\Get(summary: 'List all topics (public)')]
    #[OA\Response(response: 200, description: 'Array of topic objects')]
    #[Route('/master-data/topics', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return new JsonResponse($this->service->list());
    }

    /** Service returns null on miss; controller owns the 404 decision to keep service type-clean. */
    #[OA\Get(summary: 'Get topic by ID (public)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 200, description: 'Topic found')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/topics/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $topic = $this->service->getById($id);
        if ($topic === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($topic);
    }
}
