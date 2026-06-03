<?php
namespace App\Service;

use App\Cache\CacheService;
use App\Repository\NewsletterRepository;

class NewsletterService
{
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
}
