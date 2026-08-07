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

H2H: dict[str, Any] = {
    "p1": {"name": "Carlos Alcaraz"},
    "p2": {"name": "Jannik Sinner"},
    "totals": {"p1_wins": 6, "p2_wins": 4, "undecided": 0},
    "meetings": [
        {
            "date": "2026-06-08",
            "tournament": "Roland Garros",
            "winner": 1,
            "outcome": "completed",
        }
    ],
}

ARCHIVE_MATCHES: list[dict[str, Any]] = [
    {
        "id": 501,
        "tour": "atp",
        "event_date": "1980-07-01",
        "tournament": "Wimbledon",
        "round": "F",
        "level": "G",
        "winner": {"player_id": 9001, "name": "Bjorn Borg", "rank": 1},
        "loser": {"player_id": 9002, "name": "John McEnroe", "rank": 2},
        "score": "1-6 7-5 6-3 6-7 8-6",
        "stats": None,
    }
]

ARCHIVE_PLAYERS: list[dict[str, Any]] = [
    {
        "id": 9001,
        "tour": "atp",
        "name": "Bjorn Borg",
        "hand": "R",
        "country": "swe",
        "career_high_rank": 1,
    }
]

ARCHIVE_CAREER: dict[str, Any] = {
    "player": {"id": 9001, "name": "Bjorn Borg", "tour": "atp"},
    "record": {"wins": 654, "losses": 140},
    "titles": 66,
    "serve": {"matches_with_stats": 0},
}

RANKING_LIST_SYSTEMS = {"atp", "wta", "itf_jt", "itf_mt", "itf_wt"}

RANKINGS: list[dict[str, Any]] = [
    {
        "system": "atp",
        "rank": 1,
        "previous_rank": 1,
        "points": 11500,
        "player_id": 5533,
        "player_name": "Jannik Sinner",
        "effective_date": "2026-08-03",
    },
    {
        "system": "atp",
        "rank": 2,
        "previous_rank": 2,
        "points": 8850,
        "player_id": 4021,
        "player_name": "Carlos Alcaraz",
        "effective_date": "2026-08-03",
    },
]

STATISTICS: dict[str, Any] = {
    "match_id": 18953,
    "coverage": "live",
    "players": {
        "p1": {"hold_pct": 88.9, "measured": {"aces": 7, "double_faults": 1}},
        "p2": {"hold_pct": 80.0, "measured": {"aces": 11, "double_faults": 3}},
    },
    "freshness": {
        "derived": {"coverage": "live", "age_seconds": 4},
        "measured": {"coverage": "live", "age_seconds": 21},
    },
}

CHARTING_PLAYER: dict[str, Any] = {
    "player": {"name": "Roger Federer", "gender": "men"},
    "matches_charted": 622,
    "coverage": "curated",
    "families": {"serve_direction": {"deuce_wide": 1042}},
}

CHARTING_MATCH: dict[str, Any] = {
    "charting_match_id": 77001,
    "mcp_id": "20080706-M-Wimbledon-F-Roger_Federer-Rafael_Nadal",
    "gender": "men",
    "players": {"p1": "Roger Federer", "p2": "Rafael Nadal"},
    "families": {"serve_basics": {"p1": {"aces": 25}, "p2": {"aces": 6}}},
}


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
    multi = parse_qs(urlparse(str(request.url)).query)
    query = {k: v[0] for k, v in multi.items()}
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
        if "player" in multi:
            wanted = {int(value) for value in multi["player"]}
            items = [
                m
                for m in items
                if {m["players"]["p1"]["id"], m["players"]["p2"]["id"]} & wanted
            ]
        if "country" in query:
            if len(query["country"]) != 3:
                return _json(400, {"error": "bad_country"})
            code = query["country"].lower()
            items = [
                m
                for m in items
                if code
                in {
                    m["players"]["p1"]["country"].lower(),
                    m["players"]["p2"]["country"].lower(),
                }
            ]
        return _page(items, limit)

    if path.startswith("/matches/") and path.endswith("/statistics"):
        match_id = int(path.split("/")[2])
        if match_id != STATISTICS["match_id"]:
            return _json(404, {"error": "not_found"})
        return _json(200, STATISTICS)

    if path == "/h2h":
        p1, p2 = query.get("p1", ""), query.get("p2", "")
        if len(p1) < 3 or len(p2) < 3:
            return _json(400, {"error": "bad_request"})
        return _json(200, H2H)

    if path == "/history/archive/matches":
        tour = query.get("tour")
        if tour is not None and tour not in {"atp", "wta"}:
            return _json(400, {"error": "bad_tour"})
        name = (query.get("name") or "").lower()
        items = [
            m
            for m in ARCHIVE_MATCHES
            if (tour is None or m["tour"] == tour)
            and (
                not name
                or name in m["winner"]["name"].lower()
                or name in m["loser"]["name"].lower()
            )
        ]
        return _page(items, limit)

    if path == "/history/archive/players":
        name = (query.get("name") or "").lower()
        items = [p for p in ARCHIVE_PLAYERS if name in p["name"].lower()]
        return _page(items, limit)

    if path == "/history/archive/career":
        name = (query.get("name") or "").lower()
        if len(name) < 3:
            return _json(400, {"error": "bad_request"})
        if name not in ARCHIVE_CAREER["player"]["name"].lower():
            return _json(404, {"error": "not_found"})
        return _json(200, ARCHIVE_CAREER)

    if path == "/rankings":
        if "player" in multi:
            wanted = {int(value) for value in multi["player"]}
            items = [r for r in RANKINGS if r["player_id"] in wanted]
            return _page(items, limit)
        systems = multi.get("system", [])
        if len(systems) != 1 or systems[0] not in RANKING_LIST_SYSTEMS:
            return _json(400, {"error": "bad_request"})
        items = [r for r in RANKINGS if r["system"] == systems[0]]
        return _page(sorted(items, key=lambda r: r["rank"]), limit)

    if path == "/charting/players":
        name = (query.get("name") or "").lower()
        if len(name) < 3:
            return _json(400, {"error": "bad_request"})
        if name not in CHARTING_PLAYER["player"]["name"].lower():
            return _json(404, {"error": "not_found"})
        return _json(200, CHARTING_PLAYER)

    if path.startswith("/charting/matches/"):
        charting_id = int(path.split("/")[3])
        if charting_id != CHARTING_MATCH["charting_match_id"]:
            return _json(404, {"error": "not_found"})
        return _json(200, CHARTING_MATCH)

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
