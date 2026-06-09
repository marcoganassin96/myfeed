<?php
namespace App\Tests\Controller;

use App\Controller\NewsletterController;
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

    private function makeController(): NewsletterController
    {
        return new NewsletterController($this->service);
    }

    public function testListReturns200WithNewsletters(): void
    {
        $newsletters = [['newsletter_id' => 'nl-1', 'title' => 'Tech']];
        $this->service->method('listForUser')->with('user-1')->willReturn($newsletters);

        $request = Request::create('/master-data/newsletters', 'GET');
        $request->attributes->set('user_id', 'user-1');

        $response = $this->makeController()->list($request);
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
}
