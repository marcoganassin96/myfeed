# Symfony: Service Container

## 1. Configuration — Services & Packages per Environment

Before the container can do anything, it needs to know which rules to follow.

| Path | Purpose |
|---|---|
| `config/packages/*.yaml` | General bundle configuration |
| `config/services.yaml` | Core DI logic |
| `config/packages/{env}/*.yaml` | Environment overrides |

Environment overrides let you swap a Mock service in `dev` for the real service in `prod` without touching shared config.

---

## 2. The Core Mechanics — Autowiring vs. Binding

### When Autowiring Works

| Case | How Symfony resolves |
|---|---|
| Concrete class (`UserRepository $repo`) | Finds service whose ID exactly matches `App\Repository\UserRepository` |
| Single-implementation interface | One implementor exists → injected automatically |

### When Autowiring Fails (The Ambiguity Problem)

| Problem | Cause | Solution |
|---|---|---|
| Multiple implementations | `FastTransformer` and `SlowTransformer` both implement `TransformerInterface` | Explicit binding in `services.yaml` |
| Scalar arguments | Constructor needs `string $apiKey` — Symfony cannot guess values | Binding in `services.yaml` |
| Mismatched service ID | Class namespace doesn't match the registered service ID | Alias or explicit service definition |

### Binding

Used when autowiring isn't enough: specify exact scalar values or select a concrete implementation for an ambiguous interface.

```yaml
# config/services.yaml
services:
    _defaults:
        bind:
            string $apiKey: '%env(API_KEY)%'
            App\Contracts\TransformerInterface: '@App\Service\FastTransformer'
```

---

## 3. Automation — `_defaults` Flags

`_defaults` in `services.yaml` keeps individual service definitions lean.

```yaml
services:
    _defaults:
        autowire: true
        autoconfigure: true
```

| Flag | Effect |
|---|---|
| `autowire: true` | Symfony uses constructor reflection to resolve dependencies |
| `autoconfigure: true` | Automatically applies tags based on implemented interfaces |

Common auto-applied tags:

- `console.command` — classes extending `Command`
- `kernel.event_subscriber` — classes implementing `EventSubscriberInterface`
- `monolog.logger`

---

## 4. Advanced Optimization — Lazy Loading

### 4.1 Default Behavior (Implicit Lazy Init)

Symfony does **not** instantiate all services at startup. A service is created the first time it is requested. If never requested during a request cycle, it is never instantiated.

### 4.2 The Constructor Problem — Why `lazy: true` Exists

Default lazy init has one limitation: **dependency chains**.

If `ServiceA` is injected into `ControllerB`, the moment `ControllerB` is created Symfony must instantiate `ServiceA` to satisfy the constructor — even if no method on `ServiceA` is ever called.

**`lazy: true` tag** changes the strategy:

1. Instead of the real `ServiceA`, Symfony injects a lightweight **Proxy Object**.
2. The real `ServiceA` is only instantiated when a method is first called (`$serviceA->getData()`).

```yaml
# config/services.yaml
App\Service\HeavyService:
    lazy: true
```

Use this for services that are expensive to instantiate and only needed in edge cases.

---

## 5. The Lifecycle — Compilation, Cache Warmup & Runtime

### Phase A: Compilation

Happens during development or deployment. Symfony:

1. Runs **Compiler Passes** — resolves aliases, detects circular dependencies, optimizes the service graph.
2. Writes a single compiled PHP class to `var/cache/` representing the entire container.

The compiled container is **environment-independent** — environment-specific values are injected at runtime, not baked in at compile time.

### Phase B: Cache Warmup

```bash
php bin/console cache:warmup
```

Pre-generates compiled container, Twig templates, Doctrine proxies, and routing before the first request hits.

| When to run |
|---|
| After deployment (especially on read-only filesystems) |
| After modifying routing, Doctrine entities, or service definitions |
| In CI/CD pipeline before promoting to production |

### Phase C: Runtime

At runtime Symfony loads the compiled container from cache — **no YAML parsing, no reflection**. Two injections happen JIT the first time a service is requested:

| Injection | What happens |
|---|---|
| **Instance injection** | Container instantiates the service; recursively instantiates its dependencies |
| **Environment injection** | Dynamic parameters (env vars like a microservice URL) are resolved from the OS or `.env.local.php` and injected |

Both wiring of objects and environment-specific data filling are **Just-In-Time** — they occur the first time a service is needed during the request, not at startup.

---

## 6. MDG Implementation Audit

### ✅ Correctly Implemented

