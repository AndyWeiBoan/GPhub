-- Migration: add AI comment and weekly digest features
-- Run this on PostgreSQL after the base schema is already applied.

-- 1. Add ai_comment column to items
ALTER TABLE items
    ADD COLUMN IF NOT EXISTS ai_comment TEXT;

-- 2. Create weekly_digests table
CREATE TABLE IF NOT EXISTS weekly_digests (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_label  VARCHAR(10)  NOT NULL,          -- e.g. "2026-W13"
    title       TEXT         NOT NULL,
    analysis    TEXT         NOT NULL,
    item_ids    TEXT         NOT NULL,           -- JSON array of item UUIDs
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weekly_digests_week_label ON weekly_digests (week_label);
