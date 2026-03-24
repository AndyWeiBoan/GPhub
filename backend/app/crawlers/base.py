"""Base crawler interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from app.models import ContentCategory, GithubSubcat


@dataclass
class RawItem:
    title: str
    url: str
    category: ContentCategory
    source_name: str
    source_url: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    raw_content: Optional[str] = None
    github_stars: Optional[int] = None
    social_shares: Optional[int] = None
    citations: Optional[int] = None
    thumbnail_url: Optional[str] = None
    github_subcat: Optional[GithubSubcat] = None


class BaseCrawler(ABC):
    """All crawlers must implement this interface."""

    @abstractmethod
    async def fetch(self) -> list[RawItem]:
        """Fetch items from this source and return raw items."""
        ...
