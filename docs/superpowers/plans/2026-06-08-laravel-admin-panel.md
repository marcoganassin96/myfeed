# Laravel Admin Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold a Laravel 11 + Filament v3 admin panel service (`admin/`) that manages all newsletter domain entities through the MDG API.

**Architecture:** Custom Filament Pages (not Resources) with `InteractsWithTable` trait. MdgApiClient returns typed DTOs; Filament tables receive keyed arrays converted from DTOs. Modal CRUD via `->headerActions()` and `->recordActions()`. Eloquent used only for the `admins` table.

**Tech Stack:** PHP 8.4, Laravel 11, Filament v3, Laravel Breeze (blade), Laravel Http facade, PHPUnit, PHPStan level 8

**Prerequisite:** [MDG Endpoints plan](2026-06-08-laravel-admin-mdg-endpoints.md) completed and `docker-compose up -d` running.

**Validation after every code change:**
```bash
cd admin && php artisan test
cd admin && ./vendor/bin/phpstan analyse
```

**After every Docker rebuild, verify:**
```bash
docker-compose up -d --build admin
curl http://localhost:8080
```

---

### Task 1: Bootstrap Laravel app + Docker infrastructure

**Files:**
- Create: `admin/` (scaffold via composer)
- Create: `admin/Dockerfile`
- Create: `admin/docker/nginx.conf`
- Create: `admin/docker/www.conf`
- Create: `admin/docker/supervisord.conf`
- Create: `admin/docker/entrypoint.sh`
- Modify: `docker-compose.yml` (add admin service)

- [ ] **Step 1: Scaffold Laravel 11 via Docker composer image**

Run from the repo root (where `docker-compose.yml` lives):

```bash
docker run --rm -v "${PWD}:/workspace" -w /workspace composer:2 \
  create-project laravel/laravel:^11 admin --prefer-dist --no-interaction
```

On Windows PowerShell:
```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace composer:2 `
  create-project laravel/laravel:^11 admin --prefer-dist --no-interaction
```

Expected: `admin/` directory created with Laravel 11 scaffolding.

- [ ] **Step 2: Create `admin/Dockerfile`**

```dockerfile
FROM php:8.4-fpm-alpine

RUN apk add --no-cache nginx supervisor postgresql-dev \
    && docker-php-ext-install pdo pdo_pgsql opcache \
    && printf 'opcache.enable=1\nopcache.memory_consumption=128\nopcache.max_accelerated_files=10000\nopcache.validate_timestamps=0\n' \
       > /usr/local/etc/php/conf.d/opcache.ini

RUN rm -f /usr/local/etc/php-fpm.d/zz-docker.conf

WORKDIR /app

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

COPY composer.json composer.lock ./
RUN composer install --optimize-autoloader --no-interaction

COPY docker/www.conf /usr/local/etc/php-fpm.d/www.conf
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisord.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY . .

RUN mkdir -p storage/framework/{sessions,views,cache} storage/logs bootstrap/cache \
    && chown -R www-data:www-data storage bootstrap/cache

EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
```

- [ ] **Step 3: Create `admin/docker/nginx.conf`**

```nginx
worker_processes auto;
error_log /dev/stderr warn;
pid /tmp/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include      /etc/nginx/mime.types;
    default_type application/octet-stream;
    access_log   /dev/stdout;

    server {
        listen 80;
        root /app/public;

        client_max_body_size 10m;

        location = /health {
            access_log off;
            return 200 "ok";
            add_header Content-Type text/plain;
        }

        location / {
            try_files $uri /index.php$is_args$args;
        }

        location ~ ^/index\.php(/|$) {
            fastcgi_pass 127.0.0.1:9001;
            fastcgi_split_path_info ^(.+\.php)(/.*)$;
            include fastcgi_params;
            fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
            fastcgi_param DOCUMENT_ROOT $document_root;
            fastcgi_param PATH_INFO $fastcgi_path_info;
            internal;
        }

        location ~ \.php$ {
            return 404;
        }
    }
}
```

- [ ] **Step 4: Create `admin/docker/www.conf`**

```ini
[www]
user = www-data
group = www-data
listen = 127.0.0.1:9001
pm = dynamic
pm.max_children = 10
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 4
pm.max_requests = 500
clear_env = no
```

- [ ] **Step 5: Create `admin/docker/supervisord.conf`**

```ini
[supervisord]
nodaemon=true
user=root
logfile=/dev/null
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

[program:php-fpm]
command=/usr/local/sbin/php-fpm -F
autostart=true
autorestart=true
priority=1
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:nginx]
command=/usr/sbin/nginx -g "daemon off;"
autostart=true
autorestart=true
priority=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

- [ ] **Step 6: Create `admin/docker/entrypoint.sh`**

```sh
#!/bin/sh
set -e

# Publish Filament assets (CSS/JS to public/vendor/filament)
php artisan filament:assets --no-interaction

# Run Laravel migrations (admins table only)
php artisan migrate --force --no-interaction

# Seed default admin if not present
php artisan db:seed --class=AdminSeeder --force --no-interaction

# Cache config and routes for performance
php artisan config:cache
php artisan route:cache

exec /usr/bin/supervisord -c /etc/supervisord.conf
```

- [ ] **Step 7: Add admin service to `docker-compose.yml`**

Append to the `services:` section (before `volumes:`):

```yaml
  admin:
    build: ./admin
    ports:
      - "8080:80"
    environment:
      APP_ENV: local
      APP_KEY: base64:2fl+Mn1yYzuRlDSdRhSUvf9z7KqCv8SljH1TiPsxQAI=
      APP_DEBUG: "true"
      DB_CONNECTION: pgsql
      DB_HOST: postgres
      DB_PORT: 5432
      DB_DATABASE: newsletter
      DB_USERNAME: newsletter
      DB_PASSWORD: newsletter
      MDG_URL: http://mdg:9000
      SESSION_DRIVER: file
      CACHE_STORE: array
    depends_on:
      postgres:
        condition: service_healthy
      mdg:
        condition: service_started
```

Note: `APP_KEY` above is a placeholder. The real value must be generated once via `php artisan key:generate --show` and set permanently. For local dev, this placeholder value works.

- [ ] **Step 8: Build and verify**

```bash
docker-compose up -d --build admin
# Wait ~30s for first-time build
curl http://localhost:8080/health
```

Expected: `ok` (nginx health check responds)

- [ ] **Step 9: Commit**

```bash
git add admin/ docker-compose.yml
git commit -m "feat(admin): bootstrap Laravel 11 app with Docker infrastructure"
```

---

### Task 2: Breeze auth + admins table + Admin model + guard rename

