-- Migration: add github_subcat column to items table
-- Run this once against an existing PostgreSQL database.
-- SQLite users: the column is added automatically by SQLAlchemy on next startup
--               (CREATE TABLE IF NOT EXISTS picks up new columns via drop+recreate
--                in dev, or you can run the SQLite equivalent below).

-- PostgreSQL
DO $$
BEGIN
    -- Create the enum type if it doesn't exist yet
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'githubsubcat') THEN
        CREATE TYPE githubsubcat AS ENUM ('llm', 'agent', 'context', 'vision', 'tool');
    END IF;
END$$;

ALTER TABLE items
    ADD COLUMN IF NOT EXISTS github_subcat githubsubcat;

CREATE INDEX IF NOT EXISTS idx_items_github_subcat ON items (github_subcat)
    WHERE github_subcat IS NOT NULL;

-- SQLite equivalent (run manually in sqlite3 CLI if needed):
-- ALTER TABLE items ADD COLUMN github_subcat TEXT;
