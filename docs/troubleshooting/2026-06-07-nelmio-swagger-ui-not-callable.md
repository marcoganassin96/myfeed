# Troubleshooting: NelmioApiDocBundle Swagger UI "controller not callable"

**Date:** 2026-06-07
**Environment:** `mdg` (PHP/Symfony, local Docker)
**Status:** Resolved

---

## Symptom

`GET /api/doc` returns HTTP 500:

```
The controller for URI "/api/doc" is not callable:
Controller "nelmio_api_doc.controller.swagger_ui" does neither exist as service nor as class.
```

Occurred after adding `nelmio/api-doc-bundle` and configuring routes manually (no Symfony Flex).

---

## Root Cause

**Nelmio's controllers are missing the `controller.service_arguments` tag.**

Symfony's `RegisterControllerArgumentLocatorsPass` (a core compiler pass) runs during container compilation and does one thing: scans all services tagged `controller.service_arguments` and registers them in the controller Service Locator. Only controllers registered in that Service Locator are considered valid and dispatchable. Anything not registered is rejected at runtime — the "controller not callable" error.

In a standard Symfony app, the tag is added automatically via two mechanisms:

| Mechanism | When it fires |
|---|---|
| Extend `AbstractController` | FrameworkBundle registers `AbstractController` for autoconfiguration; any service extending it inherits `controller.service_arguments` automatically when `autoconfigure: true` |
| `#[AsController]` attribute | Explicitly requests the same autoconfigure rule |

Nelmio's controllers (`SwaggerUiController`, `SwaggerController`) do **neither**. They don't extend `AbstractController` and carry no `#[AsController]`. Nelmio also does not explicitly add `controller.service_arguments` in its own `services.yaml`. The tag is simply absent.

Because the tag is absent, `RegisterControllerArgumentLocatorsPass` ignores both Nelmio controllers entirely. They are never registered in the Service Locator. Symfony's `ContainerControllerResolver` cannot find them. The route resolves to the service ID string — `nelmio_api_doc.controller.swagger_ui` — but that string matches neither a known class nor a registered service controller. HTTP 500.

---

## Fix

Add the missing tag via a compiler pass in `Kernel::build()`. Two constraints apply:

**Constraint 1 — must use a compiler pass, not direct `build()` manipulation.**
`Kernel::build()` runs before bundle extensions load their services. At that point `nelmio_api_doc.controller.swagger_ui` does not exist yet — `$container->hasDefinition()` returns `false`. A `CompilerPassInterface` registered in `build()` runs after all extensions have loaded, so the service exists when `process()` is called.

**Constraint 2 — priority must be higher than `RegisterControllerArgumentLocatorsPass`.**
Both our pass and `RegisterControllerArgumentLocatorsPass` use `PassConfig::TYPE_BEFORE_OPTIMIZATION`. At equal priority, passes run in registration order. `FrameworkBundle::build()` runs before `Kernel::build()`, so `RegisterControllerArgumentLocatorsPass` is registered first — and therefore runs first at priority 0. Our pass must run before it, so we use priority 10.

`mdg/src/Kernel.php`:

```php
<?php
namespace App;

use Symfony\Bundle\FrameworkBundle\Kernel\MicroKernelTrait;
use Symfony\Component\DependencyInjection\Compiler\CompilerPassInterface;
use Symfony\Component\DependencyInjection\Compiler\PassConfig;
use Symfony\Component\DependencyInjection\ContainerBuilder;
use Symfony\Component\HttpKernel\Kernel as BaseKernel;

class Kernel extends BaseKernel
{
    use MicroKernelTrait;

    protected function build(ContainerBuilder $container): void
    {
        $container->addCompilerPass(new class implements CompilerPassInterface {
            public function process(ContainerBuilder $container): void
            {
                foreach (['nelmio_api_doc.controller.swagger_ui', 'nelmio_api_doc.controller.swagger_json'] as $id) {
                    if ($container->hasDefinition($id)) {
                        $container->getDefinition($id)->addTag('controller.service_arguments');
                    }
                }
            }
        }, PassConfig::TYPE_BEFORE_OPTIMIZATION, 10);
    }
}
```

After the fix, the compiled container includes `SwaggerUiController` in the Service Locator and the controller resolves correctly.

---

## Contributing Factors

### `symfony/asset` must be installed

`NelmioApiDocExtension::load()` conditionally removes `nelmio_api_doc.controller.swagger_ui`:

```php
if (!isset($bundles['TwigBundle']) || !class_exists('Symfony\Component\Asset\Packages')) {
    $container->removeDefinition('nelmio_api_doc.controller.swagger_ui');
}
```

If `symfony/asset` is absent, the service is removed before any compiler pass can tag it. Install it:

```bash
composer require symfony/asset:^7.0
```

### No Symfony Flex — manual wiring required

Without Flex, Nelmio routes and bundle registration are not created automatically.

`config/routes/nelmio_api_doc.yaml`:
```yaml
app.swagger_ui:
    path: /api/doc
    methods: GET
    defaults: { _controller: nelmio_api_doc.controller.swagger_ui }

app.swagger_json:
    path: /api/doc.json
    methods: GET
    defaults: { _controller: nelmio_api_doc.controller.swagger_json }
```