**Files:**
- Run: `composer require laravel/breeze --dev && php artisan breeze:install blade` (inside container)
- Create: migration `xxxx_create_admins_table.php` (rename from users)
- Modify: `admin/app/Models/Admin.php` (rename User model)
- Modify: `admin/config/auth.php` (rename guard to `admin`, update model)
- Modify: `admin/app/Http/Middleware/Authenticate.php` (optional redirect path)
- Create: `admin/database/seeders/AdminSeeder.php`

- [ ] **Step 1: Install Breeze inside the container**

```bash
docker exec -it python-newsletter-admin-1 sh -c "composer require laravel/breeze --dev && php artisan breeze:install blade --no-interaction"
```

Expected: Breeze files scaffolded in `admin/` (controllers, views, migrations).

- [ ] **Step 2: Rename the users migration to admins**

Breeze creates `database/migrations/xxxx_create_users_table.php`. Rename it and change the table:

Open `admin/database/migrations/*_create_users_table.php` and replace the entire `up` method with:

```php
public function up(): void
{
    Schema::create('admins', function (Blueprint $table) {
        $table->id();
        $table->string('name');
        $table->string('email')->unique();
        $table->timestamp('email_verified_at')->nullable();
        $table->string('password');
        $table->rememberToken();
        $table->timestamps();
    });
}

public function down(): void
{
    Schema::dropIfExists('admins');
}
```

Also rename the file itself from `*_create_users_table.php` to `*_create_admins_table.php`.

- [ ] **Step 3: Create `admin/app/Models/Admin.php`**

Delete `admin/app/Models/User.php` and create:

```php
<?php
namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;

class Admin extends Authenticatable
{
    use HasFactory, Notifiable;

    protected $table = 'admins';

    protected $fillable = ['name', 'email', 'password'];

    /** @var list<string> */
    protected $hidden = ['password', 'remember_token'];

    /** @return array<string, string> */
    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'password'          => 'hashed',
        ];
    }
}
```

- [ ] **Step 4: Update `admin/config/auth.php`**

Change the guards and providers section to use the Admin model:

```php
'guards' => [
    'admin' => [          // renamed from 'web'
        'driver'   => 'session',
        'provider' => 'admins',
    ],
],

'providers' => [
    'admins' => [
        'driver' => 'eloquent',
        'model'  => App\Models\Admin::class,
    ],
],

'passwords' => [
    'admins' => [
        'provider' => 'admins',
        'table'    => 'password_reset_tokens',
        'expire'   => 60,
        'throttle' => 60,
    ],
],
```

- [ ] **Step 5: Update Breeze-generated auth references from `web` to `admin`**

Search for `'web'` in all files under `admin/app/Http/`:

```bash
grep -rn "'web'" admin/app/Http/
```

Replace guard name `'web'` with `'admin'` in any auth-related middleware or controller that uses it. Typically in:
- `admin/app/Http/Controllers/Auth/*.php` — any `Auth::guard('web')` call
- `admin/bootstrap/app.php` — if the `auth` middleware references a guard

Also update `admin/app/Http/Middleware/RedirectIfAuthenticated.php` if it references the `web` guard.

- [ ] **Step 6: Create `admin/database/seeders/AdminSeeder.php`**

```php
<?php
namespace Database\Seeders;

use App\Models\Admin;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class AdminSeeder extends Seeder
{
    /** Seeds one default admin for local dev; safe to run multiple times via firstOrCreate. */
    public function run(): void
    {
        Admin::firstOrCreate(
            ['email' => 'admin@newsletter.local'],
            [
                'name'     => 'Admin',
                'password' => Hash::make('password'),
            ]
        );
    }
}
```

- [ ] **Step 7: Rebuild Docker and verify auth**

```bash
docker-compose up -d --build admin
# Wait for container to start (entrypoint runs migrations + seeder)
curl http://localhost:8080/login
```

Expected: HTTP 200 — login page HTML returned.

- [ ] **Step 8: Commit**

```bash
git add admin/
git commit -m "feat(admin): add Breeze auth with admins table and Admin model"
```

---

### Task 3: MdgApiException + MdgApiClient + tests

**Files:**
- Create: `admin/app/Exceptions/MdgApiException.php`
- Create: `admin/app/Services/MdgApiClient.php`
- Create: `admin/tests/Feature/MdgApiClientTest.php`

- [ ] **Step 1: Create `admin/app/Exceptions/MdgApiException.php`**

```php
<?php
namespace App\Exceptions;

class MdgApiException extends \RuntimeException
{
    /** Wraps MDG HTTP errors with status code and response body for Filament notification display. */
    public function __construct(
        string $message,
        private int $statusCode = 0,
        private string $responseBody = '',
        ?\Throwable $previous = null,
    ) {
        parent::__construct($message, 0, $previous);
    }

    public function getStatusCode(): int { return $this->statusCode; }
    public function getResponseBody(): string { return $this->responseBody; }
}
```

- [ ] **Step 2: Create `admin/app/Services/MdgApiClient.php`**

