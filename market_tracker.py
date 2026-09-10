#!/usr/bin/env python3
"""Warframe.market Discord deal tracker.

Reads a JSON watchlist and scans visible sell orders for listings that meet:
- seller status filter (for example: ingame only)
- maximum platinum price
- minimum seller quantity

Matching listings are sent to Discord and deduplicated with a small local state file.
"""

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_BASE = "https://api.warframe.market/v2"
USER_AGENT = os.getenv(
    "WFM_USER_AGENT",
    "warframe-market-discord-tracker/1.0"
).strip()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
WATCHLIST_PATH = Path(os.getenv("WATCHLIST_PATH", "/app/watchlist.json"))
STATE_PATH = Path(os.getenv("MARKET_STATE_PATH", "/app/data/market-state.json"))

PLATFORM = os.getenv("WFM_PLATFORM", "pc").strip().lower()
CROSSPLAY = os.getenv("WFM_CROSSPLAY", "true").strip().lower() in {
    "1", "true", "yes", "on"
}

# A full scan may contain hundreds of items. The per-request delay is kept
# above 1/3 second so the tracker stays below Warframe.market's public
# 3 requests/second limit.
REQUEST_DELAY_SECONDS = max(
    0.35, float(os.getenv("MARKET_REQUEST_DELAY_SECONDS", "0.40"))
)
POLL_SECONDS = max(30, int(os.getenv("MARKET_POLL_SECONDS", "60")))
STATE_RETENTION_SECONDS = max(
    3600, int(os.getenv("MARKET_STATE_RETENTION_SECONDS", "259200"))
)

DRY_RUN = "--dry-run" in sys.argv
RUN_ONCE = "--once" in sys.argv
stop_requested = False


def stop_handler(_signum, _frame):
    global stop_requested
    stop_requested = True


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_watchlist():
    data = load_json(WATCHLIST_PATH)
    if not isinstance(data, dict):
        raise RuntimeError(f"{WATCHLIST_PATH} must contain a JSON object")

    statuses = data.get("seller_statuses", ["ingame"])
    items = data.get("items", [])

    if not isinstance(statuses, list) or not statuses:
        raise RuntimeError("seller_statuses must be a non-empty list")
    if not isinstance(items, list):
        raise RuntimeError("items must be a list")

    normalized_statuses = {str(status).lower() for status in statuses}
    return normalized_statuses, items


def load_state():
    try:
        data = load_json(STATE_PATH)
        if not isinstance(data, dict):
            return {"alerted_orders": {}}
        data.setdefault("alerted_orders", {})
        return data
    except FileNotFoundError:
        return {"alerted_orders": {}}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid state file {STATE_PATH}: {exc}") from exc


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(STATE_PATH)


def api_headers():
    return {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Platform": PLATFORM,
        "Crossplay": "true" if CROSSPLAY else "false",
        "Language": "en",
    }


def get_orders(slug):
    safe_slug = quote(slug, safe="_-")
    url = f"{API_BASE}/orders/item/{safe_slug}"
    request = Request(url, headers=api_headers())
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected API response for {slug}")

    if payload.get("error"):
        raise RuntimeError(f"API error for {slug}: {payload['error']}")

    orders = payload.get("data")
    if not isinstance(orders, list):
        raise RuntimeError(f"Unexpected order data for {slug}")

    return orders


def order_user(order):
    user = order.get("user") or {}
    return user if isinstance(user, dict) else {}


def matching_orders(item, allowed_statuses, orders):
    max_platinum = int(item["max_platinum"])
    min_quantity = int(item.get("min_quantity", 1))
    matches = []

    for order in orders:
        if not isinstance(order, dict):
            continue
        if order.get("type") != "sell":
            continue
        if order.get("visible") is False:
            continue

        try:
            platinum = int(order.get("platinum", 0))
            quantity = int(order.get("quantity", 0))
        except (TypeError, ValueError):
            continue

        user = order_user(order)
        status = str(user.get("status", "offline")).lower()

        if status not in allowed_statuses:
            continue
        if platinum > max_platinum:
            continue
        if quantity < min_quantity:
            continue

        matches.append(order)

    matches.sort(key=lambda order: (
        int(order.get("platinum", 999999)),
        -int(order.get("quantity", 0)),
    ))
    return matches


def alert_key(order):
    # Include mutable fields so a listing that changes into a matching deal can
    # alert again even when Warframe.market keeps the same order ID.
    return "{}:{}:{}".format(
        order.get("id", "unknown"),
        order.get("platinum", "unknown"),
        order.get("quantity", "unknown"),
    )


