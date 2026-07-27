"""LangChain tools for the Live Tennis API.

Six read-only tools, one per public v1 endpoint. Each returns a JSON string, so
the model sees the API payload unaltered rather than a lossy prose summary.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from typing_extensions import Self

from ._client import MAX_LIMIT, LiveTennisClient
from .exceptions import LiveTennisAPIError

if TYPE_CHECKING:
    from langchain_core.callbacks import CallbackManagerForToolRun

Tour = Literal["atp", "wta", "challenger", "itf", "juniors"]
MatchStatus = Literal["live", "upcoming", "completed"]

_DEFAULT_LIMIT = 10


def _dumps(payload: Any) -> str:
    """Serialise an API payload for the model."""
    return json.dumps(payload, ensure_ascii=False, default=str)


class _LiveTennisBaseTool(BaseTool):
    """Shared plumbing: one configured client, uniform error translation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_key: SecretStr | None = Field(default=None, exclude=True)
    """Live Tennis API key. Defaults to the ``LIVETENNISAPI_KEY`` env var."""

    client: LiveTennisClient | None = Field(default=None, exclude=True)
    """Pre-built client. Supply one to share a connection pool across tools."""

    @model_validator(mode="after")
    def _build_client(self) -> Self:
        """Create a client from ``api_key`` when one was not supplied."""
        if self.client is None:
            key = self.api_key.get_secret_value() if self.api_key else None
            self.client = LiveTennisClient(api_key=key)
        return self

    @property
    def api(self) -> LiveTennisClient:
        """The configured Live Tennis API client."""
        if self.client is None:  # pragma: no cover - guaranteed by the validator
            self.client = LiveTennisClient()
        return self.client

    def _call(self, fn: str, /, **kwargs: Any) -> str:
        """Invoke a client method and translate failures into `ToolException`."""
        try:
            return _dumps(getattr(self.api, fn)(**kwargs))
        except LiveTennisAPIError as exc:
            raise ToolException(str(exc)) from exc


# ---------------------------------------------------------------------------
# Endpoint: /matches
# ---------------------------------------------------------------------------


class LiveTennisMatchesInput(BaseModel):
    """Input for `live_tennis_matches`."""

    status: MatchStatus = Field(
        default="live",
        description=(
            "Which slice of the schedule to read: 'live' for matches in play, "
            "'upcoming' for scheduled ones, 'completed' for finished ones "
            "(a paid History feature - a free key gets HTTP 403 for it)."
        ),
    )
    tour: Tour | None = Field(
        default=None,
        description=(
            "Restrict to one tour. Each value covers that tour's singles and "
            "doubles draws, and 'juniors' covers the boys' and girls' Grand "
            "Slam draws. Omit for all tours."
        ),
    )
    limit: int = Field(
        default=_DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of matches to return (1-200).",
    )


