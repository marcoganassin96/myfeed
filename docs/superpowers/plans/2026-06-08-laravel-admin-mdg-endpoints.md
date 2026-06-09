# MDG Admin/User/Public Route Split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor MDG controllers to enforce the public/user/admin scope contract defined in ADR-012 — admin mutations at `/admin/` prefix, user reads at bare paths, public reads with no auth.

**Architecture:** Split mixed controllers by role. Every `/master-data/admin/*` path is guarded by a new `AdminTokenListener` (X-Admin-Token header). User paths trust the X-User-Id header already set by the existing `UserContextListener`. Services and repositories are unchanged — only route paths and controller classes change.

**Tech Stack:** PHP 8.4, Symfony 7, Doctrine DBAL 3, PHPUnit 11, PHPStan level 7

**Validation after every code change:**
```bash
cd mdg && composer phpstan && composer test
```

**Smoke tests (requires Docker stack running + ADMIN_TOKEN set):**
```bash
docker-compose up -d
docker exec <mdg-container> php bin/console doctrine:migrations:migrate --no-interaction
docker exec <mdg-container> php bin/console doctrine:fixtures:load --no-interaction
ADMIN_TOKEN=dev-admin-secret cd mdg && composer smoke
```

---

## Endpoint Contract (ADR-012)

| Method | Path | Scope | Auth |
|--------|------|-------|------|
| GET | /master-data/topics | Public | none |
| GET | /master-data/topics/{id} | Public | none |
| POST | /master-data/admin/topics | Admin | X-Admin-Token |
| PUT | /master-data/admin/topics/{id} | Admin | X-Admin-Token |
| DELETE | /master-data/admin/topics/{id} | Admin | X-Admin-Token |
| GET | /master-data/news-events | User | X-User-Id |
| GET | /master-data/news-events/{id} | User | X-User-Id |
| GET | /master-data/admin/news-events | Admin | X-Admin-Token |
| GET | /master-data/admin/news-events/{id} | Admin | X-Admin-Token |
| POST | /master-data/admin/news-events | Admin | X-Admin-Token |
| PUT | /master-data/admin/news-events/{id} | Admin | X-Admin-Token |
| DELETE | /master-data/admin/news-events/{id} | Admin | X-Admin-Token |
| GET | /master-data/newsletters | User | X-User-Id |
| GET | /master-data/newsletters/{id} | User | X-User-Id |
| GET | /master-data/admin/newsletters | Admin | X-Admin-Token |
| GET | /master-data/admin/newsletters/{id} | Admin | X-Admin-Token |
| POST | /master-data/admin/newsletters | Admin | X-Admin-Token |
| PUT | /master-data/admin/newsletters/{id} | Admin | X-Admin-Token |
| DELETE | /master-data/admin/newsletters/{id} | Admin | X-Admin-Token |
| POST | /master-data/subscriptions | User | X-User-Id |
| GET | /master-data/subscriptions | User | X-User-Id |
| DELETE | /master-data/subscriptions/{topicId} | User | X-User-Id |
| GET | /master-data/admin/subscriptions | Admin | X-Admin-Token |
| DELETE | /master-data/admin/subscriptions/{userId}/{topicId} | Admin | X-Admin-Token |
| POST | /master-data/interactions | User | X-User-Id |
| GET | /master-data/admin/interactions | Admin | X-Admin-Token |

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `mdg/src/EventListener/AdminTokenListener.php` | Create | Validate X-Admin-Token on all /admin/ paths |
| `mdg/config/services.yaml` | Modify | Bind `$adminToken` from `ADMIN_TOKEN` env var |
| `mdg/docker/.env` (or docker-compose.yml) | Modify | Add `ADMIN_TOKEN=dev-admin-secret` for local dev |
| `mdg/src/Controller/TopicController.php` | Modify | Remove mutations — public GETs only |
| `mdg/src/Controller/AdminTopicController.php` | Create | POST/PUT/DELETE at /admin/topics |
| `mdg/src/Controller/NewsEventController.php` | Modify | User-scoped GETs only (/news-events) |
| `mdg/src/Controller/AdminNewsEventController.php` | Create | Full CRUD at /admin/news-events |
| `mdg/src/Repository/NewsletterRepository.php` | Modify | Add `findAll()` for admin listing |
| `mdg/src/Service/NewsletterService.php` | Modify | Add `listAll()` for admin listing |
| `mdg/src/Controller/NewsletterController.php` | Modify | Remove mutations — user GETs only |
| `mdg/src/Controller/AdminNewsletterController.php` | Create | GET list+get + mutations at /admin/newsletters |
| `mdg/src/Controller/InteractionController.php` | Modify | Remove list() — user POST only |
| `mdg/src/Controller/AdminInteractionController.php` | Create | GET /admin/interactions |
| `mdg/tests/EventListener/AdminTokenListenerTest.php` | Create | Unit tests for token validation |
| `mdg/tests/Controller/TopicControllerTest.php` | Modify | Remove mutation tests |
| `mdg/tests/Controller/AdminTopicControllerTest.php` | Create | Tests for AdminTopicController |
| `mdg/tests/Controller/NewsEventControllerTest.php` | Modify | User-scoped GET tests only |
| `mdg/tests/Controller/AdminNewsEventControllerTest.php` | Create | Tests for AdminNewsEventController |
| `mdg/tests/Service/NewsletterServiceTest.php` | Modify | Add listAll test |
| `mdg/tests/Controller/NewsletterControllerTest.php` | Modify | Remove mutation tests |
| `mdg/tests/Controller/AdminNewsletterControllerTest.php` | Create | Tests for AdminNewsletterController |
| `mdg/tests/Controller/InteractionControllerTest.php` | Modify | Remove list test |
| `mdg/tests/Controller/AdminInteractionControllerTest.php` | Create | Tests for AdminInteractionController |
| `mdg/tests/Smoke/EndpointSmokeTest.php` | Modify | Update URLs + add X-Admin-Token |

**Already correct — no changes needed:**
- `mdg/src/Repository/TopicRepository.php` ✓
- `mdg/src/Service/TopicService.php` ✓
- `mdg/src/Repository/NewsEventRepository.php` ✓
- `mdg/src/Service/NewsEventService.php` ✓
- `mdg/src/Repository/InteractionRepository.php` ✓
- `mdg/src/Service/InteractionService.php` ✓
- `mdg/src/Repository/AdminSubscriptionRepository.php` ✓
- `mdg/src/Service/AdminSubscriptionService.php` ✓
- `mdg/src/Controller/AdminSubscriptionController.php` ✓
- `mdg/src/EventListener/UserContextListener.php` ✓

---

### Task 1: AdminTokenListener

**Files:**
- Create: `mdg/src/EventListener/AdminTokenListener.php`
- Create: `mdg/tests/EventListener/AdminTokenListenerTest.php`
- Modify: `mdg/config/services.yaml`
- Modify: `docker-compose.yml` (add `ADMIN_TOKEN` to mdg service environment)

- [ ] **Step 1: Write the failing test**

```php
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mdg && ./vendor/bin/phpunit tests/EventListener/AdminTokenListenerTest.php -v
```
Expected: FAIL — `Class "App\EventListener\AdminTokenListener" not found`

- [ ] **Step 3: Create `mdg/src/EventListener/AdminTokenListener.php`**

