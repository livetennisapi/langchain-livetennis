"""Toolkit bundling every Live Tennis API tool behind one shared client."""

from __future__ import annotations

from langchain_core.tools import BaseTool, BaseToolkit
from pydantic import ConfigDict, Field, SecretStr, model_validator
from typing_extensions import Self

from ._client import LiveTennisClient
from .tools import (
    LiveTennisFixturesTool,
    LiveTennisMatchesTool,
    LiveTennisMatchTool,
    LiveTennisPlayerSearchTool,
    LiveTennisPlayerTool,
    LiveTennisScoreTool,
)


class LiveTennisToolkit(BaseToolkit):
    """All six Live Tennis API tools, sharing one HTTP connection pool.

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
        ``live_tennis_matches``, ``live_tennis_match``,
        ``live_tennis_match_score``, ``live_tennis_player_search``,
        ``live_tennis_player``, ``live_tennis_fixtures``.
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
        ]
