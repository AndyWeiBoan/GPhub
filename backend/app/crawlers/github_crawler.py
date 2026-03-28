"""GitHub Trending crawler — multi-language crawl with backend subcat assignment.

We crawl GitHub Trending for several AI-relevant languages, then classify
each repo into a GithubSubcat using keyword matching on title + description +
README.  The subcategory is stored in the DB (items.github_subcat), which
means:
  - Classification happens once at crawl time, not on every frontend render
  - The /items?github_subcat= API filter works server-side
  - The classification logic can be upgraded to an LLM in the future without
    touching the frontend

Deduplication: if the same repo appears in multiple language pages, the first
occurrence wins (higher-priority language = earlier in LANGUAGE_TARGETS).
"""
import re
import json
import asyncio
import structlog
import httpx
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

from app.crawlers.base import BaseCrawler, RawItem
from app.models import ContentCategory, GithubSubcat

log = structlog.get_logger()

README_MAX_CHARS = 1500
README_TIMEOUT   = 6.0
REPOS_PER_LANG   = 25   # GitHub shows max 25 per trending page

# Languages to scrape, in priority order (first = wins dedup)
LANGUAGE_TARGETS = [
    "python",
    "typescript",
    "javascript",
    "rust",
    "go",
]

# ── Subcat classification rules ───────────────────────────────────────────────
# Priority order: llm > agent > context > vision > tool (most specific first)
# Checked against lowercased: "{title} {description} {readme[:500]}"

_SUBCAT_RULES: list[tuple[GithubSubcat, list[str]]] = [
    (GithubSubcat.llm, [
        "large language model", "language model", "foundation model",
        "llm", "llama", "mistral", "gemma", "qwen", "gpt", "bert", "t5",
        "gguf", "ggml", "quantiz", "lora", "qlora", "fine-tun", "finetun",
        "pretrain", "pre-train", "text generation", "causal lm",
        "instruct model", "base model", "open weight", "open-weight",
        "sft ", "rlhf", "dpo", "transformers model",
    ]),
    (GithubSubcat.agent, [
        "ai agent", "llm agent", "agentic", "multi-agent", "multiagent",
        "autonomous agent", "agent framework", "agent workflow",
        "tool-use agent", "tool use agent", "function calling agent",
        "computer use", "browser automation", "web agent",
        "openai swarm", "autogen", "crewai", "langgraph", "smolagent",
    ]),
    (GithubSubcat.context, [
        "model context protocol", "mcp server", "mcp client",
        "retrieval augmented", "retrieval-augmented", "rag",
        "vector store", "vector database", "vectordb", "embedding store",
        "knowledge base", "knowledge graph",
        "long context", "context window", "context length",
        "agent memory", "episodic memory", "semantic memory",
        "chroma", "weaviate", "pinecone", "qdrant", "milvus", "faiss",
        "tool call", "function call", "tool use",
    ]),
    (GithubSubcat.vision, [
        "image generation", "text-to-image", "text to image",
        "stable diffusion", "diffusion model", "diffusers",
        "image synthesis", "inpainting", "controlnet",
        "multimodal", "vision language", "visual language", "vlm",
        "object detection", "image segmentation", "computer vision",
        "video generation", "text-to-video",
        "speech synthesis", "tts", "text-to-speech",
        "asr", "speech recognition", "whisper",
    ]),
    (GithubSubcat.tool, [
        # catch-all: broad AI tooling / infra / frameworks
        "ai tool", "ai framework", "ai sdk", "ai library",
        "llm tool", "llm framework", "llm sdk", "llm library",
        "ai assistant", "chatbot", "copilot", "ai playground",
        "ai dashboard", "ai cli", "ai inference", "ai serving",
        "ai benchmark", "ai eval", "ai pipeline", "ai workflow",
        "ai deploy", "ai endpoint", "ai api",
        "openai", "anthropic sdk", "claude sdk", "gemini sdk",
        "langchain", "llamaindex", "haystack",
    ]),
]


def classify_subcat(title: str, raw_content: str) -> GithubSubcat:
    """Assign a GithubSubcat based on keyword matching.  Most specific wins."""
    text = f"{title} {raw_content[:500]}".lower()
    for subcat, keywords in _SUBCAT_RULES:
        if any(kw in text for kw in keywords):
            return subcat
    # Default: tool (broadest bucket)
    return GithubSubcat.tool


SCHEMA = {
    "name": "GitHub Trending Repos",
    "baseSelector": "article.Box-row",
    "fields": [
        {"name": "name",             "selector": "h2 a",                        "type": "text"},
        {"name": "url",              "selector": "h2 a",                        "type": "attribute", "attribute": "href"},
        {"name": "description",      "selector": "p",                           "type": "text"},
        {"name": "stars",            "selector": "a.Link--muted:first-of-type", "type": "text"},
        {"name": "stars_this_week",  "selector": "span.d-inline-block",         "type": "text"},
    ],
}


