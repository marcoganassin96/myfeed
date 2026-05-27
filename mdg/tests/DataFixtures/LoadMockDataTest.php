<?php
namespace App\Tests\DataFixtures;

use App\DataFixtures\LoadMockData;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;

class LoadMockDataTest extends KernelTestCase
{
    private EntityManagerInterface $em;

    protected function setUp(): void
    {
        $env = $_ENV['APP_ENV'] ?? $_SERVER['APP_ENV'] ?? 'test';
        $allowedEnvs = ['local', 'dev'];
        if (!in_array($env, $allowedEnvs)) {
            $this->markTestSkipped(
                sprintf('Safety Check: Fixture loading is disabled in the "%s" environment.', $env)
            );
        }
        self::bootKernel(['environment' => $env]);
        $this->em = static::getContainer()->get(EntityManagerInterface::class);
    }

    /**
     * Validates database integrity after (and only immediatly after) migration and fixture execution.
     * It will be used to verify that the fixture loading process is working in CI/CD pipelines
     */
    /** @group test-fixture */
    public function testRowCountsAfterLoad(): void
    {
        $fixture = new LoadMockData();
        $fixture->load($this->em);

        $conn = $this->em->getConnection();

        $this->assertSame('3', $conn->fetchOne('SELECT COUNT(*)::text FROM topics'));
        $this->assertSame('15', $conn->fetchOne('SELECT COUNT(*)::text FROM threads'));
        $this->assertSame('300', $conn->fetchOne('SELECT COUNT(*)::text FROM news_events'));
        $this->assertSame('300', $conn->fetchOne('SELECT COUNT(*)::text FROM event_thread_memberships'));
        $this->assertSame('90', $conn->fetchOne('SELECT COUNT(*)::text FROM newsletters'));
        $this->assertSame('450', $conn->fetchOne('SELECT COUNT(*)::text FROM newsletter_events'));
        $this->assertSame('176', $conn->fetchOne('SELECT COUNT(*)::text FROM newsletter_context_links'));
        $this->assertSame('2000', $conn->fetchOne('SELECT COUNT(*)::text FROM subscriptions'));
        $this->assertSame('10000', $conn->fetchOne('SELECT COUNT(*)::text FROM interactions'));
    }
}