```php
<?php
namespace App\Services;

use App\DTOs\InteractionDto;
use App\DTOs\NewsEventDto;
use App\DTOs\NewsletterDto;
use App\DTOs\SubscriptionDto;
use App\DTOs\TopicDto;
use App\Exceptions\MdgApiException;
use Illuminate\Support\Facades\Http;

class MdgApiClient
{
    /** Base URL injected from MDG_URL env via AppServiceProvider binding. */
    public function __construct(private string $baseUrl) {}

    // ── Topics ──────────────────────────────────────────────────────────────

    /** @return list<TopicDto> */
    public function getTopics(): array
    {
        $res = Http::baseUrl($this->baseUrl)->get('/master-data/topics');
        if ($res->failed()) {
            throw new MdgApiException('GET /master-data/topics failed', $res->status(), $res->body());
        }
        return array_map(fn (array $r) => TopicDto::fromArray($r), $res->json());
    }

    public function getTopic(string $id): TopicDto
    {
        $res = Http::baseUrl($this->baseUrl)->get("/master-data/topics/{$id}");
        if ($res->status() === 404) {
            throw new MdgApiException("Topic {$id} not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("GET /master-data/topics/{$id} failed", $res->status(), $res->body());
        }
        return TopicDto::fromArray($res->json());
    }

    public function createTopic(TopicDto $data): TopicDto
    {
        $res = Http::baseUrl($this->baseUrl)->post('/master-data/topics', $data->toArray());
        if ($res->failed()) {
            throw new MdgApiException('POST /master-data/topics failed', $res->status(), $res->body());
        }
        return TopicDto::fromArray($res->json());
    }

    public function updateTopic(string $id, TopicDto $data): TopicDto
    {
        $res = Http::baseUrl($this->baseUrl)->put("/master-data/topics/{$id}", $data->toArray());
        if ($res->status() === 404) {
            throw new MdgApiException("Topic {$id} not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("PUT /master-data/topics/{$id} failed", $res->status(), $res->body());
        }
        return TopicDto::fromArray($res->json());
    }

    public function deleteTopic(string $id): void
    {
        $res = Http::baseUrl($this->baseUrl)->delete("/master-data/topics/{$id}");
        if ($res->status() === 404) {
            throw new MdgApiException("Topic {$id} not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("DELETE /master-data/topics/{$id} failed", $res->status());
        }
    }

    // ── Newsletters ──────────────────────────────────────────────────────────

    /** @return list<NewsletterDto> */
    public function getNewsletters(): array
    {
        $res = Http::baseUrl($this->baseUrl)->withHeader('X-User-ID', 'admin')
            ->get('/master-data/newsletters');
        if ($res->failed()) {
            throw new MdgApiException('GET /master-data/newsletters failed', $res->status(), $res->body());
        }
        return array_map(fn (array $r) => NewsletterDto::fromArray($r), $res->json());
    }

    public function getNewsletter(string $id): NewsletterDto
    {
        $res = Http::baseUrl($this->baseUrl)->withHeader('X-User-ID', 'admin')
            ->get("/master-data/newsletters/{$id}");
        if ($res->status() === 404) {
            throw new MdgApiException("Newsletter {$id} not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("GET /master-data/newsletters/{$id} failed", $res->status(), $res->body());
        }
        return NewsletterDto::fromArray($res->json());
    }

    public function createNewsletter(NewsletterDto $data): NewsletterDto
    {
        $res = Http::baseUrl($this->baseUrl)->post('/master-data/newsletters', $data->toArray());
        if ($res->failed()) {
            throw new MdgApiException('POST /master-data/newsletters failed', $res->status(), $res->body());
        }
        return NewsletterDto::fromArray($res->json());
    }

    public function updateNewsletter(string $id, NewsletterDto $data): NewsletterDto
    {
        $res = Http::baseUrl($this->baseUrl)->put("/master-data/newsletters/{$id}", $data->toUpdateArray());
        if ($res->status() === 404) {
            throw new MdgApiException("Newsletter {$id} not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("PUT /master-data/newsletters/{$id} failed", $res->status(), $res->body());
        }
        return NewsletterDto::fromArray($res->json());
    }

    public function deleteNewsletter(string $id): void
    {
        $res = Http::baseUrl($this->baseUrl)->delete("/master-data/newsletters/{$id}");
        if ($res->status() === 404) {
            throw new MdgApiException("Newsletter {$id} not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("DELETE /master-data/newsletters/{$id} failed", $res->status());
        }
    }

    // ── NewsEvents ───────────────────────────────────────────────────────────

    /** @return list<NewsEventDto> */
    public function getNewsEvents(): array
    {
        $res = Http::baseUrl($this->baseUrl)->get('/master-data/news-events');
        if ($res->failed()) {
            throw new MdgApiException('GET /master-data/news-events failed', $res->status(), $res->body());
        }
        return array_map(fn (array $r) => NewsEventDto::fromArray($r), $res->json());
    }

    public function getNewsEvent(string $id): NewsEventDto
    {
        $res = Http::baseUrl($this->baseUrl)->get("/master-data/news-events/{$id}");
        if ($res->status() === 404) {
            throw new MdgApiException("NewsEvent {$id} not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("GET /master-data/news-events/{$id} failed", $res->status(), $res->body());
        }
        return NewsEventDto::fromArray($res->json());
    }

    public function createNewsEvent(NewsEventDto $data): NewsEventDto
    {
        $res = Http::baseUrl($this->baseUrl)->post('/master-data/news-events', $data->toArray());
        if ($res->failed()) {
            throw new MdgApiException('POST /master-data/news-events failed', $res->status(), $res->body());
        }
        return NewsEventDto::fromArray($res->json());
    }

    public function updateNewsEvent(string $id, NewsEventDto $data): NewsEventDto
    {
        $res = Http::baseUrl($this->baseUrl)->put("/master-data/news-events/{$id}", $data->toArray());
        if ($res->status() === 404) {
            throw new MdgApiException("NewsEvent {$id} not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("PUT /master-data/news-events/{$id} failed", $res->status(), $res->body());
        }
        return NewsEventDto::fromArray($res->json());
    }

    public function deleteNewsEvent(string $id): void
    {
        $res = Http::baseUrl($this->baseUrl)->delete("/master-data/news-events/{$id}");
        if ($res->status() === 404) {
            throw new MdgApiException("NewsEvent {$id} not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("DELETE /master-data/news-events/{$id} failed", $res->status());
        }
    }

    // ── Subscriptions ────────────────────────────────────────────────────────

    /** @return list<SubscriptionDto> */
    public function getSubscriptions(): array
    {
        $res = Http::baseUrl($this->baseUrl)->get('/master-data/admin/subscriptions');
        if ($res->failed()) {
            throw new MdgApiException('GET /master-data/admin/subscriptions failed', $res->status(), $res->body());
        }
        return array_map(fn (array $r) => SubscriptionDto::fromArray($r), $res->json());
    }

    public function deleteSubscription(string $userId, string $topicId): void
    {
        $res = Http::baseUrl($this->baseUrl)
            ->delete("/master-data/admin/subscriptions/{$userId}/{$topicId}");
        if ($res->status() === 404) {
            throw new MdgApiException("Subscription not found", 404);
        }
        if ($res->failed()) {
            throw new MdgApiException("DELETE admin/subscriptions failed", $res->status());
        }
    }

    // ── Interactions ─────────────────────────────────────────────────────────

    /** @return list<InteractionDto> */
    public function getInteractions(): array
    {
        $res = Http::baseUrl($this->baseUrl)->get('/master-data/interactions');
        if ($res->failed()) {
            throw new MdgApiException('GET /master-data/interactions failed', $res->status(), $res->body());
        }
        return array_map(fn (array $r) => InteractionDto::fromArray($r), $res->json());
    }
}
```

- [ ] **Step 3: Register MdgApiClient in `admin/app/Providers/AppServiceProvider.php`**

Replace the `register` method:

```php
public function register(): void
{
    $this->app->singleton(\App\Services\MdgApiClient::class, function (): \App\Services\MdgApiClient {
        return new \App\Services\MdgApiClient(config('services.mdg.url', 'http://mdg:9000'));
    });
}
```

Add to `admin/config/services.php`:

```php
'mdg' => [
    'url' => env('MDG_URL', 'http://mdg:9000'),
],
```

- [ ] **Step 4: Create `admin/tests/Feature/MdgApiClientTest.php`**

```php
<?php
namespace Tests\Feature;

use App\DTOs\TopicDto;
use App\Exceptions\MdgApiException;
use App\Services\MdgApiClient;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class MdgApiClientTest extends TestCase
{
    private MdgApiClient $client;

    protected function setUp(): void
    {
        parent::setUp();
        $this->client = new MdgApiClient('http://mdg-test:9000');
    }

    public function testGetTopicsReturnsDtoList(): void
    {
        Http::fake([
            '*/master-data/topics' => Http::response(
                [['topic_id' => 'tp-1', 'name' => 'Tech', 'description' => null]],
                200
            ),
        ]);

        $topics = $this->client->getTopics();

        $this->assertCount(1, $topics);
        $this->assertInstanceOf(TopicDto::class, $topics[0]);
        $this->assertSame('tp-1', $topics[0]->id);
        $this->assertSame('Tech', $topics[0]->name);
    }

    public function testGetTopicsThrowsOnHttpError(): void
    {
        Http::fake([
            '*/master-data/topics' => Http::response([], 500),
        ]);

        $this->expectException(MdgApiException::class);
        $this->client->getTopics();
    }

    public function testCreateTopicReturnsDtoWithNewId(): void
    {
        Http::fake([
            '*/master-data/topics' => Http::response(
                ['topic_id' => 'tp-new', 'name' => 'Sport', 'description' => null],
                201
            ),
        ]);

        $result = $this->client->createTopic(new TopicDto('', 'Sport', null));

        $this->assertSame('tp-new', $result->id);
        $this->assertSame('Sport', $result->name);
    }

    public function testDeleteTopicThrowsOn404(): void
    {
        Http::fake([
            '*/master-data/topics/*' => Http::response([], 404),
        ]);

        $this->expectException(MdgApiException::class);
        $this->client->deleteTopic('nope');
    }
}
```

- [ ] **Step 5: Run tests inside Docker**

```bash
docker exec python-newsletter-admin-1 php artisan test tests/Feature/MdgApiClientTest.php
```

Expected: 4 tests, 4 assertions, PASS

- [ ] **Step 6: PHPStan**

```bash
docker exec python-newsletter-admin-1 ./vendor/bin/phpstan analyse
```

- [ ] **Step 7: Commit**

```bash
git add admin/app/Exceptions/MdgApiException.php \
        admin/app/Services/MdgApiClient.php \
        admin/app/Providers/AppServiceProvider.php \
        admin/config/services.php \
        admin/tests/Feature/MdgApiClientTest.php
git commit -m "feat(admin): add MdgApiClient with typed DTOs and Http::fake tests"
```

---

### Task 4: DTOs — 5 readonly classes

**Files:**
- Create: `admin/app/DTOs/TopicDto.php`
- Create: `admin/app/DTOs/NewsletterDto.php`
- Create: `admin/app/DTOs/NewsEventDto.php`
- Create: `admin/app/DTOs/SubscriptionDto.php`
- Create: `admin/app/DTOs/InteractionDto.php`

- [ ] **Step 1: Create `admin/app/DTOs/TopicDto.php`**

```php
<?php
namespace App\DTOs;

readonly class TopicDto
{
    public function __construct(
        public string $id,
        public string $name,
        public ?string $description,
    ) {}

    /** @param array<string, mixed> $data */
    public static function fromArray(array $data): self
    {
        return new self(
            id:          (string) ($data['topic_id'] ?? $data['id'] ?? ''),
            name:        (string) $data['name'],
            description: isset($data['description']) ? (string) $data['description'] : null,
        );
    }

    /** @return array<string, mixed> */
    public function toArray(): array
    {
        return ['name' => $this->name, 'description' => $this->description];
    }
}
```

- [ ] **Step 2: Create `admin/app/DTOs/NewsletterDto.php`**

```php
<?php
namespace App\DTOs;

readonly class NewsletterDto
{
    public function __construct(
        public string $id,
        public string $topicId,
        public string $date,
        public string $title,
        public string $narrative,
    ) {}

    /** @param array<string, mixed> $data */
    public static function fromArray(array $data): self
    {
        return new self(
            id:        (string) ($data['newsletter_id'] ?? $data['id'] ?? ''),
            topicId:   (string) $data['topic_id'],
            date:      (string) $data['date'],
            title:     (string) $data['title'],
            narrative: (string) $data['narrative'],
        );
    }

    /** Full payload for POST (create). */
    /** @return array<string, mixed> */
    public function toArray(): array
    {
        return [
            'topic_id'  => $this->topicId,
            'date'      => $this->date,
            'title'     => $this->title,
            'narrative' => $this->narrative,
        ];
    }

    /** Partial payload for PUT (update title + narrative only). */
    /** @return array<string, mixed> */
    public function toUpdateArray(): array
    {
        return ['title' => $this->title, 'narrative' => $this->narrative];
    }
}
```

- [ ] **Step 3: Create `admin/app/DTOs/NewsEventDto.php`**

```php
<?php
namespace App\DTOs;

readonly class NewsEventDto
{
    public function __construct(
        public string $id,
        public string $headline,
        public string $summary,
        public string $date,
        public ?string $sourceUrl,
    ) {}

    /** @param array<string, mixed> $data */
    public static function fromArray(array $data): self
    {
        return new self(
            id:        (string) ($data['event_id'] ?? $data['id'] ?? ''),
            headline:  (string) $data['headline'],
            summary:   (string) $data['summary'],
            date:      (string) $data['date'],
            sourceUrl: isset($data['source_url']) ? (string) $data['source_url'] : null,
        );
    }

    /** @return array<string, mixed> */
    public function toArray(): array
    {
        return [
            'headline'   => $this->headline,
            'summary'    => $this->summary,
            'date'       => $this->date,
            'source_url' => $this->sourceUrl,
        ];
    }
}
```

- [ ] **Step 4: Create `admin/app/DTOs/SubscriptionDto.php`**

```php
<?php
namespace App\DTOs;

readonly class SubscriptionDto
{
    public function __construct(
        public string $userId,
        public string $topicId,
        public string $topicName,
        public string $subscribedAt,
    ) {}

    /** @param array<string, mixed> $data */
    public static function fromArray(array $data): self
    {
        return new self(
            userId:      (string) $data['user_id'],
            topicId:     (string) $data['topic_id'],
            topicName:   (string) ($data['topic_name'] ?? ''),
            subscribedAt:(string) $data['subscribed_at'],
        );
    }

    /** @return array<string, mixed> */
    public function toArray(): array
    {
        return [
            'user_id'       => $this->userId,
            'topic_id'      => $this->topicId,
            'topic_name'    => $this->topicName,
            'subscribed_at' => $this->subscribedAt,
        ];
    }
}
```

