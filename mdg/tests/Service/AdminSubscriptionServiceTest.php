<?php
namespace App\Tests\Service;

use App\Repository\AdminSubscriptionRepository;
use App\Service\AdminSubscriptionService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;

class AdminSubscriptionServiceTest extends TestCase
{
    private AdminSubscriptionRepository&MockObject $repo;
    private AdminSubscriptionService $service;

    protected function setUp(): void
    {
        $this->repo = $this->createMock(AdminSubscriptionRepository::class);
        $this->service = new AdminSubscriptionService($this->repo);
    }

    public function testListAllDelegatesToRepo(): void
    {
        $rows = [['user_id' => 'u-1', 'topic_id' => 'tp-1', 'topic_name' => 'Tech', 'subscribed_at' => '2026-01-01T00:00:00+00:00']];
        $this->repo->expects($this->once())->method('findAll')->willReturn($rows);
        $this->assertSame($rows, $this->service->listAll());
    }

    public function testDeleteReturnsTrueWhenDeleted(): void
    {
        $this->repo->expects($this->once())->method('delete')->with('u-1', 'tp-1')->willReturn(true);
        $this->assertTrue($this->service->delete('u-1', 'tp-1'));
    }

    public function testDeleteReturnsFalseWhenNotFound(): void
    {
        $this->repo->expects($this->once())->method('delete')->with('u-1', 'tp-nope')->willReturn(false);
        $this->assertFalse($this->service->delete('u-1', 'tp-nope'));
    }
}
