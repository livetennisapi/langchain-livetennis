"""The HTTP layer: URLs, auth, parameters and error mapping."""

from __future__ import annotations

import httpx
import pytest

from langchain_livetennis import (
    LiveTennisAbuseThrottled,
    LiveTennisAuthError,
    LiveTennisBadRequest,
    LiveTennisClient,
    LiveTennisNotFound,
    LiveTennisRateLimited,
    LiveTennisServerError,
    LiveTennisUpgradeRequired,
)
from langchain_livetennis._client import DEFAULT_BASE_URL, MAX_LIMIT


def test_default_base_url_is_public_v1() -> None:
    assert DEFAULT_BASE_URL == "https://api.livetennisapi.com/api/public/v1"


def test_api_key_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVETENNISAPI_KEY", "from-env")
    assert LiveTennisClient().api_key == "from-env"


def test_explicit_key_beats_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVETENNISAPI_KEY", "from-env")
    assert LiveTennisClient(api_key="explicit").api_key == "explicit"


def test_list_matches_returns_page(client: LiveTennisClient) -> None:
    page = client.list_matches("live")
    assert [m["id"] for m in page["data"]] == [18953, 18954]
    assert page["meta"]["count"] == 2


def test_tour_filter_is_sent_to_the_server(client: LiveTennisClient) -> None:
    page = client.list_matches("live", tour="wta")
    assert [m["id"] for m in page["data"]] == [18954]


def test_unknown_tour_is_a_bad_request(client: LiveTennisClient) -> None:
    with pytest.raises(LiveTennisBadRequest):
        client.list_matches("live", tour="padel")


def test_completed_needs_a_paid_plan(client: LiveTennisClient) -> None:
    with pytest.raises(LiveTennisUpgradeRequired):
        client.list_matches("completed")


def test_limit_is_applied(client: LiveTennisClient) -> None:
    assert len(client.list_matches("live", limit=1)["data"]) == 1


def test_limit_is_clamped_to_the_api_maximum() -> None:
    seen: dict[str, str] = {}

    def spy(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"data": [], "meta": {}})

    api = LiveTennisClient(
        api_key="k", client=httpx.Client(transport=httpx.MockTransport(spy))
    )
    api.list_matches("live", limit=100_000)
    assert seen["limit"] == str(MAX_LIMIT)


def test_unset_filters_are_not_sent() -> None:
    seen: dict[str, str] = {}

    def spy(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"data": [], "meta": {}})

    api = LiveTennisClient(
        api_key="k", client=httpx.Client(transport=httpx.MockTransport(spy))
    )
    api.list_matches("live")
    assert "tour" not in seen
    assert "limit" not in seen


def test_get_match(client: LiveTennisClient) -> None:
    assert client.get_match(18953)["tournament"] == "Wimbledon"


def test_get_match_score(client: LiveTennisClient) -> None:
    assert client.get_match_score(18953)["sets"] == ["6-4", "3-6", "2-1"]


def test_missing_match_is_not_found(client: LiveTennisClient) -> None:
    with pytest.raises(LiveTennisNotFound):
        client.get_match(999999)


def test_search_players(client: LiveTennisClient) -> None:
    assert [p["id"] for p in client.search_players("alcaraz")["data"]] == [4021]


def test_get_player(client: LiveTennisClient) -> None:
    assert client.get_player(5533)["name"] == "J. Sinner"


def test_list_fixtures(client: LiveTennisClient) -> None:
    assert client.list_fixtures(limit=1)["data"][0]["id"] == 19001


def test_matches_player_filter(client: LiveTennisClient) -> None:
    page = client.list_matches("live", player=7710)
    assert [m["id"] for m in page["data"]] == [18954]


def test_matches_country_filter(client: LiveTennisClient) -> None:
    page = client.list_matches("live", country="pol")
    assert [m["id"] for m in page["data"]] == [18954]


def test_matches_date_filters_are_sent_as_from_and_to() -> None:
    seen: dict[str, str] = {}

    def spy(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"data": [], "meta": {}})

    api = LiveTennisClient(
        api_key="k", client=httpx.Client(transport=httpx.MockTransport(spy))
    )
    api.list_matches("completed", from_date="2026-08-01", to_date="2026-08-07")
    assert seen["from"] == "2026-08-01"
    assert seen["to"] == "2026-08-07"


