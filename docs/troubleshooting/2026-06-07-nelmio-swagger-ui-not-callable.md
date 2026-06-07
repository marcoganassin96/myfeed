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

Flex users import Nelmio's FQCN-based route file and never touch the Service Locator. The `controller.service_arguments` tag is irrelevant to them. The tag gap in Nelmio's `services.yaml` is invisible.

Without Flex, routes are wired manually. Writing `_controller: nelmio_api_doc.controller.swagger_ui` (service ID format) triggers the Service Locator path — and the missing tag causes the 500.

**The Kernel compiler pass is a workaround for the absence of Flex**, not a fix for a general Nelmio bug. The underlying issue (Nelmio not tagging its controllers) only matters on the service ID resolution path, which Flex users never take.

### Alternative: migrate to Flex-based setup

The cleaner long-term fix is to remove the manual route wiring and the Kernel compiler pass entirely, and switch to Flex's approach:

1. Delete `config/routes/nelmio_api_doc.yaml` (the manual file with service ID routes)
2. Remove the `nelmio_api_doc:` entries from `config/routes.yaml`
3. Import Nelmio's own bundled route resource instead:
   ```yaml
   # config/routes.yaml
   when@dev:
       nelmio_api_doc:
           resource: '@NelmioApiDocBundle/config/routes.xml'
   when@local:
       nelmio_api_doc:
           resource: '@NelmioApiDocBundle/config/routes.xml'
   ```
4. Remove the `build()` override from `Kernel.php`

This uses FQCN-based routing, bypasses the Service Locator entirely, and eliminates the need for the compiler pass hack. Nelmio's bundled route file is the supported, maintained path.
