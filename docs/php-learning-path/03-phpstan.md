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

3. Run first analysis with level 0:
```bash
vendor/bin/phpstan analyse
```
Errors:
a) vendor/bin/phpstan analyse
failes cause reached memory limit of 128M

b) vendor/bin/phpstan analyse --memory-limit 512M
1 error:
on line:
```php
    #[ORM\CustomIdGenerator(class: 'doctrine.uuid_generator')]
```
error:
    Cannot instantiate custom generator : array ('class' => 'doctrine.uuid_generator',)
explanation:
    PHPStan's Doctrine extension tries to instantiate the custom generator class to understand its behavior, but it fails because 'doctrine.uuid_generator' is a Symfony service container alias, not a real class name. To fix this, we need to change the annotation to reference the actual class.
solution:
    use Doctrine\ORM\Id\UuidGenerator real class in the annotation:
```php
    #[ORM\CustomIdGenerator(class: \Doctrine\ORM\Id\UuidGenerator::class)]
```


4. Run first analysis with level 2:
Found 38 errors:
a)
error:
    Call to an undefined method App\Cache\RedisClientInterface::method().
explanation:
    this error occurs for methods like ->method() and ->expects() called on variables typed as interfaces or classes (eg: RedisClientInterface. CacheService, ...) that are instantiated as mocks in tests. PHPStan sees the declared type but not the mock, so it thinks calls to ->method() and ->expects() are invalid since those methods exist for MockObject only, and not on that interface/class.
solution:
    use Intersection Types to tell PHPStan that the variable is both the interface and a MockObject.

eg:
    private RedisClientInterface $redis;
becomes:
    private RedisClientInterface&MockObject $redis; // Intersection Types


5. Run first analysis with level 4:
Found 28 errors:
a)
on line:
```php
class EventThreadMembership
{
    #[ORM\Id]
    #[ORM\Column(name: 'event_id', type: 'guid')]
    private string $eventId;
```
error:
    Property App\Entity\EventThreadMembership::$eventId is never written, only read.
explanation:
    The property is private, without any setter method. It worked only because Doctrine's ORM uses reflection to set the property value when hydrating the entity from the database. However, PHPStan doesn't know that and assumes it's a regular property that should be set somewhere in the code. Since it's never explicitly set, PHPStan reports it as "only read" which is a potential issue.
solution:
    create an explicit constructor that accepts the eventId and sets the property, so PHPStan can see that it's being written to:
```php
public function __construct(string $eventId)
{
    $this->eventId = $eventId;
}
```
    making constructor explicit have few benefits:
    1. It makes it clear to developers of which attributes are required to create an instance of a class, improving readability and maintainability.
    2. You don't necessary need to mock the Database/ORM just to give your entity an ID during a unit test.
