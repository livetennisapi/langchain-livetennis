"""The tools: schemas a model can fill in, and invocation through LangChain."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, ToolException

from langchain_livetennis import (
    LiveTennisArchiveCareerTool,
    LiveTennisArchiveMatchesTool,
    LiveTennisArchivePlayersTool,
    LiveTennisChartingMatchTool,
    LiveTennisChartingPlayerTool,
    LiveTennisClient,
    LiveTennisFixturesTool,
    LiveTennisH2HTool,
    LiveTennisMatchesTool,
    LiveTennisMatchStatisticsTool,
    LiveTennisMatchTool,
    LiveTennisPlayerRankingsTool,
    LiveTennisPlayerSearchTool,
    LiveTennisPlayerTool,
    LiveTennisRankingsTool,
    LiveTennisScoreTool,
)

ALL_TOOLS = [
    LiveTennisMatchesTool,
    LiveTennisMatchTool,
    LiveTennisScoreTool,
    LiveTennisPlayerSearchTool,
    LiveTennisPlayerTool,
    LiveTennisFixturesTool,
    LiveTennisH2HTool,
    LiveTennisArchiveMatchesTool,
    LiveTennisArchivePlayersTool,
    LiveTennisArchiveCareerTool,
    LiveTennisRankingsTool,
    LiveTennisPlayerRankingsTool,
    LiveTennisMatchStatisticsTool,
    LiveTennisChartingPlayerTool,
    LiveTennisChartingMatchTool,
]

#: Tools that need a paid plan, and the plan their description must name.
GATED_TOOLS = {
    LiveTennisH2HTool: "BASIC",
    LiveTennisArchiveMatchesTool: "BASIC",
    LiveTennisArchivePlayersTool: "BASIC",
    LiveTennisArchiveCareerTool: "BASIC",
    LiveTennisRankingsTool: "PRO",
    LiveTennisPlayerRankingsTool: "ULTRA",
    LiveTennisMatchStatisticsTool: "ULTRA",
    LiveTennisChartingPlayerTool: "ULTRA",
    LiveTennisChartingMatchTool: "ULTRA",
}


@pytest.mark.parametrize("tool_cls", ALL_TOOLS)
def test_tool_metadata_is_model_ready(
    tool_cls: type[BaseTool], client: LiveTennisClient
) -> None:
    tool = tool_cls(client=client)
    assert isinstance(tool, BaseTool)
    assert tool.name == tool.name.lower()
    assert tool.name.startswith("live_tennis")
    assert len(tool.description) > 40
    assert tool.args_schema is not None


@pytest.mark.parametrize("tool_cls", ALL_TOOLS)
def test_tool_json_schema_is_well_formed(
    tool_cls: type[BaseTool], client: LiveTennisClient
) -> None:
    schema = tool_cls(client=client).tool_call_schema.model_json_schema()
    assert schema["type"] == "object"
    for prop in schema["properties"].values():
        assert prop.get("description"), schema
    # The client is plumbing, not a model-visible argument.
    assert "client" not in schema["properties"]
    assert "api_key" not in schema["properties"]


def test_matches_args_expose_the_documented_enums(client: LiveTennisClient) -> None:
    schema = LiveTennisMatchesTool(client=client).tool_call_schema.model_json_schema()
    defs = json.dumps(schema)
    for value in (
        "live",
        "upcoming",
        "completed",
        "atp",
        "wta",
        "challenger",
        "itf",
        "juniors",
    ):
        assert f'"{value}"' in defs


def test_matches_limit_is_bounded(client: LiveTennisClient) -> None:
    props = LiveTennisMatchesTool(client=client).tool_call_schema.model_json_schema()[
        "properties"
    ]
    assert props["limit"]["minimum"] == 1
    assert props["limit"]["maximum"] == 200


def test_matches_invoke_directly(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisMatchesTool(client=client).invoke({"status": "live"})
    )
    assert [m["id"] for m in payload["data"]] == [18953, 18954]


def test_matches_invoke_with_tour(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisMatchesTool(client=client).invoke(
            {"status": "live", "tour": "wta", "limit": 5}
        )
    )
    assert payload["data"][0]["players"]["p1"]["name"] == "A. Sabalenka"


def test_match_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(LiveTennisMatchTool(client=client).invoke({"match_id": 18953}))
    assert payload["round"] == "R16"


def test_score_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(LiveTennisScoreTool(client=client).invoke({"match_id": 18953}))
    assert payload["server"] == 1


def test_player_search_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisPlayerSearchTool(client=client).invoke({"search": "sinner"})
    )
    assert payload["data"][0]["id"] == 5533


def test_player_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisPlayerTool(client=client).invoke({"player_id": 4021})
    )
    assert payload["country"] == "ESP"


def test_fixtures_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(LiveTennisFixturesTool(client=client).invoke({"limit": 1}))
    assert payload["data"][0]["player1_name"] == "N. Djokovic"


def test_invoke_as_a_tool_call_returns_a_tool_message(client: LiveTennisClient) -> None:
    tool = LiveTennisScoreTool(client=client)
    model_generated_tool_call = {
        "args": {"match_id": 18953},
        "id": "1",
        "name": tool.name,
        "type": "tool_call",
    }
    message = tool.invoke(model_generated_tool_call)
    assert isinstance(message, ToolMessage)
    assert json.loads(message.content)["is_tiebreak"] is False


async def test_async_invocation_works(client: LiveTennisClient) -> None:
    payload = json.loads(
        await LiveTennisFixturesTool(client=client).ainvoke({"limit": 1})
    )
    assert payload["meta"]["count"] == 1


def test_bad_arguments_are_rejected_before_the_call(client: LiveTennisClient) -> None:
    with pytest.raises(Exception, match="validation error"):
        LiveTennisMatchesTool(client=client).invoke({"status": "finished"})


def test_api_errors_become_tool_exceptions(client: LiveTennisClient) -> None:
    with pytest.raises(ToolException, match="404"):
        LiveTennisMatchTool(client=client).invoke({"match_id": 999999})


def test_upgrade_required_surfaces_as_a_tool_exception(
    client: LiveTennisClient,
) -> None:
    with pytest.raises(ToolException, match="403"):
        LiveTennisMatchesTool(client=client).invoke({"status": "completed"})


@pytest.mark.parametrize("tool_cls", list(GATED_TOOLS))
def test_gated_tools_name_their_plan(
    tool_cls: type[BaseTool], client: LiveTennisClient
) -> None:
    # An agent must be able to explain a 403, so the gate lives in the
    # model-visible description, not only in the docs.
    tool = tool_cls(client=client)
    assert GATED_TOOLS[tool_cls] in tool.description
    assert "403" in tool.description


def test_matches_filters_reach_the_server(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisMatchesTool(client=client).invoke(
            {"status": "live", "player": [7710], "country": "pol"}
        )
    )
    assert [m["id"] for m in payload["data"]] == [18954]


def test_fixtures_tour_filter(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisFixturesTool(client=client).invoke({"tour": "atp", "limit": 1})
    )
    assert payload["data"][0]["tour"] == "atp"


def test_h2h_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisH2HTool(client=client).invoke({"p1": "alcaraz", "p2": "sinner"})
    )
    assert payload["totals"] == {"p1_wins": 6, "p2_wins": 4, "undecided": 0}


def test_h2h_short_fragment_is_rejected_before_the_call(
    client: LiveTennisClient,
) -> None:
    with pytest.raises(Exception, match="validation error"):
        LiveTennisH2HTool(client=client).invoke({"p1": "al", "p2": "sinner"})


def test_archive_matches_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisArchiveMatchesTool(client=client).invoke(
            {"name": "borg", "tour": "atp", "round_code": "F"}
        )
    )
    assert payload["data"][0]["winner"]["name"] == "Bjorn Borg"


def test_archive_matches_args_expose_round_enum(client: LiveTennisClient) -> None:
    schema = LiveTennisArchiveMatchesTool(
        client=client
    ).tool_call_schema.model_json_schema()
    defs = json.dumps(schema)
    for value in ("F", "SF", "QF", "R16", "R128"):
        assert f'"{value}"' in defs


def test_archive_players_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisArchivePlayersTool(client=client).invoke({"name": "borg"})
    )
    assert payload["data"][0]["career_high_rank"] == 1


def test_archive_career_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisArchiveCareerTool(client=client).invoke({"name": "borg"})
    )
    assert payload["record"] == {"wins": 654, "losses": 140}


def test_rankings_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisRankingsTool(client=client).invoke({"system": "atp", "limit": 2})
    )
    assert [r["rank"] for r in payload["data"]] == [1, 2]


def test_rankings_system_is_required(client: LiveTennisClient) -> None:
    with pytest.raises(Exception, match="validation error"):
        LiveTennisRankingsTool(client=client).invoke({})


def test_rankings_listing_has_no_utr(client: LiveTennisClient) -> None:
    # UTR is a rating, not a ranking - only the per-player tool offers it.
    listing = LiveTennisRankingsTool(client=client).tool_call_schema
    per_player = LiveTennisPlayerRankingsTool(client=client).tool_call_schema
    assert '"utr"' not in json.dumps(listing.model_json_schema())
    assert '"utr"' in json.dumps(per_player.model_json_schema())


def test_player_rankings_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisPlayerRankingsTool(client=client).invoke(
            {"player": [4021, 5533], "as_of": "2026-08-03"}
        )
    )
    assert {r["player_id"] for r in payload["data"]} == {4021, 5533}


def test_match_statistics_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisMatchStatisticsTool(client=client).invoke({"match_id": 18953})
    )
    assert payload["players"]["p1"]["measured"]["aces"] == 7


def test_charting_player_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisChartingPlayerTool(client=client).invoke(
            {"name": "federer", "gender": "men"}
        )
    )
    assert payload["matches_charted"] == 622


def test_charting_match_invoke(client: LiveTennisClient) -> None:
    payload = json.loads(
        LiveTennisChartingMatchTool(client=client).invoke({"charting_match_id": 77001})
    )
    assert payload["players"] == {"p1": "Roger Federer", "p2": "Rafael Nadal"}


def test_tool_builds_its_own_client_from_a_key() -> None:
    tool = LiveTennisMatchesTool(api_key="secret-key")
    assert tool.api.api_key == "secret-key"
    assert "secret-key" not in repr(tool)
