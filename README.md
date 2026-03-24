# GPhub

A self-hosted tool that collects, scores and summarises the latest AI news, research papers and tools — twice a day.

![img](./imgs/gphub.png)
![img](./imgs/browse.png)


## Architecture

```
Scheduler (APScheduler)
    └── Crawlers (crawl4ai + feedparser)
            ├── RSS: HN, ArXiv, MIT TR, VentureBeat, Product Hunt
            └── Web: GitHub Trending
    └── Scoring Engine  (impact 40% · credibility 35% · novelty 25%)
    └── Summariser      (Claude Haiku)

FastAPI  ──► Next.js (http://localhost:3000)
PostgreSQL + pgvector
```

## Scoring

| Dimension | Weight | Signal |
|---|---|---|
| Impact | 40% | GitHub stars, social shares, citations |
| Credibility | 35% | Source tier (Tier 1 = 100, Tier 2 = 65, Tier 3 = 30) |
| Novelty | 25% | Exponential decay from publish time (48h half-life) + category boost |

## Quick Start

```bash
# 1. Copy and fill in your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY

# 2. Start everything
docker compose up -d

# 3. Open the web UI
open http://localhost:3000

# 4. Manually trigger a crawl (optional, no need to wait for scheduler)
curl -X POST http://localhost:8000/api/v1/trigger-crawl
```

## Development

### Backend (Python 3.12)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Run with a local Postgres (update DATABASE_URL in .env)
uvicorn app.main:app --reload
```

### Run tests

```bash
cd backend
pytest tests/ -v
```

### Frontend (Next.js 14)

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Claude Haiku API key |
| `POSTGRES_USER` | `gphub` | DB user |
| `POSTGRES_PASSWORD` | `gphub_secret` | DB password |
| `POSTGRES_DB` | `gphub` | DB name |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/items` | Paginated item feed (filterable) |
| GET | `/api/v1/items/{id}` | Single item detail |
| GET | `/api/v1/stats` | Aggregate stats |
| GET | `/api/v1/crawl-runs` | Recent crawl history |
| POST | `/api/v1/trigger-crawl` | Manually trigger a crawl |
| GET | `/health` | Health check |

## Scheduler

Crawls run at **06:00 UTC** and **18:00 UTC** by default.
Change via `SCHEDULE_HOURS` in `backend/app/config.py`.

## Adding a New Source

1. Add a row to `backend/migrations/init.sql` (for new installs) **or** `INSERT` directly into the `sources` table.
2. For RSS feeds, add an entry to `RSS_SOURCES` in `backend/app/crawlers/rss_crawler.py`.
3. For complex sites, create a new file in `backend/app/crawlers/` inheriting `BaseCrawler`.