```php
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
```

- [ ] **Step 4: Bind `$adminToken` in `mdg/config/services.yaml`**

```yaml
services:
    _defaults:
        autowire: true
        autoconfigure: true
        bind:
            string $redisUrl: '%mdg.redis_url%'
            int $cacheTtl: '%mdg.cache_ttl%'
            string $adminToken: '%env(ADMIN_TOKEN)%'

    App\:
        resource: '../src/'
        exclude:
            - '../src/Entity/'
            - '../src/Kernel.php'

    App\Cache\RedisClientInterface: '@App\Cache\PredisAdapter'
```

- [ ] **Step 5: Add `ADMIN_TOKEN` to mdg service in `docker-compose.yml`**

Find the `mdg:` service `environment:` block and add:
```yaml
ADMIN_TOKEN: ${ADMIN_TOKEN:-dev-admin-secret}
```
This defaults to `dev-admin-secret` for local dev when `ADMIN_TOKEN` is not set in the shell.

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd mdg && ./vendor/bin/phpunit tests/EventListener/AdminTokenListenerTest.php -v
```
Expected: 4 tests, 4 assertions, PASS

- [ ] **Step 7: Run full suite + PHPStan**

```bash
cd mdg && composer phpstan && composer test
```
Expected: zero PHPStan errors, all tests green

- [ ] **Step 8: Commit**

```bash
git add mdg/src/EventListener/AdminTokenListener.php \
        mdg/tests/EventListener/AdminTokenListenerTest.php \
        mdg/config/services.yaml \
        docker-compose.yml
git commit -m "feat(auth): add AdminTokenListener for /admin/ endpoint protection"
```

---

### Task 2: Refactor TopicController + create AdminTopicController

**Files:**
- Modify: `mdg/src/Controller/TopicController.php`
- Create: `mdg/src/Controller/AdminTopicController.php`
- Modify: `mdg/tests/Controller/TopicControllerTest.php`
- Create: `mdg/tests/Controller/AdminTopicControllerTest.php`

- [ ] **Step 1: Write `AdminTopicControllerTest.php`**

```php
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mdg && ./vendor/bin/phpunit tests/Controller/AdminTopicControllerTest.php -v
```
Expected: FAIL — `Class "App\Controller\AdminTopicController" not found`

- [ ] **Step 3: Create `mdg/src/Controller/AdminTopicController.php`**

```php
<?php
namespace App\Controller;

use App\Service\TopicService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Admin Topics')]
class AdminTopicController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private TopicService $service) {}

    /** Validates name presence here; service assumes valid input and owns persistence. */
    #[OA\Post(summary: 'Create topic (admin)')]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['name'],
            properties: [
                new OA\Property(property: 'name', type: 'string', maxLength: 100),
                new OA\Property(property: 'description', type: 'string', nullable: true),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Topic created')]
    #[OA\Response(response: 400, description: 'name missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/topics', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['name'])) {
            return new JsonResponse(['error' => 'name required'], 400);
        }
        $result = $this->service->create($body['name'], $body['description'] ?? null);
        return new JsonResponse($result, 201);
    }

    /** Validates name presence; service returns null when topic not found. */
    #[OA\Put(summary: 'Update topic (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['name'],
            properties: [
                new OA\Property(property: 'name', type: 'string', maxLength: 100),
                new OA\Property(property: 'description', type: 'string', nullable: true),
            ],
        ),
    )]
    #[OA\Response(response: 200, description: 'Topic updated')]
    #[OA\Response(response: 400, description: 'name missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/topics/{id}', methods: ['PUT'])]
    public function update(Request $request, string $id): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['name'])) {
            return new JsonResponse(['error' => 'name required'], 400);
        }
        $result = $this->service->update($id, $body['name'], $body['description'] ?? null);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    /** Service returns false when not found; explicit 404 over silent 204 for clarity. */
    #[OA\Delete(summary: 'Delete topic (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 204, description: 'Deleted')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/topics/{id}', methods: ['DELETE'])]
    public function delete(string $id): Response
    {
        if (!$this->service->delete($id)) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new Response('', 204);
    }
}
```

- [ ] **Step 4: Replace `mdg/src/Controller/TopicController.php` — keep public GETs only**

```php
<?php
namespace App\Controller;

use App\Service\TopicService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Topics')]
class TopicController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private TopicService $service) {}

    /** Lists all topics; public — no auth required; used by client apps to show subscription choices. */
    #[OA\Get(summary: 'List all topics (public)')]
    #[OA\Response(response: 200, description: 'Array of topic objects')]
    #[Route('/master-data/topics', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return new JsonResponse($this->service->list());
    }

    /** Service returns null on miss; controller owns the 404 decision to keep service type-clean. */
    #[OA\Get(summary: 'Get topic by ID (public)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 200, description: 'Topic found')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/topics/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $topic = $this->service->getById($id);
        if ($topic === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($topic);
    }
}
```

- [ ] **Step 5: Replace `mdg/tests/Controller/TopicControllerTest.php` — keep only list/get tests**

```php
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
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd mdg && ./vendor/bin/phpunit tests/Controller/TopicControllerTest.php tests/Controller/AdminTopicControllerTest.php -v
```
Expected: 9 tests, PASS

- [ ] **Step 7: Run full suite + PHPStan**

```bash
cd mdg && composer phpstan && composer test
```
Expected: zero PHPStan errors, all tests green

- [ ] **Step 8: Commit**

```bash
git add mdg/src/Controller/TopicController.php \
        mdg/src/Controller/AdminTopicController.php \
        mdg/tests/Controller/TopicControllerTest.php \
        mdg/tests/Controller/AdminTopicControllerTest.php
git commit -m "feat(topics): split admin mutations into AdminTopicController at /admin/topics"
```

---

### Task 3: Refactor NewsEventController + create AdminNewsEventController

**Files:**
- Modify: `mdg/src/Controller/NewsEventController.php`
- Create: `mdg/src/Controller/AdminNewsEventController.php`
- Modify: `mdg/tests/Controller/NewsEventControllerTest.php`
- Create: `mdg/tests/Controller/AdminNewsEventControllerTest.php`

- [ ] **Step 1: Write `AdminNewsEventControllerTest.php`**

```php
<?php
namespace App\Tests\Controller;

