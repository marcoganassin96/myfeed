<?php
namespace App\Repository;

use Doctrine\ORM\EntityManagerInterface;

class NewsletterRepository
{
    public function __construct(private EntityManagerInterface $em) {}

    /**
     * Returns the personalized newsletter feed for a subscriber.
     *
     * Fetches the latest newsletter per subscribed topic, ordered newest first.
     * Each row is a summary card — the minimal projection needed to render a feed
     * list (no content, no events). Full newsletter data is retrieved separately
     * via findByIdWithEvents().
     *
     * @param string $userId Cognito sub of the authenticated reader; used to join
     *                       against subscriptions and filter to their topics only.
     *
     * @return list<array{newsletterId: string, topicId: string, date: string, title: string}>
     *         Ordered newest-first. One entry per subscribed topic.
     *
     * TODO: replace array shape with a typed NewsletterSummary DTO to eliminate
     *       the @var assertion in the body and make the feed-card contract
     *       enforceable without PHPDoc.
     */
    public function findLatestPerTopicForUser(string $userId): array
    {
        /** @var list<array{newsletterId: string, topicId: string, date: string, title: string}> $result */
        $result = $this->em->createQuery(
            'SELECT DISTINCT n.newsletterId, n.topicId, n.date, n.title
             FROM App\Entity\Newsletter n
             JOIN App\Entity\Subscription s WITH s.topicId = n.topicId
             WHERE s.userId = :userId
             ORDER BY n.date DESC'
        )->setParameter('userId', $userId)->getArrayResult();
        return $result;
    }

    /** @return array{rows: list<array<string, mixed>>, links: list<array<string, mixed>>} */
    public function findByIdWithEvents(string $newsletterId): array
    {
        $conn = $this->em->getConnection();
        $rows = $conn->fetchAllAssociative(
            'SELECT
                n.newsletter_id, n.date, n.title, n.narrative,
                ne.position,
                e.event_id, e.headline, e.summary, e.date AS event_date,
                ne.thread_id, t.name AS thread_name,
                etm.previous_event_id
             FROM newsletters n
             JOIN newsletter_events ne ON ne.newsletter_id = n.newsletter_id
             JOIN news_events e ON e.event_id = ne.event_id
             JOIN event_thread_memberships etm
                 ON etm.event_id = e.event_id AND etm.thread_id = ne.thread_id
             JOIN threads t ON t.thread_id = ne.thread_id
             WHERE n.newsletter_id = :id
             ORDER BY ne.position',
            ['id' => $newsletterId]
        );
        $links = $conn->fetchAllAssociative(
            'SELECT ncl.reason, ncl.position, n2.newsletter_id, n2.date, n2.title
             FROM newsletter_context_links ncl
             JOIN newsletters n2 ON n2.newsletter_id = ncl.linked_newsletter_id
             WHERE ncl.newsletter_id = :id
             ORDER BY ncl.position',
            ['id' => $newsletterId]
        );
        return ['rows' => $rows, 'links' => $links];
    }
}
