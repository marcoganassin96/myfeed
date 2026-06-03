<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'newsletter_events')]
#[ORM\Index(name: 'idx_newsletter_events_nl_pos', columns: ['newsletter_id', 'position'])]
class NewsletterEvent
{
    public function __construct(string $newsletterId, string $eventId, string $threadId, int $position)
    {
        $this->newsletterId = $newsletterId;
        $this->eventId = $eventId;
        $this->threadId = $threadId;
        $this->position = $position;
    }

    #[ORM\Id]
    #[ORM\Column(name: 'newsletter_id', type: 'guid')]
    private string $newsletterId;

    #[ORM\Id]
    #[ORM\Column(name: 'event_id', type: 'guid')]
    private string $eventId;

    #[ORM\Column(name: 'thread_id', type: 'guid')]
    private string $threadId;

    #[ORM\Column(type: 'integer')]
    private int $position;

    public function getNewsletterId(): string { return $this->newsletterId; }
    public function getEventId(): string { return $this->eventId; }
    public function getThreadId(): string { return $this->threadId; }
    public function getPosition(): int { return $this->position; }
}
