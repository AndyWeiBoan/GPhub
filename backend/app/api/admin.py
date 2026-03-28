"""Admin API routes — backoffice operations."""

import uuid as _uuid
from typing import Optional, Literal
from datetime import datetime

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.models import Item, Source, CrawlRun, ContentCategory, SourceTier
from app.crawlers.manager import run_crawl, CRAWLER_MAP, ALL_CRAWLERS
from app.crawlers.og_fetcher import enrich_thumbnails
from app.crawlers.pexels_fetcher import enrich_with_pexels
from app.summarizer.claude import summarise_pending
from app.summarizer.comment_generator import run_comment_generation, _build_client
from app.summarizer.digest_generator import run_digest_generation
from app.summarizer.gemini import GeminiClient
from app.scoring.engine import score_item

log = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"])


# ── Job store (in-memory) ────────────────────────────────────────────────────
# Maps job_id → JobStatus dict. Simple enough; no persistence needed.

JobPhase = Literal["pending", "running", "done", "error"]


class JobStatus(BaseModel):
    job_id: str
    label: str  # human-readable name e.g. "Run All Crawlers"
    phase: JobPhase = "pending"
    steps: list[dict] = []  # [{name, status, detail}]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[dict] = None  # summary numbers on completion


_jobs: dict[str, JobStatus] = {}
_MAX_JOBS = 50  # keep last N jobs


def _new_job(label: str, steps: list[str]) -> JobStatus:
    jid = str(_uuid.uuid4())[:8]
    job = JobStatus(
        job_id=jid,
        label=label,
        phase="pending",
        steps=[{"name": s, "status": "pending", "detail": ""} for s in steps],
    )
    _jobs[jid] = job
    # Prune old jobs
    if len(_jobs) > _MAX_JOBS:
        oldest = list(_jobs.keys())[0]
        _jobs.pop(oldest, None)
    return job


def _step_start(job: JobStatus, idx: int) -> None:
    job.steps[idx]["status"] = "running"
    if job.phase == "pending":
        job.phase = "running"
        job.started_at = datetime.utcnow()


def _step_done(job: JobStatus, idx: int, detail: str = "") -> None:
    job.steps[idx]["status"] = "done"
    job.steps[idx]["detail"] = detail


def _step_error(job: JobStatus, idx: int, detail: str) -> None:
    job.steps[idx]["status"] = "error"
    job.steps[idx]["detail"] = detail


def _job_done(job: JobStatus, result: dict | None = None) -> None:
    job.phase = "done"
    job.finished_at = datetime.utcnow()
    job.result = result


def _job_error(job: JobStatus, error: str) -> None:
    job.phase = "error"
    job.finished_at = datetime.utcnow()
    job.error = error


# ── Schemas ───────────────────────────────────────────────────────────────────


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str
    tier: SourceTier
    category: ContentCategory
    is_active: bool
    created_at: Optional[datetime]
    item_count: int = 0


class SourceCreate(BaseModel):
    name: str
    url: str
    tier: SourceTier = SourceTier.tier2
    category: ContentCategory
    is_active: bool = True


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    tier: Optional[SourceTier] = None
    category: Optional[ContentCategory] = None
    is_active: Optional[bool] = None


class CrawlRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    started_at: datetime
    finished_at: Optional[datetime]
    items_fetched: int
    items_new: int
    status: str
    errors: list


class AdminStatsOut(BaseModel):
    total_items: int
    total_sources: int
    active_sources: int
    last_crawl: Optional[datetime]
    categories: dict[str, int]
    items_by_source: dict[str, int]


# ── Job status endpoint ───────────────────────────────────────────────────────


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs", response_model=list[JobStatus])
async def list_jobs(limit: int = Query(10, ge=1, le=50)):
    recent = list(reversed(list(_jobs.values())))
    return recent[:limit]


# ── Crawl triggers ────────────────────────────────────────────────────────────

