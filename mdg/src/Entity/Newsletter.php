<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'newsletters')]
class Newsletter
{
    public function __construct(string $newsletterId, string $topicId, \DateTimeInterface $date, string $title, string $narrative)
    {
        $this->newsletterId = $newsletterId;
        $this->topicId = $topicId;
        $this->date = $date;
        $this->title = $title;
        $this->narrative = $narrative;
    }

    #[ORM\Id]
    #[ORM\Column(name: 'newsletter_id', type: 'guid')]
    private string $newsletterId;

    #[ORM\Column(name: 'topic_id', type: 'guid')]
    private string $topicId;

    #[ORM\Column(type: 'date')]
    private \DateTimeInterface $date;

    #[ORM\Column(type: 'string', length: 200)]
    private string $title;

    #[ORM\Column(type: 'text')]
    private string $narrative;

    public function getNewsletterId(): string { return $this->newsletterId; }
    public function getTopicId(): string { return $this->topicId; }
    public function getDate(): \DateTimeInterface { return $this->date; }
    public function getTitle(): string { return $this->title; }
    public function getNarrative(): string { return $this->narrative; }
}