`config/routes.yaml` — scope to non-prod envs:
```yaml
when@dev:
    nelmio_api_doc:
        resource: routes/nelmio_api_doc.yaml

when@local:
    nelmio_api_doc:
        resource: routes/nelmio_api_doc.yaml
```

### Controller ID naming in Nelmio v5

`nelmio_api_doc.controller.swagger` is an **alias** for `swagger_json` (JSON spec only, no HTML). Use `swagger_ui` for the HTML UI.

---

## Operational Notes — Docker (no volume mount)

The `mdg` container bakes code at image build time (`COPY . .`). After any change to `src/` or `config/`:

```bash
# 1. Copy changed file into the running container
docker cp <local-file> python-newsletter-mdg-1:/app/<path>

# 2. Force cache rebuild (cache:warmup alone may skip recompilation if it considers cache fresh)
docker exec python-newsletter-mdg-1 sh -c "rm -rf /app/var/cache/local && cd /app && APP_ENV=local php bin/console cache:warmup"

# 3. Flush php-fpm OPcache (workers hold the old compiled container class in memory)
kill -USR2 $(docker exec python-newsletter-mdg-1 sh -c "cat /var/run/php-fpm.pid 2>/dev/null || pgrep -f 'php-fpm: master'")
```

Or restart the container: `docker-compose restart mdg`.

`cache:warmup` alone is insufficient — it does not invalidate OPcache or restart php-fpm workers.

---

## Why This Bug Only Appears Without Flex

This bug is **not a general Nelmio incompatibility with Symfony**. Almost no one reports it because Symfony Flex silently routes around the problem.

When you install via `composer require nelmio/api-doc-bundle`, Flex runs Nelmio's recipe and generates:

```yaml
# config/routes/nelmio_api_doc.yaml (Flex-generated)
nelmio_api_doc:
    resource: '@NelmioApiDocBundle/config/routes.xml'
```

Nelmio's own bundled `routes.xml` registers the controller using the **fully qualified class name**:

```xml
<route id="app.swagger_ui" path="/api/doc"
       controller="Nelmio\ApiDocBundle\Controller\SwaggerUiController"/>
```

Symfony resolves `_controller` differently depending on the value format:

| Format | Resolution path | Service Locator required? |
|---|---|---|
| `nelmio_api_doc.controller.swagger_ui` (service ID) | Service Locator lookup | Yes — `controller.service_arguments` tag required |
| `Nelmio\ApiDocBundle\Controller\SwaggerUiController` (FQCN) | Class-based resolution | No |

Flex users have the same route setup — Nelmio's own bundled route resource (`config/routing/swaggerui.php`) **also uses service ID format**:

```php
$routes->add('nelmio_api_doc.swagger_ui', '/')
    ->controller('nelmio_api_doc.controller.swagger_ui')
    ->methods(['GET']);
```

So the Service Locator path is taken regardless. Flex users on Symfony 7 hit the same missing-tag problem.

**The compiler pass is required regardless of whether Flex is used.** Flex helps with initial setup automation (bundle registration, config scaffolding) but does not solve the `controller.service_arguments` gap. The `Kernel::build()` override is a genuine fix for a Nelmio oversight — not a workaround for manual wiring.

---

## Flex Recipe Files Tried — Error Still Persists

To rule out manual wiring as the root cause, the manually-created route and config files were reverted and replaced with files matching the exact content of the Nelmio v3.0 Flex recipe (recipes-contrib ref `c8e0c38e`).

`composer recipes:install --force` was run but produced no files — git revert commits had explicitly deleted the paths, so Flex respected git state and skipped regeneration. The files were recreated manually with identical Flex recipe content:

`config/routes/nelmio_api_doc.yaml`:
```yaml
app.swagger:
    path: /api/doc.json
    methods: GET
    defaults: { _controller: nelmio_api_doc.controller.swagger }

app.swagger_ui:
    path: /api/doc
    methods: GET
    defaults: { _controller: nelmio_api_doc.controller.swagger_ui }
```

**Result: same HTTP 500 error.** The Flex recipe for Nelmio uses the same service ID format (`nelmio_api_doc.controller.swagger_ui`) as the manual wiring. The Service Locator path is taken either way. The `controller.service_arguments` tag is still absent either way. The compiler pass in `Kernel::build()` is required regardless.

---

## Related Reports Found on the Web

Searching for the exact error message `"does neither exist as service nor as class"` returns several GitHub issues in the Nelmio repo — but they document a **different root cause**.

**Issues #1220 and #1805** (nelmio/NelmioApiDocBundle):

Both report the identical error string but the cause is `symfony/asset` or `symfony/twig-bundle` not being installed. `NelmioApiDocExtension::load()` calls `$container->removeDefinition('nelmio_api_doc.controller.swagger_ui')` when either is absent:

```php
if (!isset($bundles['TwigBundle']) || !class_exists('Symfony\Component\Asset\Packages')) {
    $container->removeDefinition('nelmio_api_doc.controller.swagger_ui');
}
```

