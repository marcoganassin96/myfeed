<?php
namespace App\EventListener;

use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpFoundation\RequestStack;
use Symfony\Component\HttpKernel\Event\RequestEvent;
use Symfony\Component\HttpKernel\KernelEvents;

#[AsEventListener(event: KernelEvents::REQUEST, priority: 10)]
/*
* parameter: AsEventListener - Automatically registers the class in the service container.
* event: KernelEvents::REQUEST - Hooks into the very start of the HTTP request processing.
* priority: 10 - Ensures this runs before default listeners (higher = earlier).
This class acts as a global interceptor for incoming HTTP requests, extracting the user ID from the `X-User-Id` header and storing it in the request attributes. This allows downstream controllers and services to access the user context without needing to parse headers themselves, centralizing this logic in one place.
*/
class UserContextListener
{
    public function __construct(private RequestStack $requestStack) {}

    public function onKernelRequest(RequestEvent $event): void
    {
        if (!$event->isMainRequest()) {
            return;
        }
        $userId = $event->getRequest()->headers->get('X-User-Id');
        if ($userId) {
            $this->requestStack->getCurrentRequest()->attributes->set('user_id', $userId);
        }
    }
}
