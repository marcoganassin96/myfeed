# Backlog: MDG Service Auth — API Key Hardening

**Related ADR:** [005-mdg-service-auth.md](../decisions/005-mdg-service-auth.md)

Current state: MDG relies on VPC network isolation only (ADR-005, Option A). This task upgrades to per-caller API key auth (Option B).

## Trigger Criteria

Implement when **any** of the following becomes true:

- A second service (e.g., NLP pipeline worker, scraper) needs to call MDG, especially if running outside the VPC
- Compliance or audit requirements demand a per-caller request log at the application layer
- MDG needs a non-VPC endpoint (admin UI, staging environment with public access)

## Implementation Outline

### 1. AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name newsletter-dev/mdg-api-key \
  --secret-string '{"api_key":"<generated-uuid>"}'
```

### 2. MDG — Symfony event listener

```php
// src/EventListener/ApiKeyListener.php
class ApiKeyListener implements EventSubscriberInterface
{
    public function onKernelRequest(RequestEvent $event): void
    {
        $request = $event->getRequest();
        if ($request->headers->get('X-Api-Key') !== $this->apiKey) {
            $event->setResponse(new JsonResponse(['error' => 'Unauthorized'], 401));
        }
    }
}
```

### 3. FastAPI — add header to httpx client

```python
MDG_API_KEY = os.environ["MDG_API_KEY"]

async with httpx.AsyncClient(
    base_url=settings.MDG_URL,
    headers={"X-Api-Key": MDG_API_KEY},
) as client:
    ...
```

### 4. CI/CD

- Add `MDG_API_KEY` to ECS task definition secrets (sourced from Secrets Manager)
- Add `MDG_API_KEY` to FastAPI Fargate task definition env

### 5. Local dev

```yaml
# docker-compose.yml
services:
  mdg:
    environment:
      MDG_API_KEY: dev-local-key
  api:
    environment:
      MDG_API_KEY: dev-local-key
```

### 6. Tests

- MDG: assert 401 when header absent or wrong
- MDG: assert 200 when header correct
- FastAPI: mock httpx with header assertion
