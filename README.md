# IlBoursa Market Notifier — Roadmap & Implementation Plan

Project goal: build a Telegram bot + scheduler that scrapes ilboursa syntheses, notifies BUY/SELL opportunities twice daily (Tunis time), answers interactive commands sorted by "Potential", and supports extensions such as news sentiment analysis, persistence, multi-chat subscriptions, and analytics.

## Project overview

- Scrape: https://www.ilboursa.com/analyses/synthese_fiches  
- Scheduled pushes: 09:30 and 15:00 Tunisia time (weekdays) containing ONLY BUY and SELL opportunities  
- Instant command responses:
  - `/what_to_buy`
  - `/what_to_sell`
  - `/what_to_keep`
  - `/what_to_take_profit`  
  Each reply sorted by "Potential" (descending)
- Deployment: Docker + docker-compose
- Extensions: news sentiment analysis, persistence/history, user subscriptions, monitoring

## Tech stack

- Language: Python 3.11+  
- Libraries:
  - `requests`, `beautifulsoup4` (scraping)
  - `python-telegram-bot` (Telegram integration)
  - `pytz` (timezone)
  - Optional: `sqlalchemy` / `sqlite` / `redis` (persistence & caching)
  - Optional NLP: VADER/TextBlob or Transformer models (sentiment)
- Container: Docker, docker-compose  
- CI: GitHub Actions (lint, tests, build)  
- Monitoring/logging: Docker logs (optionally Sentry / Prometheus + Grafana)

## Repo structure (suggested)

- README.md (this file)  
- notifier_bot.py (core bot + scheduled jobs)  
- scraper.py (scraping & parsing logic)  
- sentiment.py (news sentiment utilities)  
- utils.py (cache, helpers, logging)  
- Dockerfile  
- docker-compose.yml  
- .env.example  
- tests/
  - test_scraper.py
  - test_parser.py
  - test_bot_handlers.py
- docs/
  - design.md
  - api.md
- scripts/
  - deploy.sh
  - local_run.sh

## Environment variables (.env)

Create a `.env` (never commit secrets). Example:

```env
TELEGRAM_BOT_TOKEN=123456:ABCDEF-your-bot-token
TELEGRAM_CHAT_ID=987654321     # numeric chat id for scheduled pushes (user or group)
CACHE_TTL=300                  # seconds
LOG_LEVEL=INFO
SENTIMENT_MODEL=distilbert-base-uncased-finetuned-sst-2-english
DATABASE_URL=sqlite:///data/bot.db