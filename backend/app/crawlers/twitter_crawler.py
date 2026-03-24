"""Twitter crawler using twikit (no official API key needed).

Authentication flow:
1. First run: logs in with username + password, saves cookies to TWITTER_COOKIES_PATH
2. Subsequent runs: loads saved cookies directly (fast, no login request)
3. If cookies expire: automatically re-logs in and refreshes the file

Required .env variables:
  TWITTER_USERNAME   — Twitter account username or email
  TWITTER_PASSWORD   — Twitter account password
  TWITTER_EMAIL      — Email address associated with the account (used for 2FA prompts)
  TWITTER_COOKIES_PATH — Where to store session cookies (default: ./twitter_cookies.json)
"""
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import structlog

from app.crawlers.base import BaseCrawler, RawItem
from app.models import ContentCategory
from app.config import settings

log = structlog.get_logger()

# ── Curated list of AI thought leaders ───────────────────────────────────────
AI_ACCOUNTS = [
    ("karpathy",        "Andrej Karpathy"),
    ("ylecun",          "Yann LeCun"),
    ("sama",            "Sam Altman"),
    ("demishassabis",   "Demis Hassabis"),
    ("geoffreyhinton",  "Geoffrey Hinton"),
    ("drfeifei",        "Fei-Fei Li"),
    ("jimfan",          "Jim Fan"),
    ("emollick",        "Ethan Mollick"),
    ("fchollet",        "François Chollet"),
    ("hardmaru",        "David Ha"),
    ("ilyasut",         "Ilya Sutskever"),
    ("soumithchintala", "Soumith Chintala"),
    ("GoogleDeepMind",  "Google DeepMind"),
    ("AnthropicAI",     "Anthropic"),
    ("OpenAI",          "OpenAI"),
    ("huggingface",     "Hugging Face"),
    ("mistralai",       "Mistral AI"),
]

# Only keep tweets that mention AI-related keywords
AI_KEYWORDS = [
    "llm", "gpt", "model", "ai ", " ai", "neural", "training", "inference",
    "agent", "transformer", "diffusion", "rag", "fine-tun", "benchmark",
    "dataset", "paper", "research", "open source", "weight", "token",
    "embedding", "reasoning", "multimodal", "vision", "language model",
    "machine learning", "deep learning", "reinforcement", "gradient",
    "pytorch", "tensorflow", "huggingface", "anthropic", "openai", "gemini",
    "claude", "chatgpt", "mistral", "llama", "open-source",
]

MAX_TWEETS_PER_ACCOUNT = 5
MIN_TWEET_LENGTH = 60


def _is_ai_relevant(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in AI_KEYWORDS)


