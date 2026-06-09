<?php
namespace App\Tests\Controller;

use App\Service\AdminSubscriptionService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;

class AdminSubscriptionControllerTest extends TestCase
{
    private AdminSubscriptionService&MockObject $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(AdminSubscriptionService::class);
    }

    public function testListReturns200(): void
    {
        $rows = [['user_id' => 'u-1', 'topic_id' => 'tp-1', 'topic_name' => 'Tech', 'subscribed_at' => '2026-01-01']];
        $this->service->expects($this->once())->method('listAll')->willReturn($rows);
        $controller = $this->makeController();
        $response   = $controller->list();
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('u-1', $body[0]['user_id']);
    }

    public function testDeleteReturns204(): void
    {
        $this->service->expects($this->once())->method('delete')->with('u-1', 'tp-1')->willReturn(true);
        $this->assertSame(204, $this->makeController()->delete('u-1', 'tp-1')->getStatusCode());
    }

    public function testDeleteReturns404WhenNotFound(): void
    {
        $this->service->method('delete')->willReturn(false);
        $response = $this->makeController()->delete('u-1', 'tp-nope');
        $this->assertSame(404, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('Not found', $body['error']);
    }

    private function makeController(): \App\Controller\AdminSubscriptionController
    {
        return new \App\Controller\AdminSubscriptionController($this->service);
    }
}
