"""
Pexels image enrichment.

Rules we follow (per Pexels API ToS):
  - Always store photographer name + Pexels page URL for attribution display.
  - Hotlinking is allowed; we use medium-size URLs directly.
  - Rate limit: 200 req/hour free tier.
    We process at most PEXELS_BATCH_LIMIT items per run (default 50),
    with a 1-second sleep between requests → well under the limit.
  - We only call Pexels for items that have no real image (favicon / None).
  - Results are cached in the DB so the same item is never fetched twice.
"""
import asyncio
import re
import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Item

log = structlog.get_logger()

PEXELS_SEARCH = "https://api.pexels.com/v1/search"

# Map content category → search query (broad but relevant)
CATEGORY_QUERIES: dict[str, str] = {
    "research_paper":  "artificial intelligence research",
    "news_article":    "technology news digital",
    "blog_post":       "computer coding workspace",
    "tool_release":    "software development tool",
    "product_launch":  "tech startup product launch",
    "github_project":  "programming code terminal",
}

# Domains we skip — GitHub already has avatars (good enough)
# ArXiv is now included so research papers get Pexels images
SKIP_URL_PATTERNS = ["%github.com%"]

# Seconds to sleep between Pexels requests — keeps us at ~60 req/min max
REQUEST_DELAY = 1.2


def _search_query(item: Item) -> str:
    """
    Build a Pexels search query from the item.
    Use up to 3 meaningful words from the title, fall back to category default.
    """
    STOP = {
        "the","a","an","and","or","of","in","on","for","to","with","is","are",
        "was","were","using","based","via","new","how","why","what","when",
        "llm","ai","paper","model","system","learning","deep","large",
    }
    words = [w for w in re.findall(r"[a-zA-Z]{4,}", item.title or "")
             if w.lower() not in STOP][:3]

    if words:
        return " ".join(words)
    return CATEGORY_QUERIES.get(str(item.category), "artificial intelligence")


def _is_favicon_or_empty(item: Item) -> bool:
    t = item.thumbnail_url
    if not t:
        return True
    return "favicon" in t or t.endswith(".ico")


async def enrich_with_pexels(db: AsyncSession) -> int:
    """
    Find items without a real thumbnail and fetch one from Pexels.
    Returns number of items updated.
    """
    if not settings.PEXELS_API_KEY:
        log.warning("pexels_key_missing")
        return 0

    # Build query — exclude GitHub (has avatar) and arXiv (skip by choice)
    q = select(Item).where(
        (Item.thumbnail_url.like("%favicon%")) |
        (Item.thumbnail_url.like("%.ico%")) |
        (Item.thumbnail_url.is_(None))
    )
    for pat in SKIP_URL_PATTERNS:
        q = q.where(~Item.url.like(pat))

    q = q.order_by(Item.total_score.desc()).limit(settings.PEXELS_BATCH_LIMIT)
    result = await db.execute(q)
    items = result.scalars().all()

    if not items:
        log.info("pexels_nothing_to_enrich")
        return 0

    log.info("pexels_enriching", count=len(items))
    updated = 0

    headers = {"Authorization": settings.PEXELS_API_KEY}

    async with httpx.AsyncClient(headers=headers, timeout=10) as client:
        for item in items:
            query = _search_query(item)
            try:
                resp = await client.get(
                    PEXELS_SEARCH,
                    params={"query": query, "per_page": 1, "orientation": "landscape"},
                )
                resp.raise_for_status()
                data = resp.json()
                photos = data.get("photos", [])
                if not photos:
                    log.debug("pexels_no_result", query=query)
                    await asyncio.sleep(REQUEST_DELAY)
                    continue

                photo = photos[0]
                img_url = photo["src"]["large"]          # ~940px wide
                photographer = photo.get("photographer", "Pexels")
                photo_page  = photo.get("url", "https://www.pexels.com")

                item.thumbnail_url = img_url
                item.thumbnail_attribution = (
                    f"Photo by {photographer} on Pexels|{photo_page}"
                )
                updated += 1
                log.debug("pexels_got_image", item_id=str(item.id), query=query)

            except Exception as e:
                log.warning("pexels_fetch_error", error=str(e), query=query)

            # Respect rate limit — 1.2s between requests
            await asyncio.sleep(REQUEST_DELAY)

    if updated:
        await db.commit()
        log.info("pexels_enriched", count=updated)

    return updated