def _clean_tweet(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tweet_url(handle: str, tweet_id: str) -> str:
    return f"https://twitter.com/{handle}/status/{tweet_id}"


async def _get_client():
    """
    Return an authenticated twikit Client.
    - Loads cookies from file if present and valid.
    - Otherwise logs in with username/password and saves cookies.
    - On cookie expiry, re-logs in automatically.
    """
    try:
        import twikit
    except ImportError:
        raise RuntimeError("twikit not installed — run: pip install twikit")

    username = settings.TWITTER_USERNAME
    password = settings.TWITTER_PASSWORD
    email    = settings.TWITTER_EMAIL
    cookies_path = Path(settings.TWITTER_COOKIES_PATH)

    if not username or not password:
        raise RuntimeError("TWITTER_USERNAME and TWITTER_PASSWORD must be set in .env")

    client = twikit.Client(language="en-US")

    # ── Try loading saved cookies first ──────────────────────────────────────
    if cookies_path.exists():
        try:
            client.load_cookies(str(cookies_path))
            log.info("twitter_cookies_loaded", path=str(cookies_path))
            return client
        except Exception as e:
            log.warning("twitter_cookies_invalid", error=str(e), action="re-logging in")

    # ── Fresh login ───────────────────────────────────────────────────────────
    log.info("twitter_login", username=username)
    try:
        await client.login(
            auth_info_1=username,
            auth_info_2=email,   # used when Twitter asks for email confirmation
            password=password,
        )
    except Exception as e:
        raise RuntimeError(f"Twitter login failed: {e}") from e

    # Save cookies for next run
    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    client.save_cookies(str(cookies_path))
    log.info("twitter_cookies_saved", path=str(cookies_path))

    return client


class TwitterCrawler(BaseCrawler):
    """Fetch tweets from AI thought leaders using twikit."""

    async def fetch(self) -> list[RawItem]:
        if not settings.TWITTER_USERNAME or not settings.TWITTER_PASSWORD:
            log.warning(
                "twitter_crawler_skipped",
                reason="TWITTER_USERNAME / TWITTER_PASSWORD not set in .env",
            )
            return []

        try:
            client = await _get_client()
        except RuntimeError as e:
            log.error("twitter_auth_failed", error=str(e))
            return []

        tasks = [
            self._fetch_user_tweets(client, handle, name)
            for handle, name in AI_ACCOUNTS
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[RawItem] = []
        for (handle, _name), result in zip(AI_ACCOUNTS, results):
            if isinstance(result, Exception):
                log.warning("twitter_fetch_failed", handle=handle, error=str(result))
                continue
            items.extend(result)

        log.info("twitter_crawled", total=len(items))
        return items

    async def _fetch_user_tweets(
        self,
        client,
        handle: str,
        display_name: str,
    ) -> list[RawItem]:
        try:
            user = await client.get_user_by_screen_name(handle)
            tweets = await user.get_tweets("Tweets", count=20)
        except Exception as e:
            log.warning("twitter_user_fetch_failed", handle=handle, error=str(e))
            return []

        results = []
        for tweet in tweets:
            text: str = getattr(tweet, "full_text", "") or getattr(tweet, "text", "") or ""

            # Skip retweets
            if text.startswith("RT @"):
                continue
            # Skip short / off-topic
            if len(text) < MIN_TWEET_LENGTH:
                continue
            if not _is_ai_relevant(text):
                continue

            tweet_id = str(tweet.id)
            url = _tweet_url(handle, tweet_id)

            # Parse timestamp
            published_at: Optional[datetime] = None
            raw_time = getattr(tweet, "created_at", None)
            if raw_time:
                try:
                    if isinstance(raw_time, datetime):
                        published_at = raw_time.astimezone(timezone.utc)
                    else:
                        from email.utils import parsedate_to_datetime
                        published_at = parsedate_to_datetime(str(raw_time)).astimezone(timezone.utc)
                except Exception:
                    pass

            # Social signal: likes + retweets×3
            likes    = getattr(tweet, "favorite_count", None) or getattr(tweet, "like_count", None)
            retweets = getattr(tweet, "retweet_count", None)
            social_signal: Optional[int] = None
            if likes is not None or retweets is not None:
                social_signal = (likes or 0) + (retweets or 0) * 3

            # Thumbnail: author profile picture (higher-res)
            thumbnail = None
            user_obj = getattr(tweet, "user", None)
            if user_obj:
                pic = getattr(user_obj, "profile_image_url_https", None)
                if pic:
                    thumbnail = pic.replace("_normal", "_400x400")

            clean_text = _clean_tweet(text)
            title_raw  = clean_text.split(".")[0].split("\n")[0].strip()
            title      = (title_raw[:117] + "...") if len(title_raw) > 120 else title_raw
            if not title:
                title = f"{display_name} on X"

            results.append(RawItem(
                title=title,
                url=url,
                category=ContentCategory.community,
                source_name=f"{display_name} (@{handle})",
                source_url=f"https://twitter.com/{handle}",
                author=display_name,
                published_at=published_at,
                raw_content=clean_text,
                social_shares=social_signal,
                thumbnail_url=thumbnail,
            ))

            if len(results) >= MAX_TWEETS_PER_ACCOUNT:
                break

        log.info("twitter_user_fetched", handle=handle, count=len(results))
        return results