use App\Controller\AdminNewsEventController;
use App\Service\NewsEventService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class AdminNewsEventControllerTest extends TestCase
{
    private NewsEventService&MockObject $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(NewsEventService::class);
    }

    private function makeController(): AdminNewsEventController
    {
        return new AdminNewsEventController($this->service);
    }

    public function testListReturns200(): void
    {
        $events = [['event_id' => 'ev-1', 'headline' => 'Big News']];
        $this->service->method('list')->willReturn($events);
        $response = $this->makeController()->list();
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('ev-1', $body[0]['event_id']);
    }

    public function testGetReturns200OnFound(): void
    {
        $event = ['event_id' => 'ev-1', 'headline' => 'Big News'];
        $this->service->method('getById')->with('ev-1')->willReturn($event);
        $response = $this->makeController()->get('ev-1');
        $this->assertSame(200, $response->getStatusCode());
    }

    public function testGetReturns404WhenNotFound(): void
    {
        $this->service->method('getById')->willReturn(null);
        $response = $this->makeController()->get('ev-x');
        $this->assertSame(404, $response->getStatusCode());
    }

    public function testCreateReturns201WithValidBody(): void
    {
        $created = ['event_id' => 'ev-new', 'headline' => 'H', 'summary' => 'S', 'date' => '2026-01-15'];
        $this->service->expects($this->once())->method('create')
            ->with('H', 'S', '2026-01-15', null)->willReturn($created);
        $request = Request::create('/master-data/admin/news-events', 'POST', [], [], [], [],
            json_encode(['headline' => 'H', 'summary' => 'S', 'date' => '2026-01-15']) ?: '');
        $response = $this->makeController()->create($request);
        $this->assertSame(201, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('ev-new', $body['event_id']);
    }

    public function testCreateReturns400WhenFieldsMissing(): void
    {
        $request = Request::create('/master-data/admin/news-events', 'POST', [], [], [], [],
            json_encode(['headline' => 'H']) ?: '');
        $response = $this->makeController()->create($request);
        $this->assertSame(400, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('headline, summary and date required', $body['error']);
    }

    public function testUpdateReturns200OnSuccess(): void
    {
        $updated = ['event_id' => 'ev-1', 'headline' => 'Updated'];
        $this->service->expects($this->once())->method('update')
            ->with('ev-1', 'Updated', 'S', '2026-01-20', null)->willReturn($updated);
        $request = Request::create('/master-data/admin/news-events/ev-1', 'PUT', [], [], [], [],
            json_encode(['headline' => 'Updated', 'summary' => 'S', 'date' => '2026-01-20']) ?: '');
        $response = $this->makeController()->update($request, 'ev-1');
        $this->assertSame(200, $response->getStatusCode());
    }

    public function testUpdateReturns404WhenNotFound(): void
    {
        $this->service->method('update')->willReturn(null);
        $request = Request::create('/master-data/admin/news-events/ev-x', 'PUT', [], [], [], [],
            json_encode(['headline' => 'H', 'summary' => 'S', 'date' => '2026-01-20']) ?: '');
        $response = $this->makeController()->update($request, 'ev-x');
        $this->assertSame(404, $response->getStatusCode());
    }

    public function testDeleteReturns204OnSuccess(): void
    {
        $this->service->expects($this->once())->method('delete')->with('ev-1')->willReturn(true);
        $response = $this->makeController()->delete('ev-1');
        $this->assertSame(204, $response->getStatusCode());
    }

    public function testDeleteReturns404WhenNotFound(): void
    {
        $this->service->method('delete')->willReturn(false);
        $response = $this->makeController()->delete('ev-x');
        $this->assertSame(404, $response->getStatusCode());
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mdg && ./vendor/bin/phpunit tests/Controller/AdminNewsEventControllerTest.php -v
```
Expected: FAIL — `Class "App\Controller\AdminNewsEventController" not found`

- [ ] **Step 3: Create `mdg/src/Controller/AdminNewsEventController.php`**

```php
<?php
namespace App\Controller;

use App\Service\NewsEventService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Admin NewsEvents')]
class AdminNewsEventController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private NewsEventService $service) {}

    /** Lists all news events for admin; no user context — admin sees all. */
    #[OA\Get(summary: 'List all news events (admin)')]
    #[OA\Response(response: 200, description: 'Array of news event objects')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/news-events', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return new JsonResponse($this->service->list());
    }

    /** Service returns null on miss; controller owns the 404 decision. */
    #[OA\Get(summary: 'Get news event by ID (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 200, description: 'Event found')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/news-events/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $event = $this->service->getById($id);
        if ($event === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($event);
    }

    /** Validates headline/summary/date presence; service assumes valid input. */
    #[OA\Post(summary: 'Create news event (admin)')]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['headline', 'summary', 'date'],
            properties: [
                new OA\Property(property: 'headline', type: 'string', maxLength: 300),
                new OA\Property(property: 'summary', type: 'string'),
                new OA\Property(property: 'date', type: 'string', format: 'date', example: '2026-01-15'),
                new OA\Property(property: 'source_url', type: 'string', nullable: true),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Event created')]
    #[OA\Response(response: 400, description: 'Required fields missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/news-events', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['headline']) || empty($body['summary']) || empty($body['date'])) {
            return new JsonResponse(['error' => 'headline, summary and date required'], 400);
        }
        $result = $this->service->create(
            $body['headline'],
            $body['summary'],
            $body['date'],
            $body['source_url'] ?? null,
        );
        return new JsonResponse($result, 201);
    }

    /** Validates required fields; service returns null when event not found. */
    #[OA\Put(summary: 'Update news event (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['headline', 'summary', 'date'],
            properties: [
                new OA\Property(property: 'headline', type: 'string', maxLength: 300),
                new OA\Property(property: 'summary', type: 'string'),
                new OA\Property(property: 'date', type: 'string', format: 'date'),
                new OA\Property(property: 'source_url', type: 'string', nullable: true),
            ],
        ),
    )]
    #[OA\Response(response: 200, description: 'Event updated')]
    #[OA\Response(response: 400, description: 'Required fields missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/news-events/{id}', methods: ['PUT'])]
    public function update(Request $request, string $id): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['headline']) || empty($body['summary']) || empty($body['date'])) {
            return new JsonResponse(['error' => 'headline, summary and date required'], 400);
        }
        $result = $this->service->update(
            $id,
            $body['headline'],
            $body['summary'],
            $body['date'],
            $body['source_url'] ?? null,
        );
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    /** Service returns false when not found; explicit 404 for clarity. */
    #[OA\Delete(summary: 'Delete news event (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 204, description: 'Deleted')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/news-events/{id}', methods: ['DELETE'])]
    public function delete(string $id): Response
    {
        if (!$this->service->delete($id)) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new Response('', 204);
    }
}
```

- [ ] **Step 4: Replace `mdg/src/Controller/NewsEventController.php` — user-scoped GETs only**

```php
<?php
namespace App\Controller;

use App\Service\NewsEventService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'NewsEvents')]
class NewsEventController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private NewsEventService $service) {}

    /** Lists news events for authenticated user; user_id set by UserContextListener for future filtering. */
    #[OA\Get(summary: 'List news events (user)')]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream; stored in request attributes by UserContextListener',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\Response(response: 200, description: 'Array of news event objects')]
    #[Route('/master-data/news-events', methods: ['GET'])]
    public function list(Request $request): JsonResponse
    {
        // user_id available via $request->attributes->get('user_id') for future per-user filtering
        return new JsonResponse($this->service->list());
    }

    /** Service returns null on miss; controller owns the 404 decision. */
    #[OA\Get(summary: 'Get news event by ID (user)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\Response(response: 200, description: 'Event found')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/news-events/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $event = $this->service->getById($id);
        if ($event === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($event);
    }
}
```

- [ ] **Step 5: Replace `mdg/tests/Controller/NewsEventControllerTest.php` — user GET tests only**

```php
<?php
namespace App\Tests\Controller;

