<?php
namespace App\Tests\Controller;

use App\Controller\TopicController;
use App\Service\TopicService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;

class TopicControllerTest extends TestCase
{
    private TopicService&MockObject $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(TopicService::class);
    }

    private function makeController(): TopicController
    {
        return new TopicController($this->service);
    }

    public function testListReturns200(): void
    {
        $topics = [['topic_id' => 'tp-1', 'name' => 'Tech', 'description' => null]];
        $this->service->method('list')->willReturn($topics);

        $response = $this->makeController()->list();
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('tp-1', $body[0]['topic_id']);
    }

    public function testGetReturns200OnFound(): void
    {
        $topic = ['topic_id' => 'tp-1', 'name' => 'Tech', 'description' => null];
        $this->service->method('getById')->with('tp-1')->willReturn($topic);

        $response = $this->makeController()->get('tp-1');
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('Tech', $body['name']);
    }

    public function testGetReturns404WhenNotFound(): void
    {
        $this->service->method('getById')->willReturn(null);
        $response = $this->makeController()->get('tp-x');
        $this->assertSame(404, $response->getStatusCode());
    }
}
