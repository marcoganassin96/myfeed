<?php
namespace App\Tests\Controller;

use App\Service\NewsletterService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class NewsletterControllerTest extends TestCase
{
    private NewsletterService&MockObject $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(NewsletterService::class);
    }

    public function testListReturns200WithNewsletters(): void
    {
        $newsletters = [['newsletter_id' => 'nl-1', 'title' => 'Tech']];
        $this->service->method('listForUser')->willReturn($newsletters);

        $controller = $this->makeController();
        $request = Request::create('/master-data/newsletters', 'GET');
        $request->attributes->set('user_id', 'user-1');

        $response = $controller->list($request);
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode($response->getContent(), true);
        $this->assertSame('nl-1', $body[0]['newsletter_id']);
    }

    public function testGetReturns200OnFound(): void
    {
        $nl = ['newsletter_id' => 'nl-1', 'title' => 'Tech', 'events' => []];
        $this->service->method('getById')->with('nl-1')->willReturn($nl);

        $controller = $this->makeController();
        $request = Request::create('/master-data/newsletters/nl-1', 'GET');
        $request->attributes->set('user_id', 'user-1');

        $response = $controller->get($request, 'nl-1');
        $this->assertSame(200, $response->getStatusCode());
    }

    public function testGetReturns404WhenNotFound(): void
    {
        $this->service->method('getById')->willReturn(null);

        $controller = $this->makeController();
        $request = Request::create('/master-data/newsletters/nl-x', 'GET');
        $request->attributes->set('user_id', 'user-1');

        $response = $controller->get($request, 'nl-x');
        $this->assertSame(404, $response->getStatusCode());
    }

    private function makeController(): \App\Controller\NewsletterController
    {
        return new \App\Controller\NewsletterController($this->service);
    }
}
