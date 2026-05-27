<?php
namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'newsletter_context_links')]
#[ORM\Index(name: 'idx_ncl_newsletter_id', columns: ['newsletter_id'])]
class NewsletterContextLink
{
    #[ORM\Id]
    #[ORM\Column(name: 'id', type: 'guid')]
    private string $id;

    #[ORM\Column(name: 'newsletter_id', type: 'guid')]
    private string $newsletterId;

    #[ORM\Column(name: 'linked_newsletter_id', type: 'guid')]
    private string $linkedNewsletterId;

    #[ORM\Column(type: 'text')]
    private string $reason;

    #[ORM\Column(type: 'integer')]
    private int $position;

    public function getId(): string { return $this->id; }
    public function getNewsletterId(): string { return $this->newsletterId; }
    public function getLinkedNewsletterId(): string { return $this->linkedNewsletterId; }
    public function getReason(): string { return $this->reason; }
    public function getPosition(): int { return $this->position; }
}
