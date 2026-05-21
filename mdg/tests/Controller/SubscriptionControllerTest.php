<?php
namespace App\Tests\Controller;

use App\Service\SubscriptionService;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class SubscriptionControllerTest extends TestCase
{
    private SubscriptionService $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(SubscriptionService::class);
    }

    public function testListReturns200(): void
    {
        $this->service->method('listForUser')->willReturn([['topic_id' => 't-1']]);
        $request = Request::create('/master-data/subscriptions', 'GET');
        $request->attributes->set('user_id', 'user-1');

        $response = $this->makeController()->list($request);
        $this->assertSame(200, $response->getStatusCode());
    }

    public function testSubscribeReturns201(): void
    {
        $this->service->method('subscribe')->willReturn(['topic_id' => 't-1', 'name' => 'tech', 'subscribed_at' => '2026-01-01']);
        $request = Request::create('/master-data/subscriptions', 'POST', [], [], [], [],
            json_encode(['topic_id' => 't-1']));
        $request->headers->set('Content-Type', 'application/json');
        $request->attributes->set('user_id', 'user-1');

        $response = $this->makeController()->subscribe($request);
        $this->assertSame(201, $response->getStatusCode());
    }

    public function testSubscribeReturns400WhenTopicIdMissing(): void
    {
        $request = Request::create('/master-data/subscriptions', 'POST', [], [], [], [],
            json_encode([]));
        $request->headers->set('Content-Type', 'application/json');
        $request->attributes->set('user_id', 'user-1');

        $response = $this->makeController()->subscribe($request);
        $this->assertSame(400, $response->getStatusCode());
    }

    public function testUnsubscribeReturns204(): void
    {
        $request = Request::create('/master-data/subscriptions/t-1', 'DELETE');
        $request->attributes->set('user_id', 'user-1');

        $response = $this->makeController()->unsubscribe($request, 't-1');
        $this->assertSame(204, $response->getStatusCode());
    }

    private function makeController(): \App\Controller\SubscriptionController
    {
        return new \App\Controller\SubscriptionController($this->service);
    }
}
