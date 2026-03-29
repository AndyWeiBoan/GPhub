"""FastAPI application entry point."""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.database import engine, AsyncSessionLocal, Base
from app.api.routes import router
from app.api.admin import router as admin_router
from app.scheduler.jobs import create_scheduler

log = structlog.get_logger()

# Default sources to seed on first run
DEFAULT_SOURCES = [
    (
        "Hacker News AI",
        "https://hnrss.org/newest?q=AI+LLM&points=50",
        "tier1",
        "news_article",
    ),
    ("ArXiv cs.AI", "https://rss.arxiv.org/rss/cs.AI", "tier1", "research_paper"),
    ("ArXiv cs.LG", "https://rss.arxiv.org/rss/cs.LG", "tier1", "research_paper"),
    ("ArXiv cs.CL", "https://rss.arxiv.org/rss/cs.CL", "tier1", "research_paper"),
    ("OpenAI News", "https://openai.com/news/rss.xml", "tier1", "news_article"),
    (
        "Google AI Blog",
        "https://blog.google/innovation-and-ai/technology/ai/rss/",
        "tier1",
        "news_article",
    ),
    (
        "Google DeepMind",
        "https://deepmind.google/blog/rss.xml",
        "tier1",
        "news_article",
    ),
    (
        "Microsoft AI Blog",
        "https://blogs.microsoft.com/ai/feed/",
        "tier1",
        "news_article",
    ),
    (
        "MIT Technology Review",
        "https://www.technologyreview.com/feed/",
        "tier1",
        "news_article",
    ),
    (
        "VentureBeat AI",
        "https://venturebeat.com/category/ai/feed/",
        "tier2",
        "news_article",
    ),
    (
        "Product Hunt AI",
        "https://www.producthunt.com/feed?category=artificial-intelligence",
        "tier2",
        "product_launch",
    ),
    (
        "Product Hunt Dev Tools",
        "https://www.producthunt.com/feed?category=developer-tools",
        "tier2",
        "product_launch",
    ),
    (
        "Product Hunt Tech",
        "https://www.producthunt.com/feed?category=tech",
        "tier2",
        "product_launch",
    ),
    (
        "TechCrunch AI",
        "https://techcrunch.com/tag/artificial-intelligence/feed/",
        "tier1",
        "product_launch",
    ),
    (
        "TechCrunch Startups",
        "https://techcrunch.com/category/startups/feed/",
        "tier2",
        "product_launch",
    ),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "tier2", "product_launch"),
    ("Changelog", "https://changelog.com/news/feed", "tier2", "product_launch"),
    (
        "GitHub Trending",
        "https://github.com/trending?l=python&since=daily",
        "tier2",
        "github_project",
    ),
    # Asia sources
    (
        "TechNews 科技新聞",
        "https://technews.tw/category/ai/feed/",
        "tier2",
        "news_article",
    ),
    ("iThome", "https://www.ithome.com.tw/rss", "tier2", "news_article"),
    ("Synced Review", "https://syncedreview.com/feed/", "tier1", "news_article"),
    ("36kr", "https://36kr.com/feed", "tier2", "news_article"),
    (
        "Medium – AI",
        "https://medium.com/feed/tag/artificial-intelligence",
        "tier2",
        "blog_post",
    ),
    (
        "Medium – ML",
        "https://medium.com/feed/tag/machine-learning",
        "tier2",
        "blog_post",
    ),
    ("Anthropic Blog", "https://www.anthropic.com/news", "tier1", "blog_post"),
    ("HuggingFace Blog", "https://huggingface.co/blog/feed.xml", "tier1", "blog_post"),
    ("Mozilla AI Blog", "https://blog.mozilla.ai/rss/", "tier1", "blog_post"),
    # Community — Reddit AI subreddits
    (
        "Reddit – r/MachineLearning",
        "https://www.reddit.com/r/MachineLearning/.rss",
        "tier1",
        "community",
    ),
    (
        "Reddit – r/LocalLLaMA",
        "https://www.reddit.com/r/LocalLLaMA/.rss",
        "tier1",
        "community",
    ),
    (
        "Reddit – r/artificial",
        "https://www.reddit.com/r/artificial/.rss",
        "tier2",
        "community",
    ),
    (
        "Reddit – r/singularity",
        "https://www.reddit.com/r/singularity/.rss",
        "tier2",
        "community",
    ),
    ("Reddit – r/OpenAI", "https://www.reddit.com/r/OpenAI/.rss", "tier2", "community"),
    ("Lobste.rs – AI", "https://lobste.rs/t/ai.rss", "tier1", "community"),
    ("Lobste.rs – ml", "https://lobste.rs/t/ml.rss", "tier1", "community"),
    (
        "Hacker News – 高互動 AI",
        "https://hnrss.org/newest?q=AI+OR+LLM+OR+machine+learning&points=80&comments=40",
        "tier1",
        "news_article",
    ),
    ("Dev.to – AI", "https://dev.to/feed/tag/ai", "tier2", "blog_post"),
    (
        "Dev.to – machinelearning",
        "https://dev.to/feed/tag/machinelearning",
        "tier2",
        "blog_post",
    ),
    ("Dev.to – llm", "https://dev.to/feed/tag/llm", "tier2", "blog_post"),
    ("Mastodon – #ai", "https://mastodon.social/tags/ai.rss", "tier2", "community"),
    (
        "Mastodon – #machinelearning",
        "https://mastodon.social/tags/machinelearning.rss",
        "tier2",
        "community",
    ),
]


async def _init_db():
    """Create all tables, ensure performance indexes, and seed default sources if not present."""
    from app.models import Source, SourceTier, ContentCategory
    import uuid

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Performance indexes — idempotent, safe to re-run
        _indexes = [
            "CREATE INDEX IF NOT EXISTS idx_items_category_score ON items (category, total_score DESC)",
            "CREATE INDEX IF NOT EXISTS idx_items_fetched_category ON items (fetched_at DESC, category)",
            "CREATE INDEX IF NOT EXISTS idx_items_published_category ON items (published_at DESC, category)",
            "CREATE INDEX IF NOT EXISTS idx_items_fetched_at_asc ON items (fetched_at ASC)",
        ]
        for ddl in _indexes:
            try:
                await conn.execute(text(ddl))
            except Exception:
                pass  # index may not support partial syntax on older SQLite — skip gracefully

    async with AsyncSessionLocal() as db:
        for name, url, tier, category in DEFAULT_SOURCES:
            existing = await db.execute(select(Source).where(Source.url == url))
            if existing.scalar_one_or_none() is None:
                db.add(
                    Source(
                        id=str(uuid.uuid4()),
                        name=name,
                        url=url,
                        tier=SourceTier(tier),
                        category=ContentCategory(category),
                    )
                )
        await db.commit()
    log.info("db_initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_db()
    scheduler = create_scheduler()
    scheduler.start()
    log.info("app_started")
    yield
    scheduler.shutdown(wait=False)
    log.info("app_stopped")


app = FastAPI(
    title="AI Digest API",
    description="Collects, scores and summarises the latest AI news, papers and tools.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
