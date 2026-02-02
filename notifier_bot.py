#!/usr/bin/env python3
"""
notifier_bot.py

- Scrapes https://www.ilboursa.com/analyses/synthese_fiches
- Extracts assets and their action icons and "potential" (percentage)
- Scheduled notifications at 09:30 and 15:00 Tunisia time (weekdays) with BUY and SELL only
- Telegram command handlers:
    /what_to_buy
    /what_to_sell
    /what_to_keep
    /what_to_take_profit

Environment variables:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
Optional:
- CACHE_TTL (seconds, default 300)
"""

import os
import re
import time
import logging
from datetime import datetime, time as dt_time
import pytz
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # where scheduled pushes are sent
CACHE_TTL = int(os.environ.get("CACHE_TTL", "300"))  # seconds

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set")
    raise SystemExit("TELEGRAM_BOT_TOKEN not set")
if not TELEGRAM_CHAT_ID:
    logger.error("TELEGRAM_CHAT_ID not set")
    raise SystemExit("TELEGRAM_CHAT_ID not set")

SYNTH_URL = "https://www.ilboursa.com/analyses/synthese_fiches"
ACTION_MAP = {
    "f_1b.png": "BUY",
    "f_5b.png": "SELL",
    "f_3b.png": "KEEP",
    "f_4b.png": "TAKE PROFIT"
}
POTENTIAL_RE = re.compile(r'([+-]?\d+(?:[.,]\d+)?)\s*%')
TUNIS_TZ = pytz.timezone("Africa/Tunis")

# Simple in-memory cache
_cache = {"ts": 0, "data": None}


def fetch_page(url: str, timeout: int = 15) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MarketNotifier/1.0; +https://example.com)"
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_synthese(html: str):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    links = soup.find_all("a", href=lambda x: x and x.startswith("conseil/"))
    seen = set()

    for a in links:
        href = a.get("href", "")
        code = href.split("/")[-1].strip().upper()
        name = a.text.strip()
        key = (code, name)
        if key in seen:
            continue
        seen.add(key)

        tr = a.find_parent("tr")
        parent = tr if tr else a.parent
        action = None
        potential = 0.0

        # Find nearby images to infer action
        imgs = parent.find_all("img") if parent else []
        if not imgs:
            imgs = a.find_next_siblings("img")
        if not imgs:
            imgs = a.find_all_next("img", limit=6)

        for img in imgs:
            src = img.get("src", "")
            if not src:
                continue
            filename = src.split("/")[-1]
            if filename in ACTION_MAP:
                action = ACTION_MAP[filename]
                break

        # gather text area to find potential %
        text_search_area = ""
        if tr:
            text_search_area = " ".join(td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"]))
        else:
            texts = []
            if parent:
                texts.append(parent.get_text(" ", strip=True))
            sib = a
            for _ in range(6):
                sib = sib.find_next_sibling()
                if not sib:
                    break
                texts.append(sib.get_text(" ", strip=True))
            text_search_area = " ".join(texts)

        m = POTENTIAL_RE.search(text_search_area)
        if m:
            val_str = m.group(1).replace(",", ".")
            try:
                potential = float(val_str)
            except Exception:
                potential = 0.0

        if not action:
            # skip if no action icon found
            continue

        results.append({
            "code": code,
            "name": name,
            "action": action,
            "potential": potential
        })

    return results


def scrape_with_cache():
    now = time.time()
    if _cache["data"] and (now - _cache["ts"] < CACHE_TTL):
        return _cache["data"]
    try:
        html = fetch_page(SYNTH_URL)
        items = parse_synthese(html)
        _cache["data"] = items
        _cache["ts"] = now
        return items
    except Exception as e:
        logger.exception("Scrape failed: %s", e)
        # if cache exists return stale data
        if _cache["data"]:
            return _cache["data"]
        raise


def group_by_action(items):
    groups = {"BUY": [], "SELL": [], "KEEP": [], "TAKE PROFIT": []}
    for it in items:
        act = it.get("action")
        if act in groups:
            groups[act].append(it)
    return groups


def format_items_sorted(items):
    items_sorted = sorted(items, key=lambda x: x.get("potential", 0.0), reverse=True)
    lines = []
    for it in items_sorted:
        pot = it.get("potential", 0.0)
        sign = "+" if pot > 0 else ""
        lines.append(f"{it.get('name')} ({it.get('code')}) — {sign}{pot:.2f}%")
    return "\n".join(lines)


def split_long_message(text, limit=4000):
    # Split on newlines preserving lines
    if len(text) <= limit:
        return [text]
    parts = []
    lines = text.splitlines(True)
    cur = ""
    for line in lines:
        if len(cur) + len(line) > limit:
            parts.append(cur)
            cur = line
        else:
            cur += line
    if cur:
        parts.append(cur)
    return parts


def send_buy_sell_notification(context: CallbackContext):
    tz_now = datetime.now(TUNIS_TZ)
    if tz_now.weekday() >= 5:
        logger.info("Weekend - skipping scheduled send")
        return

    try:
        items = scrape_with_cache()
    except Exception as e:
        logger.exception("Scheduled scrape failed")
        return

    groups = group_by_action(items)
    buy = groups.get("BUY", [])
    sell = groups.get("SELL", [])

    if not buy and not sell:
        text = f"📊 Market scan ({tz_now.strftime('%Y-%m-%d %H:%M %Z')})\nNo BUY/SELL opportunities found."
        context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
        logger.info("Sent notification: none found")
        return

    text = f"📊 Market scan ({tz_now.strftime('%Y-%m-%d %H:%M %Z')})\n\n"
    if buy:
        text += "✅ BUY:\n" + format_items_sorted(buy) + "\n\n"
    if sell:
        text += "🛑 SELL:\n" + format_items_sorted(sell) + "\n\n"

    # send (split if too long)
    for part in split_long_message(text):
        context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=part)
    logger.info("Sent scheduled BUY/SELL notification")