- [ ] **Step 5: Create `admin/app/DTOs/InteractionDto.php`**

```php
<?php
namespace App\DTOs;

readonly class InteractionDto
{
    public function __construct(
        public string $id,
        public string $userId,
        public string $eventId,
        public string $type,
        public string $createdAt,
    ) {}

    /** @param array<string, mixed> $data */
    public static function fromArray(array $data): self
    {
        return new self(
            id:        (string) ($data['interaction_id'] ?? ''),
            userId:    (string) $data['user_id'],
            eventId:   (string) $data['event_id'],
            type:      (string) $data['type'],
            createdAt: (string) $data['created_at'],
        );
    }

    /** @return array<string, mixed> */
    public function toArray(): array
    {
        return [
            'interaction_id' => $this->id,
            'user_id'        => $this->userId,
            'event_id'       => $this->eventId,
            'type'           => $this->type,
            'created_at'     => $this->createdAt,
        ];
    }
}
```

- [ ] **Step 6: PHPStan + commit**

```bash
docker exec python-newsletter-admin-1 ./vendor/bin/phpstan analyse
git add admin/app/DTOs/
git commit -m "feat(admin): add typed DTOs for all domain entities"
```

---

### Task 5: Filament v3 install + panel config + AdminSeeder verification

**Files:**
- Run: `composer require filament/filament:"^3.2"` (inside container)
- Run: `php artisan filament:install --panels`
- Modify: `admin/app/Providers/Filament/AdminPanelProvider.php`
- Verify: AdminSeeder runs cleanly

- [ ] **Step 1: Install Filament v3 inside container**

```bash
docker exec -it python-newsletter-admin-1 composer require filament/filament:"^3.2"
docker exec python-newsletter-admin-1 php artisan filament:install --panels --no-interaction
```

This creates `admin/app/Providers/Filament/AdminPanelProvider.php`.

- [ ] **Step 2: Configure the panel in `AdminPanelProvider.php`**

Replace the generated file with:

```php
<?php
namespace App\Providers\Filament;

use Filament\Http\Middleware\Authenticate;
use Filament\Http\Middleware\DisableBladeIconComponents;
use Filament\Http\Middleware\DispatchServingFilamentEvent;
use Filament\Pages;
use Filament\Panel;
use Filament\PanelProvider;
use Filament\Support\Colors\Color;
use Illuminate\Cookie\Middleware\AddQueuedCookiesToResponse;
use Illuminate\Cookie\Middleware\EncryptCookies;
use Illuminate\Foundation\Http\Middleware\VerifyCsrfToken;
use Illuminate\Routing\Middleware\SubstituteBindings;
use Illuminate\Session\Middleware\AuthenticateSession;
use Illuminate\Session\Middleware\StartSession;
use Illuminate\View\Middleware\ShareErrorsFromSession;

class AdminPanelProvider extends PanelProvider
{
    /** Configures the Filament admin panel: path, colors, auth guard, and page discovery. */
    public function panel(Panel $panel): Panel
    {
        return $panel
            ->default()
            ->id('admin')
            ->path('admin')
            ->login()
            ->colors(['primary' => Color::Indigo])
            ->discoverPages(in: app_path('Filament/Pages'), for: 'App\\Filament\\Pages')
            ->pages([Pages\Dashboard::class])
            ->authGuard('admin')
            ->middleware([
                EncryptCookies::class,
                AddQueuedCookiesToResponse::class,
                StartSession::class,
                AuthenticateSession::class,
                ShareErrorsFromSession::class,
                VerifyCsrfToken::class,
                SubstituteBindings::class,
                DisableBladeIconComponents::class,
                DispatchServingFilamentEvent::class,
            ])
            ->authMiddleware([Authenticate::class]);
    }
}
```

- [ ] **Step 3: Create the Pages directory**

```bash
mkdir -p admin/app/Filament/Pages
```

- [ ] **Step 4: Rebuild and verify panel loads**

```bash
docker-compose up -d --build admin
curl -I http://localhost:8080/admin/login
```

Expected: HTTP 200

- [ ] **Step 5: Verify AdminSeeder ran — check admin login**

Open `http://localhost:8080/admin/login` in a browser.
Login with: `admin@newsletter.local` / `password`
Expected: redirect to `/admin` dashboard.

- [ ] **Step 6: Commit**

```bash
git add admin/
git commit -m "feat(admin): install Filament v3 panel with admin guard and page discovery"
```

---

### Task 6: ManageTopics Filament page

**Files:**
- Create: `admin/app/Filament/Pages/ManageTopics.php`
- Create: `admin/resources/views/filament/pages/manage-topics.blade.php`

- [ ] **Step 1: Create view `admin/resources/views/filament/pages/manage-topics.blade.php`**

```blade
<x-filament-panels::page>
    {{ $this->table }}
</x-filament-panels::page>
```

- [ ] **Step 2: Create `admin/app/Filament/Pages/ManageTopics.php`**

```php
<?php
namespace App\Filament\Pages;

use App\DTOs\TopicDto;
use App\Exceptions\MdgApiException;
use App\Services\MdgApiClient;
use Filament\Actions\Action;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Concerns\InteractsWithTable;
use Filament\Tables\Contracts\HasTable;
use Filament\Tables\Table;

class ManageTopics extends Page implements HasTable
{
    use InteractsWithTable;

    protected static ?string $navigationIcon  = 'heroicon-o-tag';
    protected static ?string $navigationGroup = 'Content';
    protected static string  $view            = 'filament.pages.manage-topics';
    protected static ?string $title           = 'Topics';
    protected static ?int    $navigationSort  = 1;

    /** Keyed array: topic_id → array record; Filament uses key as record identifier. */
    public function table(Table $table): Table
    {
        $client = app(MdgApiClient::class);

        return $table
            ->records(fn (): array => collect($client->getTopics())
                ->keyBy('id')
                ->map(fn (TopicDto $t): array => [
                    'id'          => $t->id,
                    'name'        => $t->name,
                    'description' => $t->description ?? '',
                ])
                ->toArray()
            )
            ->columns([
                TextColumn::make('id')->label('ID')->toggleable(isToggledHiddenByDefault: true),
                TextColumn::make('name')->searchable(),
                TextColumn::make('description')->limit(80)->placeholder('—'),
            ])
            ->headerActions([
                Action::make('create')
                    ->label('New Topic')
                    ->modalHeading('Create Topic')
                    ->schema([
                        TextInput::make('name')->required()->maxLength(100),
                        Textarea::make('description')->rows(2),
                    ])
                    ->action(function (array $data) use ($client): void {
                        try {
                            $client->createTopic(new TopicDto('', $data['name'], $data['description'] ?? null));
                            Notification::make()->title('Topic created')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
            ])
            ->recordActions([
                Action::make('edit')
                    ->icon('heroicon-m-pencil-square')
                    ->fillForm(fn (array $record): array => $record)
                    ->schema([
                        TextInput::make('name')->required()->maxLength(100),
                        Textarea::make('description')->rows(2),
                    ])
                    ->action(function (array $record, array $data) use ($client): void {
                        try {
                            $client->updateTopic(
                                $record['id'],
                                new TopicDto($record['id'], $data['name'], $data['description'] ?? null)
                            );
                            Notification::make()->title('Topic updated')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
                Action::make('delete')
                    ->icon('heroicon-m-trash')
                    ->color('danger')
                    ->requiresConfirmation()
                    ->action(function (array $record) use ($client): void {
                        try {
                            $client->deleteTopic($record['id']);
                            Notification::make()->title('Topic deleted')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
            ]);
    }
}
```