def discord_payload(item, order):
    user = order_user(order)
    seller = (
        user.get("ingameName")
        or user.get("slug")
        or "Unknown seller"
    )
    status = user.get("status", "unknown")
    platinum = order.get("platinum", "?")
    quantity = order.get("quantity", "?")
    slug = item["slug"]
    market_url = f"https://warframe.market/items/{slug}"

    fields = [
        {"name": "Price", "value": f"**{platinum}p**", "inline": True},
        {"name": "Quantity", "value": str(quantity), "inline": True},
        {"name": "Seller", "value": str(seller), "inline": True},
        {"name": "Status", "value": str(status), "inline": True},
        {
            "name": "Watch limit",
            "value": f"≤ {item['max_platinum']}p / qty ≥ {item.get('min_quantity', 1)}",
            "inline": False,
        },
    ]

    if item.get("ducats") is not None:
        try:
            ducats = int(item["ducats"])
            fields.append(
                {"name": "Ducats", "value": str(ducats), "inline": True}
            )
            p = int(platinum)
            if p > 0:
                fields.append(
                    {
                        "name": "Ducats / Plat",
                        "value": f"{ducats / p:.1f}",
                        "inline": True,
                    }
                )
        except (TypeError, ValueError):
            pass

    return {
        "username": "Warframe Market Tracker",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": f"Deal Found: {item.get('name', slug)}",
                "url": market_url,
                "description": f"[Open on Warframe.Market]({market_url})",
                "color": 5763719,
                "fields": fields,
                "footer": {
                    "text": f"Warframe.Market • {PLATFORM.upper()} • "
                            f"{'Crossplay' if CROSSPLAY else 'No crossplay'}"
                },
            }
        ],
    }


def post_discord(payload):
    if DRY_RUN:
        logging.info("DRY RUN Discord payload: %s", json.dumps(payload))
        return

    request = Request(
        WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urlopen(request, timeout=20):
        pass


def prune_state(state):
    now = int(time.time())
    cutoff = now - STATE_RETENTION_SECONDS
    alerted = state.setdefault("alerted_orders", {})
    state["alerted_orders"] = {
        key: timestamp
        for key, timestamp in alerted.items()
        if int(timestamp) >= cutoff
    }


def scan(state):
    allowed_statuses, items = load_watchlist()
    alerted = state.setdefault("alerted_orders", {})
    request_count = 0
    match_count = 0
    new_alert_count = 0

    logging.info(
        "Scanning %d watchlist item(s); seller statuses=%s",
        len(items),
        ",".join(sorted(allowed_statuses)),
    )

    for index, item in enumerate(items, start=1):
        if stop_requested:
            break

        slug = item.get("slug")
        if not slug:
            logging.warning("Skipping watchlist entry without slug: %s", item)
            continue

        try:
            orders = get_orders(slug)
            request_count += 1
            matches = matching_orders(item, allowed_statuses, orders)
            match_count += len(matches)

            for order in matches:
                key = alert_key(order)
                if key in alerted:
                    continue

                post_discord(discord_payload(item, order))
                alerted[key] = int(time.time())
                new_alert_count += 1

                user = order_user(order)
                logging.info(
                    "Alerted: %s at %sp x%s from %s (%s)",
                    item.get("name", slug),
                    order.get("platinum"),
                    order.get("quantity"),
                    user.get("ingameName", user.get("slug", "unknown")),
                    user.get("status", "unknown"),
                )

        except HTTPError as exc:
            logging.error(
                "HTTP %s while scanning %s",
                exc.code,
                item.get("name", slug),
            )
            if exc.code == 429:
                logging.warning("Rate limited; pausing before continuing")
                time.sleep(max(10, POLL_SECONDS))
        except (URLError, TimeoutError, ValueError, RuntimeError) as exc:
            logging.error(
                "Market scan failed for %s: %s",
                item.get("name", slug),
                exc,
            )

        # Keep request rate polite and below the documented public limit.
        if index < len(items) and not stop_requested:
            time.sleep(REQUEST_DELAY_SECONDS)

    prune_state(state)
    state["last_scan_unix"] = int(time.time())
    save_state(state)

    logging.info(
        "Market scan complete: %d request(s), %d matching order(s), "
        "%d new Discord alert(s)",
        request_count,
        match_count,
        new_alert_count,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not WEBHOOK_URL and not DRY_RUN:
        raise RuntimeError("DISCORD_WEBHOOK_URL is missing from .env")

    state = load_state()
    logging.info(
        "Market tracker started: watchlist=%s, full-scan pause=%ds, "
        "request delay=%.2fs",
        WATCHLIST_PATH,
        POLL_SECONDS,
        REQUEST_DELAY_SECONDS,
    )

    while not stop_requested:
        started = time.monotonic()
        scan(state)

        if RUN_ONCE:
            break

        # POLL_SECONDS is the minimum pause after a completed full scan.
        delay = max(1, POLL_SECONDS)
        logging.info("Next full scan in %d seconds", delay)

        end = time.monotonic() + delay
        while not stop_requested and time.monotonic() < end:
            time.sleep(min(1, end - time.monotonic()))

    logging.info("Market tracker stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    try:
        main()
    except Exception as exc:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        logging.error("Fatal error: %s", exc)
        sys.exit(1)
