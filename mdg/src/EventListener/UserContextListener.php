<?php
namespace App\EventListener;

use Symfony\Component\HttpFoundation\RequestStack;
use Symfony\Component\HttpKernel\Event\RequestEvent;

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
