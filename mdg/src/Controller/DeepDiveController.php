<?php
namespace App\Controller;

use App\Service\DeepDiveService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'DeepDive')]
class DeepDiveController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private DeepDiveService $service) {}

    /** Service returns null on miss; controller owns the 404 decision to keep service type-clean. */
    #[OA\Get(summary: 'Fetch deep dive content for a news event')]
    #[OA\Parameter(
        name: 'eventId',
        in: 'path',
        required: true,
        schema: new OA\Schema(type: 'string', format: 'uuid'),
    )]
    #[OA\Response(response: 200, description: 'Deep dive found')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/deep-dive/{eventId}', methods: ['GET'])]
    public function get(string $eventId): JsonResponse
    {
        $result = $this->service->get($eventId);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    /** Coerces chunks to list<string> here so service receives a sanitized, typed input. */
    #[OA\Post(summary: 'Store deep dive chunks for a news event')]
    #[OA\Parameter(
        name: 'eventId',
        in: 'path',
        required: true,
        schema: new OA\Schema(type: 'string', format: 'uuid'),
    )]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['chunks'],
            properties: [
                new OA\Property(
                    property: 'chunks',
                    type: 'array',
                    items: new OA\Items(type: 'string'),
                ),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Chunks stored')]
    #[OA\Response(response: 400, description: 'chunks array missing or not an array')]
    #[Route('/master-data/deep-dive/{eventId}', methods: ['POST'])]
    public function store(Request $request, string $eventId): Response
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (!isset($body['chunks']) || !is_array($body['chunks'])) {
            return new JsonResponse(['error' => 'chunks array required'], 400);
        }
        // reindexes the array and casts each element to string, sanitizing untrusted JSON input
        $chunks = array_values(array_map(fn(mixed $c): string => (string) $c, $body['chunks']));
        $this->service->store($eventId, $chunks);
        return new Response('', 201);
    }
}
