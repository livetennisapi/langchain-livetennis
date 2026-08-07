# langchain-livetennis

**Official LangChain integration for the [Live Tennis API](https://livetennisapi.com).**

Give an agent real tennis: live scores, match detail, player profiles, upcoming
fixtures, head-to-head records, rankings, in-play statistics and a 1968–2022
results archive — across ATP, WTA, Challenger, ITF and juniors.

[![CI](https://github.com/livetennisapi/langchain-livetennis/actions/workflows/ci.yml/badge.svg)](https://github.com/livetennisapi/langchain-livetennis/actions/workflows/ci.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/langchain-livetennis?style=flat-square&label=%20)](https://pypi.org/project/langchain-livetennis/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Installation

```bash
pip install -U langchain-livetennis
```

## Credentials

Get a free key (100 requests/day) at
<https://livetennisapi.com/subscribe/free>, then:

```bash
export LIVETENNISAPI_KEY="twjp_..."
```

A request without a key is answered with HTTP 401 `{"error": "unauthorized"}`.

## Quickstart

```python
from langchain_livetennis import LiveTennisToolkit

toolkit = LiveTennisToolkit()
tools = toolkit.get_tools()

matches = tools[0].invoke({"status": "live", "tour": "atp", "limit": 5})
print(matches)
```

Or use a single tool on its own:

```python
from langchain_livetennis import LiveTennisScoreTool

LiveTennisScoreTool().invoke({"match_id": 18953})
```

## In an agent

```python
from langchain.agents import create_agent
from langchain_livetennis import LiveTennisToolkit

agent = create_agent(model="claude-sonnet-4-6", tools=LiveTennisToolkit().get_tools())

agent.invoke(
    {"messages": [{"role": "user", "content": "Who is leading the live ATP matches right now?"}]}
)
```

## Tools

| Tool | Endpoint | Plan | What it returns |
|---|---|---|---|
| `live_tennis_matches` | `GET /matches` | FREE (`completed`: BASIC+) | Matches by status (`live`, `upcoming`, `completed`), filterable by tour, player ids, country and date range, with the latest score |
| `live_tennis_match` | `GET /matches/{id}` | FREE | One match in full: players, tournament, surface, round, status, score |
| `live_tennis_match_score` | `GET /matches/{id}/score` | FREE | Just the score — sets, games, points, server, tiebreak flag |
| `live_tennis_player_search` | `GET /players` | FREE | Players matching a name, ranked players first |
| `live_tennis_player` | `GET /players/{id}` | FREE | One player's bio, ranking and cached statistics |
| `live_tennis_fixtures` | `GET /fixtures` | FREE | Upcoming scheduled fixtures, earliest first, filterable by tour |
| `live_tennis_h2h` | `GET /h2h` | BASIC+ | Head-to-head between two players, 1968 to now, with per-meeting outcomes |
| `live_tennis_archive_matches` | `GET /history/archive/matches` | BASIC+ | 1968–2022 results: score, round, seeds, ranks at the time, era serve stats |
| `live_tennis_archive_players` | `GET /history/archive/players` | BASIC+ | Archive player bios: hand, birth date, country, height, career-high rank |
| `live_tennis_archive_career` | `GET /history/archive/career` | BASIC+ | One player's whole archive career: W-L by surface/level/year, titles, serve sums |
| `live_tennis_rankings` | `GET /rankings` (listing) | PRO+ | The full published table in rank order for one system (ATP/WTA/ITF circuits) |
| `live_tennis_player_rankings` | `GET /rankings` (per-player) | ULTRA | Point-in-time ranking records per player and system, as of any date |
| `live_tennis_match_statistics` | `GET /matches/{id}/statistics` | ULTRA | In-play statistics: aces, serve split, hold/break %, break points, freshness per family |
| `live_tennis_charting_player` | `GET /charting/players` | ULTRA | Career shot-level charting profile (Match Charting Project) |
| `live_tennis_charting_match` | `GET /charting/matches/{id}` | ULTRA | One charted match, every stat family for both players, per set |

Every tool returns the API's JSON payload as a string, so nothing is lost on the
way to the model. Tools above the key's plan still bind and appear in
`get_tools()`; calling one surfaces the API's 403 as a `ToolException` naming
the plan that unlocks it, so an agent can explain the gate instead of retrying
it.

`tour` accepts `atp`, `wta`, `challenger`, `itf` or `juniors`. Each value covers
that tour's singles and doubles draws, and `juniors` covers the boys' and girls'
Grand Slam draws. An unrecognised value is a 400 rather than a silent
pass-through, so a caller never receives a tour it did not ask for.

## Plans & quotas

| Plan | Per minute | Per day | Price |
|---|---|---|---|
| FREE | 30 | 100 | $0 |
| BASIC | 60 | 1,000 | $9.99/mo |
| PRO | 300 | 10,000 | $29.99/mo |
| ULTRA | 600 | 500,000 | $99.99/mo |

On a free key (100/day), poll no faster than every 15 minutes; for an always-on
dashboard, BASIC is recommended. Every response carries `X-RateLimit-Limit`,
`X-RateLimit-Remaining` and `X-RateLimit-Reset` headers, and 429s a
`Retry-After`.

## Authentication

The API accepts, in order of preference:

- `Authorization: Bearer twjp_...` — preferred for direct HTTP calls
- `X-API-Key: twjp_...` — what this package sends
- `?token=twjp_...` — for header-less contexts (e.g. WebSockets)

This package reads the key from the `LIVETENNISAPI_KEY` environment variable,
or takes it explicitly via `LiveTennisToolkit(api_key=...)`.

## Errors

| Exception | When |
|---|---|
| `LiveTennisAuthError` | 401 — key missing, unknown, or disabled |
| `LiveTennisUpgradeRequired` | 403 — valid key, plan too low |
| `LiveTennisNotFound` | 404 — no such match or player, or no data yet |
| `LiveTennisBadRequest` | 400 — a query parameter was rejected |
| `LiveTennisRateLimited` | 429 — carries `.retry_after` in seconds; a daily-cap 429 also carries `.resets_at`, the exact ISO-8601 instant the day quota resets |
| `LiveTennisAbuseThrottled` | 429 `abuse_throttled` — a 24-hour block for chronic over-cap use; carries `.retry_at_epoch`. Fix the retry loop, don't retry |
| `LiveTennisServerError` | 5xx, or the API was never reached |

All inherit from `LiveTennisAPIError` (`LiveTennisAbuseThrottled` also from
`LiveTennisRateLimited`). Inside a tool call they are re-raised as LangChain's
`ToolException`, so an agent can be configured to recover:

```python
from langchain_livetennis import LiveTennisMatchesTool

tool = LiveTennisMatchesTool(handle_tool_error=True)
```

Requests retry automatically on **per-minute 429s and 5xx only**, honouring
`Retry-After` with exponential backoff and jitter. A 401 or 403 is never
retried — a bad key or an unentitled plan cannot start working, and retrying
only burns the rate limit. Nor are a daily-cap 429 or the abuse block —
waiting a few seconds cannot fix either, so they surface immediately with
`.resets_at` / `.retry_at_epoch`.

## Configuration

```python
from langchain_livetennis import LiveTennisClient, LiveTennisToolkit

toolkit = LiveTennisToolkit(api_key="...")

# Or share a fully configured client across every tool:
client = LiveTennisClient(api_key="...", timeout=10.0, max_retries=3)
toolkit = LiveTennisToolkit(client=client)
```

## Development

```bash
uv sync --all-groups
uv run pytest tests/unit_tests
uv run ruff check .
uv run ruff format --check .
uv run mypy langchain_livetennis
```

The unit suite runs entirely against an in-process fake API
(`tests/mock_api.py`) — no key and no network access required. The integration
tests under `tests/integration_tests/` skip themselves unless
`LIVETENNISAPI_KEY` is set.

## Links

- [Live Tennis API documentation](https://docs.livetennisapi.com)
- [Get a free API key](https://livetennisapi.com/subscribe/free)
- [Discord](https://discord.gg/f8WUZHgDm6)
- [GitHub org](https://github.com/livetennisapi)
- [Official Python client](https://pypi.org/project/livetennisapi/) — the
  standalone SDK, for use outside LangChain
- [OpenAPI specification](https://github.com/livetennisapi/openapi)

## Affiliate program

Know developers who need tennis data? The [affiliate program](https://affiliates.livetennisapi.com/program) pays 51% recurring commission for the life of every referred subscription — 30-day cookie, and the people you refer get 10% off.

## License

MIT
