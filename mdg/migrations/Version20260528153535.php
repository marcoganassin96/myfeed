<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

/**
 * Auto-generated Migration: Please modify to your needs!
 */
final class Version20260528153535 extends AbstractMigration
{
    public function getDescription(): string
    {
        return '';
    }

    public function up(Schema $schema): void
    {
        // this up() migration is auto-generated, please modify it to your needs
        $this->addSql('CREATE TABLE deep_dives (event_id UUID NOT NULL, chunks JSON NOT NULL, created_at TIMESTAMP(0) WITH TIME ZONE NOT NULL, PRIMARY KEY (event_id))');
        $this->addSql('CREATE TABLE event_thread_memberships (event_id UUID NOT NULL, thread_id UUID NOT NULL, position INT NOT NULL, previous_event_id UUID DEFAULT NULL, PRIMARY KEY (event_id, thread_id))');
        $this->addSql('CREATE INDEX idx_etm_thread_position ON event_thread_memberships (thread_id, position)');
        $this->addSql('CREATE TABLE interactions (interaction_id UUID NOT NULL, user_id VARCHAR(255) NOT NULL, event_id UUID NOT NULL, type VARCHAR(20) NOT NULL, created_at TIMESTAMP(0) WITH TIME ZONE NOT NULL, PRIMARY KEY (interaction_id))');
        $this->addSql('CREATE TABLE news_events (event_id UUID NOT NULL, headline VARCHAR(300) NOT NULL, summary TEXT NOT NULL, date DATE NOT NULL, source_url TEXT DEFAULT NULL, PRIMARY KEY (event_id))');
        $this->addSql('CREATE TABLE newsletter_context_links (id UUID NOT NULL, newsletter_id UUID NOT NULL, linked_newsletter_id UUID NOT NULL, reason TEXT NOT NULL, position INT NOT NULL, PRIMARY KEY (id))');
        $this->addSql('CREATE INDEX idx_ncl_newsletter_id ON newsletter_context_links (newsletter_id)');
        $this->addSql('CREATE TABLE newsletter_events (newsletter_id UUID NOT NULL, event_id UUID NOT NULL, thread_id UUID NOT NULL, position INT NOT NULL, PRIMARY KEY (newsletter_id, event_id))');
        $this->addSql('CREATE INDEX idx_newsletter_events_nl_pos ON newsletter_events (newsletter_id, position)');
        $this->addSql('CREATE TABLE newsletters (newsletter_id UUID NOT NULL, topic_id UUID NOT NULL, date DATE NOT NULL, title VARCHAR(200) NOT NULL, narrative TEXT NOT NULL, PRIMARY KEY (newsletter_id))');
        $this->addSql('CREATE TABLE subscriptions (user_id VARCHAR(255) NOT NULL, topic_id UUID NOT NULL, subscribed_at TIMESTAMP(0) WITH TIME ZONE NOT NULL, PRIMARY KEY (user_id, topic_id))');
        $this->addSql('CREATE TABLE threads (thread_id UUID NOT NULL, topic_id UUID NOT NULL, name VARCHAR(200) NOT NULL, created_at TIMESTAMP(0) WITH TIME ZONE NOT NULL, PRIMARY KEY (thread_id))');
        $this->addSql('CREATE INDEX idx_threads_topic_id ON threads (topic_id)');
        $this->addSql('CREATE TABLE topics (topic_id UUID NOT NULL, name VARCHAR(100) NOT NULL, description TEXT DEFAULT NULL, PRIMARY KEY (topic_id))');
        $this->addSql('CREATE UNIQUE INDEX uniq_topics_name ON topics (name)');
    }

    public function down(Schema $schema): void
    {
        // this down() migration is auto-generated, please modify it to your needs
        $this->addSql('DROP TABLE deep_dives');
        $this->addSql('DROP TABLE event_thread_memberships');
        $this->addSql('DROP TABLE interactions');
        $this->addSql('DROP TABLE news_events');
        $this->addSql('DROP TABLE newsletter_context_links');
        $this->addSql('DROP TABLE newsletter_events');
        $this->addSql('DROP TABLE newsletters');
        $this->addSql('DROP TABLE subscriptions');
        $this->addSql('DROP TABLE threads');
        $this->addSql('DROP TABLE topics');
    }
}