**Autowiring — concrete classes**
All controllers, services, and repositories inject concrete classes via constructor. Symfony resolves them automatically from the `App\` resource scan — no explicit wiring needed.

```php
// SubscriptionService.php
public function __construct(
    private CacheService $cache,
    private SubscriptionRepository $repo,
) {}
```

**Binding — scalar arguments**
`string $redisUrl` and `int $cacheTtl` cannot be autowired (scalars). Bound globally in `_defaults`:

```yaml
# config/services.yaml
_defaults:
    bind:
        string $redisUrl: '%mdg.redis_url%'
        int $cacheTtl: '%mdg.cache_ttl%'
```

Injected into `PredisAdapter($redisUrl)` and `CacheService($cacheTtl)` automatically.

**Solving interface ambiguity**
`CacheService` injects `RedisClientInterface $redis`. Symfony cannot guess the implementation. Explicitly wired in `services.yaml`:

```yaml
App\Cache\RedisClientInterface:
    class: App\Cache\PredisAdapter
```

**`_defaults` with `autowire` + `autoconfigure`**
Both flags set globally — individual service definitions stay empty.

**Environment config overrides**
`config/packages/dev/` and `config/packages/local/` override base config per environment.

---

### ❌ Wrongly Implemented

#### Interface binding uses `class:` instead of an alias

```yaml
# current — creates a second service instance
App\Cache\RedisClientInterface:
    class: App\Cache\PredisAdapter
```

Because autowiring is already enabled for the App\ namespace, Symfony has already automatically registered App\Cache\PredisAdapter as a service. By adding the block above, you have effectively told Symfony to create two separate objects in the container:
Service A: Named App\Cache\PredisAdapter.
Service B: Named App\Cache\RedisClientInterface (but built using the same PredisAdapter code).

Even though they do the same thing, they are two different instances in memory. If PredisAdapter opens a connection to Redis in its constructor, you might accidentally open two connections instead of one.

correct — alias points to the existing concrete service
```yaml
App\Cache\RedisClientInterface: '@App\Cache\PredisAdapter'
```

`class:` registers a new service under the interface ID. An alias (`@`) reuses the already-registered `PredisAdapter` service — no duplicate instantiation.

#### `UserContextListener` manually tagged despite `autoconfigure: true`

```yaml
# current — manual tag defeats autoconfigure
App\EventListener\UserContextListener:
    tags:
        - { name: kernel.event_listener, event: kernel.request, priority: 10 }
```

Modern approach: use the `#[AsEventListener]` PHP attribute. `autoconfigure: true` reads it automatically — no YAML entry needed.

```php
#[AsEventListener(event: KernelEvents::REQUEST, priority: 10)]
class UserContextListener { ... }
```

#### `framework.test: true` in dev environment

`config/packages/dev/framework.yaml` sets `test: true`. This flag enables the test HTTP client in the dev kernel — unintentional. It belongs in `config/packages/test/framework.yaml` only.

#### `mdg.redis_url` and DB params not defined for prod

`services.yaml` binds `%mdg.redis_url%`; `doctrine.yaml` references `%mdg.db_host%` etc. These parameters exist only in `dev/mdg.yaml` and `local/mdg.yaml`. No `prod/` config exists. A prod deployment crashes with "parameter not found" unless values are set externally.

---

### ⚠️ Not Implemented

#### `lazy: true` for `PredisAdapter`

`PredisAdapter::__construct` opens a Redis connection immediately. It is injected into `CacheService`, which is injected into every service and controller. Every request pays the connection cost even if cache is never used.

```yaml
# config/services.yaml
App\Cache\PredisAdapter:
    lazy: true
```

With `lazy: true` Symfony injects a proxy — the real connection opens only when a cache method is first called.

#### Cache warmup in deployment

No `php bin/console cache:warmup` in any Dockerfile, deployment script, or CI config. The first request after deployment pays the full compilation cost. Should be added to the deploy step:

```dockerfile
RUN php bin/console cache:warmup --env=prod
```

#### `prod/` environment config directory

`config/packages/prod/` does not exist. Prod-specific overrides (real Redis TLS URL, real DB host, stricter log levels) have no home. Without it, prod silently inherits dev parameters if `APP_ENV` is misconfigured.

#### `test/` environment config directory

`config/packages/test/` does not exist. Tests run against uncontrolled config. Test-specific overrides (in-memory transport, stub services, `framework.test: true`) should live there, isolated from dev.

### Resolution of wrongly implemented

#### Open Items

- [x] Interface binding uses `class:` instead of an alias
- [x] `UserContextListener` manually tagged despite `autoconfigure: true`
- [ ] `framework.test: true` in dev environment
- [ ] `mdg.redis_url` and DB params not defined for prod