def test_player_filter_is_repeated_and_capped_at_fifty() -> None:
    sent: list[str] = []

    def spy(request: httpx.Request) -> httpx.Response:
        sent.extend(request.url.params.get_list("player"))
        return httpx.Response(200, json={"data": [], "meta": {}})

    api = LiveTennisClient(
        api_key="k", client=httpx.Client(transport=httpx.MockTransport(spy))
    )
    api.list_matches("live", player=range(1, 60))
    assert sent == [str(i) for i in range(1, 51)]


def test_fixtures_tour_filter(client: LiveTennisClient) -> None:
    assert client.list_fixtures(tour="atp", limit=1)["data"][0]["tour"] == "atp"


def test_h2h(client: LiveTennisClient) -> None:
    record = client.get_h2h("alcaraz", "sinner")
    assert record["totals"]["p1_wins"] == 6
    assert record["meetings"][0]["outcome"] == "completed"


def test_h2h_short_fragment_is_a_bad_request(client: LiveTennisClient) -> None:
    with pytest.raises(LiveTennisBadRequest):
        client.get_h2h("al", "sinner")


def test_archive_matches(client: LiveTennisClient) -> None:
    page = client.list_archive_matches(tour="atp", name="borg")
    assert page["data"][0]["winner"]["name"] == "Bjorn Borg"


def test_archive_matches_reject_non_archive_tour(client: LiveTennisClient) -> None:
    # The archive covers ATP and WTA only.
    with pytest.raises(LiveTennisBadRequest):
        client.list_archive_matches(tour="juniors")


def test_archive_round_is_sent_as_round() -> None:
    seen: dict[str, str] = {}

    def spy(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"data": [], "meta": {}})

    api = LiveTennisClient(
        api_key="k", client=httpx.Client(transport=httpx.MockTransport(spy))
    )
    api.list_archive_matches(round_code="F", level="G")
    assert seen["round"] == "F"
    assert seen["level"] == "G"


def test_archive_players(client: LiveTennisClient) -> None:
    page = client.list_archive_players(name="borg")
    assert page["data"][0]["career_high_rank"] == 1


def test_archive_career(client: LiveTennisClient) -> None:
    career = client.get_archive_career("borg")
    assert career["record"]["wins"] == 654


def test_archive_career_unknown_name_is_not_found(client: LiveTennisClient) -> None:
    with pytest.raises(LiveTennisNotFound):
        client.get_archive_career("nobody")


def test_rankings_listing(client: LiveTennisClient) -> None:
    page = client.list_rankings("atp")
    assert [r["rank"] for r in page["data"]] == [1, 2]
    assert page["data"][0]["player_name"] == "Jannik Sinner"


def test_rankings_listing_rejects_an_unlistable_system(
    client: LiveTennisClient,
) -> None:
    # UTR has no listing mode - it is a rating, not a ranking.
    with pytest.raises(LiveTennisBadRequest):
        client.list_rankings("utr")


def test_player_rankings(client: LiveTennisClient) -> None:
    page = client.get_player_rankings(4021)
    assert page["data"][0]["player_id"] == 4021


def test_player_rankings_multiple_ids(client: LiveTennisClient) -> None:
    page = client.get_player_rankings([4021, 5533])
    assert {r["player_id"] for r in page["data"]} == {4021, 5533}


def test_player_rankings_send_system_and_as_of() -> None:
    seen: dict[str, str] = {}
    systems: list[str] = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        systems.extend(request.url.params.get_list("system"))
        return httpx.Response(200, json={"data": [], "meta": {}})

    api = LiveTennisClient(
        api_key="k", client=httpx.Client(transport=httpx.MockTransport(spy))
    )
    api.get_player_rankings(4021, system=["atp", "utr"], as_of="2025-06-01")
    assert seen["as_of"] == "2025-06-01"
    assert systems == ["atp", "utr"]


def test_match_statistics(client: LiveTennisClient) -> None:
    stats = client.get_match_statistics(18953)
    assert stats["players"]["p1"]["measured"]["aces"] == 7
    assert stats["freshness"]["derived"]["coverage"] == "live"


def test_charting_player(client: LiveTennisClient) -> None:
    profile = client.get_charting_player("federer", gender="men")
    assert profile["matches_charted"] == 622


def test_charting_match(client: LiveTennisClient) -> None:
    charted = client.get_charting_match(77001)
    assert charted["players"]["p1"] == "Roger Federer"


def test_missing_charting_match_is_not_found(client: LiveTennisClient) -> None:
    with pytest.raises(LiveTennisNotFound):
        client.get_charting_match(1)


