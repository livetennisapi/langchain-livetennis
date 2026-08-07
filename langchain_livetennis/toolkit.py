"""Toolkit bundling every Live Tennis API tool behind one shared client."""

from __future__ import annotations

from langchain_core.tools import BaseTool, BaseToolkit
from pydantic import ConfigDict, Field, SecretStr, model_validator
from typing_extensions import Self

from ._client import LiveTennisClient
from .tools import (
    LiveTennisArchiveCareerTool,
    LiveTennisArchiveMatchesTool,
    LiveTennisArchivePlayersTool,
    LiveTennisChartingMatchTool,
    LiveTennisChartingPlayerTool,
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


class LiveTennisToolkit(BaseToolkit):
    """Every Live Tennis API tool, sharing one HTTP connection pool.

    Setup:
        .. code-block:: bash

            pip install -U langchain-livetennis
            export LIVETENNISAPI_KEY="your-key"

        Free keys (100 requests/day) are at
        https://livetennisapi.com/subscribe/free.

    Instantiate:
        .. code-block:: python

            from langchain_livetennis import LiveTennisToolkit

            toolkit = LiveTennisToolkit()
            tools = toolkit.get_tools()

    Tools:
        FREE - ``live_tennis_matches``, ``live_tennis_match``,
        ``live_tennis_match_score``, ``live_tennis_player_search``,
        ``live_tennis_player``, ``live_tennis_fixtures``.
        BASIC+ - ``live_tennis_h2h``, ``live_tennis_archive_matches``,
        ``live_tennis_archive_players``, ``live_tennis_archive_career``
        (and ``status="completed"`` on ``live_tennis_matches``).
        PRO+ - ``live_tennis_rankings``.
        ULTRA - ``live_tennis_player_rankings``,
        ``live_tennis_match_statistics``, ``live_tennis_charting_player``,
        ``live_tennis_charting_match``.

        A tool above the key's plan still binds and appears in
        :meth:`get_tools`; calling it surfaces the API's 403 as a
        ``ToolException`` naming the plan that unlocks it.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_key: SecretStr | None = Field(default=None, exclude=True)
    """Live Tennis API key. Defaults to the ``LIVETENNISAPI_KEY`` env var."""

    base_url: str | None = Field(default=None, exclude=True)
    """Override the API root. Mainly useful for testing against a local fake."""

    client: LiveTennisClient | None = Field(default=None, exclude=True)
    """Pre-built client. Takes precedence over ``api_key`` and ``base_url``."""

    @model_validator(mode="after")
    def _build_client(self) -> Self:
        """Create the shared client when the caller did not supply one."""
        if self.client is None:
            key = self.api_key.get_secret_value() if self.api_key else None
            self.client = LiveTennisClient(api_key=key, base_url=self.base_url)
        return self

    def get_tools(self) -> list[BaseTool]:
        """Return every Live Tennis tool, each bound to the shared client."""
        client = self.client
        return [
            LiveTennisMatchesTool(client=client),
            LiveTennisMatchTool(client=client),
            LiveTennisScoreTool(client=client),
            LiveTennisPlayerSearchTool(client=client),
            LiveTennisPlayerTool(client=client),
            LiveTennisFixturesTool(client=client),
            LiveTennisH2HTool(client=client),
            LiveTennisArchiveMatchesTool(client=client),
            LiveTennisArchivePlayersTool(client=client),
            LiveTennisArchiveCareerTool(client=client),
            LiveTennisRankingsTool(client=client),
            LiveTennisPlayerRankingsTool(client=client),
            LiveTennisMatchStatisticsTool(client=client),
            LiveTennisChartingPlayerTool(client=client),
            LiveTennisChartingMatchTool(client=client),
        ]
