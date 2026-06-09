<?php
namespace App\Tests\Controller;

use App\Service\InteractionService;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class InteractionControllerTest extends TestCase
{
    public function testRecordReturns201(): void
    {
        $service = $this->createMock(InteractionService::class);
        $service->expects($this->once())->method('record')
            ->willReturn(['interaction_id' => 'ix-1', 'created_at' => '2026-01-01T00:00:00+00:00']);

        $request = Request::create('/master-data/interactions', 'POST', [], [], [], [],
            json_encode(['event_id' => 'ev-1', 'type' => 'click'], JSON_THROW_ON_ERROR));
        $request->headers->set('Content-Type', 'application/json');
        $request->attributes->set('user_id', 'user-1');

        $controller = new \App\Controller\InteractionController($service);
        $response   = $controller->record($request);
        $this->assertSame(201, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('ix-1', $body['interaction_id']);
    }

    public function testRecordReturns400WhenEventIdMissing(): void
    {
        $service = $this->createMock(InteractionService::class);
        $request = Request::create('/master-data/interactions', 'POST', [], [], [], [],
            json_encode(['type' => 'click'], JSON_THROW_ON_ERROR));
        $request->headers->set('Content-Type', 'application/json');
        $request->attributes->set('user_id', 'user-1');

        $controller = new \App\Controller\InteractionController($service);
        $response   = $controller->record($request);
        $this->assertSame(400, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('event_id and type required', $body['error']);
    }
}