# Command handlers
def cmd_start(update: Update, context: CallbackContext):
    update.message.reply_text("Hello — I send BUY/SELL notifications at 09:30 and 15:00 Tunisia time on weekdays.\nCommands: /what_to_buy /what_to_sell /what_to_keep /what_to_take_profit")


def cmd_list_handler(update: Update, context: CallbackContext):
    cmd = update.message.text.strip().split()[0].lower()
    mapping = {
        "/what_to_buy": "BUY",
        "/what_to_sell": "SELL",
        "/what_to_keep": "KEEP",
        "/what_to_take_profit": "TAKE PROFIT"
    }
    action = mapping.get(cmd)
    if not action:
        update.message.reply_text("Unknown command.")
        return

    try:
        items = scrape_with_cache()
    except Exception:
        update.message.reply_text("Error fetching data. Try again later.")
        return

    groups = group_by_action(items)
    lst = groups.get(action, [])
    if not lst:
        update.message.reply_text(f"No items for {action}.")
        return

    text = f"{action} list (sorted by Potential):\n\n" + format_items_sorted(lst)
    for part in split_long_message(text):
        update.message.reply_text(part)


def main():
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    jq = updater.job_queue

    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("what_to_buy", cmd_list_handler))
    dp.add_handler(CommandHandler("what_to_sell", cmd_list_handler))
    dp.add_handler(CommandHandler("what_to_keep", cmd_list_handler))
    dp.add_handler(CommandHandler("what_to_take_profit", cmd_list_handler))

    # Schedule jobs (two times) in Tunisia timezone. Job function checks weekdays.
    time_morning = dt_time(hour=9, minute=30, tzinfo=TUNIS_TZ)
    time_afternoon = dt_time(hour=15, minute=0, tzinfo=TUNIS_TZ)
    jq.run_daily(send_buy_sell_notification, time_morning)
    jq.run_daily(send_buy_sell_notification, time_afternoon)

    updater.start_polling()
    logger.info("Bot started. Polling for commands and scheduled jobs...")
    updater.idle()


if __name__ == "__main__":
    main()