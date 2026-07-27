"""Shared fixtures. Every unit test runs against the in-process fake API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mock_api import TEST_KEY, mock_http_client

from langchain_livetennis import LiveTennisClient, LiveTennisToolkit


@pytest.fixture
def client() -> Iterator[LiveTennisClient]:
    """A `LiveTennisClient` whose transport is the fake API."""
    api = LiveTennisClient(api_key=TEST_KEY, client=mock_http_client())
    yield api
    api.close()


@pytest.fixture
def keyless_client() -> Iterator[LiveTennisClient]:
    """A client with no API key, to exercise the 401 path."""
    api = LiveTennisClient(api_key="", max_retries=0, client=mock_http_client())
    yield api
    api.close()


@pytest.fixture
def toolkit(client: LiveTennisClient) -> LiveTennisToolkit:
    """A toolkit bound to the fake API."""
    return LiveTennisToolkit(client=client)
