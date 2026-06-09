<?php
namespace App\Tests\Service;

use App\Repository\TopicRepository;
use App\Service\TopicService;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;

class TopicServiceTest extends TestCase
{
    private TopicRepository&MockObject $repo;
    private TopicService $service;

    protected function setUp(): void
    {
        $this->repo    = $this->createMock(TopicRepository::class);
        $this->service = new TopicService($this->repo);
    }

    public function testListDelegatesToRepo(): void
    {
        $rows = [['topic_id' => 'tp-1', 'name' => 'Tech', 'description' => null]];
        $this->repo->expects($this->once())->method('findAll')->willReturn($rows);
        $this->assertSame($rows, $this->service->list());
    }

    public function testGetByIdReturnsTopic(): void
    {
        $row = ['topic_id' => 'tp-1', 'name' => 'Tech', 'description' => null];
        $this->repo->expects($this->once())->method('findById')->with('tp-1')->willReturn($row);
        $this->assertSame($row, $this->service->getById('tp-1'));
    }

    public function testGetByIdReturnsNullWhenNotFound(): void
    {
        $this->repo->method('findById')->willReturn(null);
        $this->assertNull($this->service->getById('nope'));
    }

    public function testCreateDelegatesToRepo(): void
    {
        $row = ['topic_id' => 'tp-new', 'name' => 'Sport', 'description' => 'Desc'];
        $this->repo->expects($this->once())->method('create')->with('Sport', 'Desc')->willReturn($row);
        $this->assertSame($row, $this->service->create('Sport', 'Desc'));
    }

    public function testUpdateReturnsUpdatedTopic(): void
    {
        $row = ['topic_id' => 'tp-1', 'name' => 'Updated', 'description' => null];
        $this->repo->expects($this->once())->method('update')->with('tp-1', 'Updated', null)->willReturn($row);
        $this->assertSame($row, $this->service->update('tp-1', 'Updated', null));
    }

    public function testUpdateReturnsNullWhenNotFound(): void
    {
        $this->repo->method('update')->willReturn(null);
        $this->assertNull($this->service->update('nope', 'Name', null));
    }

    public function testDeleteReturnsTrueWhenDeleted(): void
    {
        $this->repo->expects($this->once())->method('delete')->with('tp-1')->willReturn(true);
        $this->assertTrue($this->service->delete('tp-1'));
    }

    public function testDeleteReturnsFalseWhenNotFound(): void
    {
        $this->repo->method('delete')->willReturn(false);
        $this->assertFalse($this->service->delete('nope'));
    }
}