use App\Controller\NewsEventController;
use App\Service\NewsEventService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class NewsEventControllerTest extends TestCase
{
    private NewsEventService&MockObject $service;

    protected function setUp(): void
    {
        $this->service = $this->createMock(NewsEventService::class);
    }

    private function makeController(): NewsEventController
    {
        return new NewsEventController($this->service);
    }

    public function testListReturns200(): void
    {
        $events = [['event_id' => 'ev-1', 'headline' => 'Big News']];
        $this->service->method('list')->willReturn($events);

        $request = Request::create('/master-data/news-events', 'GET');
        $request->attributes->set('user_id', 'user-1');

        $response = $this->makeController()->list($request);
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('ev-1', $body[0]['event_id']);
    }

    public function testGetReturns200OnFound(): void
    {
        $event = ['event_id' => 'ev-1', 'headline' => 'Big News'];
        $this->service->method('getById')->with('ev-1')->willReturn($event);
        $response = $this->makeController()->get('ev-1');
        $this->assertSame(200, $response->getStatusCode());
    }

    public function testGetReturns404WhenNotFound(): void
    {
        $this->service->method('getById')->willReturn(null);
        $response = $this->makeController()->get('ev-x');
        $this->assertSame(404, $response->getStatusCode());
    }
}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd mdg && ./vendor/bin/phpunit tests/Controller/NewsEventControllerTest.php tests/Controller/AdminNewsEventControllerTest.php -v
```
Expected: 11 tests, PASS

- [ ] **Step 7: Run full suite + PHPStan**

```bash
cd mdg && composer phpstan && composer test
```
Expected: zero PHPStan errors, all tests green

- [ ] **Step 8: Commit**

```bash
git add mdg/src/Controller/NewsEventController.php \
        mdg/src/Controller/AdminNewsEventController.php \
        mdg/tests/Controller/NewsEventControllerTest.php \
        mdg/tests/Controller/AdminNewsEventControllerTest.php
git commit -m "feat(news-events): split user GETs and admin CRUD into separate controllers"
```

---

### Task 4: Add NewsletterRepository::findAll + NewsletterService::listAll

The admin panel needs to list ALL newsletters without user filtering. The existing `listForUser` is user-scoped; admin needs an unfiltered list.

**Files:**
- Modify: `mdg/src/Repository/NewsletterRepository.php`
- Modify: `mdg/src/Service/NewsletterService.php`
- Modify: `mdg/tests/Service/NewsletterServiceTest.php`

- [ ] **Step 1: Write the failing test in `mdg/tests/Service/NewsletterServiceTest.php`**

Add this test to the existing `NewsletterServiceTest` class (do not replace the whole file — add alongside existing tests):

```php
public function testListAllReturnsCachedResult(): void
{
    $rows = [['newsletter_id' => 'nl-1', 'title' => 'Tech']];
    $this->cache->method('get')->with('newsletter:list:admin')->willReturn($rows);
    $this->repo->expects($this->never())->method('findAll');

    $result = $this->service->listAll();
    $this->assertSame($rows, $result);
}

public function testListAllCallsRepoOnCacheMiss(): void
{
    $rows = [['newsletter_id' => 'nl-1', 'title' => 'Tech']];
    $this->cache->method('get')->with('newsletter:list:admin')->willReturn(null);
    $this->repo->expects($this->once())->method('findAll')->willReturn($rows);
    $this->cache->expects($this->once())->method('set')->with('newsletter:list:admin', $rows);

    $result = $this->service->listAll();
    $this->assertSame($rows, $result);
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mdg && ./vendor/bin/phpunit tests/Service/NewsletterServiceTest.php -v
```
Expected: FAIL — `Call to undefined method ...::listAll()`

- [ ] **Step 3: Add `findAll()` to `mdg/src/Repository/NewsletterRepository.php`**

Add after the existing `findLatestPerTopicForUser` method:

```php
/**
 * Returns all newsletters for admin listing; no user filter — admin sees everything.
 * @return list<array<string, mixed>>
 */
public function findAll(): array
{
    /** @var list<array<string, mixed>> $result */
    $result = $this->em->getConnection()->fetchAllAssociative(
        'SELECT newsletter_id, topic_id, date, title, narrative FROM newsletters ORDER BY date DESC'
    );
    return $result;
}
```

- [ ] **Step 4: Add `listAll()` to `mdg/src/Service/NewsletterService.php`**

Add after the existing `listForUser` method:

```php
/**
 * Returns all newsletters unfiltered for admin; cached separately from user feeds.
 * Mutations call flush() which also invalidates this key.
 * @return list<array<string, mixed>>
 */
public function listAll(): array
{
    $key = 'newsletter:list:admin';
    /** @var list<array<string, mixed>>|null $cached */
    $cached = $this->cache->get($key);
    if ($cached !== null) {
        return $cached;
    }
    $rows = $this->repo->findAll();
    $this->cache->set($key, $rows);
    return $rows;
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd mdg && ./vendor/bin/phpunit tests/Service/NewsletterServiceTest.php -v
```
Expected: all tests PASS (including the two new ones)

- [ ] **Step 6: Run full suite + PHPStan**

```bash
cd mdg && composer phpstan && composer test
```
Expected: zero PHPStan errors, all tests green

- [ ] **Step 7: Commit**

```bash
git add mdg/src/Repository/NewsletterRepository.php \
        mdg/src/Service/NewsletterService.php \
        mdg/tests/Service/NewsletterServiceTest.php
git commit -m "feat(newsletters): add listAll/findAll for admin unfiltered listing"
```

---

### Task 5: Refactor NewsletterController + create AdminNewsletterController

**Files:**
- Modify: `mdg/src/Controller/NewsletterController.php`
- Create: `mdg/src/Controller/AdminNewsletterController.php`
- Modify: `mdg/tests/Controller/NewsletterControllerTest.php`
- Create: `mdg/tests/Controller/AdminNewsletterControllerTest.php`

- [ ] **Step 1: Write `AdminNewsletterControllerTest.php`**

```php
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mdg && ./vendor/bin/phpunit tests/Controller/AdminNewsletterControllerTest.php -v
```
Expected: FAIL — `Class "App\Controller\AdminNewsletterController" not found`

- [ ] **Step 3: Create `mdg/src/Controller/AdminNewsletterController.php`**

```php
<?php
namespace App\Controller;

use App\Service\NewsletterService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Admin Newsletters')]
class AdminNewsletterController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private NewsletterService $service) {}

    /** Lists all newsletters unfiltered for admin; user-filtered list is on NewsletterController. */
    #[OA\Get(summary: 'List all newsletters (admin)')]
    #[OA\Response(response: 200, description: 'Array of newsletter objects')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/newsletters', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return new JsonResponse($this->service->listAll());
    }

    /** Service returns null on miss; controller owns the 404 decision to keep service type-clean. */
    #[OA\Get(summary: 'Get newsletter by ID (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 200, description: 'Newsletter found')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/newsletters/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $result = $this->service->getById($id);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    /** Validates all required fields; service assumes valid input and owns persistence. */
    #[OA\Post(summary: 'Create newsletter (admin)')]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['topic_id', 'date', 'title', 'narrative'],
            properties: [
                new OA\Property(property: 'topic_id', type: 'string', format: 'uuid'),
                new OA\Property(property: 'date', type: 'string', format: 'date'),
                new OA\Property(property: 'title', type: 'string', maxLength: 200),
                new OA\Property(property: 'narrative', type: 'string'),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Newsletter created')]
    #[OA\Response(response: 400, description: 'Required fields missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/newsletters', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['topic_id']) || empty($body['date']) || empty($body['title']) || empty($body['narrative'])) {
            return new JsonResponse(['error' => 'topic_id, date, title and narrative required'], 400);
        }
        $result = $this->service->create($body['topic_id'], $body['date'], $body['title'], $body['narrative']);
        return new JsonResponse($result, 201);
    }

    /** Validates that title and narrative are present; service owns persistence and type safety. */
    #[OA\Put(summary: 'Update newsletter title and narrative (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['title', 'narrative'],
            properties: [
                new OA\Property(property: 'title', type: 'string', maxLength: 200),
                new OA\Property(property: 'narrative', type: 'string'),
            ],
        ),
    )]
    #[OA\Response(response: 200, description: 'Newsletter updated')]
    #[OA\Response(response: 400, description: 'title or narrative missing')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/newsletters/{id}', methods: ['PUT'])]
    public function update(Request $request, string $id): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['title']) || empty($body['narrative'])) {
            return new JsonResponse(['error' => 'title and narrative required'], 400);
        }
        $result = $this->service->update($id, $body['title'], $body['narrative']);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }

    /** Service returns false when not found; explicit 404 avoids ambiguity with successful deletes. */
    #[OA\Delete(summary: 'Delete newsletter (admin)')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Response(response: 204, description: 'Deleted')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/admin/newsletters/{id}', methods: ['DELETE'])]
    public function delete(string $id): Response
    {
        if (!$this->service->delete($id)) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new Response('', 204);
    }
}
```

- [ ] **Step 4: Replace `mdg/src/Controller/NewsletterController.php` — user-scoped GETs only**

```php
<?php
namespace App\Controller;

