<?php
namespace App\Tests\Controller;

use App\Service\DeepDiveService;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class DeepDiveControllerTest extends TestCase
{
    public function testGetReturns200OnCacheHit(): void
    {
        $service = $this->createMock(DeepDiveService::class);
        $service->method('get')->with('ev-1')->willReturn(['chunks' => ['chunk one']]);

        $response = (new \App\Controller\DeepDiveController($service))->get('ev-1');
        $this->assertSame(200, $response->getStatusCode());
        $content = $response->getContent();
        if ($content === false) {
            throw new \RuntimeException('Response content is null');
        }
        $body = json_decode($content, true);
        $this->assertSame(['chunk one'], $body['chunks']);
    }

    public function testGetReturns404OnMiss(): void
    {
        $service = $this->createMock(DeepDiveService::class);
        $service->method('get')->willReturn(null);

        $response = (new \App\Controller\DeepDiveController($service))->get('ev-x');
        $this->assertSame(404, $response->getStatusCode());
    }

    public function testStoreReturns201(): void
    {
        $service = $this->createMock(DeepDiveService::class);
        $service->expects($this->once())->method('store')->with('ev-1', ['chunk one']);

        $request = Request::create('/master-data/deep-dive/ev-1', 'POST', [], [], [], [],
            json_encode(['chunks' => ['chunk one']], JSON_THROW_ON_ERROR));
        $request->headers->set('Content-Type', 'application/json');
        $request->attributes->set('user_id', 'user-1');

        $response = (new \App\Controller\DeepDiveController($service))->store($request, 'ev-1');
        $this->assertSame(201, $response->getStatusCode());
    }

    public function testStoreReturns400WhenChunksMissing(): void
    {
        $service = $this->createMock(DeepDiveService::class);
        $request = Request::create('/master-data/deep-dive/ev-1', 'POST', [], [], [], [],
            json_encode([], JSON_THROW_ON_ERROR));
        $request->headers->set('Content-Type', 'application/json');
        $request->attributes->set('user_id', 'user-1');

        $response = (new \App\Controller\DeepDiveController($service))->store($request, 'ev-1');
        $this->assertSame(400, $response->getStatusCode());
    }
}
