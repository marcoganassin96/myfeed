# Config Structure

## PHP vs Symfony config

Standard PHP constants belong in code. Symfony configuration lives in `config/packages/*.yaml` (or PHP/XML) — keeps logic and settings separate.

## Environment scoping

Two approaches to environment-specific config:

| Approach | When to use |
|---|---|
| `config/packages/dev/` subdirectory | Large, environment-specific bundle setups |
| `when@env:` key inside a single file | Quick, visible overrides of specific keys |

```yaml
# config/packages/monolog.yaml
monolog:
    handlers:
        main:
            level: error

when@dev:
    monolog:
        handlers:
            main:
                level: debug
```

## How values reach services

At container compilation Symfony merges all config files into a single "frozen" PHP class. Values are then:

- **Autowired** into service constructors via type-hints
- **Accessed** via `$this->getParameter('app.some_key')` or injected as constructor args using `bind` in `services.yaml`

```yaml
# config/services.yaml
parameters:
    app.some_key: 'value'

services:
    App\Service\MyService:
        arguments:
            $someKey: '%app.some_key%'
```
