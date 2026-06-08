<?php
namespace App\Controller;

use App\Service\NewsletterService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Newsletters')]
class NewsletterController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private NewsletterService $service) {}

    /** Routes listing to service layer; user_id resolved upstream by UserContextListener. */
    #[OA\Get(summary: 'List newsletters for the authenticated user')]
    #[OA\Parameter(
        name: 'X-User-ID',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream by UserContextListener; not validated here',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\Response(response: 200, description: 'Array of newsletter objects')]
    #[Route('/master-data/newsletters', methods: ['GET'])]
    public function list(Request $request): JsonResponse
    {
        $userId = $request->attributes->get('user_id', '');
        return new JsonResponse($this->service->listForUser($userId));
    }

    /** Service returns null on miss; controller owns the 404 decision to keep service type-clean. */
    #[OA\Get(summary: 'Fetch a single newsletter by ID')]
    #[OA\Parameter(
        name: 'id',
        in: 'path',
        required: true,
        schema: new OA\Schema(type: 'string', format: 'uuid'),
    )]
    #[OA\Response(response: 200, description: 'Newsletter found')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/newsletters/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $result = $this->service->getById($id);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }
}
