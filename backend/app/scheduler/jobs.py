"""
APScheduler jobs — two crawl+summarise runs per day + nightly archive.
Crawl fires at 06:00 UTC and 18:00 UTC (configurable via SCHEDULE_HOURS).
Archive fires at 03:00 UTC daily — deletes items older than ARCHIVE_DAYS.
"""
import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Item
from app.crawlers.manager import run_crawl
from app.crawlers.og_fetcher import enrich_thumbnails
from app.crawlers.pexels_fetcher import enrich_with_pexels
from app.summarizer.claude import summarise_pending
from app.summarizer.comment_generator import run_comment_generation, _build_client
from app.summarizer.digest_generator import run_digest_generation
from app.summarizer.gemini import GeminiClient

log = structlog.get_logger()


async def crawl_and_summarise():
    """
    Full pipeline with maximum parallelism:

    Phase 1 (sequential): Crawl
    Phase 2 (parallel):   OG fetch  ∥  Claude summary
    Phase 3 (parallel):   Pexels    ∥  Gemini comments  (each waits on its phase-2 dep)
    Phase 4 (sequential): Gemini digest
    """
    log.info("scheduled_job_start")

    # ── Phase 1: Crawl ────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        crawl_result = await run_crawl(db)
        log.info("crawl_done", **crawl_result)

    # ── Phase 2: OG fetch ∥ Claude summary ───────────────────────────────────
    async def _og():
        async with AsyncSessionLocal() as db:
            n = await enrich_thumbnails(db, batch=50)
            log.info("og_enriched", count=n)
            return n

    async def _claude():
        async with AsyncSessionLocal() as db:
            n = await summarise_pending(db)
            log.info("summarise_done", count=n)
            return n

    og_count, claude_count = await asyncio.gather(_og(), _claude())

    # ── Phase 3: Pexels ∥ Gemini comments ────────────────────────────────────
    # Pexels fills what OG missed (OG already done)
    # Gemini comments use item.summary written by Claude (Claude already done)
    async def _pexels():
        async with AsyncSessionLocal() as db:
            n = await enrich_with_pexels(db)
            log.info("pexels_enriched", count=n)
            return n

    # Build clients — Groq for comments, Gemini for digest
    comment_client = _build_client()  # Groq preferred, Gemini fallback
    gemini_client = GeminiClient(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
    ) if settings.GEMINI_API_KEY else None

    async def _gemini_comments():
        if not comment_client:
            return 0
        async with AsyncSessionLocal() as db:
            n = await run_comment_generation(db=db, client=comment_client)
            log.info("comment_generation_done", count=n, model=comment_client.model_label)
            return n

    pexels_count, comment_count = await asyncio.gather(
        _pexels(),
        _gemini_comments(),
    )

    # ── Phase 4: Gemini digest (sequential — reserved for quality reasoning) ──
    if gemini_client:
        async with AsyncSessionLocal() as db:
            digested = await run_digest_generation(db=db, gemini=gemini_client)
            log.info("gemini_digest_done", count=digested)
    else:
        log.info("gemini_skipped", reason="GEMINI_API_KEY not set")


async def archive_old_items():
    """
    Nightly archive job — runs at 03:00 UTC.
    Deletes items (and their cascaded star_snapshots) older than ARCHIVE_DAYS.
    GitHub projects are kept for ARCHIVE_DAYS * 2 since they're slower-moving.
    """
    archive_days = getattr(settings, "ARCHIVE_DAYS", 30)
    cutoff_default = datetime.now(timezone.utc) - timedelta(days=archive_days)
    cutoff_github  = datetime.now(timezone.utc) - timedelta(days=archive_days * 2)

    async with AsyncSessionLocal() as db:
        # Delete non-github items older than archive_days
        result_non_gh = await db.execute(
            delete(Item).where(
                Item.fetched_at < cutoff_default,
                Item.category != "github_project",
            )
        )
        # Delete github items older than archive_days * 2
        result_gh = await db.execute(
            delete(Item).where(
                Item.fetched_at < cutoff_github,
                Item.category == "github_project",
            )
        )
        await db.commit()

    deleted = result_non_gh.rowcount + result_gh.rowcount
    log.info(
        "archive_done",
        deleted_non_github=result_non_gh.rowcount,
        deleted_github=result_gh.rowcount,
        total=deleted,
        cutoff_days=archive_days,
    )


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    hours = settings.SCHEDULE_HOURS  # e.g. [6, 18]
    hour_expr = ",".join(str(h) for h in hours)

    scheduler.add_job(
        crawl_and_summarise,
        trigger=CronTrigger(hour=hour_expr, minute=0),
        id="crawl_and_summarise",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    scheduler.add_job(
        archive_old_items,
        trigger=CronTrigger(hour=3, minute=0),  # 03:00 UTC daily
        id="archive_old_items",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=600,
    )

    log.info("scheduler_created", hours=hours)
    return scheduler
