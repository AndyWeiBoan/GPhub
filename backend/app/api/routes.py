"""FastAPI route definitions."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone, timedelta

from app.database import get_db, AsyncSessionLocal
from app.models import Item, Source, CrawlRun, ContentCategory, GithubSubcat, StarSnapshot
from app.crawlers.manager import run_crawl
from app.summarizer.claude import summarise_pending
from app.scoring.trending import compute_trending_scores

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    url: str
    author: Optional[str]
    published_at: Optional[datetime]
    fetched_at: datetime
    summary: Optional[str]
    raw_content: Optional[str]
    thumbnail_url: Optional[str]
    thumbnail_attribution: Optional[str]
    source_name: Optional[str]
    category: Optional[ContentCategory]
    github_subcat: Optional[GithubSubcat]
    github_stars: Optional[int]
    impact_score: float
    credibility_score: float
    novelty_score: float
    total_score: float
    is_summarized: bool


class ItemListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ItemOut]


class CategoryRankResponse(BaseModel):
    category: str
    items: list[ItemOut]


class TrendingItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    url: str
    author: Optional[str]
    published_at: Optional[datetime]
    fetched_at: datetime
    summary: Optional[str]
    raw_content: Optional[str]
    thumbnail_url: Optional[str]
    thumbnail_attribution: Optional[str]
    source_name: Optional[str]
    category: Optional[ContentCategory]
    github_subcat: Optional[GithubSubcat]
    github_stars: Optional[int]
    impact_score: float
    credibility_score: float
    novelty_score: float
    total_score: float
    trending_score: float   # computed on-the-fly
    cross_source_count: int


class CategoryTrend(BaseModel):
    category: str
    count_7d: int
    count_24h: int
    pct_of_total: float


class TrendingResponse(BaseModel):
    items: list[TrendingItemOut]
    category_trends: list[CategoryTrend]
    window_hours: int


class TopicLeadItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    url: str
    summary: Optional[str]
    raw_content: Optional[str]
    thumbnail_url: Optional[str]
    thumbnail_attribution: Optional[str]
    source_name: Optional[str]
    category: Optional[ContentCategory]
    published_at: Optional[datetime]
    fetched_at: datetime
    trending_score: float


class TopicOut(BaseModel):
    label: str
    count: int
    lead_item: TopicLeadItem


class TopicsResponse(BaseModel):
    topics: list[TopicOut]
    window_hours: int


class CrawlRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    started_at: datetime
    finished_at: Optional[datetime]
    items_fetched: int
    items_new: int
    status: str


class StatsOut(BaseModel):
    total_items: int
    total_sources: int
    last_crawl: Optional[datetime]
    categories: dict[str, int]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/items", response_model=ItemListResponse)
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[ContentCategory] = None,
    github_subcat: Optional[GithubSubcat] = None,
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    sort_by: str = Query("total_score", pattern="^(total_score|published_at|fetched_at|github_stars)$"),
    q: Optional[str] = Query(None, description="Keyword search on title"),
    source_name: Optional[str] = Query(None, description="Filter by exact source name"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Item).where(Item.total_score >= min_score)
    if category:
        stmt = stmt.where(Item.category == category)
    if github_subcat:
        stmt = stmt.where(Item.github_subcat == github_subcat)
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    if source_name:
        stmt = stmt.where(Item.source_name == source_name)

    sort_col = {
        "total_score": Item.total_score.desc(),
        "published_at": Item.published_at.desc(),
        "fetched_at": Item.fetched_at.desc(),
        "github_stars": Item.github_stars.desc(),
    }[sort_by]
    stmt = stmt.order_by(sort_col)

    count_q = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_q)).scalar_one()

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return ItemListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/sources")
async def list_sources(
    category: Optional[ContentCategory] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return distinct source names that have items, optionally filtered by category."""
    stmt = select(Item.source_name).where(Item.source_name.isnot(None))
    if category:
        stmt = stmt.where(Item.category == category)
    stmt = stmt.distinct().order_by(Item.source_name)
    result = await db.execute(stmt)
    names = [row[0] for row in result.all() if row[0]]
    return {"sources": names}


