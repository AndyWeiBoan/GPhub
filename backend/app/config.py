from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite (default, no setup needed): sqlite+aiosqlite:///./ai_digest.db
    # PostgreSQL:                        postgresql+asyncpg://user:pass@host/db
    DATABASE_URL: str = "sqlite+aiosqlite:///./ai_digest.db"
    ANTHROPIC_API_KEY: str = ""
    PEXELS_API_KEY: str = ""

    # Google Gemini API (https://aistudio.google.com/apikey) — free tier
    # Free tier: 20 req/day (gemini-2.5-flash) — used for weekly digest only
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Groq API (https://console.groq.com/keys) — free tier
    # Free tier: 14,400 req/day (llama-3.1-8b-instant)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # Cerebras API (https://cloud.cerebras.ai) — free tier
    # Free tier: 14,400 req/day (llama-3.1-8b) — faster than Groq (~0.3s/call)
    CEREBRAS_API_KEY: str = ""
    CEREBRAS_MODEL: str = "llama-3.1-8b"

    # Max items per DB fetch chunk in comment generation (memory guard)
    COMMENT_FETCH_CHUNK: int = 500

    # NewsAPI (https://newsapi.org/) — free tier: 100 req/day
    NEWS_API_KEY: str = ""
    # Max articles per query (free tier caps at 100 per request)
    NEWS_API_MAX_RESULTS: int = 30

    # CORE API (https://core.ac.uk/) — free with registration
    CORE_API_KEY: str = ""
    # Max papers per query
    CORE_API_MAX_RESULTS: int = 20

    # Perspective API (https://perspectiveapi.com/) — free, for community quality scoring
    PERSPECTIVE_API_KEY: str = ""
    # Toxicity threshold: items above this score are filtered out (0.0–1.0)
    PERSPECTIVE_TOXICITY_THRESHOLD: float = 0.80

    # Twitter/X credentials for twikit (no official API key needed)
    # twikit logs in once, saves cookies to TWITTER_COOKIES_PATH, auto-refreshes on expiry
    TWITTER_USERNAME: str = ""      # Twitter username or email used to log in
    TWITTER_PASSWORD: str = ""      # Twitter account password
    TWITTER_EMAIL: str = ""         # Email address (used when Twitter asks for confirmation)
    TWITTER_COOKIES_PATH: str = "twitter_cookies.json"  # where to persist session

    # Pexels rate-limit guard: max images to fetch per enrichment run
    # Free tier = 200 req/hour. We crawl twice/day, keep well under limit.
    PEXELS_BATCH_LIMIT: int = 50

    # Scheduler: two runs per day (UTC)
    SCHEDULE_HOURS: list[int] = [6, 18]  # 06:00 and 18:00 UTC

    # Scoring weights (must sum to 1.0)
    WEIGHT_IMPACT: float = 0.40
    WEIGHT_CREDIBILITY: float = 0.35
    WEIGHT_NOVELTY: float = 0.25

    # Novelty decay half-life in hours
    NOVELTY_HALFLIFE_HOURS: float = 48.0


settings = Settings()
