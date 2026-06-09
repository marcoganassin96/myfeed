<?php
namespace App\Controller;

use App\Service\TopicService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Admin Topics')]
class AdminTopicController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private TopicService $service) {}

    /** Validates name presence here; service assumes valid input and owns persistence. */
    #[OA\Post(summary: 'Create topic (admin)')]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['name'],
            properties: [
                new OA\Property(property: 'name', type: 'string', maxLength: 100),
                new OA\Property(property: 'description', type: 'string', nullable: true),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Topic created')]
    #[OA\Response(response: 400, description: 'name missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/topics', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['name'])) {
            return new JsonResponse(['error' => 'name required'], 400);
        }
        $result = $this->service->create($body['name'], $body['description'] ?? null);
        return new JsonResponse($result, 201);
    }

    /** Validates name presence; service returns null when topic not found. */
    #[OA\Put(summary: 'Update topic (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['name'],
            properties: [
                new OA\Property(property: 'name', type: 'string', maxLength: 100),
                new OA\Property(property: 'description', type: 'string', nullable: true),
            ],
        ),
    )]
    #[OA\Response(response: 200, description: 'Topic updated')]
    #[OA\Response(response: 400, description: 'name missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/topics/{id}', methods: ['PUT'])]
    public function update(Request $request, string $id): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['name'])) {
            return new JsonResponse(['error' => 'name required'], 400);
        }
        $result = $this->service->update($id, $body['name'], $body['description'] ?? null);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    /** Service returns false when not found; explicit 404 over silent 204 for clarity. */
    #[OA\Delete(summary: 'Delete topic (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 204, description: 'Deleted')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/topics/{id}', methods: ['DELETE'])]
    public function delete(string $id): Response
    {
        if (!$this->service->delete($id)) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new Response('', 204);
    }
}
