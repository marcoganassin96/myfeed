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

6. Run analysis with level 6:
Found 22 errors:
a)
on line:
```php
    public function get(string $key): ?array
```
error:
    Method/Property has no value type specified in iterable type array.
explanation:
    PHPStan requires knowing what's inside an array. A bare `array` type says nothing about its contents. PHPStan enforces that every array type must declare its value type (e.g. `array<string, mixed>`, `list<string>`).
    Native PHP type hints cannot carry generic syntax — `array<string, mixed>` is not valid PHP syntax. PHPDoc is the only way to express it.
solution:
    Add `@param`/`@return`/`@var` PHPDoc with the correct generic type. Choose the most specific type possible

7. Run analysis with level 7:
Found 17 errors:
a)
on lines:
```php
// CacheService.php
$this->redis->setex($key, $this->cacheTtl, json_encode($data));
```
error:
    Parameter #N of method/function expects string, string|false given.
explanation:
    `json_encode()` has the native return type `string|false`. It returns `false` on failure
    (circular references, non-UTF-8 byte sequences). PHPStan enforces every caller handles
    the `false` branch before passing the result to a function expecting `string`.
solution:
    Throw on error with `JSON_THROW_ON_ERROR` flag, to:
    - Raise an exception if encoding fails
    - Make the return type of `json_encode()` unambiguously `string` otherwise, satisfying PHPStan's requirement.
```php
$this->redis->setex($key, $this->cacheTtl, json_encode($data, JSON_THROW_ON_ERROR));
```

b)
on lines:
```php
    $body = json_decode($response->getContent(), true);
```
error:
    Parameter #1 of method/function expects string, string|false given.
explanation:
    `Response::getContent()` has the native return type `string|false`. It returns `false` if the content is empty. PHPStan enforces every caller handles the `false` branch before passing the result to a function expecting `string`.
solution:
    Check for `false` before calling `json_decode()`, and throw an exception if it is. This way, PHPStan can be sure that `json_decode()` only receives a `string` and not `false`.
```php
    $content = $response->getContent();
    if ($content === false) {
        throw new \RuntimeException('Response content is null');
    }
    $body = json_decode($content, true);
```

c)
on lines:
```php
interface RedisClientInterface
{
    //...
    /** @param array<int, string> $keys */
    public function del(array $keys): void;
}

class CacheService
{
    public function __construct(
        private RedisClientInterface $redis,
        ...
    ) {}

    //...

    public function delete(string ...$keys): void
    {
        //...
        $this->redis->del($keys);
    }
}```

error:
    Parameter #1 $keys of method App\Cache\RedisClientInterface::del() expects array<int, string>, array<int|string, string> given.
explanation:
    A variadic parameter `string ...$keys` collects arguments into an array with sequential integer keys — conceptually a `list<string>`. However, PHPStan infers intermediate array variables conservatively as `array<int|string, string>` (it allows for the possibility of string keys). The `del()` interface declares `array<int, string>` (only integer keys), so PHPStan rejects the assignment.
solution:
    1. Decide which is the proper type, to be applied to interface and all concrete implementations. Since I would allow deletion of both single and multiple keys, I will use variadic parameters, which are more ergonomic for callers. So the proper type is `string ...$keys`.
    2. Update the `del()` method signature in `RedisClientInterface` to also use variadic parameters as decided. Change is applied to the PredisAdapter concrete implementation as well.
    3. Inside `CacheService::delete()`, `$keys` is a plain array collected from the variadic args. To forward it to another variadic function, use the spread operator `...` — without it, the whole array would be passed as a single argument, causing a `TypeError` at runtime.
```php
interface RedisClientInterface
{
    //...
    public function del(string ...$keys): void;
}

class PredisAdapter implements RedisClientInterface
{
    //...
    public function del(string ...$keys): void
    {
        $this->client->del($keys); // Predis\Client::del() accepts string[]|string — passing the collected array is valid
    }
}

class CacheService
{
    //...
    public function delete(string ...$keys): void
    {
        if ($keys) {
            $this->redis->del(...$keys); // redis is an instance of RedisClientInterface. del method wants a variadic string parameter, so we need to spread $keys with ... to pass each element as a separate argument.
        }
    }
}
```

d)
on lines:
```php
// DeepDiveController.php
$body = json_decode($request->getContent(), true) ?? [];
// ...
$this->service->store($eventId, $body['chunks']);
```
error:
    Parameter #2 $chunks of method App\Service\DeepDiveService::store() expects list<string>, array<mixed, mixed> given.
explanation:
    `json_decode(..., true)` returns `mixed`. After offset access `$body['chunks']` and an `is_array()` guard, PHPStan still only knows the value is `array<mixed, mixed>` — it cannot infer the key/value types from runtime checks alone. The callee `store()` declares `@param list<string>`, which is a strict subtype, so PHPStan rejects the assignment.
solution:
    Coerce the value explicitly in code using `array_map` (with an explicit `: string` return type) + `array_values` (reindexes to 0-based). PHPStan infers `list<string>` directly from the expression — no `@var` annotation needed. This also sanitizes untrusted JSON input at the controller boundary.
```php
if (!isset($body['chunks']) || !is_array($body['chunks'])) {
    return new JsonResponse(['error' => 'chunks array required'], 400);
}
$chunks = array_values(array_map(fn(mixed $c): string => (string) $c, $body['chunks']));
$this->service->store($eventId, $chunks);
```
note:
    A `@var list<string> $chunks` annotation would also silence PHPStan, but it is a pure assertion — it does not transform the data and silently passes non-string elements through. The coercion approach is preferred at system boundaries (controllers, API handlers) where input cannot be trusted.
