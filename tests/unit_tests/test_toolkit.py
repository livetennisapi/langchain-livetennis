"""The toolkit: it hands back every tool, all sharing one client."""

from __future__ import annotations

import json

from langchain_core.tools import BaseTool

from langchain_livetennis import LiveTennisClient, LiveTennisToolkit

EXPECTED_TOOL_NAMES = [
    "live_tennis_matches",
    "live_tennis_match",
    "live_tennis_match_score",
    "live_tennis_player_search",
    "live_tennis_player",
    "live_tennis_fixtures",
]


def test_get_tools_returns_every_tool(toolkit: LiveTennisToolkit) -> None:
    tools = toolkit.get_tools()
    assert [t.name for t in tools] == EXPECTED_TOOL_NAMES
    assert all(isinstance(t, BaseTool) for t in tools)


def test_tool_names_are_unique(toolkit: LiveTennisToolkit) -> None:
    names = [t.name for t in toolkit.get_tools()]
    assert len(names) == len(set(names))


def test_every_tool_shares_the_toolkit_client(toolkit: LiveTennisToolkit) -> None:
    for tool in toolkit.get_tools():
        assert tool.api is toolkit.client  # type: ignore[attr-defined]


def test_toolkit_builds_a_client_from_a_key() -> None:
    toolkit = LiveTennisToolkit(
        api_key="secret-key", base_url="https://example.invalid/v1"
    )
    assert toolkit.client is not None
    assert toolkit.client.api_key == "secret-key"
    assert toolkit.client.base_url == "https://example.invalid/v1"
    assert "secret-key" not in repr(toolkit)


def test_every_toolkit_tool_can_be_invoked(client: LiveTennisClient) -> None:
    tools = {t.name: t for t in LiveTennisToolkit(client=client).get_tools()}
    args = {
        "live_tennis_matches": {"status": "live", "limit": 2},
        "live_tennis_match": {"match_id": 18953},
        "live_tennis_match_score": {"match_id": 18953},
        "live_tennis_player_search": {"search": "alcaraz"},
        "live_tennis_player": {"player_id": 4021},
        "live_tennis_fixtures": {"limit": 1},
    }
    for name, payload in args.items():
        result = tools[name].invoke(payload)
        assert json.loads(result), name
