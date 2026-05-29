1. Install these dependencies:
- phpstan/phpstan: The core engine that parses the code to find bugs, type mismatches, and dead code.
- phpstan/extension-installer: A helper plugin that automatically detects and "wires up" the other extensions so you don't have to manually list them in your phpstan.neon configuration file.
- phpstan/phpstan-symfony: Teaches PHPStan about Symfony’s container. It helps PHPStan realize that $container->get(MyService::class) actually returns an instance of MyService.
- phpstan/phpstan-doctrine: Teaches PHPStan about your database entities. It can verify that your DQL queries are valid and that your entity relationships are typed correctly.

Note 1: Without the Symfony and Doctrine extensions, PHPStan would likely report hundreds of "False Positives."
For example, if you use a Doctrine Magic Method like $repo->findOneByName('x'), standard PHPStan would say:
“Method findOneByName() does not exist on EntityRepository.”

Note 2: Use --dev to install as a development dependency since PHPStan is only needed during development and testing, not in production.

```bash
composer require --dev phpstan/phpstan phpstan/extension-installer phpstan/phpstan-symfony phpstan/phpstan-doctrine
```

2. Create phpstan.neon configuration file (mdg/phpstan.neon):
This is the main configuration file of the PHPStan setup. It tells the engine:
- exactly where to look
- how strict to be
- and how to "see" inside the Symfony container
```neon
parameters:
    level: 0
    paths:
        - src
        - tests
    symfony:
        containerXmlPath: var/cache/local/App_KernelLocalDebugContainer.xml
```

- "level: 0": PHPStan has 10 levels of strictness (0-9). Level 0 performs basic checks like:
    - Missing classes or methods
    - Incorrect number of arguments passed to functions.
    - Basic syntax errors
- paths: This defines the scope of the analysis (src and tests directories).
- symfony.containerXmlPath: This points PHPStan to the compiled Symfony container XML file, allowing it to understand the services and their types. This is crucial for accurate analysis of Symfony applications.
