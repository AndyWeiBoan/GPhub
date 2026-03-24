-- Migration: add star_snapshots table for tracking GitHub star velocity
-- Run once: psql $DATABASE_URL -f migrations/add_star_snapshots.sql

CREATE TABLE IF NOT EXISTS star_snapshots (
    id          SERIAL PRIMARY KEY,
    item_id     VARCHAR(36) NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    stars       INTEGER     NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_star_snapshots_item_recorded
    ON star_snapshots (item_id, recorded_at DESC);
