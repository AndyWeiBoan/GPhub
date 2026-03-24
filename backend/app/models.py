import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Numeric,
    DateTime, ForeignKey, Enum as SAEnum, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import types
from app.database import Base, _is_sqlite


# ── Portable UUID column ──────────────────────────────────────────────────────
# PostgreSQL uses native UUID; SQLite stores as string.
def _uuid_col(primary_key=False, fk=None):
    if _is_sqlite:
        col_type = String(36)
    else:
        col_type = PG_UUID(as_uuid=True)

    kwargs = dict(primary_key=primary_key, default=lambda: str(uuid.uuid4()))
    if fk:
        return Column(col_type, ForeignKey(fk, ondelete="SET NULL"), **kwargs)
    return Column(col_type, **kwargs)


# ── Enums ─────────────────────────────────────────────────────────────────────

class SourceTier(str, enum.Enum):
    tier1 = "tier1"
    tier2 = "tier2"
    tier3 = "tier3"


class ContentCategory(str, enum.Enum):
    research_paper = "research_paper"
    news_article = "news_article"
    blog_post = "blog_post"
    community = "community"
    product_launch = "product_launch"
    github_project = "github_project"


class GithubSubcat(str, enum.Enum):
    llm     = "llm"       # Open-source LLMs, fine-tuning, foundational models
    agent   = "agent"     # AI agents, multi-agent, agentic workflows
    context = "context"   # MCP, RAG, vector stores, memory
    vision  = "vision"    # Image generation, diffusion, multimodal, CV
    tool    = "tool"      # Dev tools, frameworks, SDKs, infra, benchmarks


# ── Models ────────────────────────────────────────────────────────────────────

class Source(Base):
    __tablename__ = "sources"

    id = _uuid_col(primary_key=True)
    name = Column(String(255), nullable=False)
    url = Column(Text, nullable=False, unique=True)
    tier = Column(SAEnum(SourceTier), nullable=False, default=SourceTier.tier2)
    category = Column(SAEnum(ContentCategory), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Item(Base):
    __tablename__ = "items"

    id = _uuid_col(primary_key=True)
    source_id = Column(
        String(36) if _is_sqlite else PG_UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False, unique=True)
    author = Column(String(255))
    published_at = Column(DateTime(timezone=True))
    fetched_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    raw_content = Column(Text)
    summary = Column(Text)
    thumbnail_url = Column(Text)
    thumbnail_attribution = Column(Text)   # "Photo by X on Pexels" + pexels page URL
    source_name = Column(String(255))
    category = Column(SAEnum(ContentCategory))
    github_subcat = Column(SAEnum(GithubSubcat), nullable=True)   # only set for github_project

    github_stars = Column(Integer)
    social_shares = Column(Integer)
    citations = Column(Integer)

    impact_score = Column(Numeric(4, 3), default=0)
    credibility_score = Column(Numeric(4, 3), default=0)
    novelty_score = Column(Numeric(4, 3), default=0)
    total_score = Column(Numeric(4, 3), default=0)

    # embedding omitted for SQLite; add pgvector column in a migration when on PostgreSQL
    is_summarized = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class StarSnapshot(Base):
    """One row per (item, crawl) — records github_stars at a point in time."""
    __tablename__ = "star_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(
        String(36) if _is_sqlite else PG_UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
    )
    stars = Column(Integer, nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id = _uuid_col(primary_key=True)
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at = Column(DateTime(timezone=True))
    items_fetched = Column(Integer, default=0)
    items_new = Column(Integer, default=0)
    errors = Column(JSON, default=list)   # JSON works on both SQLite & PG
    status = Column(String(50), default="running")