- [ ] **Step 3: Rebuild and verify in browser**

```bash
docker-compose up -d --build admin
```

Open `http://localhost:8080/admin` → login → navigate to "Topics" in sidebar.
Expected: table lists topics from MDG, Create/Edit/Delete buttons work.

- [ ] **Step 4: Manual curl to verify the underlying API is hit**

```bash
# Create via browser form, then verify via curl
curl http://localhost:9000/master-data/topics
```

- [ ] **Step 5: Commit**

```bash
git add admin/app/Filament/Pages/ManageTopics.php \
        admin/resources/views/filament/pages/manage-topics.blade.php
git commit -m "feat(admin): add Filament ManageTopics page with modal CRUD"
```

---

### Task 7: ManageNewsletters Filament page

**Files:**
- Create: `admin/app/Filament/Pages/ManageNewsletters.php`
- Create: `admin/resources/views/filament/pages/manage-newsletters.blade.php`

- [ ] **Step 1: Create view `admin/resources/views/filament/pages/manage-newsletters.blade.php`**

```blade
<x-filament-panels::page>
    {{ $this->table }}
</x-filament-panels::page>
```

- [ ] **Step 2: Create `admin/app/Filament/Pages/ManageNewsletters.php`**

```php
<?php
namespace App\Filament\Pages;

use App\DTOs\NewsletterDto;
use App\Exceptions\MdgApiException;
use App\Services\MdgApiClient;
use Filament\Actions\Action;
use Filament\Forms\Components\DatePicker;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Concerns\InteractsWithTable;
use Filament\Tables\Contracts\HasTable;
use Filament\Tables\Table;

class ManageNewsletters extends Page implements HasTable
{
    use InteractsWithTable;

    protected static ?string $navigationIcon  = 'heroicon-o-newspaper';
    protected static ?string $navigationGroup = 'Content';
    protected static string  $view            = 'filament.pages.manage-newsletters';
    protected static ?string $title           = 'Newsletters';
    protected static ?int    $navigationSort  = 2;

    public function table(Table $table): Table
    {
        $client = app(MdgApiClient::class);

        return $table
            ->records(fn (): array => collect($client->getNewsletters())
                ->keyBy('id')
                ->map(fn (NewsletterDto $n): array => [
                    'id'        => $n->id,
                    'topic_id'  => $n->topicId,
                    'date'      => $n->date,
                    'title'     => $n->title,
                    'narrative' => $n->narrative,
                ])
                ->toArray()
            )
            ->columns([
                TextColumn::make('id')->label('ID')->toggleable(isToggledHiddenByDefault: true),
                TextColumn::make('date')->sortable(),
                TextColumn::make('title')->searchable()->limit(60),
                TextColumn::make('topic_id')->label('Topic ID')->toggleable(isToggledHiddenByDefault: true),
            ])
            ->headerActions([
                Action::make('create')
                    ->label('New Newsletter')
                    ->modalHeading('Create Newsletter')
                    ->schema([
                        TextInput::make('topic_id')->label('Topic ID')->required()
                            ->helperText('UUID of the topic from the Topics page'),
                        DatePicker::make('date')->required(),
                        TextInput::make('title')->required()->maxLength(200),
                        Textarea::make('narrative')->required()->rows(4),
                    ])
                    ->action(function (array $data) use ($client): void {
                        try {
                            $client->createNewsletter(new NewsletterDto(
                                '', $data['topic_id'], $data['date'], $data['title'], $data['narrative']
                            ));
                            Notification::make()->title('Newsletter created')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
            ])
            ->recordActions([
                Action::make('edit')
                    ->icon('heroicon-m-pencil-square')
                    ->fillForm(fn (array $record): array => $record)
                    ->schema([
                        TextInput::make('title')->required()->maxLength(200),
                        Textarea::make('narrative')->required()->rows(4),
                    ])
                    ->action(function (array $record, array $data) use ($client): void {
                        try {
                            $client->updateNewsletter(
                                $record['id'],
                                new NewsletterDto($record['id'], $record['topic_id'],
                                    $record['date'], $data['title'], $data['narrative'])
                            );
                            Notification::make()->title('Newsletter updated')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
                Action::make('delete')
                    ->icon('heroicon-m-trash')
                    ->color('danger')
                    ->requiresConfirmation()
                    ->action(function (array $record) use ($client): void {
                        try {
                            $client->deleteNewsletter($record['id']);
                            Notification::make()->title('Newsletter deleted')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
            ]);
    }
}
```

- [ ] **Step 3: Rebuild + browser verify**

```bash
docker-compose up -d --build admin
```

Open `http://localhost:8080/admin` → "Newsletters" in sidebar.
Expected: table lists newsletters from MDG fixture data.

- [ ] **Step 4: Commit**

```bash
git add admin/app/Filament/Pages/ManageNewsletters.php \
        admin/resources/views/filament/pages/manage-newsletters.blade.php
git commit -m "feat(admin): add Filament ManageNewsletters page with modal CRUD"
```

---

### Task 8: ManageNewsEvents Filament page

**Files:**
- Create: `admin/app/Filament/Pages/ManageNewsEvents.php`
- Create: `admin/resources/views/filament/pages/manage-news-events.blade.php`

- [ ] **Step 1: Create view `admin/resources/views/filament/pages/manage-news-events.blade.php`**

```blade
<x-filament-panels::page>
    {{ $this->table }}
</x-filament-panels::page>
```

