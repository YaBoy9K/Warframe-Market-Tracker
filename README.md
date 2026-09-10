# Warframe Market & Mission Discord Tracker

A self-hosted Python + Docker tracker that watches **Warframe.Market** for
configured deals and sends **Discord webhook alerts**. It also includes a
second service that alerts when a **Steel Path Omnia Void Cascade** fissure
appears.

This repository is based on the tracker I built for my homelab and includes
the later watchlist/filter changes I made while using it.

## What It Does

### Market Tracker

- Reads deal rules from JSON watchlists.
- Watches Warframe.Market sell orders.
- Filters by:
  - seller status (`ingame`, or `online` + `ingame`)
  - maximum platinum price
  - minimum listed quantity
- Supports ducat metadata and ducats-per-platinum information.
- Sends Discord embeds for matching listings.
- Saves alerted order IDs locally so the same listing does not repeatedly ping.
- Runs continuously in Docker.

### Mission Tracker

- Polls the WarframeStat fissure endpoint.
- Looks specifically for:
  - **Steel Path**
  - **Omnia**
  - **Void Cascade**
- Sends a Discord alert containing the node, enemy faction, and mission expiry.
- Saves alerted fissure IDs so the same fissure only alerts once.

## Watchlists Included

### `watchlist.json`

This is the recovered final main watchlist.

- Seller filter: **`ingame` only**
- 493 configured entries
- Includes per-item:
  - `name`
  - `slug`
  - `max_platinum`
  - `min_quantity`
  - `ducats`
  - some later entries also include `min_ducats_per_platinum`

Example:

```json
{
  "name": "Acceltra Prime Receiver",
  "slug": "acceltra_prime_receiver",
  "max_platinum": 1,
  "min_quantity": 2,
  "ducats": 45
}
```

### `watchlist-all-ducat-deals.json`

The broader recovered ducat-deal list.

- Seller filter: `online` and `ingame`
- 339 configured entries

### `watchlist-1p-frequent.json`

A GitHub-ready copy derived from the final main watchlist for the later
"frequent 1 platinum" idea.

- Seller filter: `ingame`
- Contains the 182 final-watchlist entries whose `max_platinum` is exactly `1`

It is included as an alternate config and is **not enabled by default**.

## Repository Layout

```text
warframe-market-discord-tracker/
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── market_tracker.py
├── mission_tracker.py
├── requirements.txt
├── watchlist.json
├── watchlist-all-ducat-deals.json
├── watchlist-1p-frequent.json
├── CHANGELOG.md
└── data/
    └── .gitkeep
```

## Setup

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd warframe-market-discord-tracker
```

### 2. Create the environment file

```bash
cp .env.example .env
```

Edit `.env` and replace the placeholder with your Discord webhook:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Do **not** commit `.env`.

### 3. Build and start

```bash
docker compose up -d --build
```

Check both services:

```bash
docker compose ps
```

### 4. View logs

Market tracker:

```bash
docker compose logs -f market-tracker
```

Mission tracker:

```bash
docker compose logs -f mission-tracker
```

### Restart only one tracker

```bash
docker compose restart market-tracker
```

```bash
docker compose restart mission-tracker
```

### Stop the stack

```bash
docker compose down
```

## Changing Which Market Watchlist Runs

The default Compose service mounts:

```text
./watchlist.json -> /app/watchlist.json
```

To use the frequent 1p list instead, change the market tracker volume in
`docker-compose.yml` to:

```yaml
- ./watchlist-1p-frequent.json:/app/watchlist.json:ro
```

For the broader ducat-deal list:

```yaml
- ./watchlist-all-ducat-deals.json:/app/watchlist.json:ro
```

Then recreate the service:

```bash
docker compose up -d --force-recreate market-tracker
```

## Watchlist Format

```json
{
  "seller_statuses": [
    "ingame"
  ],
  "items": [
    {
      "name": "Example Prime Part",
      "slug": "example_prime_part",
      "max_platinum": 2,
      "min_quantity": 1,
      "ducats": 100
    }
  ]
}
```

### `seller_statuses`

Examples:

```json
["ingame"]
```

or:

```json
["online", "ingame"]
```

### `max_platinum`

The highest price the tracker should alert for.

### `min_quantity`

The minimum quantity the seller must have listed.

## Environment Variables

| Variable | Default | Purpose |
|---|---:|---|
| `DISCORD_WEBHOOK_URL` | required | Discord webhook used by both trackers |
| `WFM_PLATFORM` | `pc` | Warframe.Market platform |
| `WFM_CROSSPLAY` | `true` | Include crossplay-compatible orders |
| `WFM_USER_AGENT` | tracker name | Identifies this client to Warframe.Market |
| `MARKET_POLL_SECONDS` | `60` | Pause after each completed full market scan |
| `MARKET_REQUEST_DELAY_SECONDS` | `0.40` | Delay between Warframe.Market item requests |
| `MARKET_STATE_RETENTION_SECONDS` | `259200` | How long market alert keys remain in state |
| `MISSION_POLL_SECONDS` | `60` | Mission/fissure polling interval |

## Dry Run / One Scan

You can test without sending Discord alerts:

```bash
docker compose run --rm market-tracker python market_tracker.py --dry-run --once
```

Mission tracker:

```bash
docker compose run --rm mission-tracker python mission_tracker.py --dry-run --once
```

## Runtime State

The trackers create local state files under `data/`:

```text
data/market-state.json
data/mission-state.json
```

The folder is mounted into the containers so alerts remain deduplicated after
container restarts.

The state files are ignored by Git.

## API Notes

The GitHub version of the market scanner uses the current Warframe.Market v2
HTTP API:

```text
https://api.warframe.market/v2/orders/item/{slug}
```

Warframe.Market currently documents a public limit of 3 HTTP requests per
second. The default `0.40` second request delay keeps this scanner below that
limit.

Warframe.Market's public API is still evolving, so an API change may require
small updates later.

The mission tracker uses:

```text
https://api.warframestat.us/pc/fissures
```

This replaced the earlier direct Digital Extremes world-state request that
was returning HTTP 409 errors during testing.

## Security

- Never commit `.env`.
- Never put a real Discord webhook in a watchlist or source file.
- If a webhook is accidentally committed, regenerate it in Discord.
- Runtime state is ignored by Git.

## Disclaimer

This is a personal third-party project and is not affiliated with Digital
Extremes or Warframe.Market. Use public APIs responsibly and follow their
current API/client rules.
