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
