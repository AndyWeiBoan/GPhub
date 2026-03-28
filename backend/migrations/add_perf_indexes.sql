-- Performance indexes for feed queries
-- Run once against PostgreSQL. SQLite ignores IF NOT EXISTS gracefully.

-- Composite: category + total_score — covers /trending?include=X ORDER BY total_score
CREATE INDEX IF NOT EXISTS idx_items_category_score
    ON items (category, total_score DESC);

-- Composite: fetched_at + category — covers the hot OR-date-range + category filter
-- Using fetched_at alone (always set) avoids the OR on two nullable columns
CREATE INDEX IF NOT EXISTS idx_items_fetched_category
    ON items (fetched_at DESC, category);

-- Composite: published_at + category — same query from the published_at side
CREATE INDEX IF NOT EXISTS idx_items_published_category
    ON items (published_at DESC, category);

-- Composite: category + ai_comment — covers comment generation queries
-- (WHERE category = X AND ai_comment IS NULL ORDER BY total_score DESC)
CREATE INDEX IF NOT EXISTS idx_items_category_comment
    ON items (category, total_score DESC)
    WHERE ai_comment IS NULL;

-- Speeds up archive cleanup job (DELETE WHERE fetched_at < cutoff)
CREATE INDEX IF NOT EXISTS idx_items_fetched_at_asc
    ON items (fetched_at ASC);