def test_keyless_request_is_unauthorized(keyless_client: LiveTennisClient) -> None:
    with pytest.raises(LiveTennisAuthError) as excinfo:
        keyless_client.list_matches("live")
    assert "unauthorized" in str(excinfo.value)
    assert "livetennisapi.com/subscribe/free" in str(excinfo.value)


def test_x_api_key_header_is_sent() -> None:
    seen: dict[str, str] = {}

    def spy(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.headers))
        return httpx.Response(200, json={"data": []})

    api = LiveTennisClient(
        api_key="k", client=httpx.Client(transport=httpx.MockTransport(spy))
    )
    api.list_fixtures()
    assert seen["x-api-key"] == "k"
    assert "authorization" not in seen


def test_rate_limit_carries_retry_after() -> None:
    def limited(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(
            429, json={"error": "rate_limited"}, headers={"retry-after": "7"}
        )

    api = LiveTennisClient(
        api_key="k",
        max_retries=0,
        client=httpx.Client(transport=httpx.MockTransport(limited)),
    )
    with pytest.raises(LiveTennisRateLimited) as excinfo:
        api.list_fixtures()
    assert excinfo.value.retry_after == 7.0


def test_minute_rate_limit_has_no_daily_reset() -> None:
    def limited(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(429, json={"error": "rate_limited"})

    api = LiveTennisClient(
        api_key="k",
        max_retries=0,
        client=httpx.Client(transport=httpx.MockTransport(limited)),
    )
    with pytest.raises(LiveTennisRateLimited) as excinfo:
        api.list_fixtures()
    assert excinfo.value.resets_at is None


def test_daily_rate_limit_carries_resets_at_and_is_not_retried() -> None:
    calls: list[int] = []

    def daily(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        calls.append(1)
        return httpx.Response(
            429,
            json={
                "error": "rate_limited",
                "scope": "day",
                "limit_per_day": 100,
                "resets_at": "2026-08-07T21:00:00Z",
            },
        )

    api = LiveTennisClient(
        api_key="k",
        max_retries=3,
        client=httpx.Client(transport=httpx.MockTransport(daily)),
    )
    with pytest.raises(LiveTennisRateLimited) as excinfo:
        api.list_fixtures()
    assert excinfo.value.resets_at == "2026-08-07T21:00:00Z"
    assert "2026-08-07T21:00:00Z" in str(excinfo.value)
    assert not isinstance(excinfo.value, LiveTennisAbuseThrottled)
    assert len(calls) == 1


def test_abuse_throttle_carries_epoch_and_is_not_retried() -> None:
    calls: list[int] = []

    def blocked(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        calls.append(1)
        return httpx.Response(
            429, json={"error": "abuse_throttled", "retry_at_epoch": 1786600000}
        )

    api = LiveTennisClient(
        api_key="k",
        max_retries=3,
        client=httpx.Client(transport=httpx.MockTransport(blocked)),
    )
    with pytest.raises(LiveTennisAbuseThrottled) as excinfo:
        api.list_fixtures()
    assert excinfo.value.retry_at_epoch == 1786600000
    assert "1786600000" in str(excinfo.value)
    assert len(calls) == 1


def test_abuse_throttle_is_still_a_rate_limit() -> None:
    # A caller that only catches LiveTennisRateLimited keeps working.
    assert issubclass(LiveTennisAbuseThrottled, LiveTennisRateLimited)


def test_server_error_is_retried_then_raised() -> None:
    calls: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        calls.append(1)
        return httpx.Response(503, json={"error": "unavailable"})

    api = LiveTennisClient(
        api_key="k",
        max_retries=1,
        client=httpx.Client(transport=httpx.MockTransport(flaky)),
    )
    with pytest.raises(LiveTennisServerError):
        api.list_fixtures()
    assert len(calls) == 2


def test_auth_error_is_never_retried() -> None:
    calls: list[int] = []

    def denied(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        calls.append(1)
        return httpx.Response(401, json={"error": "unauthorized"})

    api = LiveTennisClient(
        api_key="",
        max_retries=3,
        client=httpx.Client(transport=httpx.MockTransport(denied)),
    )
    with pytest.raises(LiveTennisAuthError):
        api.list_fixtures()
    assert len(calls) == 1


def test_retry_recovers_on_second_attempt() -> None:
    calls: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(500, json={"error": "server_error"})
        return httpx.Response(200, json={"data": [], "meta": {"count": 0}})

    api = LiveTennisClient(
        api_key="k",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(flaky)),
    )
    assert api.list_fixtures()["meta"]["count"] == 0
    assert len(calls) == 2
