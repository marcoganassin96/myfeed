<?php
namespace App\Controller;

use App\Service\NewsletterService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Admin Newsletters')]
class AdminNewsletterController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private NewsletterService $service) {}

    /** Lists all newsletters unfiltered for admin; user-filtered list is on NewsletterController. */
    #[OA\Get(summary: 'List all newsletters (admin)')]
    #[OA\Response(response: 200, description: 'Array of newsletter objects')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/newsletters', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return new JsonResponse($this->service->listAll());
    }

    /** Service returns null on miss; controller owns the 404 decision to keep service type-clean. */
    #[OA\Get(summary: 'Get newsletter by ID (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 200, description: 'Newsletter found')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/newsletters/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $result = $this->service->getById($id);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    /** Validates all required fields; service assumes valid input and owns persistence. */
    #[OA\Post(summary: 'Create newsletter (admin)')]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['topic_id', 'date', 'title', 'narrative'],
            properties: [
                new OA\Property(property: 'topic_id', type: 'string', format: 'uuid'),
                new OA\Property(property: 'date', type: 'string', format: 'date'),
                new OA\Property(property: 'title', type: 'string', maxLength: 200),
                new OA\Property(property: 'narrative', type: 'string'),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Newsletter created')]
    #[OA\Response(response: 400, description: 'Required fields missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/newsletters', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['topic_id']) || empty($body['date']) || empty($body['title']) || empty($body['narrative'])) {
            return new JsonResponse(['error' => 'topic_id, date, title and narrative required'], 400);
        }
        $result = $this->service->create($body['topic_id'], $body['date'], $body['title'], $body['narrative']);
        return new JsonResponse($result, 201);
    }

    /** Validates that title and narrative are present; service owns persistence and type safety. */
    #[OA\Put(summary: 'Update newsletter title and narrative (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['title', 'narrative'],
            properties: [
                new OA\Property(property: 'title', type: 'string', maxLength: 200),
                new OA\Property(property: 'narrative', type: 'string'),
            ],
        ),
    )]
    #[OA\Response(response: 200, description: 'Newsletter updated')]
    #[OA\Response(response: 400, description: 'title or narrative missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/newsletters/{id}', methods: ['PUT'])]
    public function update(Request $request, string $id): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['title']) || empty($body['narrative'])) {
            return new JsonResponse(['error' => 'title and narrative required'], 400);
        }
        $result = $this->service->update($id, $body['title'], $body['narrative']);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    /** Service returns false when not found; explicit 404 avoids ambiguity with successful deletes. */
    #[OA\Delete(summary: 'Delete newsletter (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 204, description: 'Deleted')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/newsletters/{id}', methods: ['DELETE'])]
    public function delete(string $id): Response
    {
        if (!$this->service->delete($id)) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new Response('', 204);
    }
}
