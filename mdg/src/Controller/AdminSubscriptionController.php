<?php
namespace App\Controller;

use App\Service\AdminSubscriptionService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Admin Subscriptions')]
class AdminSubscriptionController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private AdminSubscriptionService $service) {}

    /** Lists all subscriptions across all users; no user context required — admin endpoint. */
    #[OA\Get(summary: 'List all subscriptions (admin — all users)')]
    #[OA\Response(response: 200, description: 'Array of subscription objects with user_id and topic data')]
    #[Route('/master-data/admin/subscriptions', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return new JsonResponse($this->service->listAll());
    }

    /** Admin force-delete; bypasses user context check on the standard DELETE endpoint. */
    #[OA\Delete(summary: 'Admin-delete a subscription by user + topic')]
    #[OA\Parameter(name: 'userId', in: 'path', required: true, schema: new OA\Schema(type: 'string'))]
    #[OA\Parameter(name: 'topicId', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 204, description: 'Deleted')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/subscriptions/{userId}/{topicId}', methods: ['DELETE'])]
    public function delete(string $userId, string $topicId): Response
    {
        if (!$this->service->delete($userId, $topicId)) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new Response('', 204);
    }
}
