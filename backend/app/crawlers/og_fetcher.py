"""
Fetch OpenGraph / Twitter Card images for items that only have a favicon.
Runs after the main crawl as a best-effort enrichment pass.
"""
import asyncio
import re
import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item

log = structlog.get_logger()

# Sources where we know favicon is the only thing available — skip OG fetch
SKIP_OG_DOMAINS = {"arxiv.org", "rss.arxiv.org"}

# Reliable OG image patterns per domain (faster than fetching the page)
DOMAIN_OG_TEMPLATES = {
    "technologyreview.com": None,   # fetch page
    "venturebeat.com":      None,
    "producthunt.com":      None,
    "news.ycombinator.com": None,
}

# Match either attribute order: property then content, or content then property
_OG_RE  = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\'> ]+)', re.I)
_OG_RE2 = re.compile(r'<meta[^>]+content=["\'](https?://[^"\'> ]+)[^>]+property=["\']og:image["\']', re.I)
_TW_RE  = re.compile(r'<meta[^>]+(?:name|property)=["\']twitter:image(?::src)?["\'][^>]+content=["\'](https?://[^"\'> ]+)', re.I)
_TW_RE2 = re.compile(r'<meta[^>]+content=["\'](https?://[^"\'> ]+)[^>]+(?:name|property)=["\']twitter:image', re.I)


def _domain(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else ""


async def _fetch_og(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, timeout=8, follow_redirects=True)
        if r.status_code != 200:
            return None
        html = r.text[:20_000]   # only need the <head>
        for pattern in (_OG_RE, _OG_RE2, _TW_RE, _TW_RE2):
            m = pattern.search(html)
            if m:
                img = m.group(1)
                # Filter out tiny icons / tracker pixels
                if any(x in img.lower() for x in ("favicon", "pixel", "tracking", "1x1", ".ico")):
                    continue
                return img
    except Exception:
        pass
    return None


async def enrich_thumbnails(db: AsyncSession, batch: int = 30) -> int:
    """
    Find items whose thumbnail_url looks like a favicon and try to replace
    it with a proper OG image.  Returns the number of items updated.
    """
    # Skip domains where we know only favicons exist (no editorial images)
    skip_url_patterns = ["%github.com%", "%arxiv.org%", "%rss.arxiv.org%"]

    q = (
        select(Item)
        .where(
            (Item.thumbnail_url.like("%favicon%")) |
            (Item.thumbnail_url.like("%.ico%")) |
            (Item.thumbnail_url.is_(None))
        )
    )
    for pat in skip_url_patterns:
        q = q.where(~Item.url.like(pat))

    q = q.order_by(Item.total_score.desc()).limit(batch)
    result = await db.execute(q)
    items = result.scalars().all()
    if not items:
        return 0

    updated = 0
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; AIDigestBot/1.0)"},
        timeout=10,
        follow_redirects=True,
    ) as client:
        tasks = {}
        for item in items:
            dom = _domain(item.url)
            if any(skip in dom for skip in SKIP_OG_DOMAINS):
                continue
            tasks[item.id] = asyncio.create_task(_fetch_og(client, item.url))

        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)

        for item in items:
            task = tasks.get(item.id)
            if task is None:
                continue
            try:
                og = task.result()
            except Exception:
                og = None
            if og:
                item.thumbnail_url = og
                updated += 1

    if updated:
        await db.commit()
        log.info("og_thumbnails_enriched", count=updated)
    return updated
