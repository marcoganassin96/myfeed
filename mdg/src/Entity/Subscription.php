<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'subscriptions')]
class Subscription
{
    #[ORM\Id]
    #[ORM\Column(name: 'user_id', type: 'string')]
    private string $userId;

    #[ORM\Id]
    #[ORM\Column(name: 'topic_id', type: 'guid')]
    private string $topicId;

    #[ORM\Column(name: 'subscribed_at', type: 'datetimetz_immutable')]
    private \DateTimeImmutable $subscribedAt;

    public function getUserId(): string { return $this->userId; }
    public function getTopicId(): string { return $this->topicId; }
    public function getSubscribedAt(): \DateTimeImmutable { return $this->subscribedAt; }

    public function setUserId(string $userId): void { $this->userId = $userId; }
    public function setTopicId(string $topicId): void { $this->topicId = $topicId; }
}
