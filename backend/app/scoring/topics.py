"""
Topic trend engine.

Algorithm
---------
1. Collect all items from the past N days.
2. Extract significant bigrams + unigrams from titles using TF-IDF-style scoring:
   - Count how many items mention each candidate phrase.
   - Downweight phrases that appear in almost every item (too generic).
3. Cluster items under each top phrase (an item can belong to multiple topics).
4. For each topic, pick the highest trending-score item as the "lead" article.
5. Return top K topics sorted by item count (popularity this week).

No external ML libraries needed — pure Python stdlib + regex.
"""
import re
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Sequence

from app.scoring.trending import compute_trending_scores

# ── Stop words ────────────────────────────────────────────────────────────────
STOP = {
    "a","an","the","and","or","of","in","on","for","to","with","is","are","was",
    "were","by","via","from","into","onto","its","it","at","as","be","been",
    "this","that","these","those","which","when","where","how","what","who",
    "using","based","new","large","model","models","system","systems","approach",
    "method","methods","data","task","tasks","show","shows","paper","work",
    "learning","deep","language","neural","network","networks","toward","towards",
    "results","performance","evaluation","efficient","effective","improved",
    "improving","study","studies","framework","frameworks","agent","agents",
    "multi","single","end","use","used","uses","make","makes","made","high",
    "low","two","three","joint","novel","first","also","well","both","than",
    "more","most","our","we","they","their","us","your","can","not","but",
    "llm","llms","gpt","foundation","alignment","training","inference",
}

