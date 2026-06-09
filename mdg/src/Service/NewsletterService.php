<?php
namespace App\Service;

use App\Cache\CacheService;
use App\Repository\NewsletterRepository;

class NewsletterService
{
    /** Wraps predis with domain-level TTL defaults; injected so tests can mock without a Redis server. */
    public function __construct(
        private CacheService $cache,
        private NewsletterRepository $repo,
    ) {}

    /** @return list<array<string, mixed>> */
    public function listForUser(string $userId): array
    {
        $key = "newsletter:list:{$userId}";
        /** @var list<array<string, mixed>>|null $cached */
        $cached = $this->cache->get($key);
        if ($cached !== null) {
            return $cached;
        }
        $rows = $this->repo->findLatestPerTopicForUser($userId);
        $this->cache->set($key, $rows);
        return $rows;
    }

    /** @return array<string, mixed>|null */
    public function getById(string $newsletterId): ?array
    {
        $key = "newsletter:{$newsletterId}";
        $cached = $this->cache->get($key);
        if ($cached !== null) {
            return $cached;
        }
        ['rows' => $rows, 'links' => $links] = $this->repo->findByIdWithEvents($newsletterId);
        if (empty($rows)) {
            return null;
        }
        $first = $rows[0];
        $result = [
            'newsletter_id' => $first['newsletter_id'],
            'date'          => $first['date'],
            'title'         => $first['title'],
            'narrative'     => $first['narrative'],
            'context_links' => $links,
            'events'        => array_map(fn($r) => [
                'position'          => $r['position'],
                'event_id'          => $r['event_id'],
                'headline'          => $r['headline'],
                'summary'           => $r['summary'],
                'event_date'        => $r['event_date'],
                'thread_id'         => $r['thread_id'],
                'thread_name'       => $r['thread_name'],
                'previous_event_id' => $r['previous_event_id'],
            ], $rows),
        ];
        $this->cache->set($key, $result);
        return $result;
    }

    /**
     * Returns all newsletters unfiltered for admin; cached separately from user feeds.
     * Mutations call flush() which also invalidates this key.
     * @return list<array<string, mixed>>
     */
    public function listAll(): array
    {
        $key = 'newsletter:list:admin';
        /** @var list<array<string, mixed>>|null $cached */
        $cached = $this->cache->get($key);
        if ($cached !== null) {
            return $cached;
        }
        $rows = $this->repo->findAll();
        $this->cache->set($key, $rows);
        return $rows;
    }

    /**
     * Flushes all newsletter caches after create; admin mutations are rare but invalidate all user feeds.
     * @return array<string, mixed>
     */
    public function create(string $topicId, string $date, string $title, string $narrative): array
    {
        $result = $this->repo->create($topicId, $date, $title, $narrative);
        $this->cache->flush();
        return $result;
    }

    /**
     * Flushes all newsletter caches after update; user feeds may reference updated title/narrative.
     * Returns null when newsletter_id not found so callers control the 404 response.
     * @return array<string, mixed>|null
     */
    public function update(string $id, string $title, string $narrative): ?array
    {
        $result = $this->repo->update($id, $title, $narrative);
        $this->cache->flush();
        return $result;
    }

    /** Flushes all newsletter caches after delete to purge stale feed entries. */
    public function delete(string $id): bool
    {
        $deleted = $this->repo->delete($id);
        $this->cache->flush();
        return $deleted;
    }
}
