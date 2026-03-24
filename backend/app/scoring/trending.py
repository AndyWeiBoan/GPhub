"""
Cross-category trending score.

Formula
-------
trending_score = base_score × freshness_multiplier × coverage_boost

base_score
  The existing weighted total_score (impact 40% + credibility 35% + novelty 25%).

freshness_multiplier
  Exponential decay with 72-hour half-life so items stay relevant for ~7 days.
  f(age_h) = exp(-ln(2) / 72 × age_h)

coverage_boost
  Items covered by multiple *different* sources on the same topic signal real
  traction.  CRITICAL: we count distinct source_name values, NOT title similarity
  within the same source.  ArXiv publishes 90+ papers/day — they must not boost
  each other.

  Two items are "about the same topic" only when they come from DIFFERENT sources
  AND share ≥ 3 significant title tokens (raised from 2 to cut false positives).

  boost = 1.0 + 0.40 × min(distinct_sources - 1, 3)
  (1 source = 1.0×, 2 sources = 1.4×, 4+ sources = 2.2×)

Diversity floor (enforced in the API layer, not here)
  The caller is responsible for ensuring at least 1 slot per active category
  in the final top-N list.
"""
import math
import re
from datetime import datetime, timezone
from collections import defaultdict
from typing import Sequence


FRESHNESS_HALFLIFE_H = 72.0   # 3 days
COVERAGE_STEP        = 0.40   # +40% per additional *different* source (capped at 3)
MIN_SHARED_TOKENS    = 3      # raised to reduce same-source false positives


def _age_hours(item) -> float:
    ref = item.published_at or item.fetched_at
    if ref is None:
        return 0.0
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - ref).total_seconds() / 3600, 0.0)


def _freshness(age_h: float) -> float:
    lam = math.log(2) / FRESHNESS_HALFLIFE_H
    return math.exp(-lam * age_h)


def _tokens(title: str) -> frozenset[str]:
    """Lower-cased significant words (len ≥ 4, not common stop-words)."""
    STOP = {
        "with", "from", "that", "this", "into", "using", "based", "large",
        "model", "models", "neural", "learning", "deep", "language", "agent",
        "agents", "multi", "system", "systems", "approach", "method", "data",
        "analysis", "framework", "toward", "towards", "novel", "paper",
        "study", "work", "task", "tasks", "performance", "results", "show",
        "efficient", "effective", "improved", "improving", "evaluation",
    }
    return frozenset(
        w for w in re.findall(r"[a-z]{4,}", title.lower()) if w not in STOP
    )


def _build_coverage_map(items: Sequence) -> dict[str, int]:
    """
    For each item, count how many *distinct other source names* have published
    something on the same topic (≥ MIN_SHARED_TOKENS shared title tokens).

    Returns {item.id: distinct_source_count}  (minimum 1).
    """
    id_to_tokens  = {item.id: _tokens(item.title) for item in items}
    id_to_source  = {item.id: (getattr(item, "source_name", None) or "") for item in items}

    # Map item_id → set of source_names that also covered this topic
    coverage: dict[str, set[str]] = {item.id: set() for item in items}

    ids = [item.id for item in items]
    for i, a in enumerate(ids):
        src_a = id_to_source[a]
        for b in ids[i + 1:]:
            src_b = id_to_source[b]
            # Only count cross-source matches
            if src_a == src_b:
                continue
            shared = id_to_tokens[a] & id_to_tokens[b]
            if len(shared) >= MIN_SHARED_TOKENS:
                coverage[a].add(src_b)
                coverage[b].add(src_a)

    return {iid: max(1, len(srcs) + 1) for iid, srcs in coverage.items()}


def compute_trending_scores(items: Sequence) -> dict[str, float]:
    """
    Return {item.id: trending_score} for all items.
    Does NOT write to DB — caller decides what to do with the scores.
    """
    coverage = _build_coverage_map(items)

    scores: dict[str, float] = {}
    for item in items:
        base      = float(item.total_score or 0)
        age_h     = _age_hours(item)
        fresh     = _freshness(age_h)
        n_sources = coverage.get(item.id, 1)
        boost     = 1.0 + COVERAGE_STEP * min(n_sources - 1, 3)
        scores[item.id] = round(base * fresh * boost, 4)

    return scores