use App\Service\NewsletterService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Newsletters')]
class NewsletterController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private NewsletterService $service) {}

    /** Routes listing to service layer; user_id resolved upstream by UserContextListener. */
    #[OA\Get(summary: 'List newsletters for the authenticated user')]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream by UserContextListener; not validated here',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\Response(response: 200, description: 'Array of newsletter objects')]
    #[Route('/master-data/newsletters', methods: ['GET'])]
    public function list(Request $request): JsonResponse
    {
        $userId = $request->attributes->get('user_id', '');
        return new JsonResponse($this->service->listForUser($userId));
    }

    /** Service returns null on miss; controller owns the 404 decision to keep service type-clean. */
    #[OA\Get(summary: 'Fetch a single newsletter by ID')]
    #[OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'string', format: 'uuid'))]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\Response(response: 200, description: 'Newsletter found')]
    #[OA\Response(response: 404, description: 'Not found')]
    #[Route('/master-data/newsletters/{id}', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $result = $this->service->getById($id);
        if ($result === null) {
            return new JsonResponse(['error' => 'Not found'], 404);
        }
        return new JsonResponse($result);
    }
}
```

- [ ] **Step 5: Replace `mdg/tests/Controller/NewsletterControllerTest.php` — user GET tests only**

```php
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
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd mdg && ./vendor/bin/phpunit tests/Controller/NewsletterControllerTest.php tests/Controller/AdminNewsletterControllerTest.php -v
```
Expected: 11 tests, PASS

- [ ] **Step 7: Run full suite + PHPStan**

```bash
cd mdg && composer phpstan && composer test
```
Expected: zero PHPStan errors, all tests green

- [ ] **Step 8: Commit**

```bash
git add mdg/src/Controller/NewsletterController.php \
        mdg/src/Controller/AdminNewsletterController.php \
        mdg/tests/Controller/NewsletterControllerTest.php \
        mdg/tests/Controller/AdminNewsletterControllerTest.php
git commit -m "feat(newsletters): split admin mutations into AdminNewsletterController at /admin/newsletters"
```

---

### Task 6: Refactor InteractionController + create AdminInteractionController

**Files:**
- Modify: `mdg/src/Controller/InteractionController.php`
- Create: `mdg/src/Controller/AdminInteractionController.php`
- Modify: `mdg/tests/Controller/InteractionControllerTest.php`
- Create: `mdg/tests/Controller/AdminInteractionControllerTest.php`

- [ ] **Step 1: Write `AdminInteractionControllerTest.php`**

```php
<?php
namespace App\Tests\Controller;

use App\Controller\AdminInteractionController;
use App\Service\InteractionService;
use PHPUnit\Framework\TestCase;

class AdminInteractionControllerTest extends TestCase
{
    public function testListReturns200(): void
    {
        $service = $this->createMock(InteractionService::class);
        $rows    = [['interaction_id' => 'ix-1', 'type' => 'read']];
        $service->method('listAll')->willReturn($rows);

        $controller = new AdminInteractionController($service);
        $response   = $controller->list();
        $this->assertSame(200, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('ix-1', $body[0]['interaction_id']);
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mdg && ./vendor/bin/phpunit tests/Controller/AdminInteractionControllerTest.php -v
```
Expected: FAIL — `Class "App\Controller\AdminInteractionController" not found`

- [ ] **Step 3: Create `mdg/src/Controller/AdminInteractionController.php`**

```php
<?php
namespace App\Controller;

use App\Service\InteractionService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Admin Interactions')]
class AdminInteractionController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private InteractionService $service) {}

    /** Lists all interactions across all users for admin review; no user context required. */
    #[OA\Get(summary: 'List all interactions (admin)')]
    #[OA\Response(response: 200, description: 'Array of interaction objects')]
    #[OA\Response(response: 401, description: 'X-Admin-Token missing or wrong')]
    #[Route('/master-data/admin/interactions', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return new JsonResponse($this->service->listAll());
    }
}
```

- [ ] **Step 4: Replace `mdg/src/Controller/InteractionController.php` — user POST only**

```php
<?php
namespace App\Controller;

use App\Service\InteractionService;
use OpenApi\Attributes as OA;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

#[OA\Tag(name: 'Interactions')]
class InteractionController
{
    /** Injected by Symfony DI; no factory needed — single implementation, no ambiguity. */
    public function __construct(private InteractionService $service) {}

    /** Validates required fields here; service assumes valid input and owns persistence. */
    #[OA\Post(summary: 'Record a user interaction with a news event')]
    #[OA\Parameter(
        name: 'X-User-Id',
        in: 'header',
        required: true,
        description: 'Cognito sub injected upstream by UserContextListener; not validated here',
        schema: new OA\Schema(type: 'string'),
    )]
    #[OA\RequestBody(
        required: true,
        content: new OA\JsonContent(
            required: ['event_id', 'type'],
            properties: [
                new OA\Property(property: 'event_id', type: 'string', format: 'uuid'),
                new OA\Property(property: 'type', type: 'string', example: 'read'),
            ],
        ),
    )]
    #[OA\Response(response: 201, description: 'Interaction recorded')]
    #[OA\Response(response: 400, description: 'event_id or type missing')]
    #[Route('/master-data/interactions', methods: ['POST'])]
    public function record(Request $request): JsonResponse
    {
        $body = json_decode($request->getContent(), true) ?? [];
        if (empty($body['event_id']) || empty($body['type'])) {
            return new JsonResponse(['error' => 'event_id and type required'], 400);
        }
        $userId = $request->attributes->get('user_id', '');
        $result = $this->service->record($userId, $body['event_id'], $body['type']);
        return new JsonResponse($result, 201);
    }
}
```

- [ ] **Step 5: Replace `mdg/tests/Controller/InteractionControllerTest.php` — user POST only**

```php
<?php
namespace App\Tests\Controller;

