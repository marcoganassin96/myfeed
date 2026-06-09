<?php
namespace App\Tests\Controller;

use App\Controller\AdminTopicController;
use App\Service\TopicService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class AdminTopicControllerTest extends TestCase
{
    private TopicService&MockObject $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(TopicService::class);
    }

    private function makeController(): AdminTopicController
    {
        return new AdminTopicController($this->service);
    }

    public function testCreateReturns201WithValidBody(): void
    {
        $created = ['topic_id' => 'tp-new', 'name' => 'Tech', 'description' => null];
        $this->service->expects($this->once())->method('create')
            ->with('Tech', null)->willReturn($created);

        $request = Request::create('/master-data/admin/topics', 'POST', [], [], [], [],
            json_encode(['name' => 'Tech']) ?: '');
        $response = $this->makeController()->create($request);
        $this->assertSame(201, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('tp-new', $body['topic_id']);
    }

    public function testCreateReturns400WhenNameMissing(): void
    {
        $request = Request::create('/master-data/admin/topics', 'POST', [], [], [], [],
            json_encode(['description' => 'x']) ?: '');
        $response = $this->makeController()->create($request);
        $this->assertSame(400, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('name required', $body['error']);
    }

    public function testUpdateReturns200OnSuccess(): void
    {
        $updated = ['topic_id' => 'tp-1', 'name' => 'Updated', 'description' => null];
        $this->service->expects($this->once())->method('update')
            ->with('tp-1', 'Updated', null)->willReturn($updated);

        $request = Request::create('/master-data/admin/topics/tp-1', 'PUT', [], [], [], [],
            json_encode(['name' => 'Updated']) ?: '');
        $response = $this->makeController()->update($request, 'tp-1');
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('Updated', $body['name']);
    }

    public function testUpdateReturns400WhenNameMissing(): void
    {
        $request = Request::create('/master-data/admin/topics/tp-1', 'PUT', [], [], [], [],
            json_encode([]) ?: '');
        $response = $this->makeController()->update($request, 'tp-1');
        $this->assertSame(400, $response->getStatusCode());
    }

    public function testUpdateReturns404WhenNotFound(): void
    {
        $this->service->method('update')->willReturn(null);
        $request = Request::create('/master-data/admin/topics/tp-x', 'PUT', [], [], [], [],
            json_encode(['name' => 'x']) ?: '');
        $response = $this->makeController()->update($request, 'tp-x');
        $this->assertSame(404, $response->getStatusCode());
    }

    public function testDeleteReturns204OnSuccess(): void
    {
        $this->service->expects($this->once())->method('delete')->with('tp-1')->willReturn(true);
        $response = $this->makeController()->delete('tp-1');
        $this->assertSame(204, $response->getStatusCode());
    }

    public function testDeleteReturns404WhenNotFound(): void
    {
        $this->service->method('delete')->willReturn(false);
        $response = $this->makeController()->delete('tp-x');
        $this->assertSame(404, $response->getStatusCode());
    }
}
