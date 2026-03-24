"""Orchestrate all crawlers and persist results."""
import structlog
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawlers.base import RawItem
from app.crawlers.rss_crawler import RSSCrawler
from app.crawlers.github_crawler import GitHubCrawler
from app.crawlers.anthropic_crawler import AnthropicCrawler
# TwitterCrawler kept for future use (requires Twitter account credentials)
# from app.crawlers.twitter_crawler import TwitterCrawler
from app.models import Item, Source, CrawlRun, ContentCategory
from app.scoring.engine import score_item

log = structlog.get_logger()


async def run_crawl(db: AsyncSession) -> dict:
    """Run all crawlers, persist new items, return summary dict."""
    run = CrawlRun(started_at=datetime.now(timezone.utc))
    db.add(run)
    await db.commit()

    errors = []
    all_items: list[RawItem] = []

    for CrawlerClass in [RSSCrawler, GitHubCrawler, AnthropicCrawler]:
        try:
            crawler = CrawlerClass()
            items = await crawler.fetch()
            all_items.extend(items)
        except Exception as e:
            log.error("crawler_error", crawler=CrawlerClass.__name__, error=str(e))
            errors.append({"crawler": CrawlerClass.__name__, "error": str(e)})

    # Fetch existing sources map
    sources_result = await db.execute(select(Source))
    sources = {s.url: s for s in sources_result.scalars().all()}

    items_new = 0
    for raw in all_items:
        # Check duplicate
        existing = await db.execute(select(Item).where(Item.url == raw.url))
        if existing.scalar_one_or_none():
            continue

        # Get or create source
        source = sources.get(raw.source_url)
        if not source:
            import uuid as _uuid
            source = Source(
                id=str(_uuid.uuid4()),
                name=raw.source_name,
                url=raw.source_url,
                category=raw.category,
            )
            db.add(source)
            await db.flush()
            sources[raw.source_url] = source

        item = Item(
            source_id=source.id,
            source_name=raw.source_name,
            title=raw.title,
            url=raw.url,
            author=raw.author,
            published_at=raw.published_at,
            raw_content=raw.raw_content,
            category=raw.category,
            github_subcat=raw.github_subcat,
            github_stars=raw.github_stars,
            social_shares=raw.social_shares,
            citations=raw.citations,
            thumbnail_url=raw.thumbnail_url,
        )

        # Score immediately
        scores = score_item(item, source)
        item.impact_score = scores["impact"]
        item.credibility_score = scores["credibility"]
        item.novelty_score = scores["novelty"]
        item.total_score = scores["total"]

        db.add(item)
        items_new += 1

    run.finished_at = datetime.now(timezone.utc)
    run.items_fetched = len(all_items)
    run.items_new = items_new
    run.errors = errors
    run.status = "success" if not errors else "partial"

    await db.commit()

    log.info("crawl_complete", fetched=len(all_items), new=items_new, errors=len(errors))
    return {"fetched": len(all_items), "new": items_new, "errors": errors}
