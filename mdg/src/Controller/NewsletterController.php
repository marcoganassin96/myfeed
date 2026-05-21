<?php
namespace App\Controller;

use App\Service\NewsletterService;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

class NewsletterController
{
    public function __construct(private NewsletterService $service) {}

    #[Route('/master-data/newsletters', methods: ['GET'])]
    public function list(Request $request): JsonResponse
    {
        $userId = $request->attributes->get('user_id', '');
        return new JsonResponse($this->service->listForUser($userId));
    }

    #[Route('/master-data/newsletters/{id}', methods: ['GET'])]
    public function get(Request $request, string $id): JsonResponse
    {
        $result = $this->service->getById($id);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }
}
