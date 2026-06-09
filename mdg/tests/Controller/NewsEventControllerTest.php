<?php
namespace App\Tests\Controller;

use App\Controller\NewsEventController;
use App\Service\NewsEventService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class NewsEventControllerTest extends TestCase
{
    private NewsEventService&MockObject $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(NewsEventService::class);
    }

    private function makeController(): NewsEventController
    {
        return new NewsEventController($this->service);
    }

    public function testListReturns200(): void
    {
        $events = [['event_id' => 'ev-1', 'headline' => 'Big News']];
        $this->service->method('list')->willReturn($events);

        $request = Request::create('/master-data/news-events', 'GET');
        $request->attributes->set('user_id', 'user-1');

        $response = $this->makeController()->list($request);
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('ev-1', $body[0]['event_id']);
    }

    public function testGetReturns200OnFound(): void
    {
        $event = ['event_id' => 'ev-1', 'headline' => 'Big News'];
        $this->service->method('getById')->with('ev-1')->willReturn($event);
        $response = $this->makeController()->get('ev-1');
        $this->assertSame(200, $response->getStatusCode());
    }

    public function testGetReturns404WhenNotFound(): void
    {
        $this->service->method('getById')->willReturn(null);
        $response = $this->makeController()->get('ev-x');
        $this->assertSame(404, $response->getStatusCode());
    }
}
