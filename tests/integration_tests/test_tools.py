"""Integration tests against the real API.

Skipped unless ``LIVETENNISAPI_KEY`` is set, so `pytest` stays green offline and
no credential is ever required to run the unit suite.
"""

from __future__ import annotations

import json
import os

import pytest

from langchain_livetennis import LiveTennisToolkit

pytestmark = pytest.mark.skipif(
    not os.environ.get("LIVETENNISAPI_KEY"),
    reason="set LIVETENNISAPI_KEY to run integration tests",
)


@pytest.mark.requires_key
def test_live_matches_round_trip() -> None:
    tools = {t.name: t for t in LiveTennisToolkit().get_tools()}
    payload = json.loads(
        tools["live_tennis_matches"].invoke({"status": "live", "limit": 3})
    )
    assert "data" in payload


@pytest.mark.requires_key
def test_fixtures_round_trip() -> None:
    tools = {t.name: t for t in LiveTennisToolkit().get_tools()}
    payload = json.loads(tools["live_tennis_fixtures"].invoke({"limit": 3}))
    assert "data" in payload
