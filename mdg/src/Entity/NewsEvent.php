<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'news_events')]
class NewsEvent
{
    #[ORM\Id]
    #[ORM\Column(name: 'event_id', type: 'guid')]
    private string $eventId;

    #[ORM\Column(type: 'string', length: 300)]
    private string $headline;

    #[ORM\Column(type: 'text')]
    private string $summary;

    #[ORM\Column(type: 'date_immutable')]
    private \DateTimeImmutable $date;

    #[ORM\Column(name: 'source_url', type: 'text', nullable: true)]
    private ?string $sourceUrl = null;

    public function getEventId(): string { return $this->eventId; }
    public function getHeadline(): string { return $this->headline; }
    public function getSummary(): string { return $this->summary; }
    public function getDate(): \DateTimeImmutable { return $this->date; }
    public function getSourceUrl(): ?string { return $this->sourceUrl; }
}
