<?php
namespace App\Tests\Controller;

use App\Controller\AdminNewsletterController;
use App\Service\NewsletterService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class AdminNewsletterControllerTest extends TestCase
{
    private NewsletterService&MockObject $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(NewsletterService::class);
    }

    private function makeController(): AdminNewsletterController
    {
        return new AdminNewsletterController($this->service);
    }

    public function testListReturns200(): void
    {
        $newsletters = [['newsletter_id' => 'nl-1', 'title' => 'Tech']];
        $this->service->method('listAll')->willReturn($newsletters);
        $response = $this->makeController()->list();
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('nl-1', $body[0]['newsletter_id']);
    }

    public function testGetReturns200OnFound(): void
    {
        $nl = ['newsletter_id' => 'nl-1', 'title' => 'Tech', 'events' => []];
        $this->service->method('getById')->with('nl-1')->willReturn($nl);
        $response = $this->makeController()->get('nl-1');
        $this->assertSame(200, $response->getStatusCode());
    }

    public function testGetReturns404WhenNotFound(): void
    {
        $this->service->method('getById')->willReturn(null);
        $response = $this->makeController()->get('nl-x');
        $this->assertSame(404, $response->getStatusCode());
    }

    public function testCreateReturns201WithValidBody(): void
    {
        $created = ['newsletter_id' => 'nl-new', 'topic_id' => 'tp-1',
                    'date' => '2026-01-01', 'title' => 'T', 'narrative' => 'N'];
        $this->service->expects($this->once())->method('create')
            ->with('tp-1', '2026-01-01', 'T', 'N')->willReturn($created);
        $request = Request::create('/master-data/admin/newsletters', 'POST', [], [], [], [],
            json_encode(['topic_id' => 'tp-1', 'date' => '2026-01-01',
                         'title' => 'T', 'narrative' => 'N']) ?: '');
        $response = $this->makeController()->create($request);
        $this->assertSame(201, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('nl-new', $body['newsletter_id']);
    }

    public function testCreateReturns400WhenFieldsMissing(): void
    {
        $request = Request::create('/master-data/admin/newsletters', 'POST', [], [], [], [],
            json_encode(['title' => 'T']) ?: '');
        $response = $this->makeController()->create($request);
        $this->assertSame(400, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('topic_id, date, title and narrative required', $body['error']);
    }

    public function testUpdateReturns200OnSuccess(): void
    {
        $updated = ['newsletter_id' => 'nl-1', 'title' => 'Updated', 'narrative' => 'N'];
        $this->service->expects($this->once())->method('update')
            ->with('nl-1', 'Updated', 'N')->willReturn($updated);
        $request = Request::create('/master-data/admin/newsletters/nl-1', 'PUT', [], [], [], [],
            json_encode(['title' => 'Updated', 'narrative' => 'N']) ?: '');
        $response = $this->makeController()->update($request, 'nl-1');
        $this->assertSame(200, $response->getStatusCode());
    }

    public function testUpdateReturns400WhenFieldsMissing(): void
    {
        $request = Request::create('/master-data/admin/newsletters/nl-1', 'PUT', [], [], [], [],
            json_encode(['title' => 'T']) ?: '');
        $response = $this->makeController()->update($request, 'nl-1');
        $this->assertSame(400, $response->getStatusCode());
    }

    public function testUpdateReturns404WhenNotFound(): void
    {
        $this->service->method('update')->willReturn(null);
        $request = Request::create('/master-data/admin/newsletters/nl-x', 'PUT', [], [], [], [],
            json_encode(['title' => 'T', 'narrative' => 'N']) ?: '');
        $response = $this->makeController()->update($request, 'nl-x');
        $this->assertSame(404, $response->getStatusCode());
    }

    public function testDeleteReturns204OnSuccess(): void
    {
        $this->service->expects($this->once())->method('delete')->with('nl-1')->willReturn(true);
        $response = $this->makeController()->delete('nl-1');
        $this->assertSame(204, $response->getStatusCode());
    }

    public function testDeleteReturns404WhenNotFound(): void
    {
        $this->service->method('delete')->willReturn(false);
        $response = $this->makeController()->delete('nl-x');
        $this->assertSame(404, $response->getStatusCode());
    }
}
