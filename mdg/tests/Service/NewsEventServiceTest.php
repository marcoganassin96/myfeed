<?php
namespace App\Tests\Service;

use App\Repository\NewsEventRepository;
use App\Service\NewsEventService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;

class NewsEventServiceTest extends TestCase
{
    private NewsEventRepository&MockObject $repo;
    private NewsEventService $service;

    protected function setUp(): void
    {
        $this->repo    = $this->createMock(NewsEventRepository::class);
        $this->service = new NewsEventService($this->repo);
    }

    public function testListDelegatesToRepo(): void
    {
        $rows = [['event_id' => 'ev-1', 'headline' => 'H', 'summary' => 'S', 'date' => '2026-01-01', 'source_url' => null]];
        $this->repo->expects($this->once())->method('findAll')->willReturn($rows);
        $this->assertSame($rows, $this->service->list());
    }

    public function testGetByIdReturnsEvent(): void
    {
        $row = ['event_id' => 'ev-1', 'headline' => 'H', 'summary' => 'S', 'date' => '2026-01-01', 'source_url' => null];
        $this->repo->expects($this->once())->method('findById')->with('ev-1')->willReturn($row);
        $this->assertSame($row, $this->service->getById('ev-1'));
    }

    public function testGetByIdReturnsNullWhenNotFound(): void
    {
        $this->repo->method('findById')->willReturn(null);
        $this->assertNull($this->service->getById('nope'));
    }

    public function testCreateDelegatesToRepo(): void
    {
        $row = ['event_id' => 'ev-new', 'headline' => 'H', 'summary' => 'S', 'date' => '2026-01-01', 'source_url' => null];
        $this->repo->expects($this->once())->method('create')
            ->with('H', 'S', '2026-01-01', null)->willReturn($row);
        $this->assertSame($row, $this->service->create('H', 'S', '2026-01-01', null));
    }

    public function testUpdateReturnsUpdatedEvent(): void
    {
        $row = ['event_id' => 'ev-1', 'headline' => 'New H', 'summary' => 'S', 'date' => '2026-01-02', 'source_url' => null];
        $this->repo->expects($this->once())->method('update')
            ->with('ev-1', 'New H', 'S', '2026-01-02', null)->willReturn($row);
        $this->assertSame($row, $this->service->update('ev-1', 'New H', 'S', '2026-01-02', null));
    }

    public function testUpdateReturnsNullWhenNotFound(): void
    {
        $this->repo->method('update')->willReturn(null);
        $this->assertNull($this->service->update('nope', 'H', 'S', '2026-01-01', null));
    }

    public function testDeleteReturnsTrueWhenDeleted(): void
    {
        $this->repo->expects($this->once())->method('delete')->with('ev-1')->willReturn(true);
        $this->assertTrue($this->service->delete('ev-1'));
    }

    public function testDeleteReturnsFalseWhenNotFound(): void
    {
        $this->repo->method('delete')->willReturn(false);
        $this->assertFalse($this->service->delete('nope'));
    }
}
