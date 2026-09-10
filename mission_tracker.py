#!/usr/bin/env python3
"""Discord alerts for new Steel Path Omnia Void Cascade fissures."""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


FISSURES_URL = "https://api.warframestat.us/pc/fissures"
USER_AGENT = "warframe-mission-discord-tracker/1.0"
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
POLL_SECONDS = max(30, int(os.getenv("MISSION_POLL_SECONDS", "60")))
STATE_PATH = Path(os.getenv("MISSION_STATE_PATH", "/app/data/mission-state.json"))
DRY_RUN = "--dry-run" in sys.argv
RUN_ONCE = "--once" in sys.argv
stop_requested = False


def stop_handler(_signum, _frame):
    global stop_requested
    stop_requested = True


def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"alerted_ids": {}}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid state file {STATE_PATH}: {exc}") from exc


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(STATE_PATH)


def get_fissures():
    request = Request(
        FISSURES_URL,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=20) as response:
        result = json.load(response)
    if not isinstance(result, list):
        raise RuntimeError("Unexpected fissure API response")
    return result


def expiry_unix(expiry):
    parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    return int(parsed.timestamp())


def is_target(fissure):
    return (
        fissure.get("tier") == "Omnia"
        and fissure.get("missionType") == "Void Cascade"
        and fissure.get("isHard") is True
        and expiry_unix(fissure["expiry"]) > int(time.time())
    )


def discord_payload(fissure):
    end = expiry_unix(fissure["expiry"])
    node = fissure.get("node", "Unknown node")
    enemy = fissure.get("enemy", "Unknown")
    return {
        "username": "Warframe Mission Tracker",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": "New Steel Path OMNIA Void Fissure",
                "description": f"**Void Cascade ({node})**",
                "color": 15258703,
                "fields": [
                    {"name": "Enemy", "value": enemy, "inline": True},
                    {
                        "name": "Ends",
                        "value": f"<t:{end}:F>\n<t:{end}:R>",
                        "inline": False,
                    },
                ],
                "footer": {"text": "Steel Path • Omnia • PC world state"},
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
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urlopen(request, timeout=20):
        pass


def scan(state):
    now = int(time.time())
    alerted = state.setdefault("alerted_ids", {})
    # Keep only active IDs so the state file stays small.
    alerted = {fissure_id: end for fissure_id, end in alerted.items() if end > now}
    state["alerted_ids"] = alerted

    fissures = get_fissures()
    matches = [fissure for fissure in fissures if is_target(fissure)]
    for fissure in matches:
        fissure_id = fissure["id"]
        if fissure_id in alerted:
            continue
        post_discord(discord_payload(fissure))
        alerted[fissure_id] = expiry_unix(fissure["expiry"])
        logging.info(
            "Alerted: Steel Path Omnia Void Cascade at %s, expires %s",
            fissure.get("node", "Unknown node"),
            fissure["expiry"],
        )

    state["last_scan_unix"] = now
    save_state(state)
    logging.info("Checked %d fissures: %d matching active mission(s)", len(fissures), len(matches))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not WEBHOOK_URL and not DRY_RUN:
        raise RuntimeError("DISCORD_WEBHOOK_URL is missing from .env")
    state = load_state()
    logging.info("Mission tracker polling every %d seconds", POLL_SECONDS)
    while not stop_requested:
        started = time.monotonic()
        try:
            scan(state)
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            logging.error("Mission scan failed: %s", exc)
        if RUN_ONCE:
            break
        delay = max(1, POLL_SECONDS - (time.monotonic() - started))
        end = time.monotonic() + delay
        while not stop_requested and time.monotonic() < end:
            time.sleep(min(1, end - time.monotonic()))
    logging.info("Mission tracker stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    try:
        main()
    except Exception as exc:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        logging.error("Fatal error: %s", exc)
        sys.exit(1)
