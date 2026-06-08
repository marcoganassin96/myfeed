# NelmioApiDocBundle: OpenAPI / Swagger for Symfony

## 1. What It Is

**NelmioApiDocBundle** is Symfony's standard library for generating OpenAPI 3 specs and a Swagger UI from existing PHP code.

Direction: **code → spec + UI** (code-first). The spec is always in sync with the real routes because it is derived from them at runtime.

Spring analogy:

| Spring | Symfony |
|--------|---------|
| `springdoc-openapi` / `springfox` | NelmioApiDocBundle |
| `@Operation`, `@Parameter` | `#[OA\Get]`, `#[OA\Parameter]` |
| Swagger UI at `/swagger-ui.html` | Swagger UI at `/api/doc` |
| `swagger-codegen` (spec → stubs) | No equivalent — Symfony goes code → spec only |

Under the hood NelmioApiDocBundle wraps **zircote/swagger-php**, which reads PHP 8 attributes (`#[OA\...]`) and merges them with Symfony route metadata auto-detected from `#[Route]`.

---

## 2. Installation

```bash
composer require nelmio/api-doc-bundle
```

NelmioApiDocBundle requires a template engine to render the Swagger UI page:

```bash
composer require twig/twig symfony/twig-bundle
```

Symfony Flex registers the bundle automatically. No manual `bundles.php` edit needed.

---

## 3. Configuration

Flex generates `config/packages/nelmio_api_doc.yaml`. Minimal working config:

```yaml
# config/packages/nelmio_api_doc.yaml
nelmio_api_doc:
    documentation:
        info:
            title: 'Master Data Gateway'
            description: 'Internal API for newsletter master data'
            version: '1.0.0'
    areas:
        default:
            path_patterns:
                - ^/master-data   # only document routes under this prefix
```

`path_patterns` under `areas.default` prevents internal Symfony routes (profiler, debug toolbar) from appearing in the spec.

Add the UI and JSON spec routes:

```yaml
# config/routes/nelmio_api_doc.yaml
app.swagger:
    path: /api/doc.json
    methods: GET
    defaults: { _controller: nelmio_api_doc.controller.swagger }

app.swagger_ui:
    path: /api/doc
    methods: GET
    defaults: { _controller: nelmio_api_doc.controller.swagger_ui }
```

Service IDs: `nelmio_api_doc.controller.swagger` is an alias for the JSON spec controller; `nelmio_api_doc.controller.swagger_ui` serves the HTML page. There is no `nelmio_api_doc.controller.spec`.

---

## 4. Route Autodiscovery — Free Docs

Nelmio reads `#[Route]` attributes automatically. No annotation needed for basic docs:

```php
#[Route('/master-data/newsletters', methods: ['GET'])]
public function list(Request $request): JsonResponse
```

Generates:

```
GET /master-data/newsletters
```

Method, path, and HTTP verb are free. Everything else (summary, parameters, response shapes) must be added with `#[OA\...]` attributes.

---

## 5. Enriching with OpenAPI Attributes

Import namespace:

```php
use OpenApi\Attributes as OA;
```

### 5.1 Operation Summary

```php
#[OA\Get(summary: 'List newsletters for the authenticated user')]
#[Route('/master-data/newsletters', methods: ['GET'])]
public function list(Request $request): JsonResponse
```

### 5.2 Path Parameters

```php
#[OA\Get(summary: 'Fetch a single newsletter by ID')]
#[OA\Parameter(
    name: 'id',
    in: 'path',
    required: true,
    schema: new OA\Schema(type: 'string', format: 'uuid'),
)]
#[Route('/master-data/newsletters/{id}', methods: ['GET'])]
public function get(Request $request, string $id): JsonResponse
```

### 5.3 Query Parameters

```php
#[OA\Parameter(
    name: 'topic',
    in: 'query',
    required: false,
    schema: new OA\Schema(type: 'string'),
)]
```

### 5.4 Response Shapes

```php
#[OA\Response(
    response: 200,
    description: 'Newsletter found',
    content: new OA\JsonContent(
        properties: [
            new OA\Property(property: 'id', type: 'string', format: 'uuid'),
            new OA\Property(property: 'title', type: 'string'),
            new OA\Property(property: 'published_at', type: 'string', format: 'date-time'),
        ]
    )
)]
#[OA\Response(response: 404, description: 'Not found')]
```

### 5.5 Request Body (POST / PATCH)

```php
#[OA\Post(summary: 'Create subscription')]
#[OA\RequestBody(
    required: true,
    content: new OA\JsonContent(
        required: ['user_id', 'newsletter_id'],
        properties: [
            new OA\Property(property: 'user_id', type: 'string', format: 'uuid'),
            new OA\Property(property: 'newsletter_id', type: 'string', format: 'uuid'),
        ]
    )
)]
```

