<?php
namespace App\Controller;

use App\Service\SubscriptionService;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

class SubscriptionController
{
    public function __construct(private SubscriptionService $service) {}

    #[Route('/master-data/subscriptions', methods: ['GET'])]
    public function list(Request $request): JsonResponse
    {
        $userId = $request->attributes->get('user_id', '');
        return new JsonResponse($this->service->listForUser($userId));
    }

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

    #[Route('/master-data/subscriptions/{topicId}', methods: ['DELETE'])]
    public function unsubscribe(Request $request, string $topicId): Response
    {
        $userId = $request->attributes->get('user_id', '');
        $this->service->unsubscribe($userId, $topicId);
        return new Response('', 204);
    }
}