When the service is removed entirely, no tag can save it — and the same "does neither exist as service nor as class" message is thrown. The fix in those issues was simply `composer require symfony/asset symfony/twig-bundle`.

**Our case is different.** Both `symfony/twig-bundle` and `symfony/asset` are installed. The service is not removed — it is present but untagged. The root cause is the missing `controller.service_arguments` tag documented above.

No GitHub issues were found specifically reporting the missing-tag variant of this error. The compiler pass approach appears to be an original fix.

---

## Follow-up Investigation — 2026-06-08

After the above was documented, the compiler pass theory was put to an empirical test.

**Setup:**

- `Kernel.php` reverted to vanilla — no `build()` override, no compiler pass
- `symfony/asset` and `symfony/twig-bundle` presence confirmed via vendor filesystem and `debug:container`
- `debug:container nelmio_api_doc.controller.swagger_ui` output: `Public: yes`, `Tags: -` (no `controller.service_arguments` tag)

**Test sequence:**

1. `docker-compose up -d` (no rebuild) → `curl http://localhost:9000/api/doc` → **HTTP 200**  
   (served from stale cached image built before compiler pass was reverted — stale image still had old compiled container)

2. `docker-compose build mdg && docker-compose up -d --force-recreate mdg` → fresh image from current code  
   → `curl http://localhost:9000/api/doc` → **HTTP 500**:
   ```
   Environment variable not found: "DEFAULT_URI".
   ```

3. Added `DEFAULT_URI: http://localhost:9000` to `docker-compose.yml` under `mdg.environment`, rebuilt and force-recreated  
   → `curl http://localhost:9000/api/doc` → **HTTP 200 with full Swagger UI HTML**

**Conclusion:** `/api/doc` works correctly with vanilla `Kernel.php` and no `controller.service_arguments` tag. The compiler pass is not required.

---

## Root Cause Correction — 2026-06-08

The theory documented in the "Root Cause" section above — missing `controller.service_arguments` tag — is **incorrect**. The actual resolution mechanism works differently.

### How controller resolution actually works

`ContainerControllerResolver::instantiateController()` does NOT use the controller Service Locator for resolution. It uses the **full `service_container`**:

```php
// vendor/symfony/http-kernel/Controller/ContainerControllerResolver.php
protected function instantiateController(string $class): object
{
    $class = ltrim($class, '\\');
    if ($this->container->has($class)) {   // full container, not service locator
        return $this->container->get($class);
    }
    // ...
    throw new \InvalidArgumentException(sprintf(
        'Controller "%s" does neither exist as service nor as class.', $class
    ));
}
```

`$this->container` is the full `service_container`. Any service marked `->public()` is accessible via `has()`/`get()` on the full container — no tag required.

Nelmio registers its controllers as `->public()` in its `services.php`. The `controller.service_arguments` tag governs whether a controller's **method arguments** are injected via the service locator (i.e. typed-hint service params). It has no effect on whether the controller itself can be resolved. `SwaggerUiController::__invoke()` takes only `Request` (handled by `RequestValueResolver`) and `string $area` (route param) — no service-typed arguments, so the tag is irrelevant in every sense.

### Actual root causes

**Original "controller not callable" error:**  
The Docker image was stale — built before `NelmioApiDocBundle` was registered in `bundles.php`. The compiled PHP container classes pre-dated Nelmio's service definitions. `$container->has('nelmio_api_doc.controller.swagger_ui')` returned `false` because the service did not exist in the compiled container. The compiler pass was added in the same commit that triggered a `docker-compose build`; the rebuild was the actual fix. The pass was incidental.

**HTTP 500 after fresh rebuild:**  
Symfony Flex's `routing.yaml` recipe sets `framework.router.default_uri: '%env(DEFAULT_URI)%'`. This is resolved lazily — only when Symfony generates a URL outside an HTTP request context. `SwaggerUiController` generates the absolute URL to the JSON spec endpoint on first render, triggering this code path. Without the env var, Symfony throws `Environment variable not found: "DEFAULT_URI"` → HTTP 500.

**Fix:** add `DEFAULT_URI` to `docker-compose.yml`:

```yaml
mdg:
  environment:
    DEFAULT_URI: http://localhost:9000
```

This value only affects CLI URL generation. Real HTTP requests use the actual `Request` context for absolute URL generation and ignore this env var.

### Why the compiler pass appeared to work

The pass was committed and tested against a stale Docker image. That image returned HTTP 200 from its pre-compiled container (which already had Nelmio services baked in from an earlier build). The pass was never actually exercised. When both the compiler pass removal AND the `DEFAULT_URI` fix were in place simultaneously, there was no single-variable test — it looked like the pass was the fix. The 2026-06-08 test isolated the variables: no pass, only `DEFAULT_URI`, HTTP 200.

### Note on the "Why This Bug Only Appears Without Flex" section

The FQCN vs service ID format distinction described there is accurate. The conclusion — "Service Locator is required for service ID format" — is wrong. Service ID format resolves via the full container (which includes all public services). FQCN format resolves via class instantiation. Both paths work for public services. The `controller.service_arguments` tag is never required for controller resolution regardless of format.