use App\Controller\InteractionController;
use App\Service\InteractionService;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

class InteractionControllerTest extends TestCase
{
    public function testRecordReturns201(): void
    {
        $service = $this->createMock(InteractionService::class);
        $service->expects($this->once())->method('record')
            ->willReturn(['interaction_id' => 'ix-1', 'created_at' => '2026-01-01T00:00:00+00:00']);

        $request = Request::create('/master-data/interactions', 'POST', [], [], [], [],
            json_encode(['event_id' => 'ev-1', 'type' => 'click'], JSON_THROW_ON_ERROR));
        $request->headers->set('Content-Type', 'application/json');
        $request->attributes->set('user_id', 'user-1');

        $controller = new InteractionController($service);
        $response   = $controller->record($request);
        $this->assertSame(201, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('ix-1', $body['interaction_id']);
    }

    public function testRecordReturns400WhenEventIdMissing(): void
    {
        $service = $this->createMock(InteractionService::class);
        $request = Request::create('/master-data/interactions', 'POST', [], [], [], [],
            json_encode(['type' => 'click'], JSON_THROW_ON_ERROR));
        $request->headers->set('Content-Type', 'application/json');
        $request->attributes->set('user_id', 'user-1');

        $controller = new InteractionController($service);
        $response   = $controller->record($request);
        $this->assertSame(400, $response->getStatusCode());
        $body = json_decode((string) $response->getContent(), true);
        $this->assertSame('event_id and type required', $body['error']);
    }
}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd mdg && ./vendor/bin/phpunit tests/Controller/InteractionControllerTest.php tests/Controller/AdminInteractionControllerTest.php -v
```
Expected: 3 tests, PASS

- [ ] **Step 7: Run full suite + PHPStan**

```bash
cd mdg && composer phpstan && composer test
```
Expected: zero PHPStan errors, all tests green

- [ ] **Step 8: Commit**

```bash
git add mdg/src/Controller/InteractionController.php \
        mdg/src/Controller/AdminInteractionController.php \
        mdg/tests/Controller/InteractionControllerTest.php \
        mdg/tests/Controller/AdminInteractionControllerTest.php
git commit -m "feat(interactions): move admin list to AdminInteractionController at /admin/interactions"
```

---

### Task 7: Update EndpointSmokeTest for ADR-012 paths

All admin mutations and lists must use `/admin/` paths and send `X-Admin-Token`. User GETs already have `X-User-Id` via `$this->client`.

**Files:**
- Modify: `mdg/tests/Smoke/EndpointSmokeTest.php`

- [ ] **Step 1: Replace `mdg/tests/Smoke/EndpointSmokeTest.php` with the updated version**

```php
<?php
namespace App\Tests\Smoke;

use PHPUnit\Framework\Attributes\Depends;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpClient\HttpClient;
use Symfony\Contracts\HttpClient\HttpClientInterface;

/**
 * Smoke suite: real HTTP calls against localhost:9000 after migration + fixtures.
 * Skips cleanly when the server is not reachable.
 *
 * Run: ADMIN_TOKEN=dev-admin-secret composer smoke
 * Requires: docker-compose up -d && doctrine:migrations:migrate && doctrine:fixtures:load
 */
class EndpointSmokeTest extends TestCase
{
    private static bool $serverAvailable = true;

    /** Fixture user subscribed to 2 topics — provides real newsletter/event IDs. */
    private const SEEDED_USER = 'mock-user-0001';

    /** Clean user with no subscriptions — used for the POST /subscriptions write test. */
    private const SMOKE_USER = 'smoke-test-user';

    private HttpClientInterface $client;
    private HttpClientInterface $adminClient;

    /** @var list<\Closure> Deferred cleanup callbacks run in tearDown. */
    private array $tearDownCallbacks = [];

    private static function baseUrl(): string
    {
        return $_ENV['MDG_SMOKE_BASE_URL'] ?? (string) getenv('MDG_SMOKE_BASE_URL') ?: 'http://localhost:9000';
    }

    private static function adminToken(): string
    {
        return $_ENV['ADMIN_TOKEN'] ?? (string) getenv('ADMIN_TOKEN') ?: 'dev-admin-secret';
    }

    public static function setUpBeforeClass(): void
    {
        try {
            HttpClient::create()
                ->request('GET', self::baseUrl() . '/master-data/newsletters', [
                    'headers' => ['X-User-Id' => self::SEEDED_USER],
                    'timeout' => 2.0,
                ])
                ->getStatusCode();
        } catch (\Throwable) {
            self::$serverAvailable = false;
        }
    }

    protected function setUp(): void
    {
        if (!self::$serverAvailable) {
            $this->markTestSkipped('MDG server not reachable at ' . self::baseUrl());
        }
        $this->client = HttpClient::create([
            'headers' => ['X-User-Id' => self::SEEDED_USER],
        ]);
        $this->adminClient = HttpClient::create([
            'headers' => ['X-Admin-Token' => self::adminToken()],
        ]);
        $this->tearDownCallbacks = [];
    }

    protected function tearDown(): void
    {
        foreach ($this->tearDownCallbacks as $callback) {
            $callback();
        }
        parent::tearDown();
    }

    /**
     * Root of the dependency chain — fetches newsletters for the seeded user.
     *
     * @return array{newsletterId: string, topicId: string}
     *
     * curl http://localhost:9000/master-data/newsletters -H "X-User-Id: mock-user-0001"
     */
    public function testNewslettersListReturns200(): array
    {
        $response = $this->client->request('GET', self::baseUrl() . '/master-data/newsletters');
        $this->assertSame(200, $response->getStatusCode());
        /** @var list<array<string, mixed>> $body */
        $body = $response->toArray();
        $this->assertNotEmpty($body, 'Newsletters list is empty — run fixtures first');
        $this->assertArrayHasKey('newsletterId', $body[0]);
        $this->assertArrayHasKey('topicId', $body[0]);

        return [
            'newsletterId' => (string) $body[0]['newsletterId'],
            'topicId'      => (string) $body[0]['topicId'],
        ];
    }

    /**
     * @param array{newsletterId: string, topicId: string} $ids
     * @return array{newsletterId: string, topicId: string, eventId: string}
     *
     * curl http://localhost:9000/master-data/newsletters/{id} -H "X-User-Id: mock-user-0001"
     */
    #[Depends('testNewslettersListReturns200')]
    public function testNewsletterGetByIdReturns200(array $ids): array
    {
        $response = $this->client->request(
            'GET',
            self::baseUrl() . '/master-data/newsletters/' . $ids['newsletterId']
        );
        $this->assertSame(200, $response->getStatusCode());
        /** @var array<string, mixed> $body */
        $body = $response->toArray();
        $this->assertSame($ids['newsletterId'], $body['newsletter_id']);
        $this->assertNotEmpty($body['events'], 'Newsletter has no events — check fixtures');

        return [
            ...$ids,
            'eventId' => (string) $body['events'][0]['event_id'],
        ];
    }

