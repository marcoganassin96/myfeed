<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'topics')]
#[ORM\UniqueConstraint(name: 'uniq_topics_name', columns: ['name'])]
class Topic
{
    #[ORM\Id]
    #[ORM\Column(name: 'topic_id', type: 'guid')]
    private string $topicId;

    #[ORM\Column(type: 'string', length: 100)]
    private string $name;

    #[ORM\Column(type: 'text', nullable: true)]
    private ?string $description = null;

    public function getTopicId(): string { return $this->topicId; }
    public function getName(): string { return $this->name; }
    public function getDescription(): ?string { return $this->description; }
}
