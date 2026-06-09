<?php
namespace App\Tests\Controller;

use App\Controller\AdminNewsEventController;
use App\Service\NewsEventService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class AdminNewsEventControllerTest extends TestCase
{
    private NewsEventService&MockObject $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(NewsEventService::class);
    }

    private function makeController(): AdminNewsEventController
    {
        return new AdminNewsEventController($this->service);
    }

    public function testListReturns200(): void
    {
        $events = [['event_id' => 'ev-1', 'headline' => 'Big News']];
        $this->service->method('list')->willReturn($events);
        $response = $this->makeController()->list();
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

    public function testCreateReturns201WithValidBody(): void
    {
        $created = ['event_id' => 'ev-new', 'headline' => 'H', 'summary' => 'S', 'date' => '2026-01-15'];
        $this->service->expects($this->once())->method('create')
            ->with('H', 'S', '2026-01-15', null)->willReturn($created);
        $request = Request::create('/master-data/admin/news-events', 'POST', [], [], [], [],
            json_encode(['headline' => 'H', 'summary' => 'S', 'date' => '2026-01-15']) ?: '');
        $response = $this->makeController()->create($request);
        $this->assertSame(201, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('ev-new', $body['event_id']);
    }

    public function testCreateReturns400WhenFieldsMissing(): void
    {
        $request = Request::create('/master-data/admin/news-events', 'POST', [], [], [], [],
            json_encode(['headline' => 'H']) ?: '');
        $response = $this->makeController()->create($request);
        $this->assertSame(400, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('headline, summary and date required', $body['error']);
    }

    public function testUpdateReturns200OnSuccess(): void
    {
        $updated = ['event_id' => 'ev-1', 'headline' => 'Updated'];
        $this->service->expects($this->once())->method('update')
            ->with('ev-1', 'Updated', 'S', '2026-01-20', null)->willReturn($updated);
        $request = Request::create('/master-data/admin/news-events/ev-1', 'PUT', [], [], [], [],
            json_encode(['headline' => 'Updated', 'summary' => 'S', 'date' => '2026-01-20']) ?: '');
        $response = $this->makeController()->update($request, 'ev-1');
        $this->assertSame(200, $response->getStatusCode());
    }

    public function testUpdateReturns404WhenNotFound(): void
    {
        $this->service->method('update')->willReturn(null);
        $request = Request::create('/master-data/admin/news-events/ev-x', 'PUT', [], [], [], [],
            json_encode(['headline' => 'H', 'summary' => 'S', 'date' => '2026-01-20']) ?: '');
        $response = $this->makeController()->update($request, 'ev-x');
        $this->assertSame(404, $response->getStatusCode());
    }

    public function testDeleteReturns204OnSuccess(): void
    {
        $this->service->expects($this->once())->method('delete')->with('ev-1')->willReturn(true);
        $response = $this->makeController()->delete('ev-1');
        $this->assertSame(204, $response->getStatusCode());
    }

    public function testDeleteReturns404WhenNotFound(): void
    {
        $this->service->method('delete')->willReturn(false);
        $response = $this->makeController()->delete('ev-x');
        $this->assertSame(404, $response->getStatusCode());
    }
}