- [ ] **Step 2: Create `admin/app/Filament/Pages/ManageNewsEvents.php`**

```php
<?php
namespace App\Filament\Pages;

use App\DTOs\NewsEventDto;
use App\Exceptions\MdgApiException;
use App\Services\MdgApiClient;
use Filament\Actions\Action;
use Filament\Forms\Components\DatePicker;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Concerns\InteractsWithTable;
use Filament\Tables\Contracts\HasTable;
use Filament\Tables\Table;

class ManageNewsEvents extends Page implements HasTable
{
    use InteractsWithTable;

    protected static ?string $navigationIcon  = 'heroicon-o-bolt';
    protected static ?string $navigationGroup = 'Content';
    protected static string  $view            = 'filament.pages.manage-news-events';
    protected static ?string $title           = 'News Events';
    protected static ?int    $navigationSort  = 3;

    public function table(Table $table): Table
    {
        $client = app(MdgApiClient::class);

        return $table
            ->records(fn (): array => collect($client->getNewsEvents())
                ->keyBy('id')
                ->map(fn (NewsEventDto $e): array => [
                    'id'         => $e->id,
                    'headline'   => $e->headline,
                    'summary'    => $e->summary,
                    'date'       => $e->date,
                    'source_url' => $e->sourceUrl ?? '',
                ])
                ->toArray()
            )
            ->columns([
                TextColumn::make('id')->label('ID')->toggleable(isToggledHiddenByDefault: true),
                TextColumn::make('date')->sortable(),
                TextColumn::make('headline')->searchable()->limit(80),
                TextColumn::make('source_url')->label('Source')->limit(50)->placeholder('—'),
            ])
            ->headerActions([
                Action::make('create')
                    ->label('New Event')
                    ->modalHeading('Create News Event')
                    ->schema([
                        TextInput::make('headline')->required()->maxLength(300),
                        Textarea::make('summary')->required()->rows(3),
                        DatePicker::make('date')->required(),
                        TextInput::make('source_url')->label('Source URL')->url()->nullable(),
                    ])
                    ->action(function (array $data) use ($client): void {
                        try {
                            $client->createNewsEvent(new NewsEventDto(
                                '', $data['headline'], $data['summary'],
                                $data['date'], $data['source_url'] ?? null
                            ));
                            Notification::make()->title('Event created')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
            ])
            ->recordActions([
                Action::make('edit')
                    ->icon('heroicon-m-pencil-square')
                    ->fillForm(fn (array $record): array => $record)
                    ->schema([
                        TextInput::make('headline')->required()->maxLength(300),
                        Textarea::make('summary')->required()->rows(3),
                        DatePicker::make('date')->required(),
                        TextInput::make('source_url')->label('Source URL')->url()->nullable(),
                    ])
                    ->action(function (array $record, array $data) use ($client): void {
                        try {
                            $client->updateNewsEvent(
                                $record['id'],
                                new NewsEventDto(
                                    $record['id'], $data['headline'], $data['summary'],
                                    $data['date'], $data['source_url'] ?? null
                                )
                            );
                            Notification::make()->title('Event updated')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
                Action::make('delete')
                    ->icon('heroicon-m-trash')
                    ->color('danger')
                    ->requiresConfirmation()
                    ->action(function (array $record) use ($client): void {
                        try {
                            $client->deleteNewsEvent($record['id']);
                            Notification::make()->title('Event deleted')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
            ]);
    }
}
```

- [ ] **Step 3: Rebuild + commit**

```bash
docker-compose up -d --build admin
git add admin/app/Filament/Pages/ManageNewsEvents.php \
        admin/resources/views/filament/pages/manage-news-events.blade.php
git commit -m "feat(admin): add Filament ManageNewsEvents page with modal CRUD"
```

---

### Task 9: ManageSubscriptions Filament page (list + admin delete)

**Files:**
- Create: `admin/app/Filament/Pages/ManageSubscriptions.php`
- Create: `admin/resources/views/filament/pages/manage-subscriptions.blade.php`

- [ ] **Step 1: Create view `admin/resources/views/filament/pages/manage-subscriptions.blade.php`**

```blade
<x-filament-panels::page>
    {{ $this->table }}
</x-filament-panels::page>
```

- [ ] **Step 2: Create `admin/app/Filament/Pages/ManageSubscriptions.php`**

```php
<?php
namespace App\Filament\Pages;

use App\DTOs\SubscriptionDto;
use App\Exceptions\MdgApiException;
use App\Services\MdgApiClient;
use Filament\Actions\Action;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Concerns\InteractsWithTable;
use Filament\Tables\Contracts\HasTable;
use Filament\Tables\Table;

class ManageSubscriptions extends Page implements HasTable
{
    use InteractsWithTable;

    protected static ?string $navigationIcon  = 'heroicon-o-users';
    protected static ?string $navigationGroup = 'Users';
    protected static string  $view            = 'filament.pages.manage-subscriptions';
    protected static ?string $title           = 'Subscriptions';
    protected static ?int    $navigationSort  = 1;

    public function table(Table $table): Table
    {
        $client = app(MdgApiClient::class);

        return $table
            ->records(fn (): array => collect($client->getSubscriptions())
                ->map(fn (SubscriptionDto $s): array => [
                    'key'          => $s->userId . '::' . $s->topicId,
                    'user_id'      => $s->userId,
                    'topic_id'     => $s->topicId,
                    'topic_name'   => $s->topicName,
                    'subscribed_at'=> $s->subscribedAt,
                ])
                ->keyBy('key')
                ->toArray()
            )
            ->columns([
                TextColumn::make('user_id')->label('User ID')->searchable(),
                TextColumn::make('topic_name')->label('Topic')->searchable(),
                TextColumn::make('topic_id')->label('Topic ID')->toggleable(isToggledHiddenByDefault: true),
                TextColumn::make('subscribed_at')->label('Subscribed')->sortable(),
            ])
            ->recordActions([
                Action::make('delete')
                    ->icon('heroicon-m-trash')
                    ->color('danger')
                    ->requiresConfirmation()
                    ->modalDescription('This will unsubscribe the user from this topic.')
                    ->action(function (array $record) use ($client): void {
                        try {
                            $client->deleteSubscription($record['user_id'], $record['topic_id']);
                            Notification::make()->title('Subscription deleted')->success()->send();
                        } catch (MdgApiException $e) {
                            Notification::make()->title('Error: ' . $e->getMessage())->danger()->send();
                        }
                    }),
            ]);
    }
}
```

- [ ] **Step 3: Rebuild + commit**

