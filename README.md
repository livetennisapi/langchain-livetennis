# langchain-livetennis

**Official LangChain integration for the [Live Tennis API](https://livetennisapi.com).**

Give an agent real-time tennis: live scores, match detail, player profiles and
upcoming fixtures for ATP, WTA, Challenger, ITF and junior Grand Slam draws.

[![PyPI - Version](https://img.shields.io/pypi/v/langchain-livetennis?style=flat-square&label=%20)](https://pypi.org/project/langchain-livetennis/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Installation

```bash
pip install -U langchain-livetennis
```

## Credentials

Get a free key (1,000 requests/day) at
<https://livetennisapi.com/subscribe/free>, then:

```bash
export LIVETENNISAPI_KEY="your-key"
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

| Tool | Endpoint | What it returns |
|---|---|---|
| `live_tennis_matches` | `GET /matches` | Matches by status (`live`, `upcoming`, `completed`), optionally one `tour`, with the latest score |
| `live_tennis_match` | `GET /matches/{id}` | One match in full: players, tournament, surface, round, status, score |
| `live_tennis_match_score` | `GET /matches/{id}/score` | Just the score — sets, games, points, server, tiebreak flag |
| `live_tennis_player_search` | `GET /players` | Players matching a name, ranked players first |
| `live_tennis_player` | `GET /players/{id}` | One player's bio, ranking and cached statistics |
| `live_tennis_fixtures` | `GET /fixtures` | Upcoming scheduled fixtures, earliest first |

Every tool returns the API's JSON payload as a string, so nothing is lost on the
way to the model.

`tour` accepts `atp`, `wta`, `challenger`, `itf` or `juniors`. Each value covers
that tour's singles and doubles draws, and `juniors` covers the boys' and girls'
Grand Slam draws. An unrecognised value is a 400 rather than a silent
pass-through, so a caller never receives a tour it did not ask for.

## Plans

`status="live"`, `status="upcoming"` and every other tool here work on the FREE
key. `status="completed"` is part of the paid History product and needs BASIC or
above — a free key gets HTTP 403, surfaced as `LiveTennisUpgradeRequired`.

## Errors

| Exception | When |
|---|---|
| `LiveTennisAuthError` | 401 — key missing, unknown, or disabled |
| `LiveTennisUpgradeRequired` | 403 — valid key, plan too low |
| `LiveTennisNotFound` | 404 — no such match or player, or no data yet |
| `LiveTennisBadRequest` | 400 — a query parameter was rejected |
| `LiveTennisRateLimited` | 429 — carries `.retry_after` in seconds |
| `LiveTennisServerError` | 5xx, or the API was never reached |

All inherit from `LiveTennisAPIError`. Inside a tool call they are re-raised as
LangChain's `ToolException`, so an agent can be configured to recover:

```python
from langchain_livetennis import LiveTennisMatchesTool

tool = LiveTennisMatchesTool(handle_tool_error=True)
```

Requests retry automatically on **429 and 5xx only**, honouring `Retry-After`
with exponential backoff and jitter. A 401 or 403 is never retried — a bad key
or an unentitled plan cannot start working, and retrying only burns the rate
limit.

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
- [Official Python client](https://pypi.org/project/livetennisapi/) — the
  standalone SDK, for use outside LangChain
- [OpenAPI specification](https://github.com/livetennisapi/openapi)

## License

MIT