def _parse_stars(raw: str) -> int:
    if not raw:
        return 0
    raw = raw.strip().replace(",", "")
    m = re.search(r"[\d.]+k?", raw, re.IGNORECASE)
    if not m:
        return 0
    val = m.group()
    if val.lower().endswith("k"):
        return int(float(val[:-1]) * 1000)
    return int(val)


async def _fetch_readme(client: httpx.AsyncClient, owner: str, repo: str) -> str:
    for branch in ("main", "master"):
        for filename in ("README.md", "readme.md", "README.rst", "README"):
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
            try:
                resp = await client.get(url, timeout=README_TIMEOUT)
                if resp.status_code == 200:
                    text = resp.text[:README_MAX_CHARS]
                    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
                    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
                    text = re.sub(r'#+\s*', '', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    return text
            except Exception:
                pass
    return ""


async def _crawl_language(
    crawler: AsyncWebCrawler,
    language: str,
) -> list[dict]:
    url = f"https://github.com/trending/{language}?since=weekly"
    strategy = JsonCssExtractionStrategy(SCHEMA, verbose=False)
    config = CrawlerRunConfig(extraction_strategy=strategy)

    try:
        result = await crawler.arun(url=url, config=config)
    except Exception as e:
        log.warning("github_lang_crawl_failed", language=language, error=str(e))
        return []

    if not result.success or not result.extracted_content:
        log.warning("github_lang_empty", language=language)
        return []

    try:
        repos = json.loads(result.extracted_content)
    except Exception:
        return []

    basic: list[dict] = []
    for repo in repos[:REPOS_PER_LANG]:
        href = (repo.get("url") or "").strip()
        if not href:
            continue
        full_url = f"https://github.com{href}" if href.startswith("/") else href
        raw_name = (repo.get("name") or "").strip()
        clean_name = re.sub(r'\s*/\s*\n?\s*', '/', raw_name).strip()
        path = href.lstrip("/")
        parts = path.split("/")
        owner = parts[0] if len(parts) >= 1 else ""
        repo_name = parts[1] if len(parts) >= 2 else ""
        # Prefer "X stars this week" over total stars — matches github.com weekly ranking
        stars_this_week = _parse_stars(repo.get("stars_this_week", ""))
        stars_total     = _parse_stars(repo.get("stars", ""))
        basic.append({
            "title": clean_name or full_url,
            "url": full_url,
            "owner": owner,
            "repo": repo_name,
            "description": (repo.get("description") or "").strip(),
            "stars": stars_this_week if stars_this_week > 0 else stars_total,
            "thumbnail": f"https://avatars.githubusercontent.com/{owner}?s=80",
            "language": language,
        })

    log.info("github_lang_scraped", language=language, count=len(basic))
    return basic


class GitHubCrawler(BaseCrawler):
    async def fetch(self) -> list[RawItem]:
        # ── Phase 1: scrape all language trending pages sequentially
        all_basic: list[dict] = []
        async with AsyncWebCrawler(verbose=False) as crawler:
            for lang in LANGUAGE_TARGETS:
                batch = await _crawl_language(crawler, lang)
                all_basic.extend(batch)

        # ── Phase 2: dedup by URL (first-seen language wins)
        seen_urls: set[str] = set()
        deduped: list[dict] = []
        for repo in all_basic:
            if repo["url"] not in seen_urls:
                seen_urls.add(repo["url"])
                deduped.append(repo)

        log.info("github_deduped", before=len(all_basic), after=len(deduped))

        # ── Phase 3: fetch READMEs concurrently
        async with httpx.AsyncClient(follow_redirects=True) as client:
            readmes = await asyncio.gather(
                *[_fetch_readme(client, r["owner"], r["repo"]) for r in deduped],
                return_exceptions=True,
            )

        # ── Phase 4: build RawItems with backend subcat classification
        items: list[RawItem] = []
        subcat_counts: dict[str, int] = {}

        for repo_info, readme in zip(deduped, readmes):
            readme_text = readme if isinstance(readme, str) else ""
            raw_content = repo_info["description"]
            if readme_text:
                raw_content = f"{raw_content}\n\n{readme_text}".strip()

            subcat = classify_subcat(repo_info["title"], raw_content)
            subcat_counts[subcat.value] = subcat_counts.get(subcat.value, 0) + 1

            # Source name includes language for traceability
            source_url = f"https://github.com/trending/{repo_info['language']}?since=weekly"

            items.append(RawItem(
                title=repo_info["title"],
                url=repo_info["url"],
                category=ContentCategory.github_project,
                github_subcat=subcat,
                source_name="GitHub Trending",
                source_url=source_url,
                raw_content=raw_content,
                github_stars=repo_info["stars"],
                thumbnail_url=repo_info["thumbnail"],
            ))

        log.info(
            "github_fetched",
            count=len(items),
            with_readme=sum(1 for r in readmes if isinstance(r, str) and r),
            subcat_distribution=subcat_counts,
        )
        return items