# ── Curated high-signal AI topic seeds ───────────────────────────────────────
# These help surface meaningful labels even when raw freq is scattered.
# Each seed maps to a canonical topic label.
TOPIC_SEEDS: dict[str, str] = {
    "ai agent":         "AI Agents",
    "agentic":          "AI Agents",
    "multi agent":      "Multi-Agent Systems",
    "multiagent":       "Multi-Agent Systems",
    "reasoning":        "Reasoning & Planning",
    "chain of thought": "Reasoning & Planning",
    "code generation":  "Code Generation",
    "code gen":         "Code Generation",
    "rag":              "Retrieval-Augmented Generation",
    "retrieval":        "Retrieval-Augmented Generation",
    "vision":           "Vision & Multimodal",
    "multimodal":       "Vision & Multimodal",
    "image generation": "Image Generation",
    "diffusion":        "Image Generation",
    "safety":           "AI Safety & Alignment",
    "alignment":        "AI Safety & Alignment",
    "robotics":         "Robotics",
    "embodied":         "Robotics",
    "graph":            "Graph Neural Networks",
    "knowledge graph":  "Graph Neural Networks",
    "time series":      "Time Series & Forecasting",
    "forecasting":      "Time Series & Forecasting",
    "medical":          "AI in Healthcare",
    "clinical":         "AI in Healthcare",
    "drug":             "AI in Healthcare",
    "benchmark":        "Benchmarks & Evaluation",
    "evaluation":       "Benchmarks & Evaluation",
    "efficient":        "Efficiency & Optimization",
    "quantization":     "Efficiency & Optimization",
    "compression":      "Efficiency & Optimization",
    "browser":          "AI Browser Automation",
    "web agent":        "AI Browser Automation",
    "open source":      "Open Source AI",
    "github":           "Open Source AI",
    "product":          "New AI Products",
    "launch":           "New AI Products",
    "startup":          "New AI Products",
    # Community / Social
    "tweet":            "AI Community",
    "discussion":       "AI Community",
    "opinion":          "AI Community",
    "thoughts on":      "AI Community",
    "hot take":         "AI Community",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _has_seed(title_lower: str, seed: str) -> bool:
    return seed in title_lower


@dataclass
class TopicResult:
    label: str
    count: int
    item_ids: list[str]
    lead_item: object   # Item with highest trending_score in this topic
    trending_score: float


def extract_topics(
    items: Sequence,
    top_k: int = 6,
    min_count: int = 2,
) -> list[TopicResult]:
    """
    Given a list of Item objects, return top_k topic clusters.
    Each item may appear in multiple topics.
    Topics with < min_count items are dropped.
    """
    if not items:
        return []

    # Compute trending scores for all items
    scores = compute_trending_scores(items)

    # Map each seed → list of (item, trending_score)
    seed_to_items: dict[str, list] = defaultdict(list)

    for item in items:
        title_lower = _normalize(item.title or "")
        raw_content_lower = _normalize((item.raw_content or "")[:300])
        combined = title_lower + " " + raw_content_lower

        for seed in TOPIC_SEEDS:
            if _has_seed(combined, seed):
                seed_to_items[seed].append(item)

    # Merge seeds that share the same canonical label
    label_to_items: dict[str, list] = defaultdict(list)
    for seed, matched_items in seed_to_items.items():
        label = TOPIC_SEEDS[seed]
        label_to_items[label].extend(matched_items)

    # Deduplicate items within each topic (by id)
    label_to_unique: dict[str, dict] = {}
    for label, matched_items in label_to_items.items():
        seen: dict[str, object] = {}
        for item in matched_items:
            if item.id not in seen:
                seen[item.id] = item
        label_to_unique[label] = seen

    # Build results
    results: list[TopicResult] = []
    for label, item_map in label_to_unique.items():
        count = len(item_map)
        if count < min_count:
            continue

        # Pick lead item: highest trending_score
        best_item = max(item_map.values(), key=lambda x: scores.get(x.id, 0))
        best_score = scores.get(best_item.id, 0)

        results.append(TopicResult(
            label=label,
            count=count,
            item_ids=list(item_map.keys()),
            lead_item=best_item,
            trending_score=best_score,
        ))

    # Sort by count desc, break ties by trending_score
    results.sort(key=lambda r: (r.count, r.trending_score), reverse=True)

    # Categories ranked by "show-ability" as a lead (rich image, visible content)
    # Categories ranked by visual richness as a lead card.
    # GitHub projects have small avatar thumbnails — push to last.
    PREFERRED_CATS = ["product_launch", "news_article", "blog_post",
                      "community", "research_paper", "github_project"]

    # Minimum impact score required to be considered as a lead article.
    MIN_LEAD_IMPACT = 0.05

    def _has_rich_thumbnail(item) -> bool:
        """Mirror the frontend topicHasRealImg logic."""
        t = item.thumbnail_url
        if not t:
            return False
        if "favicon" in t or ".ico" in t:
            return False
        if "avatars.githubusercontent.com" in t:
            return False
        if "redditstatic.com" in t:
            return False
        if "media2.dev.to" in t:
            return False
        return True

    def _lead_priority(item) -> tuple:
        cat = str(item.category) if item.category else "research_paper"
        cat_rank = PREFERRED_CATS.index(cat) if cat in PREFERRED_CATS else 99
        ts = scores.get(item.id, 0)
        has_rich_img = _has_rich_thumbnail(item)
        # Items below the impact threshold are sorted to the back
        has_impact = int((item.impact_score or 0) >= MIN_LEAD_IMPACT)
        # Priority: impact first, then image quality, then category, then score
        return (-has_impact, -int(has_rich_img), cat_rank, -ts)

    # Re-pick lead per topic using priority
    for r in results:
        topic_items = sorted(label_to_unique[r.label].values(), key=_lead_priority)
        r.lead_item = topic_items[0]
        r.trending_score = scores.get(r.lead_item.id, 0)

    # Re-sort by count
    results.sort(key=lambda r: (r.count, r.trending_score), reverse=True)

    # Deduplicate lead items across topics
    used_lead_ids: set[str] = set()
    final: list[TopicResult] = []
    for r in results:
        topic_items = sorted(label_to_unique[r.label].values(), key=_lead_priority)
        replaced = False
        for candidate in topic_items:
            if candidate.id not in used_lead_ids:
                r.lead_item = candidate
                r.trending_score = scores.get(candidate.id, 0)
                used_lead_ids.add(candidate.id)
                replaced = True
                break
        if not replaced:
            continue
        final.append(r)
        if len(final) >= top_k:
            break

    return final
