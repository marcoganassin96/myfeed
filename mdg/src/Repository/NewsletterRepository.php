<?php
namespace App\Repository;

use Doctrine\ORM\EntityManagerInterface;

class NewsletterRepository
{
    public function __construct(private EntityManagerInterface $em) {}

    /** @return list<array<string, mixed>> */
    public function findLatestPerTopicForUser(string $userId): array
    {
        return $this->em->createQuery(
            'SELECT DISTINCT n.newsletterId, n.topicId, n.date, n.title
             FROM App\Entity\Newsletter n
             JOIN App\Entity\Subscription s WITH s.topicId = n.topicId
             WHERE s.userId = :userId
             ORDER BY n.date DESC'
        )->setParameter('userId', $userId)->getArrayResult();
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
