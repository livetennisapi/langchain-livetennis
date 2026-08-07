# Changelog

## 0.2.0 — 2026-08-07

New API coverage — nine new tools, fifteen total:

- `live_tennis_h2h` — head-to-head across the 1968–2022 archive and completed
  matches from 2023 on (BASIC+).
- `live_tennis_archive_matches`, `live_tennis_archive_players`,
  `live_tennis_archive_career` — the 1968–2022 results archive: results with
  era serve stats, player bios, career aggregates (BASIC+).
- `live_tennis_rankings` — rank-ordered listing for one system (PRO+).
- `live_tennis_player_rankings` — per-player point-in-time records (ULTRA).
- `live_tennis_match_statistics` — in-play statistics, derived + measured
  families with per-family freshness (ULTRA).
- `live_tennis_charting_player`, `live_tennis_charting_match` — Match Charting
  Project shot-level data (ULTRA).

Filters:

- `live_tennis_matches` gains `player` (up to 50 ids), `country` (IOC-style
  3-letter code), `from_date` and `to_date`.
- `live_tennis_fixtures` gains `tour` (atp, wta, challenger, itf, juniors).

Errors:

- New `LiveTennisAbuseThrottled` (429 `abuse_throttled`): the 24-hour block for
  chronic over-cap clients, with `.retry_at_epoch`. Subclasses
  `LiveTennisRateLimited`, so existing handlers keep working.
- Daily-cap 429s now carry `.resets_at` (the exact ISO-8601 reset instant) on
  `LiveTennisRateLimited`, and the message states it.
- Daily-cap and abuse 429s are no longer retried in-process — waiting seconds
  cannot fix either.

Docs & CI:

- README: tier-gated tool table, quota table (2026-08-06 grid), authentication
  section, Discord/org links.
- Tier gates stated in every tool description, so an agent can explain a 403.
- `scripts/truthcheck.sh` pins product facts (quotas, URLs) in CI.

## 0.1.0 — 2026-07-27

Initial release.

- `LiveTennisToolkit` bundling six tools over the Live Tennis API public v1.
- `live_tennis_matches`, `live_tennis_match`, `live_tennis_match_score`,
  `live_tennis_player_search`, `live_tennis_player`, `live_tennis_fixtures`.
- Typed exception hierarchy; retries on 429/5xx only.
