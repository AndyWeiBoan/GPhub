"""Anthropic blog crawler via their public Sanity CMS API."""
import httpx
import structlog
from datetime import datetime, timezone

from app.crawlers.base import BaseCrawler, RawItem
from app.models import ContentCategory

log = structlog.get_logger()

SANITY_PROJECT = "4zrzovbb"
SANITY_DATASET = "website"
SANITY_API = f"https://{SANITY_PROJECT}.api.sanity.io/v2021-10-21/data/query/{SANITY_DATASET}"

# Fetch latest 20 posts ordered by creation date
QUERY = """*[_type == "post"] | order(_createdAt desc) [0..19] {
  title,
  "slug": slug.current,
  _createdAt,
  "summary": array::join(body[_type=="block" && style=="normal"][0..2].children[].text, " ")
}"""

SOURCE_URL = "https://www.anthropic.com/news"


class AnthropicCrawler(BaseCrawler):
    async def fetch(self) -> list[RawItem]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    SANITY_API,
                    params={"query": QUERY},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            log.warning("anthropic_crawl_failed", error=str(e))
            return []

        posts = data.get("result") or []
        items: list[RawItem] = []

        for post in posts:
            slug = post.get("slug")
            title = post.get("title")
            if not slug or not title:
                continue

            url = f"https://www.anthropic.com/news/{slug}"
            created_at = post.get("_createdAt")
            published_at = None
            if created_at:
                try:
                    published_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:
                    pass

            summary = post.get("summary") or ""

            items.append(RawItem(
                title=title,
                url=url,
                category=ContentCategory.blog_post,
                source_name="Anthropic Blog",
                source_url=SOURCE_URL,
                raw_content=summary[:500] if summary else None,
                published_at=published_at,
                thumbnail_url="https://www.anthropic.com/images/icons/apple-touch-icon.png",
            ))

        log.info("anthropic_fetched", count=len(items))
        return items
