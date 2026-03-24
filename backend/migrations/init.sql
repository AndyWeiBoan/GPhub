-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Source tiers for credibility scoring
CREATE TYPE source_tier AS ENUM ('tier1', 'tier2', 'tier3');

-- Content categories
CREATE TYPE content_category AS ENUM (
    'research_paper',
    'news_article',
    'blog_post',
    'tool_release',
    'product_launch',
    'github_project',
    'community'
);

-- Sources table
CREATE TABLE IF NOT EXISTS sources (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) NOT NULL,
    url         TEXT NOT NULL UNIQUE,
    tier        source_tier NOT NULL DEFAULT 'tier2',
    category    content_category NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Items table (collected AI content)
CREATE TABLE IF NOT EXISTS items (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id           UUID REFERENCES sources(id) ON DELETE SET NULL,
    title               TEXT NOT NULL,
    url                 TEXT NOT NULL UNIQUE,
    author              VARCHAR(255),
    published_at        TIMESTAMPTZ,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_content         TEXT,
    summary             TEXT,                      -- Claude Haiku generated
    category            content_category,

    -- Raw signals for scoring
    github_stars        INTEGER,
    social_shares       INTEGER,
    citations           INTEGER,

    -- Computed scores (0.0 - 1.0 each)
    impact_score        NUMERIC(4,3) DEFAULT 0,    -- 影響力 40%
    credibility_score   NUMERIC(4,3) DEFAULT 0,    -- 來源可信度 35%
    novelty_score       NUMERIC(4,3) DEFAULT 0,    -- 新穎程度 25%
    total_score         NUMERIC(4,3) DEFAULT 0,    -- weighted total

    -- Vector embedding for semantic dedup
    embedding           vector(1536),

    is_summarized       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast feed queries
CREATE INDEX IF NOT EXISTS idx_items_total_score ON items (total_score DESC);
CREATE INDEX IF NOT EXISTS idx_items_published_at ON items (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_category ON items (category);
CREATE INDEX IF NOT EXISTS idx_items_fetched_at ON items (fetched_at DESC);

-- Crawl run log
CREATE TABLE IF NOT EXISTS crawl_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    items_fetched   INTEGER DEFAULT 0,
    items_new       INTEGER DEFAULT 0,
    errors          JSONB DEFAULT '[]',
    status          VARCHAR(50) DEFAULT 'running'  -- running | success | failed
);

-- Seed default sources
INSERT INTO sources (name, url, tier, category) VALUES
    ('Hacker News',         'https://hnrss.org/newest?q=AI+LLM&points=50', 'tier1', 'news_article'),
    ('ArXiv cs.AI',         'https://rss.arxiv.org/rss/cs.AI',             'tier1', 'research_paper'),
    ('ArXiv cs.LG',         'https://rss.arxiv.org/rss/cs.LG',             'tier1', 'research_paper'),
    ('ArXiv cs.CL',         'https://rss.arxiv.org/rss/cs.CL',             'tier1', 'research_paper'),
    ('Papers With Code',    'https://paperswithcode.com/latest',            'tier1', 'research_paper'),
    ('MIT Tech Review AI',  'https://www.technologyreview.com/feed/',       'tier1', 'news_article'),
    ('VentureBeat AI',      'https://venturebeat.com/category/ai/feed/',    'tier2', 'news_article'),
    ('The Batch',           'https://www.deeplearning.ai/the-batch/',       'tier1', 'blog_post'),
    ('GitHub Trending',     'https://github.com/trending?l=python&since=daily', 'tier2', 'github_project'),
    ('Product Hunt AI',     'https://www.producthunt.com/feed?category=artificial-intelligence', 'tier2', 'product_launch'),
    ('Lobste.rs – AI',      'https://lobste.rs/t/ai.rss',                    'tier1', 'community'),
    ('Lobste.rs – ml',      'https://lobste.rs/t/ml.rss',                    'tier1', 'community'),
    ('Hacker News – 高互動 AI', 'https://hnrss.org/newest?q=AI+OR+LLM+OR+machine+learning&points=80&comments=40', 'tier1', 'news_article'),
    ('Dev.to – AI',         'https://dev.to/feed/tag/ai',                    'tier2', 'blog_post'),
    ('Dev.to – machinelearning', 'https://dev.to/feed/tag/machinelearning',  'tier2', 'blog_post'),
    ('Dev.to – llm',        'https://dev.to/feed/tag/llm',                   'tier2', 'blog_post'),
    ('Mastodon – #ai',      'https://mastodon.social/tags/ai.rss',           'tier2', 'community'),
    ('Mastodon – #machinelearning', 'https://mastodon.social/tags/machinelearning.rss', 'tier2', 'community')
ON CONFLICT (url) DO NOTHING;
