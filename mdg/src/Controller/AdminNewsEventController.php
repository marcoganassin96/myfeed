<?php
namespace App\Controller;

use App\Service\NewsEventService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: '🔒 Admin / NewsEvents')]
class AdminNewsEventController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private NewsEventService $service) {}

    /** Lists all news events for admin; no user context — admin sees all. */
    #[OA\Get(summary: 'List all news events (admin)', security: [['AdminToken' => []]])]
    #[OA\Response(response: 200, description: 'Array of news event objects')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/news-events', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return new JsonResponse($this->service->list());
    }

    /** Service returns null on miss; controller owns the 404 decision. */
    #[OA\Get(summary: 'Get news event by ID (admin)', security: [['AdminToken' => []]])]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 200, description: 'Event found')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/news-events/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $event = $this->service->getById($id);
        if ($event === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($event);
    }

    /** Validates headline/summary/date presence; service assumes valid input. */
    #[OA\Post(summary: 'Create news event (admin)', security: [['AdminToken' => []]])]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['headline', 'summary', 'date'],
            properties: [
                new OA\Property(property: 'headline', type: 'string', maxLength: 300),
                new OA\Property(property: 'summary', type: 'string'),
                new OA\Property(property: 'date', type: 'string', format: 'date', example: '2026-01-15'),
                new OA\Property(property: 'source_url', type: 'string', nullable: true),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Event created')]
    #[OA\Response(response: 400, description: 'Required fields missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/news-events', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['headline']) || empty($body['summary']) || empty($body['date'])) {
            return new JsonResponse(['error' => 'headline, summary and date required'], 400);
        }
        $result = $this->service->create(
            $body['headline'],
            $body['summary'],
            $body['date'],
            $body['source_url'] ?? null,
        );
        return new JsonResponse($result, 201);
    }

    /** Validates required fields; service returns null when event not found. */
    #[OA\Put(summary: 'Update news event (admin)', security: [['AdminToken' => []]])]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['headline', 'summary', 'date'],
            properties: [
                new OA\Property(property: 'headline', type: 'string', maxLength: 300),
                new OA\Property(property: 'summary', type: 'string'),
                new OA\Property(property: 'date', type: 'string', format: 'date'),
                new OA\Property(property: 'source_url', type: 'string', nullable: true),
            ],
        ),
    )]
    #[OA\Response(response: 200, description: 'Event updated')]
    #[OA\Response(response: 400, description: 'Required fields missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/news-events/{id}', methods: ['PUT'])]
    public function update(Request $request, string $id): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['headline']) || empty($body['summary']) || empty($body['date'])) {
            return new JsonResponse(['error' => 'headline, summary and date required'], 400);
        }
        $result = $this->service->update(
            $id,
            $body['headline'],
            $body['summary'],
            $body['date'],
            $body['source_url'] ?? null,
        );
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    /** Service returns false when not found; explicit 404 for clarity. */
    #[OA\Delete(summary: 'Delete news event (admin)', security: [['AdminToken' => []]])]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 204, description: 'Deleted')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/news-events/{id}', methods: ['DELETE'])]
    public function delete(string $id): Response
    {
        if (!$this->service->delete($id)) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new Response('', 204);
    }
}
