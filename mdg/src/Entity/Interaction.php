<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'interactions')]
class Interaction
{
    #[ORM\Id]
    #[ORM\Column(name: 'interaction_id', type: 'guid')]
    #[ORM\GeneratedValue(strategy: 'CUSTOM')]
    #[ORM\CustomIdGenerator(class: 'doctrine.uuid_generator')]
    private ?string $interactionId = null;

    #[ORM\Column(name: 'user_id', type: 'string')]
    private string $userId;

    #[ORM\Column(name: 'event_id', type: 'guid')]
    private string $eventId;

    #[ORM\Column(type: 'string', length: 20)]
    private string $type;

    #[ORM\Column(name: 'created_at', type: 'datetimetz_immutable')]
    private \DateTimeImmutable $createdAt;

    public function getInteractionId(): ?string { return $this->interactionId; }
    public function getCreatedAt(): \DateTimeImmutable { return $this->createdAt; }

    public function setUserId(string $userId): void { $this->userId = $userId; }
    public function setEventId(string $eventId): void { $this->eventId = $eventId; }
    public function setType(string $type): void { $this->type = $type; }
    public function setCreatedAt(\DateTimeImmutable $createdAt): void { $this->createdAt = $createdAt; }
}
