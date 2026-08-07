"""The public surface is stable and complete."""

from __future__ import annotations

import langchain_livetennis

EXPECTED = [
    "LiveTennisAPIError",
    "LiveTennisAbuseThrottled",
    "LiveTennisArchiveCareerTool",
    "LiveTennisArchiveMatchesTool",
    "LiveTennisArchivePlayersTool",
    "LiveTennisAuthError",
    "LiveTennisBadRequest",
    "LiveTennisChartingMatchTool",
    "LiveTennisChartingPlayerTool",
    "LiveTennisClient",
    "LiveTennisFixturesTool",
    "LiveTennisH2HTool",
    "LiveTennisMatchStatisticsTool",
    "LiveTennisMatchTool",
    "LiveTennisMatchesTool",
    "LiveTennisNotFound",
    "LiveTennisPlayerRankingsTool",
    "LiveTennisPlayerSearchTool",
    "LiveTennisPlayerTool",
    "LiveTennisRankingsTool",
    "LiveTennisRateLimited",
    "LiveTennisScoreTool",
    "LiveTennisServerError",
    "LiveTennisToolkit",
    "LiveTennisUpgradeRequired",
    "__version__",
]


def test_all_matches_expected() -> None:
    assert sorted(langchain_livetennis.__all__) == sorted(EXPECTED)


def test_everything_in_all_is_importable() -> None:
    for name in langchain_livetennis.__all__:
        assert getattr(langchain_livetennis, name) is not None
