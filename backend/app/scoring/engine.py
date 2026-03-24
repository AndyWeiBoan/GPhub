"""
Scoring engine — three dimensions:

  Impact      (40%)  — social/github signals, normalized
  Credibility (35%)  — source tier mapping
  Novelty     (25%)  — time-decay from published_at

Total = 0.40 * impact + 0.35 * credibility + 0.25 * novelty
All sub-scores are in [0.0, 1.0].
"""
import math
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.models import Item, Source, SourceTier, ContentCategory

# ── Credibility lookup ────────────────────────────────────────────────────────
TIER_SCORE: dict[SourceTier, float] = {
    SourceTier.tier1: 1.0,
    SourceTier.tier2: 0.65,
    SourceTier.tier3: 0.30,
}

# ── Signal caps for normalisation (tune these over time) ─────────────────────
STARS_CAP = 50_000
SHARES_CAP = 5_000
CITATIONS_CAP = 500

# ── Category novelty boost ────────────────────────────────────────────────────
# Items in these categories get a +0.10 novelty bonus (capped at 1.0)
NOVELTY_BOOST_CATEGORIES = {
    ContentCategory.research_paper,
    ContentCategory.community,
    ContentCategory.github_project,
}


def _normalise(value: Optional[int], cap: int) -> float:
    if not value or value <= 0:
        return 0.0
    return min(value / cap, 1.0)


def _time_decay(published_at: Optional[datetime]) -> float:
    """
    Exponential decay: score = exp(-λ * age_hours)
    Half-life is configurable via NOVELTY_HALFLIFE_HOURS.
    Returns 1.0 for brand-new items, ~0.5 at half-life.
    """
    if published_at is None:
        return 0.5  # unknown age → neutral

    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    age_hours = max((now - published_at).total_seconds() / 3600, 0)
    lam = math.log(2) / settings.NOVELTY_HALFLIFE_HOURS
    return math.exp(-lam * age_hours)


def _impact_score(item: Item) -> float:
    stars = _normalise(item.github_stars, STARS_CAP)
    shares = _normalise(item.social_shares, SHARES_CAP)
    citations = _normalise(item.citations, CITATIONS_CAP)

    # Weight by availability: prefer citations > shares > stars
    # Use whichever signals exist
    weights = []
    values = []
    if item.citations is not None:
        weights.append(0.5); values.append(citations)
    if item.social_shares is not None:
        weights.append(0.3); values.append(shares)
    if item.github_stars is not None:
        weights.append(0.2); values.append(stars)

    if not weights:
        return 0.1  # no signal data → small non-zero floor

    total_weight = sum(weights)
    score = sum(w * v for w, v in zip(weights, values)) / total_weight
    return round(min(score, 1.0), 3)


def _credibility_score(source: Optional[Source]) -> float:
    if source is None:
        return TIER_SCORE[SourceTier.tier3]
    return TIER_SCORE.get(source.tier, TIER_SCORE[SourceTier.tier3])


def _novelty_score(item: Item) -> float:
    base = _time_decay(item.published_at)
    boost = 0.10 if item.category in NOVELTY_BOOST_CATEGORIES else 0.0
    return round(min(base + boost, 1.0), 3)


def score_item(item: Item, source: Optional[Source] = None) -> dict:
    impact = _impact_score(item)
    credibility = _credibility_score(source)
    novelty = _novelty_score(item)

    total = (
        settings.WEIGHT_IMPACT * impact
        + settings.WEIGHT_CREDIBILITY * credibility
        + settings.WEIGHT_NOVELTY * novelty
    )
    return {
        "impact": round(impact, 3),
        "credibility": round(credibility, 3),
        "novelty": round(novelty, 3),
        "total": round(total, 3),
    }