    /**
     * curl http://localhost:9000/master-data/subscriptions -H "X-User-Id: mock-user-0001"
     */
    public function testSubscriptionsListReturns200(): void
    {
        $response = $this->client->request('GET', self::baseUrl() . '/master-data/subscriptions');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }

    /**
     * @param array{newsletterId: string, topicId: string} $ids
     *
     * curl -X POST http://localhost:9000/master-data/subscriptions -H "X-User-Id: smoke-test-user" -H "Content-Type: application/json" -d '{"topic_id": "<uuid>"}'
     */
    #[Depends('testNewslettersListReturns200')]
    public function testSubscribeReturns201(array $ids): void
    {
        $topicId    = $ids['topicId'];
        $smokeClient = HttpClient::create([
            'headers' => [
                'X-User-Id'    => self::SMOKE_USER,
                'Content-Type' => 'application/json',
            ],
        ]);
        $response = $smokeClient->request(
            'POST',
            self::baseUrl() . '/master-data/subscriptions',
            ['json' => ['topic_id' => $topicId]]
        );
        $this->assertSame(201, $response->getStatusCode());
        /** @var array<string, mixed> $body */
        $body = $response->toArray();
        $this->assertSame($topicId, $body['topic_id']);

        $this->tearDownCallbacks[] = function () use ($topicId, $smokeClient): void {
            $status = $smokeClient->request(
                'DELETE',
                self::baseUrl() . '/master-data/subscriptions/' . $topicId
            )->getStatusCode();
            if (!in_array($status, [200, 204, 404], true)) {
                fwrite(STDERR, "Smoke teardown: DELETE /master-data/subscriptions/$topicId returned $status\n");
            }
        };
    }

    /**
     * @param array{newsletterId: string, topicId: string, eventId: string} $ids
     *
     * curl -X POST http://localhost:9000/master-data/interactions -H "X-User-Id: mock-user-0001" -H "Content-Type: application/json" -d '{"event_id": "<uuid>", "type": "view"}'
     */
    #[Depends('testNewsletterGetByIdReturns200')]
    public function testInteractionRecordReturns201(array $ids): void
    {
        $response = $this->client->request(
            'POST',
            self::baseUrl() . '/master-data/interactions',
            [
                'headers' => ['Content-Type' => 'application/json'],
                'json'    => ['event_id' => $ids['eventId'], 'type' => 'view'],
            ]
        );
        $this->assertSame(201, $response->getStatusCode());
    }

    /**
     * curl http://localhost:9000/master-data/deep-dive/{eventId} -H "X-User-Id: mock-user-0001"
     */
    #[Depends('testNewsletterGetByIdReturns200')]
    public function testDeepDiveReturns200(array $ids): void
    {
        $response = $this->client->request(
            'GET',
            self::baseUrl() . '/master-data/deep-dive/' . $ids['eventId']
        );
        $this->assertSame(200, $response->getStatusCode());
    }

    /**
     * Topics list is public — no auth header needed.
     *
     * curl http://localhost:9000/master-data/topics
     */
    public function testTopicsListReturns200(): void
    {
        $plainClient = HttpClient::create();
        $response    = $plainClient->request('GET', self::baseUrl() . '/master-data/topics');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }

    /**
     * Topic CRUD round-trip via admin endpoints.
     *
     * curl -X POST http://localhost:9000/master-data/admin/topics -H "X-Admin-Token: dev-admin-secret" -H "Content-Type: application/json" -d '{"name":"Smoke Topic"}'
     * curl http://localhost:9000/master-data/topics/{id}
     * curl -X PUT http://localhost:9000/master-data/admin/topics/{id} -H "X-Admin-Token: dev-admin-secret" -H "Content-Type: application/json" -d '{"name":"Updated"}'
     * curl -X DELETE http://localhost:9000/master-data/admin/topics/{id} -H "X-Admin-Token: dev-admin-secret"
     */
    public function testTopicCrudRoundTrip(): void
    {
        $jsonAdmin = HttpClient::create(['headers' => [
            'Content-Type'  => 'application/json',
            'X-Admin-Token' => self::adminToken(),
        ]]);
        $base = self::baseUrl();

        $res = $jsonAdmin->request('POST', "{$base}/master-data/admin/topics",
            ['json' => ['name' => 'Smoke Topic', 'description' => 'auto']]);
        $this->assertSame(201, $res->getStatusCode(), 'POST /admin/topics failed');
        /** @var array<string, mixed> $created */
        $created = $res->toArray();
        $topicId = (string) $created['topic_id'];

        $this->tearDownCallbacks[] = static function () use ($topicId, $jsonAdmin, $base): void {
            $jsonAdmin->request('DELETE', "{$base}/master-data/admin/topics/{$topicId}")->getStatusCode();
        };

        // GET is public
        $plainClient = HttpClient::create();
        $res = $plainClient->request('GET', "{$base}/master-data/topics/{$topicId}");
        $this->assertSame(200, $res->getStatusCode());
        $this->assertSame('Smoke Topic', $res->toArray()['name']);

        $res = $jsonAdmin->request('PUT', "{$base}/master-data/admin/topics/{$topicId}",
            ['json' => ['name' => 'Updated Topic']]);
        $this->assertSame(200, $res->getStatusCode());
        $this->assertSame('Updated Topic', $res->toArray()['name']);

        $res = $jsonAdmin->request('DELETE', "{$base}/master-data/admin/topics/{$topicId}");
        $this->assertSame(204, $res->getStatusCode());

        $res = $plainClient->request('GET', "{$base}/master-data/topics/{$topicId}");
        $this->assertSame(404, $res->getStatusCode(), 'GET after DELETE should 404');
    }

    /**
     * Tests that admin token is required — no token → 401.
     *
     * curl http://localhost:9000/master-data/admin/topics  (no token — expect 401)
     */
    public function testAdminTopicsWithoutTokenReturns401(): void
    {
        $plainClient = HttpClient::create();
        $response    = $plainClient->request('GET', self::baseUrl() . '/master-data/admin/topics');
        $this->assertSame(401, $response->getStatusCode());
    }

    /**
     * News events list is user-scoped; $this->client sends X-User-Id.
     *
     * curl http://localhost:9000/master-data/news-events -H "X-User-Id: mock-user-0001"
     */
    public function testNewsEventsListReturns200(): void
    {
        $response = $this->client->request('GET', self::baseUrl() . '/master-data/news-events');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }

