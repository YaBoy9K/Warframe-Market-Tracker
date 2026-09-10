# Change Log / Reconstructed Project History

This file documents the main changes made while the tracker was being used.

## Market tracker

- Added a self-hosted Docker-based Warframe.Market scanner.
- Added Discord webhook notifications for matching market listings.
- Moved deal settings into JSON watchlists instead of hard-coding every item.
- Added per-item `max_platinum` filters.
- Added per-item `min_quantity` filters.
- Added seller-status filtering.
- Tightened the final primary watchlist to **`ingame` sellers only**.
- Expanded the ducat-focused watchlist.
- Kept a broader ducat list that allows both `online` and `ingame` sellers.
- Added ducat values to the later primary watchlist.
- Added some later `min_ducats_per_platinum` metadata for higher-level deal rules.
- Added a separate frequent-1p watchlist derived from the final main watchlist.
- Kept tracker state so repeated scans do not repeatedly alert on the same order.

## Mission tracker

- Added a separate `mission-tracker` Docker Compose service.
- Added Discord alerts for Steel Path Omnia Void Cascade fissures.
- The earlier direct `api.warframe.com/cdn/worldState.php` approach produced
  HTTP 409 responses during testing.
- The final mission tracker uses the WarframeStat PC fissures endpoint instead:
  `https://api.warframestat.us/pc/fissures`.
- Added persistent fissure-ID deduplication.
- Added mission expiry cleanup so the state file stays small.
- Added `--dry-run` and `--once` testing modes.
- Added graceful Docker stop handling.

## GitHub packaging

The recovered final versions of these files were preserved as-is:

- `watchlist.json`
- `watchlist-all-ducat-deals.json`
- `mission_tracker.py`

The original final `market_tracker.py`, `Dockerfile`, and
`docker-compose.yml` were not preserved as standalone saved files, so the
GitHub package reconstructs those pieces around the same behavior and updates
the market HTTP calls to the current Warframe.Market v2 API.
