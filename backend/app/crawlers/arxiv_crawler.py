"""arXiv API crawler — replaces the arXiv RSS feeds.

Uses the official arXiv Atom API (no auth required) which supports:
- Precise category + keyword queries
- Sorting by submittedDate (most recent first)
- Pagination

We query four AI-relevant categories simultaneously and deduplicate by arxiv ID.
The API is free and has no rate limit for reasonable usage (3 req/sec guideline).

Docs: https://arxiv.org/help/api/user-manual
"""
import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
import httpx
import structlog

from app.crawlers.base import BaseCrawler, RawItem
from app.models import ContentCategory

log = structlog.get_logger()

ARXIV_API_BASE = "https://export.arxiv.org/api/query"
ARXIV_FAVICON  = "https://arxiv.org/favicon.ico"

# Categories to fetch and how many per category
ARXIV_QUERIES: list[tuple[str, int]] = [
    # (search_query, max_results)
    ("cat:cs.AI",  30),   # Artificial Intelligence
    ("cat:cs.LG",  30),   # Machine Learning
    ("cat:cs.CL",  20),   # Computation and Language (NLP)
    ("cat:cs.CV",  15),   # Computer Vision
    ("cat:cs.MA",  10),   # Multi-Agent Systems
]

# Atom namespace
_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

ABSTRACT_MAX = 800  # chars to keep from abstract


def _text(el: Optional[ET.Element]) -> str:
    return el.text.strip() if el is not None and el.text else ""


def _parse_feed(xml_text: str, source_query: str) -> list[RawItem]:
    """Parse an arXiv Atom feed into RawItems."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("arxiv_parse_error", error=str(e))
        return []

    items: list[RawItem] = []
    for entry in root.findall("atom:entry", _NS):
        # arXiv ID → canonical URL
        entry_id = _text(entry.find("atom:id", _NS))
        if not entry_id:
            continue
        # entry_id is like http://arxiv.org/abs/2310.12345v1
        abs_url = re.sub(r"v\d+$", "", entry_id)   # strip version suffix

        title = _text(entry.find("atom:title", _NS)).replace("\n", " ")
        summary = _text(entry.find("atom:summary", _NS)).replace("\n", " ")
        abstract = summary[:ABSTRACT_MAX]

        # Authors
        authors = [
            _text(a.find("atom:name", _NS))
            for a in entry.findall("atom:author", _NS)
        ]
        author_str = ", ".join(a for a in authors if a) or None

        # Published date
        published_raw = _text(entry.find("atom:published", _NS))
        published_at: Optional[datetime] = None
        if published_raw:
            try:
                published_at = datetime.fromisoformat(
                    published_raw.replace("Z", "+00:00")
                ).astimezone(timezone.utc)
            except ValueError:
                pass

        # Categories (for raw_content enrichment)
        cats = [
            c.get("term", "")
            for c in entry.findall("atom:category", _NS)
        ]
        cat_str = " ".join(c for c in cats if c)

        raw_content = f"{abstract}\n\nCategories: {cat_str}".strip()

        items.append(RawItem(
            title=title,
            url=abs_url,
            category=ContentCategory.research_paper,
            source_name="arXiv",
            source_url=f"{ARXIV_API_BASE}?{source_query}",
            author=author_str,
            published_at=published_at,
            raw_content=raw_content,
            thumbnail_url=ARXIV_FAVICON,
        ))

    return items


async def _fetch_query(
    client: httpx.AsyncClient,
    search_query: str,
    max_results: int,
) -> list[RawItem]:
    params = {
        "search_query": search_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    try:
        resp = await client.get(ARXIV_API_BASE, params=params, timeout=30.0)
        resp.raise_for_status()
        items = _parse_feed(resp.text, search_query)
        log.info("arxiv_fetched", query=search_query, count=len(items))
        return items
    except Exception as e:
        log.warning("arxiv_fetch_failed", query=search_query, error=str(e))
        return []


class ArXivCrawler(BaseCrawler):
    """Fetch recent papers from arXiv across AI-relevant categories."""

    async def fetch(self) -> list[RawItem]:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Stagger requests slightly to be polite (3 req/sec guideline)
            all_items: list[RawItem] = []
            for query, max_results in ARXIV_QUERIES:
                batch = await _fetch_query(client, query, max_results)
                all_items.extend(batch)
                await asyncio.sleep(0.4)

        # Deduplicate by URL (same paper can appear in multiple categories)
        seen: set[str] = set()
        deduped: list[RawItem] = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                deduped.append(item)

        log.info("arxiv_total", before=len(all_items), after=len(deduped))
        return deduped
