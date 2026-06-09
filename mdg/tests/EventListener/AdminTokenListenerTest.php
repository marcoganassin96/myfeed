<?php
namespace App\Tests\EventListener;

use App\EventListener\AdminTokenListener;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpKernel\Event\RequestEvent;
use Symfony\Component\HttpKernel\HttpKernelInterface;

class AdminTokenListenerTest extends TestCase
{
    private function makeEvent(string $uri, ?string $token): RequestEvent
    {
        $kernel  = $this->createMock(HttpKernelInterface::class);
        $request = Request::create($uri);
        if ($token !== null) {
            $request->headers->set('X-Admin-Token', $token);
        }
        return new RequestEvent($kernel, $request, HttpKernelInterface::MAIN_REQUEST);
    }

    public function testNonAdminPathPassesThrough(): void
    {
        $listener = new AdminTokenListener('secret');
        $event    = $this->makeEvent('/master-data/topics', null);
        $listener->onKernelRequest($event);
        $this->assertNull($event->getResponse());
    }

    public function testAdminPathWithCorrectTokenPassesThrough(): void
    {
        $listener = new AdminTokenListener('secret');
        $event    = $this->makeEvent('/master-data/admin/topics', 'secret');
        $listener->onKernelRequest($event);
        $this->assertNull($event->getResponse());
    }

    public function testAdminPathWithMissingTokenReturns401(): void
    {
        $listener = new AdminTokenListener('secret');
        $event    = $this->makeEvent('/master-data/admin/topics', null);
        $listener->onKernelRequest($event);
        $this->assertNotNull($event->getResponse());
        $this->assertSame(401, $event->getResponse()->getStatusCode());
        $body = json_decode((string) $event->getResponse()->getContent(), true);
        $this->assertSame('Unauthorized', $body['error']);
    }

    public function testAdminPathWithWrongTokenReturns401(): void
    {
        $listener = new AdminTokenListener('secret');
        $event    = $this->makeEvent('/master-data/admin/topics', 'wrong');
        $listener->onKernelRequest($event);
        $this->assertNotNull($event->getResponse());
        $this->assertSame(401, $event->getResponse()->getStatusCode());
    }
}