class SubcatRankResponse(BaseModel):
    subcategory: str
    items: list[ItemOut]


@router.get("/ranking", response_model=list[CategoryRankResponse])
async def get_ranking(
    top_n: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Return top N items per category, sorted by total_score."""
    categories = list(ContentCategory)
    result = []
    for cat in categories:
        rows = await db.execute(
            select(Item)
            .where(Item.category == cat)
            .order_by(Item.total_score.desc())
            .limit(top_n)
        )
        items = rows.scalars().all()
        if items:
            result.append(CategoryRankResponse(category=cat.value, items=items))
    return result


@router.get("/ranking/github", response_model=list[SubcatRankResponse])
async def get_github_ranking(
    top_n: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Return top N GitHub projects per subcategory, sorted by total_score.

    This is the authoritative subcategory ranking — subcategories are assigned
    at crawl time based on which targeted URL the repo was found on, not by
    keyword guessing.
    """
    result = []
    for subcat in GithubSubcat:
        rows = await db.execute(
            select(Item)
            .where(Item.category == ContentCategory.github_project)
            .where(Item.github_subcat == subcat)
            .order_by(Item.total_score.desc())
            .limit(top_n)
        )
        items = rows.scalars().all()
        if items:
            result.append(SubcatRankResponse(subcategory=subcat.value, items=items))
    return result


@router.get("/topics", response_model=TopicsResponse)
async def get_topics(
    top_k: int = Query(6, ge=1, le=12),
    window_hours: int = Query(168, ge=24, le=720),
    exclude: Optional[str] = Query(None, description="Comma-separated categories to exclude"),
    db: AsyncSession = Depends(get_db),
):
    """Return top trending AI topics with a lead article per topic."""
    from app.scoring.topics import extract_topics
    from app.scoring.trending import compute_trending_scores

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    stmt = select(Item).where(
        (Item.published_at >= cutoff) | (Item.fetched_at >= cutoff)
    )

    if exclude:
        cats = [c.strip() for c in exclude.split(",") if c.strip()]
        if cats:
            stmt = stmt.where(Item.category.notin_(cats))

    rows = await db.execute(stmt)
    pool = rows.scalars().all()

    if not pool:
        return TopicsResponse(topics=[], window_hours=window_hours)

    scores = compute_trending_scores(pool)
    topic_results = extract_topics(pool, top_k=top_k)

    out = []
    for t in topic_results:
        lead = t.lead_item
        out.append(TopicOut(
            label=t.label,
            count=t.count,
            lead_item=TopicLeadItem(
                id=str(lead.id),
                title=lead.title,
                url=lead.url,
                summary=lead.summary,
                raw_content=lead.raw_content,
                thumbnail_url=lead.thumbnail_url,
                thumbnail_attribution=lead.thumbnail_attribution,
                source_name=lead.source_name,
                category=lead.category,
                published_at=lead.published_at,
                fetched_at=lead.fetched_at,
                trending_score=scores.get(lead.id, 0),
            ),
        ))

    return TopicsResponse(topics=out, window_hours=window_hours)


@router.get("/trending", response_model=TrendingResponse)
async def get_trending(
    top_n: int = Query(10, ge=1, le=30),
    window_hours: int = Query(168, ge=24, le=720),  # default 7 days
    exclude: Optional[str] = Query(None, description="Comma-separated categories to exclude, e.g. research_paper"),
    include: Optional[str] = Query(None, description="Comma-separated categories to include only"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return top N trending items. Optionally filter by category via
    exclude= or include= (comma-separated ContentCategory values).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    q = select(Item).where(
        (Item.published_at >= cutoff) | (Item.fetched_at >= cutoff)
    )

    if include:
        cats = [c.strip() for c in include.split(",") if c.strip()]
        q = q.where(Item.category.in_(cats))
    elif exclude:
        cats = [c.strip() for c in exclude.split(",") if c.strip()]
        q = q.where(Item.category.notin_(cats))

    rows = await db.execute(q)
    pool = rows.scalars().all()

    if not pool:
        return TrendingResponse(items=[], category_trends=[], window_hours=window_hours)

    # Compute trending scores
    scores = compute_trending_scores(pool)

    # Build coverage counts for response
    from app.scoring.trending import _build_coverage_map
    coverage = _build_coverage_map(pool)

    # ── Diversity-aware top-N selection ──────────────────────────────────────
    # Sort full pool by trending score
    all_ranked = sorted(pool, key=lambda x: scores.get(x.id, 0), reverse=True)

    # Reserve 1 guaranteed slot for each category that has items in the window
    active_cats = list({item.category for item in pool if item.category})
    guaranteed: list = []
    guaranteed_ids: set = set()

    for cat in active_cats:
        # Best item of this category not yet picked
        best = next((i for i in all_ranked if i.category == cat and i.id not in guaranteed_ids), None)
        if best:
            guaranteed.append(best)
            guaranteed_ids.add(best.id)

    # Fill remaining slots with pure trending-score order (skip already picked)
    remaining_slots = top_n - len(guaranteed)
    extras = [i for i in all_ranked if i.id not in guaranteed_ids][:max(remaining_slots, 0)]

    # Merge: guaranteed first (sorted by score), then extras
    guaranteed.sort(key=lambda x: scores.get(x.id, 0), reverse=True)
    ranked = (guaranteed + extras)[:top_n]

    out_items = [
        TrendingItemOut(
            **{c.key: getattr(item, c.key) for c in Item.__table__.columns
               if c.key not in ("embedding",)},
            trending_score=scores.get(item.id, 0),
            cross_source_count=coverage.get(item.id, 1),
        )
        for item in ranked
    ]

    # Category trends
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    cat_7d_rows = await db.execute(
        select(Item.category, func.count(Item.id))
        .where((Item.published_at >= cutoff) | (Item.fetched_at >= cutoff))
        .group_by(Item.category)
    )
    cat_24h_rows = await db.execute(
        select(Item.category, func.count(Item.id))
        .where((Item.published_at >= cutoff_24h) | (Item.fetched_at >= cutoff_24h))
        .group_by(Item.category)
    )
    total_7d_count = (await db.execute(
        select(func.count(Item.id))
        .where((Item.published_at >= cutoff) | (Item.fetched_at >= cutoff))
    )).scalar_one() or 1

    map_7d = {row[0]: row[1] for row in cat_7d_rows.all()}
    map_24h = {row[0]: row[1] for row in cat_24h_rows.all()}

    category_trends = [
        CategoryTrend(
            category=cat.value,
            count_7d=map_7d.get(cat, 0),
            count_24h=map_24h.get(cat, 0),
            pct_of_total=round(map_7d.get(cat, 0) / total_7d_count * 100, 1),
        )
        for cat in ContentCategory
        if map_7d.get(cat, 0) > 0
    ]
    category_trends.sort(key=lambda x: x.count_7d, reverse=True)

    return TrendingResponse(
        items=out_items,
        category_trends=category_trends,
        window_hours=window_hours,
    )


@router.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.get("/stats", response_model=StatsOut)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_items = (await db.execute(select(func.count(Item.id)))).scalar_one()
    total_sources = (await db.execute(select(func.count(Source.id)))).scalar_one()

    last_run = (await db.execute(
        select(CrawlRun.finished_at)
        .where(CrawlRun.status.in_(["success", "partial"]))
        .order_by(CrawlRun.finished_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    cat_rows = (await db.execute(
        select(Item.category, func.count(Item.id))
        .group_by(Item.category)
    )).all()
    categories = {(row[0].value if row[0] else "unknown"): row[1] for row in cat_rows}

    return StatsOut(
        total_items=total_items,
        total_sources=total_sources,
        last_crawl=last_run,
        categories=categories,
    )


@router.get("/crawl-runs", response_model=list[CrawlRunOut])
async def list_crawl_runs(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CrawlRun).order_by(CrawlRun.started_at.desc()).limit(limit)
    )
    return result.scalars().all()


@router.post("/trigger-crawl")
async def trigger_crawl(background_tasks: BackgroundTasks):
    """Manually trigger a crawl + OG enrichment + Pexels + summarise run."""
    from app.crawlers.og_fetcher import enrich_thumbnails
    from app.crawlers.pexels_fetcher import enrich_with_pexels

    async def _run():
        async with AsyncSessionLocal() as db:
            await run_crawl(db)
        async with AsyncSessionLocal() as db:
            await enrich_thumbnails(db, batch=50)
        async with AsyncSessionLocal() as db:
            await enrich_with_pexels(db)
        async with AsyncSessionLocal() as db:
            await summarise_pending(db)

    background_tasks.add_task(_run)
    return {"message": "Crawl triggered in background"}


@router.post("/trigger-pexels")
async def trigger_pexels(background_tasks: BackgroundTasks):
    """Manually run only the Pexels enrichment pass (for backfilling)."""
    from app.crawlers.pexels_fetcher import enrich_with_pexels

    async def _run():
        async with AsyncSessionLocal() as db:
            n = await enrich_with_pexels(db)
            log.info("manual_pexels_done", count=n)

    background_tasks.add_task(_run)
    return {"message": "Pexels enrichment triggered"}


class GithubRisingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    url: str
    summary: Optional[str]
    thumbnail_url: Optional[str]
    source_name: Optional[str]
    github_subcat: Optional[GithubSubcat]
    github_stars: Optional[int]
    star_delta: int          # stars gained in the window
    star_delta_pct: float    # percentage growth
    total_score: float


class GithubRisingResponse(BaseModel):
    items: list[GithubRisingItem]
    window_hours: int


@router.get("/github-rising", response_model=GithubRisingResponse)
async def get_github_rising(
    top_n: int = Query(10, ge=1, le=30),
    window_hours: int = Query(48, ge=6, le=336),
    db: AsyncSession = Depends(get_db),
):
    """Return GitHub repos ranked by star growth (delta) over the past window_hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    # For each item, get the latest snapshot and the oldest snapshot within the window
    from sqlalchemy import and_

    # Fetch all GitHub items that have snapshots
    rows = await db.execute(
        select(Item).where(Item.category == ContentCategory.github_project)
    )
    github_items = {str(item.id): item for item in rows.scalars().all()}

    if not github_items:
        return GithubRisingResponse(items=[], window_hours=window_hours)

    # Fetch all snapshots within window for these items
    snap_rows = await db.execute(
        select(StarSnapshot).where(
            and_(
                StarSnapshot.item_id.in_(list(github_items.keys())),
                StarSnapshot.recorded_at >= cutoff,
            )
        ).order_by(StarSnapshot.item_id, StarSnapshot.recorded_at.asc())
    )
    snapshots = snap_rows.scalars().all()

    # Also fetch the most recent snapshot before the window (baseline)
    baseline_rows = await db.execute(
        select(StarSnapshot).where(
            and_(
                StarSnapshot.item_id.in_(list(github_items.keys())),
                StarSnapshot.recorded_at < cutoff,
            )
        ).order_by(StarSnapshot.item_id, StarSnapshot.recorded_at.desc())
    )
    baselines_raw = baseline_rows.scalars().all()

    # Keep only the latest baseline per item
    baselines: dict[str, int] = {}
    for snap in baselines_raw:
        iid = str(snap.item_id)
        if iid not in baselines:
            baselines[iid] = snap.stars

    # Group window snapshots by item
    from collections import defaultdict
    window_snaps: dict[str, list] = defaultdict(list)
    for snap in snapshots:
        window_snaps[str(snap.item_id)].append(snap)

    results = []
    for item_id, snaps in window_snaps.items():
        item = github_items.get(item_id)
        if not item:
            continue

        latest_stars = snaps[-1].stars
        # Baseline: oldest snapshot before the window, or first snapshot in window
        baseline_stars = baselines.get(item_id, snaps[0].stars)

        delta = latest_stars - baseline_stars
        if delta <= 0:
            continue

        delta_pct = round((delta / baseline_stars * 100) if baseline_stars > 0 else 0.0, 1)

        results.append(GithubRisingItem(
            id=str(item.id),
            title=item.title,
            url=item.url,
            summary=item.summary,
            thumbnail_url=item.thumbnail_url,
            source_name=item.source_name,
            github_subcat=item.github_subcat,
            github_stars=latest_stars,
            star_delta=delta,
            star_delta_pct=delta_pct,
            total_score=float(item.total_score or 0),
        ))

    # Sort by absolute delta desc
    results.sort(key=lambda x: x.star_delta, reverse=True)

    return GithubRisingResponse(items=results[:top_n], window_hours=window_hours)


@router.post("/backfill-star-snapshots")
async def backfill_star_snapshots(background_tasks: BackgroundTasks):
    """Backfill star_snapshots from existing github_stars on items.

    Writes one baseline snapshot per GitHub item (recorded 3 days ago),
    so the next crawl can compute a meaningful delta.
    Only runs for items that have no snapshot yet.
    """
    async def _run():
        from sqlalchemy import and_
        baseline_time = datetime.now(timezone.utc) - timedelta(days=3)
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(Item).where(
                    and_(
                        Item.category == ContentCategory.github_project,
                        Item.github_stars.isnot(None),
                    )
                )
            )
            items = rows.scalars().all()

            # Find items that already have at least one snapshot
            existing = await db.execute(
                select(StarSnapshot.item_id).distinct()
            )
            already_snapped = {str(r[0]) for r in existing.all()}

            count = 0
            for item in items:
                if str(item.id) in already_snapped:
                    continue
                db.add(StarSnapshot(
                    item_id=item.id,
                    stars=item.github_stars,
                    recorded_at=baseline_time,
                ))
                count += 1

            await db.commit()
            log.info("star_snapshot_backfill_done", count=count)

    background_tasks.add_task(_run)
    return {"message": "Star snapshot backfill triggered in background"}


@router.post("/trigger-rescore")
async def trigger_rescore(background_tasks: BackgroundTasks):
    """Re-compute impact/credibility/novelty/total_score for every item in the DB.

    Useful after:
    - A fresh crawl (novelty scores have decayed since items were first stored)
    - Tuning the scoring weights in config
    - Backfilling new items that arrived without proper signals
    """
    from app.scoring.engine import score_item

    async def _run():
        async with AsyncSessionLocal() as db:
            # Load all sources for credibility lookup
            sources_result = await db.execute(select(Source))
            sources_by_id = {str(s.id): s for s in sources_result.scalars().all()}

            # Stream items in batches to avoid loading everything into memory
            BATCH = 200
            offset = 0
            total_updated = 0

            while True:
                rows = await db.execute(
                    select(Item).order_by(Item.created_at).offset(offset).limit(BATCH)
                )
                batch = rows.scalars().all()
                if not batch:
                    break

                for item in batch:
                    source = sources_by_id.get(str(item.source_id))
                    scores = score_item(item, source)
                    item.impact_score = scores["impact"]
                    item.credibility_score = scores["credibility"]
                    item.novelty_score = scores["novelty"]
                    item.total_score = scores["total"]

                await db.commit()
                total_updated += len(batch)
                offset += BATCH

            log.info("rescore_complete", total_updated=total_updated)

    background_tasks.add_task(_run)
    return {"message": "Full rescore triggered in background"}
