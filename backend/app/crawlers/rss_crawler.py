"""RSS feed crawler using feedparser."""
import asyncio
import re
import feedparser
import httpx
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
import structlog

from app.crawlers.base import BaseCrawler, RawItem
from app.models import ContentCategory

log = structlog.get_logger()

RSS_SOURCES = [
    {
        "name": "Hacker News AI",
        "url": "https://hnrss.org/newest?q=AI+LLM&points=50",
        "category": ContentCategory.news_article,
        "favicon": "https://news.ycombinator.com/favicon.ico",
    },
    {
        "name": "ArXiv cs.AI",
        "url": "https://rss.arxiv.org/rss/cs.AI",
        "category": ContentCategory.research_paper,
        "favicon": "https://arxiv.org/favicon.ico",
    },
    {
        "name": "ArXiv cs.LG",
        "url": "https://rss.arxiv.org/rss/cs.LG",
        "category": ContentCategory.research_paper,
        "favicon": "https://arxiv.org/favicon.ico",
    },
    {
        "name": "ArXiv cs.CL",
        "url": "https://rss.arxiv.org/rss/cs.CL",
        "category": ContentCategory.research_paper,
        "favicon": "https://arxiv.org/favicon.ico",
    },
    # ── Official AI company blogs ─────────────────────────────────────────────
    {
        "name": "OpenAI News",
        "url": "https://openai.com/news/rss.xml",
        "category": ContentCategory.news_article,
        "favicon": "https://openai.com/favicon.ico",
    },
    {
        "name": "Google AI Blog",
        "url": "https://blog.google/innovation-and-ai/technology/ai/rss/",
        "category": ContentCategory.news_article,
        "favicon": "https://www.google.com/favicon.ico",
    },
    {
        "name": "Google DeepMind",
        "url": "https://deepmind.google/blog/rss.xml",
        "category": ContentCategory.news_article,
        "favicon": "https://deepmind.google/favicon.ico",
    },
    {
        "name": "Microsoft AI Blog",
        "url": "https://blogs.microsoft.com/ai/feed/",
        "category": ContentCategory.news_article,
        "favicon": "https://www.microsoft.com/favicon.ico",
    },
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "MIT Technology Review AI",
        "url": "https://www.technologyreview.com/feed/",
        "category": ContentCategory.news_article,
        "favicon": "https://www.technologyreview.com/favicon.ico",
    },
    {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "category": ContentCategory.news_article,
        "favicon": "https://venturebeat.com/favicon.ico",
    },
    # ── Product Launch sources ────────────────────────────────────────────────
    {
        "name": "Product Hunt AI",
        "url": "https://www.producthunt.com/feed?category=artificial-intelligence",
        "category": ContentCategory.product_launch,
        "favicon": "https://www.producthunt.com/favicon.ico",
    },
    {
        "name": "Product Hunt Dev Tools",
        "url": "https://www.producthunt.com/feed?category=developer-tools",
        "category": ContentCategory.product_launch,
        "favicon": "https://www.producthunt.com/favicon.ico",
    },
    {
        "name": "Product Hunt Tech",
        "url": "https://www.producthunt.com/feed?category=tech",
        "category": ContentCategory.product_launch,
        "favicon": "https://www.producthunt.com/favicon.ico",
    },
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/tag/artificial-intelligence/feed/",
        "category": ContentCategory.product_launch,
        "favicon": "https://techcrunch.com/favicon.ico",
    },
    {
        "name": "TechCrunch Startups",
        "url": "https://techcrunch.com/category/startups/feed/",
        "category": ContentCategory.product_launch,
        "favicon": "https://techcrunch.com/favicon.ico",
    },
    {
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "category": ContentCategory.product_launch,
        "favicon": "https://www.theverge.com/favicon.ico",
    },
    {
        "name": "Changelog",
        "url": "https://changelog.com/news/feed",
        "category": ContentCategory.product_launch,
        "favicon": "https://changelog.com/favicon.ico",
    },
    # ── Asia sources ──────────────────────────────────────────────────────────
    {
        "name": "TechNews 科技新聞",
        "url": "https://technews.tw/category/ai/feed/",
        "category": ContentCategory.news_article,
        "favicon": "https://technews.tw/favicon.ico",
    },
    {
        "name": "iThome",
        "url": "https://www.ithome.com.tw/rss",
        "category": ContentCategory.news_article,
        "favicon": "https://www.ithome.com.tw/favicon.ico",
    },
    {
        "name": "Synced Review",
        "url": "https://syncedreview.com/feed/",
        "category": ContentCategory.news_article,
        "favicon": "https://syncedreview.com/favicon.ico",
    },
    {
        "name": "36kr",
        "url": "https://36kr.com/feed",
        "category": ContentCategory.news_article,
        "favicon": "https://36kr.com/favicon.ico",
    },
    # ── Blog sources ──────────────────────────────────────────────────────────
    {
        "name": "Medium – AI",
        "url": "https://medium.com/feed/tag/artificial-intelligence",
        "category": ContentCategory.blog_post,
        "favicon": "https://miro.medium.com/v2/1*m-R_BkNf1Qjr1YbyOIJY2w.png",
    },
    {
        "name": "Medium – Machine Learning",
        "url": "https://medium.com/feed/tag/machine-learning",
        "category": ContentCategory.blog_post,
        "favicon": "https://miro.medium.com/v2/1*m-R_BkNf1Qjr1YbyOIJY2w.png",
    },
    {
        "name": "HuggingFace Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "category": ContentCategory.blog_post,
        "favicon": "https://huggingface.co/favicon.ico",
    },
    # ── Community (Reddit) ────────────────────────────────────────────────────
    {
        "name": "Reddit – r/MachineLearning",
        "url": "https://www.reddit.com/r/MachineLearning/.rss",
        "category": ContentCategory.community,
        "favicon": "https://www.redditstatic.com/icon.png",
        "user_agent": "ai-digest-bot/1.0 (aggregator)",
    },
    {
        "name": "Reddit – r/LocalLLaMA",
        "url": "https://www.reddit.com/r/LocalLLaMA/.rss",
        "category": ContentCategory.community,
        "favicon": "https://www.redditstatic.com/icon.png",
        "user_agent": "ai-digest-bot/1.0 (aggregator)",
    },
    {
        "name": "Reddit – r/artificial",
        "url": "https://www.reddit.com/r/artificial/.rss",
        "category": ContentCategory.community,
        "favicon": "https://www.redditstatic.com/icon.png",
        "user_agent": "ai-digest-bot/1.0 (aggregator)",
    },
    {
        "name": "Reddit – r/singularity",
        "url": "https://www.reddit.com/r/singularity/.rss",
        "category": ContentCategory.community,
        "favicon": "https://www.redditstatic.com/icon.png",
        "user_agent": "ai-digest-bot/1.0 (aggregator)",
    },
    {
        "name": "Reddit – r/OpenAI",
        "url": "https://www.reddit.com/r/OpenAI/.rss",
        "category": ContentCategory.community,
        "favicon": "https://www.redditstatic.com/icon.png",
        "user_agent": "ai-digest-bot/1.0 (aggregator)",
    },
    # ── Community (Lobste.rs, HN high-engagement, Dev.to, Mastodon) ─────────
    {
        "name": "Lobste.rs – AI",
        "url": "https://lobste.rs/t/ai.rss",
        "category": ContentCategory.community,
        "favicon": "https://lobste.rs/favicon.ico",
    },
    {
        "name": "Lobste.rs – ml",
        "url": "https://lobste.rs/t/ml.rss",
        "category": ContentCategory.community,
        "favicon": "https://lobste.rs/favicon.ico",
    },
    {
        "name": "Hacker News – 高互動 AI",
        "url": (
            "https://hnrss.org/newest?"
            "q=AI+OR+LLM+OR+machine+learning&points=80&comments=40"
        ),
        "category": ContentCategory.news_article,
        "favicon": "https://news.ycombinator.com/favicon.ico",
    },
    {
        "name": "Dev.to – AI",
        "url": "https://dev.to/feed/tag/ai",
        "category": ContentCategory.blog_post,
        "favicon": "https://dev.to/favicon.ico",
    },
    {
        "name": "Dev.to – machinelearning",
        "url": "https://dev.to/feed/tag/machinelearning",
        "category": ContentCategory.blog_post,
        "favicon": "https://dev.to/favicon.ico",
    },
    {
        "name": "Dev.to – llm",
        "url": "https://dev.to/feed/tag/llm",
        "category": ContentCategory.blog_post,
        "favicon": "https://dev.to/favicon.ico",
    },
    {
        "name": "Mastodon – #ai (mastodon.social)",
        "url": "https://mastodon.social/tags/ai.rss",
        "category": ContentCategory.community,
        "favicon": "https://mastodon.social/favicon.ico",
    },
    {
        "name": "Mastodon – #machinelearning (mastodon.social)",
        "url": "https://mastodon.social/tags/machinelearning.rss",
        "category": ContentCategory.community,
        "favicon": "https://mastodon.social/favicon.ico",
    },
]