```bash
docker-compose up -d --build admin
git add admin/app/Filament/Pages/ManageSubscriptions.php \
        admin/resources/views/filament/pages/manage-subscriptions.blade.php
git commit -m "feat(admin): add Filament ManageSubscriptions page (list + admin delete)"
```

---

### Task 10: ManageInteractions Filament page (read-only)

**Files:**
- Create: `admin/app/Filament/Pages/ManageInteractions.php`
- Create: `admin/resources/views/filament/pages/manage-interactions.blade.php`

- [ ] **Step 1: Create view `admin/resources/views/filament/pages/manage-interactions.blade.php`**

```blade
<x-filament-panels::page>
    {{ $this->table }}
</x-filament-panels::page>
```

- [ ] **Step 2: Create `admin/app/Filament/Pages/ManageInteractions.php`**

```php
<?php
namespace App\Filament\Pages;

use App\DTOs\InteractionDto;
use App\Services\MdgApiClient;
use Filament\Pages\Page;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Concerns\InteractsWithTable;
use Filament\Tables\Contracts\HasTable;
use Filament\Tables\Table;

class ManageInteractions extends Page implements HasTable
{
    use InteractsWithTable;

    protected static ?string $navigationIcon  = 'heroicon-o-chart-bar';
    protected static ?string $navigationGroup = 'Users';
    protected static string  $view            = 'filament.pages.manage-interactions';
    protected static ?string $title           = 'Interactions';
    protected static ?int    $navigationSort  = 2;

    public function table(Table $table): Table
    {
        $client = app(MdgApiClient::class);

        return $table
            ->records(fn (): array => collect($client->getInteractions())
                ->map(fn (InteractionDto $i): array => [
                    'id'         => $i->id,
                    'user_id'    => $i->userId,
                    'event_id'   => $i->eventId,
                    'type'       => $i->type,
                    'created_at' => $i->createdAt,
                ])
                ->keyBy('id')
                ->toArray()
            )
            ->columns([
                TextColumn::make('id')->label('ID')->toggleable(isToggledHiddenByDefault: true),
                TextColumn::make('user_id')->label('User')->searchable(),
                TextColumn::make('event_id')->label('Event ID')->toggleable(isToggledHiddenByDefault: true),
                TextColumn::make('type')->badge()
                    ->color(fn (string $state): string => match($state) {
                        'read'  => 'success',
                        'click' => 'warning',
                        default => 'gray',
                    }),
                TextColumn::make('created_at')->label('At')->sortable(),
            ]);
    }
}
```

- [ ] **Step 3: Rebuild + browser verify**

```bash
docker-compose up -d --build admin
```

Open `http://localhost:8080/admin` → "Interactions" in sidebar.
Expected: read-only table, no actions.

- [ ] **Step 4: Run all tests + PHPStan**

```bash
docker exec python-newsletter-admin-1 php artisan test
docker exec python-newsletter-admin-1 ./vendor/bin/phpstan analyse
```

Expected: all green, zero PHPStan errors.

- [ ] **Step 5: Commit**

```bash
git add admin/app/Filament/Pages/ManageInteractions.php \
        admin/resources/views/filament/pages/manage-interactions.blade.php
git commit -m "feat(admin): add read-only Filament ManageInteractions page"
```

---

### Task 11: admin/CLAUDE.md

**Files:**
- Create: `admin/CLAUDE.md`

- [ ] **Step 1: Create `admin/CLAUDE.md`**

```markdown
# CLAUDE.md — admin (PHP/Laravel)

App-specific guidance. Repo-wide rules in root `CLAUDE.md`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | PHP 8.4, Docker |
| Framework | Laravel 11 |
| Admin UI | Filament v3 |
| Auth | Laravel Breeze (blade stack, admins table) |
| HTTP client | Laravel `Http` facade |
| DB access | Eloquent (admins table only) |
| Testing | PHPUnit (via `php artisan test`) |
| Static analysis | PHPStan level 8 |

---

## File Structure

```
admin/
  app/
    DTOs/               # Readonly PHP 8.2 DTOs — one per domain entity
    Exceptions/         # MdgApiException
    Filament/
      Pages/            # Custom Filament pages (not Resources) with InteractsWithTable
    Http/
      Controllers/      # Breeze auth controllers only — no domain controllers
    Models/
      Admin.php         # Eloquent — admins table only
    Providers/
      AppServiceProvider.php   # MdgApiClient singleton binding
      Filament/
        AdminPanelProvider.php # Filament panel config
    Services/
      MdgApiClient.php  # Http facade wrapper for all MDG calls
  database/
    migrations/         # Only admins table (and Breeze password_reset_tokens)
    seeders/
      AdminSeeder.php   # Default admin user (idempotent via firstOrCreate)
  docker/               # nginx.conf, www.conf, supervisord.conf, entrypoint.sh
  tests/
    Feature/
      MdgApiClientTest.php    # Http::fake() tests — no real MDG needed
```

---

## Validation

```bash
# Run inside Docker container
docker exec python-newsletter-admin-1 php artisan test
docker exec python-newsletter-admin-1 ./vendor/bin/phpstan analyse
```

Or from outside Docker:
```bash
cd admin && php artisan test
cd admin && ./vendor/bin/phpstan analyse
```

Gate: PHPStan zero errors + all tests green before every commit.

---

## Key Patterns

### Filament Pages (not Resources)

All domain entities use `ManageX extends Page implements HasTable` with `InteractsWithTable` trait.  
Records are keyed arrays (keyed by ID) from `MdgApiClient` DTOs.  
CRUD via modal actions: `->headerActions()` (create) and `->recordActions()` (edit, delete).

### MdgApiClient

- Base URL from `MDG_URL` env (default `http://mdg:9000`)
- All methods return typed DTOs
- Throws `MdgApiException` on HTTP errors
- Test with `Http::fake()` — no real MDG needed in tests

### Auth Guard

Guard name is `admin` (not `web`). Configured in `config/auth.php`.  
Filament panel uses `->authGuard('admin')` in `AdminPanelProvider`.

---

## Local Access

```
Admin panel:  http://localhost:8080/admin
Login:        admin@newsletter.local / password
```
```

- [ ] **Step 2: Commit**

```bash
git add admin/CLAUDE.md
git commit -m "docs(admin): add admin/CLAUDE.md with stack and pattern documentation"
```

---

## Plan complete

All 5 Filament pages are live at `http://localhost:8080/admin`.

**Final verification:**
```bash
# Full test suite
docker exec python-newsletter-admin-1 php artisan test
docker exec python-newsletter-admin-1 ./vendor/bin/phpstan analyse

# All MDG endpoints still work
cd mdg && composer test:all

# Admin panel accessible
curl -I http://localhost:8080/admin/login
```
