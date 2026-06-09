<?php
namespace App\EventListener;

use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpKernel\Event\RequestEvent;
use Symfony\Component\HttpKernel\KernelEvents;

#[AsEventListener(event: KernelEvents::REQUEST, priority: 20)]
class AdminTokenListener
{
    /** Injected via services.yaml bind from ADMIN_TOKEN env var; validated on every /admin/ request. */
    public function __construct(private readonly string $adminToken) {}

    /** Rejects requests to /admin/ paths when X-Admin-Token header is absent or does not match. */
    public function onKernelRequest(RequestEvent $event): void
    {
        if (!$event->isMainRequest()) {
            return;
        }
        if (!str_contains($event->getRequest()->getPathInfo(), '/admin/')) {
            return;
        }
        $token = $event->getRequest()->headers->get('X-Admin-Token');
        if ($token === null || $token !== $this->adminToken) {
            $event->setResponse(new JsonResponse(['error' => 'Unauthorized'], 401));
        }
    }
}