def _clean_content(raw: str, is_reddit: bool = False) -> str:
    """Strip boilerplate and HTML so raw_content is human-readable."""
    text = re.sub(r"<[^>]+>", " ", raw)                      # strip HTML tags
    text = re.sub(r"arXiv:\S+\s*", "", text, flags=re.I)     # arXiv IDs
    text = re.sub(r"Announce Type:\s*\w+\.?\s*", "", text, flags=re.I)
    text = re.sub(r"^Abstract:\s*", "", text.strip(), flags=re.I)
    if is_reddit:
        # Reddit HTML entities and boilerplate
        text = re.sub(r"&#\d+;", " ", text)                  # &#32; &#x200b; etc.
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"submitted by\s*/u/\S+", "", text, flags=re.I)
        text = re.sub(r"\[link\]", "", text)
        text = re.sub(r"\[comments\]", "", text)
        text = re.sub(r"/u/\S+", "", text)                   # remaining user mentions
        text = re.sub(r"/r/\S+", "", text)                   # subreddit mentions
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Reddit-specific skip patterns (AutoModerator sticky threads)
_REDDIT_SKIP_TITLES = re.compile(
    r"(self.promotion|who.s hiring|who wants to be hired|"
    r"monthly thread|weekly thread|discussion thread|"
    r"simple question|career advice|what are you working on)",
    re.I,
)
_REDDIT_SKIP_AUTHORS = {"automoderator", "/u/automoderator"}


