<?php
namespace App\Controller;

use App\Service\DeepDiveService;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

class DeepDiveController
{
    public function __construct(private DeepDiveService $service) {}

    #[Route('/master-data/deep-dive/{eventId}', methods: ['GET'])]
    public function get(Request $request, string $eventId): JsonResponse
    {
        $result = $this->service->get($eventId);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    #[Route('/master-data/deep-dive/{eventId}', methods: ['POST'])]
    public function store(Request $request, string $eventId): Response
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (!isset($body['chunks']) || !is_array($body['chunks'])) {
            return new JsonResponse(['error' => 'chunks array required'], 400);
        }
        // Explicitly (no PHPDoc) coerce to list<string> in code - PHPStan infer the correct type
        // reindexes the array and casts each element to string, sanitizing untrusted JSON input
        $chunks = array_values(array_map(fn(mixed $c): string => (string) $c, $body['chunks']));
        $this->service->store($eventId, $chunks);
        return new Response('', 201);
    }
}
