"""LangChain tools for the Live Tennis API.

Read-only tools, one per public v1 endpoint. Each returns a JSON string, so
the model sees the API payload unaltered rather than a lossy prose summary.

Tier gates: every tool states in its description which plan unlocks it, so an
agent can explain a 403 instead of retrying it. FREE covers live/upcoming
matches, players and fixtures; BASIC adds completed matches, head-to-head and
the 1968-2022 results archive; PRO adds the rankings listing; ULTRA adds
per-player as-of rankings, in-play statistics and shot-level charting.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from typing_extensions import Self

from ._client import MAX_LIMIT, MAX_PLAYER_IDS, LiveTennisClient
from .exceptions import LiveTennisAPIError

if TYPE_CHECKING:
    from langchain_core.callbacks import CallbackManagerForToolRun

Tour = Literal["atp", "wta", "challenger", "itf", "juniors"]
MatchStatus = Literal["live", "upcoming", "completed"]
ArchiveTour = Literal["atp", "wta"]
ArchiveRound = Literal[
    "F",
    "SF",
    "QF",
    "R16",
    "R32",
    "R64",
    "R128",
    "RR",
    "BR",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "ER",
]
RankingListSystem = Literal["atp", "wta", "itf_jt", "itf_mt", "itf_wt"]
RankingSystem = Literal["atp", "wta", "itf_jt", "itf_mt", "itf_wt", "utr"]
Gender = Literal["men", "women"]

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
    player: list[int] | None = Field(
        default=None,
        max_length=MAX_PLAYER_IDS,
        description=(
            "Restrict to matches where any of these player ids (from "
            "live_tennis_player_search) is either participant. Max 50 ids."
        ),
    )
    country: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description=(
            "Restrict to matches where either participant's country equals "
            "this lowercase 3-letter IOC-style code (e.g. 'ned', 'sui', 'gre' "
            "- the same codes the player objects return, not ISO-3166)."
        ),
    )
    from_date: str | None = Field(
        default=None,
        description=(
            "Earliest play date, YYYY-MM-DD or ISO-8601 UTC datetime. A bare "
            "date is a UTC day boundary. Works with every status."
        ),
    )
    to_date: str | None = Field(
        default=None,
        description=(
            "Latest play date (a bare date includes the whole UTC day); must "
            "not precede from_date."
        ),
    )
    limit: int = Field(
        default=_DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of matches to return (1-200).",
    )


class LiveTennisMatchesTool(_LiveTennisBaseTool):
    """List tennis matches by lifecycle status, with optional filters.

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
        "juniors; filter by tour, player ids, country or date range. "
        "status='completed' needs the BASIC plan or above. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisMatchesInput

    def _run(
        self,
        status: MatchStatus = "live",
        tour: Tour | None = None,
        player: list[int] | None = None,
        country: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = _DEFAULT_LIMIT,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /matches``."""
        return self._call(
            "list_matches",
            status=status,
            tour=tour,
            player=player,
            country=country,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )


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

    tour: Tour | None = Field(
        default=None,
        description=(
            "Restrict to one tour: 'atp', 'wta', 'challenger', 'itf' or "
            "'juniors'. Omit for all tours."
        ),
    )
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
        tour: Tour | None = None,
        limit: int = _DEFAULT_LIMIT,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /fixtures``."""
        return self._call("list_fixtures", tour=tour, limit=limit)


# ---------------------------------------------------------------------------
# Endpoint: /h2h
# ---------------------------------------------------------------------------


class LiveTennisH2HInput(BaseModel):
    """Input for `live_tennis_h2h`."""

    p1: str = Field(
        min_length=3,
        description="First player's name, or a fragment of it (min 3 chars).",
    )
    p2: str = Field(
        min_length=3,
        description="Second player's name, or a fragment of it (min 3 chars).",
    )


class LiveTennisH2HTool(_LiveTennisBaseTool):
    """Head-to-head record between two players, 1968 to now.

    Requires the BASIC plan or above (or any History plan).

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisH2HTool

            LiveTennisH2HTool().invoke({"p1": "alcaraz", "p2": "sinner"})
    """

    name: str = "live_tennis_h2h"
    description: str = (
        "Get the head-to-head record between two tennis players, assembled "
        "from the 1968-2022 results archive plus completed matches from 2023 "
        "on. Names are the keys; an ambiguous fragment is refused with the "
        "candidate list. Each meeting carries its outcome (walkovers and "
        "retirements included), and undecided meetings are counted apart. "
        "Requires the BASIC plan or above - a FREE key gets HTTP 403. "
        "Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisH2HInput

    def _run(
        self,
        p1: str,
        p2: str,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /h2h``."""
        return self._call("get_h2h", p1=p1, p2=p2)


# ---------------------------------------------------------------------------
# Endpoint: /history/archive/matches
# ---------------------------------------------------------------------------


class LiveTennisArchiveMatchesInput(BaseModel):
    """Input for `live_tennis_archive_matches`."""

    name: str | None = Field(
        default=None,
        min_length=3,
        description=(
            "Case-insensitive substring matched against either player's name "
            "(min 3 chars). Omit to browse by the other filters."
        ),
    )
    tour: ArchiveTour | None = Field(
        default=None,
        description="'atp' or 'wta' - the archive covers those two tours.",
    )
    from_date: str | None = Field(
        default=None,
        description="Earliest tournament start date, YYYY-MM-DD.",
    )
    to_date: str | None = Field(
        default=None,
        description="Latest tournament start date, YYYY-MM-DD.",
    )
    round_code: ArchiveRound | None = Field(
        default=None,
        description="Round: F, SF, QF, R16, R32, R64, R128, RR, BR, Q1-Q4 or ER.",
    )
    level: str | None = Field(
        default=None,
        description=(
            "Source tier code: G=grand slam, M=masters, A=tour, F=finals, "
            "D=davis cup, C=challenger, O=olympics; futures tiers carry their "
            "category codes (e.g. 15, 25)."
        ),
    )
    limit: int = Field(
        default=_DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of results to return (1-200).",
    )


class LiveTennisArchiveMatchesTool(_LiveTennisBaseTool):
    """Search the 1968-2022 results archive - 1.4M+ completed matches.

    Requires the BASIC plan or above (or any History plan).

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisArchiveMatchesTool

            LiveTennisArchiveMatchesTool().invoke({"name": "borg", "round_code": "F"})
    """

    name: str = "live_tennis_archive_matches"
    description: str = (
        "Search historical tennis results from 1968 through 2022: ATP and WTA "
        "main draws, qualifying, challengers and futures, with final score, "
        "round, seeds, the players' ranks at the time, and serve statistics "
        "where the era recorded them. Use it for questions about past decades; "
        "matches from 2023 on live in live_tennis_matches (status='completed') "
        "instead. Requires the BASIC plan or above - a FREE key gets HTTP 403. "
        "Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisArchiveMatchesInput

    def _run(
        self,
        name: str | None = None,
        tour: ArchiveTour | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        round_code: ArchiveRound | None = None,
        level: str | None = None,
        limit: int = _DEFAULT_LIMIT,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /history/archive/matches``."""
        return self._call(
            "list_archive_matches",
            name=name,
            tour=tour,
            from_date=from_date,
            to_date=to_date,
            round_code=round_code,
            level=level,
            limit=limit,
        )


# ---------------------------------------------------------------------------
# Endpoint: /history/archive/players
# ---------------------------------------------------------------------------


class LiveTennisArchivePlayersInput(BaseModel):
    """Input for `live_tennis_archive_players`."""

    name: str | None = Field(
        default=None,
        min_length=3,
        description="Case-insensitive substring of the player's name (min 3 chars).",
    )
    tour: ArchiveTour | None = Field(
        default=None,
        description="'atp' or 'wta'. Omit for both.",
    )
    limit: int = Field(
        default=_DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of players to return (1-200).",
    )


class LiveTennisArchivePlayersTool(_LiveTennisBaseTool):
    """Search archive player bios: hand, birth date, country, career-high rank.

    Requires the BASIC plan or above (or any History plan).

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisArchivePlayersTool

            LiveTennisArchivePlayersTool().invoke({"name": "navratilova"})
    """

    name: str = "live_tennis_archive_players"
    description: str = (
        "Find players of the 1968-2022 results archive and get their bio: "
        "hand, date of birth, country, height, and career-high rank with the "
        "week it was first reached (rankings back to 1973). Archive ids are a "
        "separate id space from live player ids - archive match rows carry "
        "them as winner/loser player_id. Null fields are the era's silence, "
        "never guessed. Requires the BASIC plan or above - a FREE key gets "
        "HTTP 403. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisArchivePlayersInput

    def _run(
        self,
        name: str | None = None,
        tour: ArchiveTour | None = None,
        limit: int = _DEFAULT_LIMIT,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /history/archive/players``."""
        return self._call("list_archive_players", name=name, tour=tour, limit=limit)


# ---------------------------------------------------------------------------
# Endpoint: /history/archive/career
# ---------------------------------------------------------------------------


class LiveTennisArchiveCareerInput(BaseModel):
    """Input for `live_tennis_archive_career`."""

    name: str = Field(
        min_length=3,
        description=(
            "Player name or fragment (min 3 chars); must resolve to exactly "
            "one archive person, otherwise the API refuses with candidates."
        ),
    )


class LiveTennisArchiveCareerTool(_LiveTennisBaseTool):
    """One player's whole 1968-2022 archive career in a single response.

    Requires the BASIC plan or above (or any History plan).

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisArchiveCareerTool

            LiveTennisArchiveCareerTool().invoke({"name": "bjorn borg"})
    """

    name: str = "live_tennis_archive_career"
    description: str = (
        "Get a historical player's career aggregates over the 1968-2022 "
        "archive: win-loss record overall and by surface, level and year, "
        "titles, and summed serve statistics with derived ratios (serve stats "
        "recorded from 1991 only, and the response states its own coverage). "
        "An ambiguous name is refused with the candidate list. Requires the "
        "BASIC plan or above - a FREE key gets HTTP 403. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisArchiveCareerInput

    def _run(
        self,
        name: str,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /history/archive/career``."""
        return self._call("get_archive_career", name=name)


# ---------------------------------------------------------------------------
# Endpoint: /rankings (listing mode)
# ---------------------------------------------------------------------------


class LiveTennisRankingsInput(BaseModel):
    """Input for `live_tennis_rankings`."""

    system: RankingListSystem = Field(
        description=(
            "Which published table to read: 'atp', 'wta', or an ITF circuit "
            "('itf_jt' juniors, 'itf_mt' men's, 'itf_wt' women's). UTR has no "
            "listing - it is a rating, not a ranking."
        ),
    )
    as_of: str | None = Field(
        default=None,
        description=(
            "YYYY-MM-DD; returns the newest published week at or before this "
            "date. Omit for the latest table."
        ),
    )
    limit: int = Field(
        default=_DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of ranking rows to return (1-200).",
    )


class LiveTennisRankingsTool(_LiveTennisBaseTool):
    """The full published ranking table for one system, in rank order.

    Requires the PRO plan or above.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisRankingsTool

            LiveTennisRankingsTool().invoke({"system": "atp", "limit": 10})
    """

    name: str = "live_tennis_rankings"
    description: str = (
        "Get a rank-ordered ranking table: ATP, WTA or an ITF circuit, the "
        "newest published week at or before as_of. Rows carry rank, "
        "previous_rank, points and the player's name as published (player_id "
        "is null for players outside the live roster, so the table has no "
        "silent holes). Use it for 'who is world number N' and top-N "
        "questions. Requires the PRO plan or above - lower tiers get "
        "HTTP 403. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisRankingsInput

    def _run(
        self,
        system: RankingListSystem,
        as_of: str | None = None,
        limit: int = _DEFAULT_LIMIT,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /rankings`` without ``player`` (listing mode)."""
        return self._call("list_rankings", system=system, as_of=as_of, limit=limit)


# ---------------------------------------------------------------------------
# Endpoint: /rankings (per-player as-of mode)
# ---------------------------------------------------------------------------


class LiveTennisPlayerRankingsInput(BaseModel):
    """Input for `live_tennis_player_rankings`."""

    player: list[int] = Field(
        min_length=1,
        max_length=MAX_PLAYER_IDS,
        description=(
            "Player id(s) from live_tennis_player_search, max 50. Each gets "
            "its own as-of record per ranking system."
        ),
    )
    system: list[RankingSystem] | None = Field(
        default=None,
        description=(
            "Restrict to one or more systems: 'atp', 'wta', ITF circuits, or "
            "'utr' (a rating: null rank and points). Omit for all."
        ),
    )
    as_of: str | None = Field(
        default=None,
        description=(
            "YYYY-MM-DD; returns the newest record effective on or before "
            "this date - never one dated after it. Omit for the latest."
        ),
    )


class LiveTennisPlayerRankingsTool(_LiveTennisBaseTool):
    """Point-in-time ranking records for specific players.

    Requires the ULTRA plan.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisPlayerRankingsTool

            tool = LiveTennisPlayerRankingsTool()
            tool.invoke({"player": [4021], "as_of": "2025-06-01"})
    """

    name: str = "live_tennis_player_rankings"
    description: str = (
        "Get the ranking a player actually held on a given date: per system, "
        "the newest record effective on or before as_of. Every other ranking "
        "field in this API is the player's current value joined at read time; "
        "this is the point-in-time answer, so use it for 'what was X ranked "
        "when...'. Systems stay separate (UTR is a rating with null rank). "
        "Requires the ULTRA plan - lower tiers get HTTP 403. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisPlayerRankingsInput

    def _run(
        self,
        player: list[int],
        system: list[RankingSystem] | None = None,
        as_of: str | None = None,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /rankings`` with ``player`` (per-player as-of mode)."""
        return self._call(
            "get_player_rankings", player=player, system=system, as_of=as_of
        )


# ---------------------------------------------------------------------------
# Endpoint: /matches/{id}/statistics
# ---------------------------------------------------------------------------


class LiveTennisMatchStatisticsInput(BaseModel):
    """Input for `live_tennis_match_statistics`."""

    match_id: int = Field(
        description=(
            "Numeric match id, as returned in the 'id' field by "
            "live_tennis_matches or live_tennis_fixtures."
        )
    )


class LiveTennisMatchStatisticsTool(_LiveTennisBaseTool):
    """In-play statistics for one match: aces, serve split, hold/break rates.

    Requires the ULTRA plan.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisMatchStatisticsTool

            LiveTennisMatchStatisticsTool().invoke({"match_id": 18953})
    """

    name: str = "live_tennis_match_statistics"
    description: str = (
        "Get in-play statistics for one tennis match, in two families: "
        "derived figures rebuilt from the point-by-point record (hold and "
        "break percentages, break points faced/saved/converted, service and "
        "return points) and measured figures counted upstream (aces, double "
        "faults, serve split, winners and unforced errors where covered). "
        "Absent measured fields are omitted, never zero-filled, and each "
        "family carries its own freshness. Works on live and completed "
        "matches. Requires the ULTRA plan - lower tiers get HTTP 403. "
        "Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisMatchStatisticsInput

    def _run(
        self,
        match_id: int,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /matches/{id}/statistics``."""
        return self._call("get_match_statistics", match_id=match_id)


# ---------------------------------------------------------------------------
# Endpoint: /charting/players
# ---------------------------------------------------------------------------


class LiveTennisChartingPlayerInput(BaseModel):
    """Input for `live_tennis_charting_player`."""

    name: str = Field(
        min_length=3,
        description=(
            "Player name or fragment (min 3 chars); must resolve to one "
            "charted person, otherwise the API refuses with candidates."
        ),
    )
    gender: Gender | None = Field(
        default=None,
        description="'men' or 'women', to disambiguate a name fragment.",
    )


class LiveTennisChartingPlayerTool(_LiveTennisBaseTool):
    """Career shot-level charting profile for one player (Match Charting Project).

    Requires the ULTRA plan.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisChartingPlayerTool

            LiveTennisChartingPlayerTool().invoke({"name": "federer", "gender": "men"})
    """

    name: str = "live_tennis_charting_player"
    description: str = (
        "Get the deepest serve/return profile held for a player, summed over "
        "their charted matches: serve placement by court side and direction, "
        "return depth and outcomes, net and serve-and-volley conversion, "
        "clutch-point serving, winners and errors by wing, rally-length "
        "tendencies. Coverage is curated (11,646 charted matches, "
        "concentrated on the majors) and matches_charted states the sample. "
        "Requires the ULTRA plan - lower tiers get HTTP 403. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisChartingPlayerInput

    def _run(
        self,
        name: str,
        gender: Gender | None = None,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /charting/players``."""
        return self._call("get_charting_player", name=name, gender=gender)


# ---------------------------------------------------------------------------
# Endpoint: /charting/matches/{id}
# ---------------------------------------------------------------------------


class LiveTennisChartingMatchInput(BaseModel):
    """Input for `live_tennis_charting_match`."""

    charting_match_id: int = Field(
        description=(
            "Charting match id - this product's own id space (1960-2026), "
            "distinct from live match ids."
        )
    )


class LiveTennisChartingMatchTool(_LiveTennisBaseTool):
    """Every charted stat family for one match, both players, per set.

    Requires the ULTRA plan.

    Invoke:
        .. code-block:: python

            from langchain_livetennis import LiveTennisChartingMatchTool

            LiveTennisChartingMatchTool().invoke({"charting_match_id": 77001})
    """

    name: str = "live_tennis_charting_match"
    description: str = (
        "Get one charted match from the Match Charting Project: every stat "
        "family for both players with the per-set split exactly as charted. "
        "Charting ids are their own id space (1960-2026), mostly matches with "
        "no counterpart in the live table. Requires the ULTRA plan - lower "
        "tiers get HTTP 403. Returns JSON."
    )
    args_schema: type[BaseModel] = LiveTennisChartingMatchInput

    def _run(
        self,
        charting_match_id: int,
        run_manager: CallbackManagerForToolRun | None = None,  # noqa: ARG002
    ) -> str:
        """Call ``GET /charting/matches/{id}``."""
        return self._call("get_charting_match", charting_match_id=charting_match_id)
