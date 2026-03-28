"""
APScheduler jobs — two crawl+summarise runs per day.
Fires at 06:00 UTC and 18:00 UTC by default (configurable via SCHEDULE_HOURS).
"""
import asyncio
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import AsyncSessionLocal
from app.crawlers.manager import run_crawl
from app.crawlers.og_fetcher import enrich_thumbnails
from app.crawlers.pexels_fetcher import enrich_with_pexels
from app.summarizer.claude import summarise_pending
from app.summarizer.comment_generator import run_comment_generation
from app.summarizer.digest_generator import run_digest_generation
from app.summarizer.gemini import GeminiClient

log = structlog.get_logger()


async def crawl_and_summarise():
    """Full pipeline: crawl → score → enrich OG → pexels → Claude summary → Gemini comments → Gemini digest."""
    log.info("scheduled_job_start")
    async with AsyncSessionLocal() as db:
        crawl_result = await run_crawl(db)
        log.info("crawl_done", **crawl_result)

    async with AsyncSessionLocal() as db:
        enriched = await enrich_thumbnails(db, batch=50)
        log.info("og_enriched", count=enriched)

    # Pexels runs AFTER OG fetch so it only fills what OG couldn't
    async with AsyncSessionLocal() as db:
        pexels_count = await enrich_with_pexels(db)
        log.info("pexels_enriched", count=pexels_count)

    async with AsyncSessionLocal() as db:
        summarised = await summarise_pending(db)
        log.info("summarise_done", count=summarised)

    # Gemini AI comments and weekly digest (graceful skip if no API key)
    if settings.GEMINI_API_KEY:
        gemini = GeminiClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
        )
        async with AsyncSessionLocal() as db:
            commented = await run_comment_generation(db=db, gemini=gemini)
            log.info("gemini_comments_done", count=commented)

        async with AsyncSessionLocal() as db:
            digested = await run_digest_generation(db=db, gemini=gemini)
            log.info("gemini_digest_done", count=digested)
    else:
        log.info("gemini_skipped", reason="GEMINI_API_KEY not set")


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

    log.info("scheduler_created", hours=hours)
    return scheduler
