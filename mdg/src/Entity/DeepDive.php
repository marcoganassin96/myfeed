<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'deep_dives')]
class DeepDive
{
    #[ORM\Id]
    #[ORM\Column(name: 'event_id', type: 'guid')]
    private string $eventId;

    /** @var list<string> */
    #[ORM\Column(type: 'json')]
    private array $chunks = [];

    #[ORM\Column(name: 'created_at', type: 'datetimetz_immutable')]
    private \DateTimeImmutable $createdAt;

    public function getEventId(): string { return $this->eventId; }
    /** @return list<string> */
    public function getChunks(): array { return $this->chunks; }

    public function setEventId(string $eventId): void { $this->eventId = $eventId; }
    /** @param list<string> $chunks */
    public function setChunks(array $chunks): void { $this->chunks = $chunks; }
    public function setCreatedAt(\DateTimeImmutable $createdAt): void { $this->createdAt = $createdAt; }
}