### 5.6 Reusable Schemas

Define once, reference everywhere:

```php
#[OA\Schema(
    schema: 'Newsletter',
    properties: [
        new OA\Property(property: 'id', type: 'string', format: 'uuid'),
        new OA\Property(property: 'title', type: 'string'),
    ]
)]
class Newsletter { ... }
```

Reference in responses:

```php
content: new OA\JsonContent(ref: '#/components/schemas/Newsletter')
```

---

## 6. Global API Metadata

Set once in config, not per-controller. Covers auth schemes, servers, global headers.

```yaml
nelmio_api_doc:
    documentation:
        info:
            title: 'Master Data Gateway'
            version: '1.0.0'
        components:
            securitySchemes:
                bearerAuth:
                    type: http
                    scheme: bearer
                    bearerFormat: JWT
        security:
            - bearerAuth: []
```

With `security` set globally, every operation inherits the bearer auth scheme — no per-route repeat.

---

## 7. Accessing the Docs

| URL | Content |
|-----|---------|
| `/api/doc` | Swagger UI (HTML) |
| `/api/doc.json` | Raw OpenAPI 3 JSON spec |

The spec can be imported into Postman, Insomnia, or used by Swagger Codegen to generate client SDKs.

---

## 8. Dev-Only — Hiding the UI in Production

**Important — MicroKernelTrait caveat:** `MicroKernelTrait` auto-loads every file under `config/routes/` for ALL environments. A standalone `config/routes/nelmio_api_doc.yaml` exposes the routes in production. To scope to non-prod envs, either:

**Option A** — wrap the routes file with env conditions in `config/routes.yaml`:

```yaml
# config/routes.yaml
when@dev:
    nelmio_api_doc:
        resource: routes/nelmio_api_doc.yaml
when@local:
    nelmio_api_doc:
        resource: routes/nelmio_api_doc.yaml
```

**Option B** — wrap inside the routes file itself (works with MicroKernelTrait because Symfony still evaluates `when@` blocks):

```yaml
# config/routes/nelmio_api_doc.yaml
when@dev:
    app.swagger:
        path: /api/doc.json
        methods: GET
        defaults: { _controller: nelmio_api_doc.controller.swagger }
    app.swagger_ui:
        path: /api/doc
        methods: GET
        defaults: { _controller: nelmio_api_doc.controller.swagger_ui }
```

Either option ensures the spec is never exposed on prod without an explicit decision.

---

## 9. MDG Setup

### Controllers to document

| Controller | Routes |
|------------|--------|
| `NewsletterController` | `GET /master-data/newsletters`, `GET /master-data/newsletters/{id}` |
| `SubscriptionController` | subscription CRUD |
| `InteractionController` | interaction endpoints |
| `DeepDiveController` | deep dive endpoints |

### Setup order

1. Install bundle + Twig: `composer require nelmio/api-doc-bundle twig/twig symfony/twig-bundle`
2. Create `config/packages/nelmio_api_doc.yaml` with `areas.default.path_patterns: [^/master-data]`
3. Create `config/routes/nelmio_api_doc.yaml` with `app.swagger` and `app.swagger_ui` routes (service ID format)
4. Add `DEFAULT_URI` env var (required by Flex's `routing.yaml` recipe — `SwaggerUiController` generates an absolute URL to the JSON spec on first render):
   ```yaml
   # docker-compose.yml
   mdg:
     environment:
       DEFAULT_URI: http://localhost:9000
   ```
5. Rebuild the Docker image after any change to `bundles.php` or `config/` — the container bakes code at build time; a stale image will not have Nelmio services compiled in
6. Add `#[OA\...]` attributes to all four controllers
7. Define reusable schemas on Doctrine entities (`Newsletter`, `Subscription`, `Interaction`, `DeepDive`)
8. Add bearer auth to global config (MDG receives `X-User-ID` from upstream, but Cognito JWT is validated before traffic reaches MDG — document the expected header)
9. Visit `/api/doc` and verify all routes appear

### `user_id` context header

MDG reads `user_id` from request attributes set by `UserContextListener` (injected upstream from Cognito JWT). Document it as a header parameter on the `list` operations:

```php
#[OA\Parameter(
    name: 'X-User-ID',
    in: 'header',
    required: true,
    description: 'User identifier injected by UserContextListener from upstream JWT validation. In local dev any string works (e.g. mock-user-0001).',
    schema: new OA\Schema(type: 'string'),
)]
```
