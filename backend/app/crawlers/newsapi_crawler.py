"""NewsAPI crawler — fetches AI news from newsapi.org.

Free tier: 100 requests/day, up to 100 articles per request.
Requires NEWS_API_KEY in config.

We run two queries:
1. Top headlines in Technology category (broad, high-quality sources)
2. Everything matching AI/LLM keywords (sorted by publishedAt)

This supplements the existing RSS feeds with additional news sources
that don't have public RSS feeds or whose RSS we don't currently track.

Docs: https://newsapi.org/docs
"""
import httpx
import structlog
from datetime import datetime, timezone
from typing import Optional

from app.crawlers.base import BaseCrawler, RawItem
from app.models import ContentCategory
from app.config import settings

log = structlog.get_logger()

NEWSAPI_BASE    = "https://newsapi.org/v2"
NEWSAPI_FAVICON = "https://newsapi.org/favicon.ico"

# Queries: (endpoint, params, source_label)
# We use 'everything' endpoint with AI-focused keywords + reputable domains
NEWSAPI_QUERIES = [
    {
        "endpoint": "everything",
        "params": {
            "q": "(artificial intelligence OR large language model OR LLM OR AI agent OR generative AI)",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 30,
        },
        "source_name": "NewsAPI – AI",
    },
    {
        "endpoint": "top-headlines",
        "params": {
            "category": "technology",
            "language": "en",
            "pageSize": 20,
        },
        "source_name": "NewsAPI – Tech Headlines",
    },
]

# Domains to skip — already covered by existing RSS crawlers
_SKIP_DOMAINS = {
    "techcrunch.com",
    "venturebeat.com",
    "theverge.com",
    "technologyreview.com",
    "reddit.com",
    "medium.com",
}


def _should_skip(url: str) -> bool:
    for domain in _SKIP_DOMAINS:
        if domain in url:
            return True
    return False


def _parse_article(article: dict, source_name: str, source_url: str) -> Optional[RawItem]:
    url = article.get("url", "")
    if not url or url == "https://removed.com":
        return None
    if _should_skip(url):
        return None

    title = (article.get("title") or "").strip()
    if not title or title == "[Removed]":
        return None

    description = (article.get("description") or "").strip()
    content     = (article.get("content") or "").strip()
    # NewsAPI truncates content at 200 chars with "[+N chars]" — strip that
    import re
    content = re.sub(r"\[\+\d+ chars\]$", "", content).strip()
    raw_content = description
    if content and content != description:
        raw_content = f"{description}\n\n{content}".strip()

    published_at: Optional[datetime] = None
    pub_raw = article.get("publishedAt")
    if pub_raw:
        try:
            published_at = datetime.fromisoformat(
                pub_raw.replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except ValueError:
            pass

    thumbnail = article.get("urlToImage") or None

    # Source name: prefer article's own source name
    src_obj = article.get("source") or {}
    api_src_name = src_obj.get("name") or source_name

    return RawItem(
        title=title,
        url=url,
        category=ContentCategory.news_article,
        source_name=f"NewsAPI – {api_src_name}",
        source_url=source_url,
        author=article.get("author"),
        published_at=published_at,
        raw_content=raw_content,
        thumbnail_url=thumbnail,
    )


class NewsAPICrawler(BaseCrawler):
    """Fetch AI news articles from NewsAPI."""

    async def fetch(self) -> list[RawItem]:
        if not settings.NEWS_API_KEY:
            log.info("newsapi_skipped", reason="NEWS_API_KEY not set")
            return []

        headers = {"X-Api-Key": settings.NEWS_API_KEY}
        all_items: list[RawItem] = []

        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            for query_cfg in NEWSAPI_QUERIES:
                endpoint    = query_cfg["endpoint"]
                params      = dict(query_cfg["params"])
                source_name = query_cfg["source_name"]
                url         = f"{NEWSAPI_BASE}/{endpoint}"

                # Apply global max from config
                params["pageSize"] = min(
                    params.get("pageSize", 20),
                    settings.NEWS_API_MAX_RESULTS,
                )

                try:
                    resp = await client.get(url, params=params, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    log.warning("newsapi_fetch_failed", endpoint=endpoint, error=str(e))
                    continue

                if data.get("status") != "ok":
                    log.warning("newsapi_error_response", message=data.get("message"))
                    continue

                articles = data.get("articles") or []
                source_url = str(resp.url)

                for article in articles:
                    item = _parse_article(article, source_name, source_url)
                    if item:
                        all_items.append(item)

                log.info(
                    "newsapi_fetched",
                    endpoint=endpoint,
                    total_results=data.get("totalResults", 0),
                    parsed=len([a for a in articles if a.get("url")]),
                )

        # Deduplicate by URL
        seen: set[str] = set()
        deduped: list[RawItem] = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                deduped.append(item)

        log.info("newsapi_total", count=len(deduped))
        return deduped
