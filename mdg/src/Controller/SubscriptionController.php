<?php
namespace App\Controller;

use App\Service\SubscriptionService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: '👤 User / Subscriptions')]
class SubscriptionController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private SubscriptionService $service) {}

    /** Routes listing to service layer; user_id resolved upstream by UserContextListener. */
    #[OA\Get(summary: 'List topic subscriptions for the authenticated user')]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream by UserContextListener; not validated here',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\Response(response: 200, description: 'Array of subscription objects')]
    #[Route('/master-data/subscriptions', methods: ['GET'])]
    public function list(Request $request): JsonResponse
    {
        $userId = $request->attributes->get('user_id', '');
        return new JsonResponse($this->service->listForUser($userId));
    }

    /** Validates topic_id presence here; service assumes valid input and owns persistence. */
    #[OA\Post(summary: 'Subscribe the authenticated user to a topic')]
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
            required: ['topic_id'],
            properties: [
                new OA\Property(property: 'topic_id', type: 'string', format: 'uuid'),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Subscription created')]
    #[OA\Response(response: 400, description: 'topic_id missing')]
    #[Route('/master-data/subscriptions', methods: ['POST'])]
    public function subscribe(Request $request): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['topic_id'])) {
            return new JsonResponse(['error' => 'topic_id required'], 400);
        }
        $userId = $request->attributes->get('user_id', '');
        $row = $this->service->subscribe($userId, $body['topic_id']);
        return new JsonResponse($row, 201);
    }

    /** 204 No Content on success; service throws if not found — controller catches upstream. */
    #[OA\Delete(summary: 'Unsubscribe the authenticated user from a topic')]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream by UserContextListener; not validated here',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\Parameter(
        name: 'topicId',
        in: 'path',
        required: true,
        schema: new OA\Schema(type: 'string', format: 'uuid'),
    )]
    #[OA\Response(response: 204, description: 'Unsubscribed')]
    #[Route('/master-data/subscriptions/{topicId}', methods: ['DELETE'])]
    public function unsubscribe(Request $request, string $topicId): Response
    {
        $userId = $request->attributes->get('user_id', '');
        $this->service->unsubscribe($userId, $topicId);
        return new Response('', 204);
    }
}
