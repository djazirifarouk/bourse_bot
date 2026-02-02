FROM python:3.11-slim

WORKDIR /app

# Install system deps for TLS and building
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY notifier_bot.py /app/notifier_bot.py

RUN pip install --no-cache-dir requests beautifulsoup4 python-telegram-bot==13.15 pytz

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/notifier_bot.py"]