def _parse_date(entry) -> Optional[datetime]:
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return parsedate_to_datetime(val).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def _entry_display_title(entry) -> str:
    """Use RSS title, or a snippet from summary/body (Mastodon / ActivityPub omit title)."""
    raw = entry.get("title")
    if raw:
        t = str(raw).strip()
        if t:
            return t
    summary = entry.get("summary") or ""
    content = entry.get("content")
    if isinstance(content, list) and content:
        summary = summary or (content[0].get("value", "") if isinstance(content[0], dict) else "")
    text = re.sub(r"<[^>]+>", " ", str(summary))
    text = re.sub(r"\s+", " ", text).strip()
    if text:
        return text[:280] + ("…" if len(text) > 280 else "")
    return ""


class RSSCrawler(BaseCrawler):
    async def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            tasks = [self._fetch_one(client, src) for src in RSS_SOURCES]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for src, result in zip(RSS_SOURCES, results):
            if isinstance(result, Exception):
                log.warning("rss_fetch_failed", source=src["name"], error=str(result))
                continue
            items.extend(result)

        return items

    async def _fetch_one(self, client: httpx.AsyncClient, src: dict) -> list[RawItem]:
        headers = {}
        if src.get("user_agent"):
            headers["User-Agent"] = src["user_agent"]
        resp = await client.get(src["url"], headers=headers)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        results = []
        is_reddit = "reddit.com" in src["url"]
        # Medium publishes hundreds/day — cap lower; Reddit cap at 25; others 30
        cap = 20 if "medium.com" in src["url"] else 25 if is_reddit else 30
        for entry in feed.entries[:cap]:
            url = entry.get("link", "")
            title = _entry_display_title(entry)
            if not url or not title:
                continue

            # Reddit-specific filters
            if is_reddit:
                author = (entry.get("author") or "").lower().strip()
                if author in _REDDIT_SKIP_AUTHORS:
                    continue
                if _REDDIT_SKIP_TITLES.search(title):
                    continue
            # Try to get OG image from media tags, fall back to source favicon
            thumbnail = None
            # 1. Try media tags (works for many RSS feeds)
            media = entry.get("media_thumbnail") or entry.get("media_content")
            if media and isinstance(media, list) and media[0].get("url"):
                thumbnail = media[0]["url"]
            # 2. Try extracting first <img> from the HTML description (Medium uses this)
            if not thumbnail:
                raw_html = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
                img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_html, re.I)
                if img_match:
                    candidate = img_match.group(1)
                    # Filter out tiny icons
                    if not any(x in candidate.lower() for x in ("favicon", "1x1", "pixel", ".ico")):
                        thumbnail = candidate
            # 3. Fall back to source favicon
            if not thumbnail:
                thumbnail = src.get("favicon")

            results.append(RawItem(
                title=title,
                url=url,
                category=src["category"],
                source_name=src["name"],
                source_url=src["url"],
                author=entry.get("author"),
                published_at=_parse_date(entry),
                raw_content=_clean_content(entry.get("summary", ""), is_reddit=is_reddit),
                thumbnail_url=thumbnail,
            ))
        log.info("rss_fetched", source=src["name"], count=len(results))
        return results