class LiveTennisMatchesTool(_LiveTennisBaseTool):
    """List tennis matches by lifecycle status, optionally filtered to one tour.

    Setup:
        Install ``langchain-livetennis`` and set ``LIVETENNISAPI_KEY``.

        .. code-block:: bash

            pip install -U langchain-livetennis
            export LIVETENNISAPI_KEY="your-key"

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisMatchesTool

            tool = LiveTennisMatchesTool()
            tool.invoke({"status": "live", "tour": "atp", "limit": 5})
    """

    name: str = "live_tennis_matches"
    description: str = (
        "Get tennis matches from the Live Tennis API, with the current score on "
        "each. Use it to answer 'what is on right now', 'who is playing today' "
        "or 'what were the results'. Covers ATP, WTA, Challenger, ITF and "
        "junior Grand Slam draws. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisMatchesInput

    def _run(
        self,
        status: MatchStatus = "live",
        tour: Tour | None = None,
        limit: int = _DEFAULT_LIMIT,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /matches``."""
        return self._call("list_matches", status=status, tour=tour, limit=limit)


# ---------------------------------------------------------------------------
# Endpoint: /matches/{id}
# ---------------------------------------------------------------------------


class LiveTennisMatchInput(BaseModel):
    """Input for `live_tennis_match`."""

    match_id: int = Field(
        description=(
            "Numeric match id, as returned in the 'id' field by "
            "live_tennis_matches or live_tennis_fixtures."
        )
    )


class LiveTennisMatchTool(_LiveTennisBaseTool):
    """Fetch one match in full: players, tournament, surface, round and score.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisMatchTool

            LiveTennisMatchTool().invoke({"match_id": 18953})
    """

    name: str = "live_tennis_match"
    description: str = (
        "Get the full detail of one tennis match by its id: both players, "
        "tournament, surface, round, status and the latest score. Call "
        "live_tennis_matches first if you do not already have a match id. "
        "Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisMatchInput

    def _run(
        self,
        match_id: int,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /matches/{id}``."""
        return self._call("get_match", match_id=match_id)


# ---------------------------------------------------------------------------
# Endpoint: /matches/{id}/score
# ---------------------------------------------------------------------------


class LiveTennisScoreInput(BaseModel):
    """Input for `live_tennis_match_score`."""

    match_id: int = Field(description="Numeric match id to read the score for.")


class LiveTennisScoreTool(_LiveTennisBaseTool):
    """Fetch only the live score of a match - the lowest-latency read available.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisScoreTool

            LiveTennisScoreTool().invoke({"match_id": 18953})
    """

    name: str = "live_tennis_match_score"
    description: str = (
        "Get just the current score of one tennis match: sets, games, points, "
        "who is serving and whether a tiebreak is in play. Cheaper and fresher "
        "than fetching the whole match. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisScoreInput

    def _run(
        self,
        match_id: int,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /matches/{id}/score``."""
        return self._call("get_match_score", match_id=match_id)


# ---------------------------------------------------------------------------
# Endpoint: /players
# ---------------------------------------------------------------------------


class LiveTennisPlayerSearchInput(BaseModel):
    """Input for `live_tennis_player_search`."""

    search: str = Field(description="Part of a player's name, e.g. 'alcaraz'.")
    limit: int = Field(
        default=_DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of players to return (1-200).",
    )


class LiveTennisPlayerSearchTool(_LiveTennisBaseTool):
    """Search the player directory by name, ranked players first.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisPlayerSearchTool

            LiveTennisPlayerSearchTool().invoke({"search": "alcaraz"})
    """

    name: str = "live_tennis_player_search"
    description: str = (
        "Find tennis players by name and get their id, tour, country and "
        "current ranking. Use it to turn a player's name into the id the other "
        "tools need. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisPlayerSearchInput

    def _run(
        self,
        search: str,
        limit: int = _DEFAULT_LIMIT,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /players``."""
        return self._call("search_players", search=search, limit=limit)


# ---------------------------------------------------------------------------
# Endpoint: /players/{id}
# ---------------------------------------------------------------------------


class LiveTennisPlayerInput(BaseModel):
    """Input for `live_tennis_player`."""

    player_id: int = Field(
        description=(
            "Numeric player id, as returned in the 'id' field by "
            "live_tennis_player_search."
        )
    )


class LiveTennisPlayerTool(_LiveTennisBaseTool):
    """Fetch one player's profile: bio, ranking and cached statistics.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisPlayerTool

            LiveTennisPlayerTool().invoke({"player_id": 4021})
    """

    name: str = "live_tennis_player"
    description: str = (
        "Get one tennis player's profile by id: name, tour, country, ranking "
        "and ranking points, plus cached statistics. Call "
        "live_tennis_player_search first to resolve a name to an id. "
        "Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisPlayerInput

    def _run(
        self,
        player_id: int,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /players/{id}``."""
        return self._call("get_player", player_id=player_id)


# ---------------------------------------------------------------------------
# Endpoint: /fixtures
# ---------------------------------------------------------------------------


class LiveTennisFixturesInput(BaseModel):
    """Input for `live_tennis_fixtures`."""

    limit: int = Field(
        default=_DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of fixtures to return (1-200).",
    )


class LiveTennisFixturesTool(_LiveTennisBaseTool):
    """List upcoming scheduled fixtures, earliest first.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisFixturesTool

            LiveTennisFixturesTool().invoke({"limit": 5})
    """

    name: str = "live_tennis_fixtures"
    description: str = (
        "List upcoming tennis fixtures, earliest first, with the date, "
        "tournament, round, surface and both player names. Use it to answer "
        "'what is scheduled next'. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisFixturesInput

    def _run(
        self,
        limit: int = _DEFAULT_LIMIT,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /fixtures``."""
        return self._call("list_fixtures", limit=limit)
