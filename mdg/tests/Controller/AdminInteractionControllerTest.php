<?php
namespace App\Tests\Controller;

use App\Controller\AdminInteractionController;
use App\Service\InteractionService;
use PHPUnit\Framework\TestCase;

class AdminInteractionControllerTest extends TestCase
{
    public function testListReturns200(): void
    {
        $service = $this->createMock(InteractionService::class);
        $rows    = [['interaction_id' => 'ix-1', 'type' => 'read']];
        $service->method('listAll')->willReturn($rows);

        $controller = new AdminInteractionController($service);
        $response   = $controller->list();
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('ix-1', $body[0]['interaction_id']);
    }
}
