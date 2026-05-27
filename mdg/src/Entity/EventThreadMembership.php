<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'event_thread_memberships')]
#[ORM\Index(name: 'idx_etm_thread_position', columns: ['thread_id', 'position'])]
class EventThreadMembership
{
    #[ORM\Id]
    #[ORM\Column(name: 'event_id', type: 'guid')]
    private string $eventId;

    #[ORM\Id]
    #[ORM\Column(name: 'thread_id', type: 'guid')]
    private string $threadId;

    #[ORM\Column(type: 'integer')]
    private int $position;

    #[ORM\Column(name: 'previous_event_id', type: 'guid', nullable: true)]
    private ?string $previousEventId = null;

    public function getEventId(): string { return $this->eventId; }
    public function getThreadId(): string { return $this->threadId; }
    public function getPosition(): int { return $this->position; }
    public function getPreviousEventId(): ?string { return $this->previousEventId; }
}
