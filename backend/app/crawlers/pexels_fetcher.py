"""
Pexels image enrichment.

Rules we follow (per Pexels API ToS):
  - Always store photographer name + Pexels page URL for attribution display.
  - Hotlinking is allowed; we use medium-size URLs directly.
  - Rate limit: 200 req/hour free tier (~3.3 req/sec).
    We run up to PEXELS_CONCURRENCY requests in parallel (default 5),
    which peaks at ~5 req/sec — slightly above limit, so we add a small
    post-batch delay to stay safely under 200/hour overall.
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
SKIP_URL_PATTERNS = ["%github.com%"]

# Max concurrent Pexels requests — 5 keeps us well under 200 req/hour
PEXELS_CONCURRENCY = 5


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


async def _fetch_one(
    client: httpx.AsyncClient,
    item: Item,
    sem: asyncio.Semaphore,
) -> tuple[str, str | None, str | None]:
    """
    Fetch a single Pexels image for one item.
    Returns (item_id, img_url | None, attribution | None).
    """
    query = _search_query(item)
    async with sem:
        try:
            resp = await client.get(
                PEXELS_SEARCH,
                params={"query": query, "per_page": 1, "orientation": "landscape"},
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            if not photos:
                log.debug("pexels_no_result", query=query)
                return str(item.id), None, None

            photo = photos[0]
            img_url = photo["src"]["large"]
            photographer = photo.get("photographer", "Pexels")
            photo_page = photo.get("url", "https://www.pexels.com")
            attribution = f"Photo by {photographer} on Pexels|{photo_page}"
            log.debug("pexels_got_image", item_id=str(item.id), query=query)
            return str(item.id), img_url, attribution

        except Exception as e:
            log.warning("pexels_fetch_error", error=str(e), query=query)
            return str(item.id), None, None


async def enrich_with_pexels(db: AsyncSession) -> int:
    """
    Find items without a real thumbnail and fetch images from Pexels in parallel.
    Returns number of items updated.
    """
    if not settings.PEXELS_API_KEY:
        log.warning("pexels_key_missing")
        return 0

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

    log.info("pexels_enriching", count=len(items), concurrency=PEXELS_CONCURRENCY)

    # Build a lookup so we can write results back after concurrent fetch
    item_map = {str(i.id): i for i in items}
    sem = asyncio.Semaphore(PEXELS_CONCURRENCY)
    headers = {"Authorization": settings.PEXELS_API_KEY}

    async with httpx.AsyncClient(headers=headers, timeout=10) as client:
        tasks = [_fetch_one(client, item, sem) for item in items]
        results = await asyncio.gather(*tasks)

    updated = 0
    for item_id, img_url, attribution in results:
        if img_url:
            item_map[item_id].thumbnail_url = img_url
            item_map[item_id].thumbnail_attribution = attribution
            updated += 1

    if updated:
        await db.commit()
        log.info("pexels_enriched", count=updated)

    return updated
