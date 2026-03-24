"""Unit tests for the scoring engine (no DB required)."""
import pytest
from datetime import datetime, timezone, timedelta
from app.models import Item, Source, SourceTier, ContentCategory
from app.scoring.engine import score_item, _time_decay


def make_source(tier: SourceTier = SourceTier.tier1) -> Source:
    s = Source()
    s.tier = tier
    s.category = ContentCategory.news_article
    return s


def make_item(**kwargs) -> Item:
    item = Item()
    item.category = kwargs.get("category", ContentCategory.news_article)
    item.github_stars = kwargs.get("github_stars", None)
    item.social_shares = kwargs.get("social_shares", None)
    item.citations = kwargs.get("citations", None)
    item.published_at = kwargs.get("published_at", None)
    return item


# ── Credibility ───────────────────────────────────────────────────────────────

def test_tier1_credibility():
    scores = score_item(make_item(), make_source(SourceTier.tier1))
    assert scores["credibility"] == 1.0

def test_tier2_credibility():
    scores = score_item(make_item(), make_source(SourceTier.tier2))
    assert scores["credibility"] == 0.65

def test_tier3_credibility():
    scores = score_item(make_item(), make_source(SourceTier.tier3))
    assert scores["credibility"] == 0.30

def test_no_source_falls_back_to_tier3():
    scores = score_item(make_item(), None)
    assert scores["credibility"] == 0.30


# ── Novelty / time decay ──────────────────────────────────────────────────────

def test_brand_new_item_high_novelty():
    item = make_item(
        published_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        category=ContentCategory.news_article,
    )
    scores = score_item(item, make_source())
    assert scores["novelty"] > 0.90

def test_old_item_low_novelty():
    item = make_item(
        published_at=datetime.now(timezone.utc) - timedelta(days=14),
        category=ContentCategory.news_article,
    )
    scores = score_item(item, make_source())
    assert scores["novelty"] < 0.10

def test_novelty_boost_for_research():
    # A research paper of the same age should score >= news
    now = datetime.now(timezone.utc) - timedelta(hours=10)
    research = make_item(published_at=now, category=ContentCategory.research_paper)
    news = make_item(published_at=now, category=ContentCategory.news_article)
    r_scores = score_item(research, make_source())
    n_scores = score_item(news, make_source())
    assert r_scores["novelty"] >= n_scores["novelty"]


# ── Impact ────────────────────────────────────────────────────────────────────

def test_no_signals_gives_floor_impact():
    scores = score_item(make_item(), make_source())
    assert scores["impact"] == 0.1

def test_high_github_stars():
    item = make_item(github_stars=50_000)
    scores = score_item(item, make_source())
    assert scores["impact"] >= 0.9

def test_impact_capped_at_1():
    item = make_item(github_stars=999_999, citations=999_999, social_shares=999_999)
    scores = score_item(item, make_source())
    assert scores["impact"] <= 1.0


# ── Total score ───────────────────────────────────────────────────────────────

def test_total_score_weighted_sum():
    item = make_item(
        github_stars=1000,
        published_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    source = make_source(SourceTier.tier1)
    s = score_item(item, source)
    expected = round(0.40 * s["impact"] + 0.35 * s["credibility"] + 0.25 * s["novelty"], 3)
    assert abs(s["total"] - expected) < 0.001

def test_total_in_range():
    item = make_item(github_stars=500, published_at=datetime.now(timezone.utc))
    s = score_item(item, make_source(SourceTier.tier2))
    assert 0.0 <= s["total"] <= 1.0
