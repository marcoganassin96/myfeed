<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'threads')]
#[ORM\Index(name: 'idx_threads_topic_id', columns: ['topic_id'])]
class Thread
{
    #[ORM\Id]
    #[ORM\Column(name: 'thread_id', type: 'guid')]
    private string $threadId;

    #[ORM\Column(name: 'topic_id', type: 'guid')]
    private string $topicId;

    #[ORM\Column(type: 'string', length: 200)]
    private string $name;

    #[ORM\Column(name: 'created_at', type: 'datetimetz_immutable')]
    private \DateTimeImmutable $createdAt;

    public function getThreadId(): string { return $this->threadId; }
    public function getTopicId(): string { return $this->topicId; }
    public function getName(): string { return $this->name; }
    public function getCreatedAt(): \DateTimeImmutable { return $this->createdAt; }
}