COMMENT_STEPS = ["AI 短評生成"]
DIGEST_STEPS  = ["AI 週報摘要生成"]

FULL_CRAWL_STEPS = [
    "爬蟲 (RSS + GitHub + Anthropic)",   # 0 — Phase 1
    "OG 圖片補全",                         # 1 — Phase 2a ∥
    "AI 摘要 (Claude)",                   # 2 — Phase 2b ∥
    "Pexels 圖片",                         # 3 — Phase 3a ∥
    "AI 短評 (Gemini)",                   # 4 — Phase 3b ∥
    "週報摘要 (Gemini)",                   # 5 — Phase 4
]
SINGLE_CRAWL_STEPS = ["爬蟲", "OG 圖片補全"]
RESCORE_STEPS = ["重新評分"]


@router.post("/trigger-crawl")
async def trigger_crawl_all(background_tasks: BackgroundTasks):
    job = _new_job("Run All Crawlers", FULL_CRAWL_STEPS)

    async def _run():
        try:
            from app.config import settings as _settings

            # ── Phase 1: Crawl ────────────────────────────────────────────────
            _step_start(job, 0)
            async with AsyncSessionLocal() as db:
                r = await run_crawl(db)
            _step_done(job, 0, f"抓取 {r['fetched']}，新增 {r['new']} 筆")

            # ── Phase 2: OG ∥ Claude (parallel) ──────────────────────────────
            async def _og():
                _step_start(job, 1)
                async with AsyncSessionLocal() as db:
                    n = await enrich_thumbnails(db, batch=50)
                _step_done(job, 1, f"補全 {n} 張")
                return n

            async def _claude():
                _step_start(job, 2)
                async with AsyncSessionLocal() as db:
                    n = await summarise_pending(db)
                _step_done(job, 2, f"摘要 {n} 筆")
                return n

            await asyncio.gather(_og(), _claude())

            # ── Phase 3: Pexels ∥ AI comments (parallel) ─────────────────────
            # Groq for comments (14,400 req/day), Gemini for digest (quality)
            comment_client = _build_client()
            gemini_client = GeminiClient(
                api_key=_settings.GEMINI_API_KEY,
                model=_settings.GEMINI_MODEL,
            ) if _settings.GEMINI_API_KEY else None

            async def _pexels():
                _step_start(job, 3)
                async with AsyncSessionLocal() as db:
                    n = await enrich_with_pexels(db)
                _step_done(job, 3, f"Pexels {n} 張")
                return n

            async def _ai_comments():
                if not comment_client:
                    _step_done(job, 4, "跳過 (無 LLM API key)")
                    return 0
                _step_start(job, 4)
                async with AsyncSessionLocal() as db:
                    n = await run_comment_generation(db=db, client=comment_client)
                _step_done(job, 4, f"短評 {n} 筆 ({comment_client.model_label})")
                return n

            await asyncio.gather(_pexels(), _ai_comments())

            # ── Phase 4: Gemini digest (sequential — quality reasoning) ────────
            if gemini_client:
                _step_start(job, 5)
                async with AsyncSessionLocal() as db:
                    nd = await run_digest_generation(db=db, gemini=gemini_client)
                _step_done(job, 5, f"週報 {nd} 則")
            else:
                _step_done(job, 5, "跳過 (無 GEMINI_API_KEY)")

            _job_done(job, {"fetched": r["fetched"], "new": r["new"]})
        except Exception as e:
            _job_error(job, str(e))
            log.error("admin_crawl_all_failed", error=str(e))

    background_tasks.add_task(_run)
    return {"job_id": job.job_id, "message": "All crawlers triggered"}


