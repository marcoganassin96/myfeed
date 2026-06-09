<?php
namespace App\Tests\Service;

use App\Repository\InteractionRepository;
use App\Service\InteractionService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;

class InteractionServiceTest extends TestCase
{
    private InteractionRepository&MockObject $repo;
    private InteractionService $service;

    protected function setUp(): void
    {
        $this->repo = $this->createMock(InteractionRepository::class);
        $this->service = new InteractionService($this->repo);
    }

    public function testRecordPersistsAndReturnsInteractionData(): void
    {
        $this->repo->expects($this->once())
            ->method('save')
            ->with('user-1', 'ev-1', 'click')
            ->willReturn(['interaction_id' => 'ix-1', 'created_at' => '2026-01-01T00:00:00+00:00']);

        $result = $this->service->record('user-1', 'ev-1', 'click');
        $this->assertSame('ix-1', $result['interaction_id']);
    }

    public function testListAllDelegatesToRepo(): void
    {
        $rows = [['interaction_id' => 'ix-1', 'user_id' => 'u-1', 'event_id' => 'ev-1',
                  'type' => 'read', 'created_at' => '2026-01-01T00:00:00+00:00']];
        $this->repo->expects($this->once())->method('findAll')->willReturn($rows);
        $this->assertSame($rows, $this->service->listAll());
    }
}
