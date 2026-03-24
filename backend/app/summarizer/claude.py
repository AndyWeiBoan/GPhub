"""
Summarisation service using Claude Haiku.
Processes un-summarised items in batches to stay within rate limits.
"""
import asyncio
import structlog
import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Item

log = structlog.get_logger()

SYSTEM_PROMPT = (
    "You are an expert AI research analyst. "
    "Given the title and raw content of an AI-related article, "
    "write a concise 2-3 sentence English summary that captures: "
    "1) what the main finding or product is, "
    "2) why it matters for the AI field, "
    "3) any key numbers or results if available. "
    "Be factual and neutral. Do not add opinions."
)

BATCH_SIZE = 10
RATE_LIMIT_DELAY = 0.5  # seconds between API calls


async def summarise_pending(db: AsyncSession) -> int:
    """Find items without summaries and generate them. Returns count processed."""
    result = await db.execute(
        select(Item)
        .where(Item.is_summarized == False)
        .where(Item.raw_content.isnot(None))
        .order_by(Item.total_score.desc())
        .limit(BATCH_SIZE)
    )
    items = result.scalars().all()

    if not items:
        return 0

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    processed = 0

    for item in items:
        try:
            summary = await _summarise_one(client, item)
            item.summary = summary
            item.is_summarized = True
            processed += 1
            await asyncio.sleep(RATE_LIMIT_DELAY)
        except Exception as e:
            log.warning("summarise_failed", item_id=str(item.id), error=str(e))

    await db.commit()
    log.info("summarise_complete", processed=processed)
    return processed


async def _summarise_one(client: anthropic.AsyncAnthropic, item: Item) -> str:
    content_preview = (item.raw_content or "")[:2000]
    user_message = f"Title: {item.title}\n\nContent:\n{content_preview}"

    message = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text.strip()