@router.post("/trigger-crawl/{crawler_name}")
async def trigger_crawl_one(crawler_name: str, background_tasks: BackgroundTasks):
    if crawler_name not in CRAWLER_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown crawler '{crawler_name}'. Valid: {list(CRAWLER_MAP.keys())}",
        )
    CrawlerClass = CRAWLER_MAP[crawler_name]
    job = _new_job(f"Run {crawler_name.upper()} Crawler", SINGLE_CRAWL_STEPS)

    async def _run():
        try:
            _step_start(job, 0)
            async with AsyncSessionLocal() as db:
                r = await run_crawl(db, crawlers=[CrawlerClass])
            _step_done(job, 0, f"抓取 {r['fetched']}，新增 {r['new']} 筆")

            _step_start(job, 1)
            async with AsyncSessionLocal() as db:
                n = await enrich_thumbnails(db, batch=50)
            _step_done(job, 1, f"補全 {n} 張")

            _job_done(job, {"fetched": r["fetched"], "new": r["new"]})
        except Exception as e:
            _job_error(job, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job.job_id, "message": f"Crawler '{crawler_name}' triggered"}


@router.post("/trigger-crawl-category/{category}")
async def trigger_crawl_category(category: str, background_tasks: BackgroundTasks):
    try:
        cat = ContentCategory(category)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown category '{category}'. Valid: {[c.value for c in ContentCategory]}",
        )

    category_crawler_map: dict[ContentCategory, list] = {
        ContentCategory.research_paper: [CRAWLER_MAP["rss"]],
        ContentCategory.news_article: [CRAWLER_MAP["rss"]],
        ContentCategory.blog_post: [CRAWLER_MAP["rss"], CRAWLER_MAP["anthropic"]],
        ContentCategory.community: [CRAWLER_MAP["rss"]],
        ContentCategory.product_launch: [CRAWLER_MAP["rss"]],
        ContentCategory.github_project: [CRAWLER_MAP["github"]],
    }
    crawlers = category_crawler_map.get(cat, ALL_CRAWLERS)
    names = ", ".join(c.__name__.replace("Crawler", "") for c in crawlers)
    job = _new_job(f"Crawl Category: {category}", SINGLE_CRAWL_STEPS)

    async def _run():
        try:
            _step_start(job, 0)
            async with AsyncSessionLocal() as db:
                r = await run_crawl(db, crawlers=crawlers)
            _step_done(job, 0, f"抓取 {r['fetched']}，新增 {r['new']} 筆 (via {names})")

            _step_start(job, 1)
            async with AsyncSessionLocal() as db:
                n = await enrich_thumbnails(db, batch=50)
            _step_done(job, 1, f"補全 {n} 張")

            _job_done(job, {"fetched": r["fetched"], "new": r["new"]})
        except Exception as e:
            _job_error(job, str(e))

    background_tasks.add_task(_run)
    return {
        "job_id": job.job_id,
        "message": f"Crawlers for category '{category}' triggered",
        "crawlers": [c.__name__ for c in crawlers],
    }


# ── Rescore ───────────────────────────────────────────────────────────────────


