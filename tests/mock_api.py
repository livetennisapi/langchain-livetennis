"""A local, in-process fake of the Live Tennis API.

Used by the unit tests and by the end-to-end tool-calling proof. It speaks the
same shapes as the real API (payloads modelled on the published OpenAPI 3.1
spec) and enforces the same auth rule: no ``x-api-key`` header means HTTP 401
``{"error": "unauthorized"}``.

No network access is required or performed.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

TEST_KEY = "test-key-not-a-real-credential"

TOURS = {"atp", "wta", "challenger", "itf", "juniors"}
STATUSES = {"live", "upcoming", "completed"}

MATCHES: list[dict[str, Any]] = [
    {
        "id": 18953,
        "tournament": "Wimbledon",
        "surface": "grass",
        "indoor": False,
        "format": "BO5",
        "round": "R16",
        "status": "live",
        "event_status": "in_progress",
        "is_doubles": False,
        "scheduled_time": "2026-07-06T13:00:00Z",
        "players": {
            "p1": {
                "id": 4021,
                "name": "C. Alcaraz",
                "tour": "atp",
                "country": "ESP",
                "ranking": 2,
            },
            "p2": {
                "id": 5533,
                "name": "J. Sinner",
                "tour": "atp",
                "country": "ITA",
                "ranking": 1,
            },
        },
        "score": {
            "sets": ["6-4", "3-6", "2-1"],
            "games": ["40-30"],
            "points": ["40", "30"],
            "server": 1,
            "is_tiebreak": False,
        },
        "winner": None,
    },
    {
        "id": 18954,
        "tournament": "Wimbledon",
        "surface": "grass",
        "indoor": False,
        "format": "BO3",
        "round": "QF",
        "status": "live",
        "event_status": "in_progress",
        "is_doubles": False,
        "scheduled_time": "2026-07-06T15:00:00Z",
        "players": {
            "p1": {
                "id": 7710,
                "name": "A. Sabalenka",
                "tour": "wta",
                "country": "BLR",
                "ranking": 1,
            },
            "p2": {
                "id": 7712,
                "name": "I. Swiatek",
                "tour": "wta",
                "country": "POL",
                "ranking": 2,
            },
        },
        "score": {
            "sets": ["7-5", "1-0"],
            "games": ["15-0"],
            "points": ["15", "0"],
            "server": 2,
            "is_tiebreak": False,
        },
        "winner": None,
    },
]

PLAYERS: list[dict[str, Any]] = [
    {
        "id": 4021,
        "name": "C. Alcaraz",
        "tour": "atp",
        "country": "ESP",
        "ranking": 2,
        "ranking_points": 8850,
        "ranking_movement": "same",
        "hand": "R",
        "is_doubles_team": False,
    },
    {
        "id": 5533,
        "name": "J. Sinner",
        "tour": "atp",
        "country": "ITA",
        "ranking": 1,
        "ranking_points": 11500,
        "ranking_movement": "same",
        "hand": "R",
        "is_doubles_team": False,
    },
]

FIXTURES: list[dict[str, Any]] = [
    {
        "id": 19001,
        "event_date": "2026-07-07T11:00:00Z",
        "tour": "atp",
        "tournament": "Wimbledon",
        "round": "QF",
        "surface": "grass",
        "player1_name": "N. Djokovic",
        "player2_name": "A. Zverev",
        "status": "upcoming",
    }
]


def _json(
    status: int, payload: Any, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json", **(headers or {})},
    )


def _page(items: list[dict[str, Any]], limit: int | None) -> httpx.Response:
    sliced = items[: limit or len(items)]
    return _json(
        200, {"data": sliced, "meta": {"count": len(items), "limit": limit or 50}}
    )


def handler(request: httpx.Request) -> httpx.Response:
    """Route one request against the fake API."""
    if request.headers.get("x-api-key") != TEST_KEY:
        return _json(401, {"error": "unauthorized"})

    path = urlparse(str(request.url)).path
    path = path.split("/api/public/v1", 1)[-1] or "/"
    query = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}
    limit = int(query["limit"]) if "limit" in query else None

    if path == "/matches":
        status = query.get("status", "live")
        if status not in STATUSES:
            return _json(400, {"error": "bad_request"})
        if status == "completed":
            return _json(403, {"error": "upgrade_required"})
        tour = query.get("tour")
        if tour is not None and tour not in TOURS:
            return _json(400, {"error": "bad_request"})
        items = [
            m for m in MATCHES if tour is None or m["players"]["p1"]["tour"] == tour
        ]
        return _page(items, limit)

    if path.startswith("/matches/") and path.endswith("/score"):
        match_id = int(path.split("/")[2])
        found = next((m for m in MATCHES if m["id"] == match_id), None)
        return (
            _json(200, found["score"]) if found else _json(404, {"error": "not_found"})
        )

    if path.startswith("/matches/"):
        match_id = int(path.split("/")[2])
        found = next((m for m in MATCHES if m["id"] == match_id), None)
        return _json(200, found) if found else _json(404, {"error": "not_found"})

    if path == "/players":
        search = (query.get("search") or "").lower()
        items = [p for p in PLAYERS if search in p["name"].lower()]
        return _page(items, limit)

    if path.startswith("/players/"):
        player_id = int(path.split("/")[2])
        found = next((p for p in PLAYERS if p["id"] == player_id), None)
        return _json(200, found) if found else _json(404, {"error": "not_found"})

    if path == "/fixtures":
        return _page(FIXTURES, limit)

    return _json(404, {"error": "not_found"})


def mock_transport() -> httpx.MockTransport:
    """An ``httpx`` transport that answers from the fake API, never the network."""
    return httpx.MockTransport(handler)


def mock_http_client() -> httpx.Client:
    """An ``httpx.Client`` wired to the fake API instead of the network.

    It deliberately sets no auth header of its own, so the ``x-api-key`` the
    package sends is the only thing that can satisfy the fake's auth check.
    """
    return httpx.Client(transport=mock_transport())