    /**
     * NewsEvent CRUD round-trip via admin endpoints.
     *
     * curl -X POST http://localhost:9000/master-data/admin/news-events -H "X-Admin-Token: dev-admin-secret" -H "Content-Type: application/json" -d '{"headline":"Smoke Event","summary":"Test summary","date":"2026-01-15"}'
     */
    public function testNewsEventCrudRoundTrip(): void
    {
        $jsonAdmin = HttpClient::create(['headers' => [
            'Content-Type'  => 'application/json',
            'X-Admin-Token' => self::adminToken(),
        ]]);
        $base = self::baseUrl();

        $res = $jsonAdmin->request('POST', "{$base}/master-data/admin/news-events", [
            'json' => ['headline' => 'Smoke Event', 'summary' => 'Test summary', 'date' => '2026-01-15'],
        ]);
        $this->assertSame(201, $res->getStatusCode(), 'POST /admin/news-events failed');
        /** @var array<string, mixed> $created */
        $created = $res->toArray();
        $eventId = (string) $created['event_id'];

        $this->tearDownCallbacks[] = static function () use ($eventId, $jsonAdmin, $base): void {
            $jsonAdmin->request('DELETE', "{$base}/master-data/admin/news-events/{$eventId}")->getStatusCode();
        };

        $res = $jsonAdmin->request('GET', "{$base}/master-data/admin/news-events/{$eventId}");
        $this->assertSame(200, $res->getStatusCode());
        $this->assertSame('Smoke Event', $res->toArray()['headline']);

        $res = $jsonAdmin->request('PUT', "{$base}/master-data/admin/news-events/{$eventId}", [
            'json' => ['headline' => 'Updated Event', 'summary' => 'Updated summary', 'date' => '2026-01-20'],
        ]);
        $this->assertSame(200, $res->getStatusCode());
        $this->assertSame('Updated Event', $res->toArray()['headline']);

        $res = $jsonAdmin->request('DELETE', "{$base}/master-data/admin/news-events/{$eventId}");
        $this->assertSame(204, $res->getStatusCode());

        $res = $jsonAdmin->request('GET', "{$base}/master-data/admin/news-events/{$eventId}");
        $this->assertSame(404, $res->getStatusCode(), 'GET after DELETE should 404');
    }

    /**
     * Newsletter mutations via admin endpoints; GET (user) verifies 404 after delete.
     *
     * curl -X POST http://localhost:9000/master-data/admin/newsletters -H "X-Admin-Token: dev-admin-secret" -H "Content-Type: application/json" -d '{"topic_id":"<uuid>","date":"2026-06-09","title":"Smoke Newsletter","narrative":"Body"}'
     */
    public function testNewsletterMutationsRoundTrip(): void
    {
        $jsonAdmin = HttpClient::create(['headers' => [
            'Content-Type'  => 'application/json',
            'X-Admin-Token' => self::adminToken(),
        ]]);
        $base = self::baseUrl();

        // Get a topic_id from the public topics list
        $topicsRes = HttpClient::create()->request('GET', "{$base}/master-data/topics");
        $this->assertSame(200, $topicsRes->getStatusCode(), 'Topics list failed');
        /** @var list<array<string, mixed>> $topics */
        $topics  = $topicsRes->toArray();
        $this->assertNotEmpty($topics, 'Topics list empty — run fixtures');
        $topicId = (string) $topics[0]['topic_id'];

        $res = $jsonAdmin->request('POST', "{$base}/master-data/admin/newsletters", [
            'json' => ['topic_id' => $topicId, 'date' => '2026-06-09',
                       'title' => 'Smoke Newsletter', 'narrative' => 'Test narrative'],
        ]);
        $this->assertSame(201, $res->getStatusCode(), 'POST /admin/newsletters failed');
        /** @var array<string, mixed> $created */
        $created      = $res->toArray();
        $newsletterId = (string) $created['newsletter_id'];

        $this->tearDownCallbacks[] = static function () use ($newsletterId, $jsonAdmin, $base): void {
            $jsonAdmin->request('DELETE', "{$base}/master-data/admin/newsletters/{$newsletterId}")->getStatusCode();
        };

        $res = $jsonAdmin->request('PUT', "{$base}/master-data/admin/newsletters/{$newsletterId}", [
            'json' => ['title' => 'Updated Newsletter', 'narrative' => 'Updated narrative'],
        ]);
        $this->assertSame(200, $res->getStatusCode(), 'PUT /admin/newsletters/{id} failed');
        $this->assertSame('Updated Newsletter', $res->toArray()['title']);

        $res = $jsonAdmin->request('DELETE', "{$base}/master-data/admin/newsletters/{$newsletterId}");
        $this->assertSame(204, $res->getStatusCode(), 'DELETE /admin/newsletters/{id} failed');

        // Verify deletion via admin GET
        $res = $jsonAdmin->request('GET', "{$base}/master-data/admin/newsletters/{$newsletterId}");
        $this->assertSame(404, $res->getStatusCode(), 'GET after DELETE should 404');
    }

    /**
     * Admin interactions list via admin endpoint.
     *
     * curl http://localhost:9000/master-data/admin/interactions -H "X-Admin-Token: dev-admin-secret"
     */
    public function testAdminInteractionsListReturns200(): void
    {
        $response = $this->adminClient->request('GET', self::baseUrl() . '/master-data/admin/interactions');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }

    /**
     * Admin subscriptions list via admin endpoint.
     *
     * curl http://localhost:9000/master-data/admin/subscriptions -H "X-Admin-Token: dev-admin-secret"
     */
    public function testAdminSubscriptionsListReturns200(): void
    {
        $response = $this->adminClient->request('GET', self::baseUrl() . '/master-data/admin/subscriptions');
        $this->assertSame(200, $response->getStatusCode());
        $response->toArray();
    }
}
```

- [ ] **Step 2: Run unit + PHPStan (smoke requires Docker)**

```bash
cd mdg && composer phpstan && composer test
```
Expected: zero PHPStan errors, all unit tests green (smoke tests skipped if Docker not running)

- [ ] **Step 3: Commit**

```bash
git add mdg/tests/Smoke/EndpointSmokeTest.php
git commit -m "test(smoke): update all endpoint URLs to match ADR-012 scopes, add X-Admin-Token"
```

---

## Self-Review

**Spec coverage against ADR-012:**

| ADR-012 endpoint | Task covering it |
|---|---|
| GET /topics (Public) | Task 2 — TopicController.list() |
| GET /topics/{id} (Public) | Task 2 — TopicController.get() |
| POST/PUT/DELETE /admin/topics (Admin) | Task 2 — AdminTopicController |
| GET /news-events (User) | Task 3 — NewsEventController.list() |
| GET /news-events/{id} (User) | Task 3 — NewsEventController.get() |
| GET /admin/news-events (Admin) | Task 3 — AdminNewsEventController.list() |
| GET /admin/news-events/{id} (Admin) | Task 3 — AdminNewsEventController.get() |
| POST/PUT/DELETE /admin/news-events (Admin) | Task 3 — AdminNewsEventController |
| GET /newsletters (User) | Task 5 — NewsletterController.list() |
| GET /newsletters/{id} (User) | Task 5 — NewsletterController.get() |
| GET /admin/newsletters (Admin) | Task 5 — AdminNewsletterController.list() |
| GET /admin/newsletters/{id} (Admin) | Task 5 — AdminNewsletterController.get() |
| POST/PUT/DELETE /admin/newsletters (Admin) | Task 5 — AdminNewsletterController |
| POST /subscriptions (User) | Existing SubscriptionController ✓ |
| GET /subscriptions (User) | Existing SubscriptionController ✓ |
| DELETE /subscriptions/{topicId} (User) | Existing SubscriptionController ✓ |
| GET /admin/subscriptions (Admin) | Existing AdminSubscriptionController ✓ |
| DELETE /admin/subscriptions/{userId}/{topicId} (Admin) | Existing AdminSubscriptionController ✓ |
| POST /interactions (User) | Task 6 — InteractionController.record() |
| GET /admin/interactions (Admin) | Task 6 — AdminInteractionController.list() |
| AdminTokenListener guards all /admin/ | Task 1 |

All 26 endpoints covered. No gaps.