@router.post("/trigger-rescore")
async def trigger_rescore(background_tasks: BackgroundTasks):
    job = _new_job("Rescore All Items", RESCORE_STEPS)

    async def _run():
        try:
            _step_start(job, 0)
            async with AsyncSessionLocal() as db:
                sources_result = await db.execute(select(Source))
                sources_by_id = {str(s.id): s for s in sources_result.scalars().all()}

                BATCH = 200
                offset = 0
                total_updated = 0
                while True:
                    rows = await db.execute(
                        select(Item)
                        .order_by(Item.created_at)
                        .offset(offset)
                        .limit(BATCH)
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
                    # Update detail in real-time
                    job.steps[0]["detail"] = f"已處理 {total_updated} 筆…"

            _step_done(job, 0, f"共更新 {total_updated} 筆")
            _job_done(job, {"total_updated": total_updated})
            log.info("admin_rescore_complete", total_updated=total_updated)
        except Exception as e:
            _job_error(job, str(e))

    background_tasks.add_task(_run)
    return {"job_id": job.job_id, "message": "Full rescore triggered"}


# ── AI workload triggers ──────────────────────────────────────────────────────


@router.post("/trigger-comments")
async def trigger_comments(background_tasks: BackgroundTasks):
    """Standalone trigger: generate AI comments for pending items."""
    job = _new_job("Generate AI Comments", COMMENT_STEPS)

    async def _run():
        try:
            from app.config import settings as _settings
            client = _build_client()
            if not client:
                _step_done(job, 0, "跳過 (無 LLM API key)")
                _job_done(job, {"commented": 0})
                return

            _step_start(job, 0)
            async with AsyncSessionLocal() as db:
                n = await run_comment_generation(db=db, client=client)
            _step_done(job, 0, f"{n} 筆 ({client.model_label})")
            _job_done(job, {"commented": n})
        except Exception as e:
            _job_error(job, str(e))
            log.error("admin_trigger_comments_failed", error=str(e))

    background_tasks.add_task(_run)
    return {"job_id": job.job_id, "message": "Comment generation triggered"}


@router.post("/trigger-comments/{category}")
async def trigger_comments_by_category(category: str, background_tasks: BackgroundTasks):
    """Standalone trigger: generate AI comments for a specific category only."""
    # Validate category
    valid_cats = {c.value for c in ContentCategory}
    if category not in valid_cats:
        raise HTTPException(status_code=422, detail=f"Invalid category: {category}. Valid: {sorted(valid_cats)}")

    job = _new_job(f"Generate AI Comments · {category}", COMMENT_STEPS)

    async def _run():
        try:
            _step_start(job, 0)
            async with AsyncSessionLocal() as db:
                # Pass no client — let run_comment_generation pick the right
                # provider per category (Gemini for github_project, fast clients otherwise)
                n = await run_comment_generation(db=db, only_category=category)
            _step_done(job, 0, f"{n} 筆")
            _job_done(job, {"commented": n})
        except Exception as e:
            _job_error(job, str(e))
            log.error("admin_trigger_comments_category_failed", category=category, error=str(e))

    background_tasks.add_task(_run)
    return {"job_id": job.job_id, "message": f"Comment generation triggered for {category}"}


@router.post("/trigger-digest")
async def trigger_digest(background_tasks: BackgroundTasks):
    """Standalone trigger: regenerate this week's AI digest."""
    job = _new_job("Generate Weekly Digest", DIGEST_STEPS)

    async def _run():
        try:
            from app.config import settings as _settings
            if not _settings.GEMINI_API_KEY:
                _step_done(job, 0, "跳過 (無 GEMINI_API_KEY)")
                _job_done(job, {"digests": 0})
                return

            gemini = GeminiClient(
                api_key=_settings.GEMINI_API_KEY,
                model=_settings.GEMINI_MODEL,
            )
            _step_start(job, 0)
            async with AsyncSessionLocal() as db:
                n = await run_digest_generation(db=db, gemini=gemini)
            _step_done(job, 0, f"{n} 則")
            _job_done(job, {"digests": n})
        except Exception as e:
            _job_error(job, str(e))
            log.error("admin_trigger_digest_failed", error=str(e))

    background_tasks.add_task(_run)
    return {"job_id": job.job_id, "message": "Digest generation triggered"}


# ── Sources CRUD ──────────────────────────────────────────────────────────────


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(
    category: Optional[ContentCategory] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Source)
    if category:
        stmt = stmt.where(Source.category == category)
    if is_active is not None:
        stmt = stmt.where(Source.is_active == is_active)
    stmt = stmt.order_by(Source.category, Source.name)

    result = await db.execute(stmt)
    sources = result.scalars().all()

    count_rows = await db.execute(
        select(Item.source_id, func.count(Item.id)).group_by(Item.source_id)
    )
    count_map = {str(row[0]): row[1] for row in count_rows.all()}

    out = []
    for s in sources:
        out.append(
            SourceOut(
                id=str(s.id),
                name=s.name,
                url=s.url,
                tier=s.tier,
                category=s.category,
                is_active=s.is_active,
                created_at=s.created_at,
                item_count=count_map.get(str(s.id), 0),
            )
        )
    return out


@router.get("/sources/{source_id}", response_model=SourceOut)
async def get_source(source_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    count = (
        await db.execute(select(func.count(Item.id)).where(Item.source_id == source_id))
    ).scalar_one()

    return SourceOut(
        id=str(source.id),
        name=source.name,
        url=source.url,
        tier=source.tier,
        category=source.category,
        is_active=source.is_active,
        created_at=source.created_at,
        item_count=count,
    )


@router.post("/sources", response_model=SourceOut, status_code=201)
async def create_source(body: SourceCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Source).where(Source.url == body.url))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Source with this URL already exists"
        )

    source = Source(
        id=str(_uuid.uuid4()),
        name=body.name,
        url=body.url,
        tier=body.tier,
        category=body.category,
        is_active=body.is_active,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    return SourceOut(
        id=str(source.id),
        name=source.name,
        url=source.url,
        tier=source.tier,
        category=source.category,
        is_active=source.is_active,
        created_at=source.created_at,
        item_count=0,
    )


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: str, body: SourceUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if body.name is not None:
        source.name = body.name
    if body.url is not None:
        source.url = body.url
    if body.tier is not None:
        source.tier = body.tier
    if body.category is not None:
        source.category = body.category
    if body.is_active is not None:
        source.is_active = body.is_active

    await db.commit()
    await db.refresh(source)

    count = (
        await db.execute(select(func.count(Item.id)).where(Item.source_id == source_id))
    ).scalar_one()

    return SourceOut(
        id=str(source.id),
        name=source.name,
        url=source.url,
        tier=source.tier,
        category=source.category,
        is_active=source.is_active,
        created_at=source.created_at,
        item_count=count,
    )


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await db.delete(source)
    await db.commit()


# ── Data management ───────────────────────────────────────────────────────────


@router.delete("/items")
async def delete_items_by_category(
    category: ContentCategory = Query(...),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(
        select(func.count(Item.id)).where(Item.category == category)
    )
    count = count_result.scalar_one()
    await db.execute(delete(Item).where(Item.category == category))
    await db.commit()
    log.info("admin_items_deleted", category=category.value, count=count)
    return {"deleted": count, "category": category.value}


# ── Stats ─────────────────────────────────────────────────────────────────────


@router.get("/stats", response_model=AdminStatsOut)
async def admin_stats(db: AsyncSession = Depends(get_db)):
    total_items = (await db.execute(select(func.count(Item.id)))).scalar_one()
    total_sources = (await db.execute(select(func.count(Source.id)))).scalar_one()
    active_sources = (
        await db.execute(select(func.count(Source.id)).where(Source.is_active == True))
    ).scalar_one()

    last_run = (
        await db.execute(
            select(CrawlRun.finished_at)
            .where(CrawlRun.status.in_(["success", "partial"]))
            .order_by(CrawlRun.finished_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    cat_rows = (
        await db.execute(
            select(Item.category, func.count(Item.id)).group_by(Item.category)
        )
    ).all()
    categories = {(r[0].value if r[0] else "unknown"): r[1] for r in cat_rows}

    source_rows = (
        await db.execute(
            select(Item.source_name, func.count(Item.id))
            .where(Item.source_name.isnot(None))
            .group_by(Item.source_name)
            .order_by(func.count(Item.id).desc())
            .limit(20)
        )
    ).all()
    items_by_source = {r[0]: r[1] for r in source_rows}

    return AdminStatsOut(
        total_items=total_items,
        total_sources=total_sources,
        active_sources=active_sources,
        last_crawl=last_run,
        categories=categories,
        items_by_source=items_by_source,
    )


@router.get("/crawl-runs", response_model=list[CrawlRunOut])
async def list_crawl_runs(
    limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CrawlRun).order_by(CrawlRun.started_at.desc()).limit(limit)
    )
    return result.scalars().all()
