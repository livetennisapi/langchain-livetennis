"""Thin HTTP client for the Live Tennis API public v1 surface.

Only the endpoints the tools expose are implemented. Everything is a ``GET``;
the API is read-only.
"""

from __future__ import annotations

import os
import random
import time
from typing import TYPE_CHECKING, Any, NoReturn

import httpx
from typing_extensions import Self

from .exceptions import (
    LiveTennisAbuseThrottled,
    LiveTennisAPIError,
    LiveTennisAuthError,
    LiveTennisBadRequest,
    LiveTennisNotFound,
    LiveTennisRateLimited,
    LiveTennisServerError,
    LiveTennisUpgradeRequired,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_BASE_URL = "https://api.livetennisapi.com/api/public/v1"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2

API_KEY_ENV_VAR = "LIVETENNISAPI_KEY"
BASE_URL_ENV_VAR = "LIVETENNISAPI_BASE_URL"

#: Tours the API accepts on the ``tour`` filter. Each value covers that tour's
#: singles and doubles draws.
TOURS = ("atp", "wta", "challenger", "itf", "juniors")

#: Lifecycle values the ``/matches`` endpoint accepts.
MATCH_STATUSES = ("live", "upcoming", "completed")

#: Tours the results archive (1968-2022) covers.
ARCHIVE_TOURS = ("atp", "wta")

#: Ranking systems ``/rankings`` can list in rank order (PRO mode). UTR has no
#: listing - it is a rating, not a ranking.
RANKING_LIST_SYSTEMS = ("atp", "wta", "itf_jt", "itf_mt", "itf_wt")

#: Every ranking system, for per-player as-of reads (ULTRA mode).
RANKING_SYSTEMS = (*RANKING_LIST_SYSTEMS, "utr")

#: The API rejects a ``limit`` above this.
MAX_LIMIT = 200

#: ``player`` filters accept at most this many ids per request.
MAX_PLAYER_IDS = 50

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def _retry_after_seconds(headers: httpx.Headers) -> float | None:
    """Parse a ``Retry-After`` header. Only the delta-seconds form is emitted."""
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _body(response: httpx.Response) -> dict[str, Any]:
    """The JSON object body of a response, or ``{}`` when there is none."""
    try:
        parsed = response.json()
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _message(response: httpx.Response) -> str:
    """Best-effort human-readable message from an error response body."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:200] or response.reason_phrase
    if isinstance(body, dict):
        for key in ("error", "message", "detail"):
            value = body.get(key)
            if isinstance(value, str):
                return value
    return str(body)[:200]


def _raise_rate_limited(response: httpx.Response, message: str) -> NoReturn:
    """Raise the right 429: per-minute, daily cap, or the 24-hour abuse block."""
    body = _body(response)
    retry_after = _retry_after_seconds(response.headers)
    if body.get("error") == "abuse_throttled":
        retry_at_epoch = body.get("retry_at_epoch")
        if not isinstance(retry_at_epoch, int):
            retry_at_epoch = None
        detail = (
            f"{message}. 24-hour block for repeatedly exceeding the quota - "
            "fix the retry loop rather than retrying"
        )
        if retry_at_epoch is not None:
            detail += f"; the block lifts at epoch {retry_at_epoch}"
        raise LiveTennisAbuseThrottled(
            detail, retry_after=retry_after, retry_at_epoch=retry_at_epoch
        )
    resets_at = body.get("resets_at")
    if not isinstance(resets_at, str):
        resets_at = None
    if resets_at is not None:
        message = f"{message}. Daily quota exhausted; it resets at {resets_at}"
    raise LiveTennisRateLimited(message, retry_after=retry_after, resets_at=resets_at)


def _is_retryable(response: httpx.Response) -> bool:
    """Whether waiting and resending could possibly change the answer.

    A per-minute 429 and any 5xx can clear within a request's lifetime. A
    daily-cap 429 (``resets_at`` in the body) and the 24-hour abuse block
    (``abuse_throttled``) cannot, so they are surfaced immediately instead of
    burning retries against a closed door.
    """
    if response.status_code not in _RETRY_STATUSES:
        return False
    if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
        return True
    body = _body(response)
    return body.get("error") != "abuse_throttled" and "resets_at" not in body


def _raise_for_status(response: httpx.Response) -> None:
    """Map an error response onto this package's exception hierarchy."""
    status = response.status_code
    if status < httpx.codes.BAD_REQUEST:
        return
    message = f"{status} from Live Tennis API: {_message(response)}"
    if status == httpx.codes.UNAUTHORIZED:
        unauthorized = (
            f"{message}. Set {API_KEY_ENV_VAR}, or pass api_key=... . "
            "Free keys: https://livetennisapi.com/subscribe/free"
        )
        raise LiveTennisAuthError(unauthorized)
    if status == httpx.codes.FORBIDDEN:
        raise LiveTennisUpgradeRequired(message)
    if status == httpx.codes.NOT_FOUND:
        raise LiveTennisNotFound(message)
    if status == httpx.codes.BAD_REQUEST:
        raise LiveTennisBadRequest(message)
    if status == httpx.codes.TOO_MANY_REQUESTS:
        _raise_rate_limited(response, message)
    if status >= httpx.codes.INTERNAL_SERVER_ERROR:
        raise LiveTennisServerError(message)
    raise LiveTennisAPIError(message)


def _query(**values: Any) -> dict[str, Any]:
    """Drop ``None`` values so an unset filter is never sent as an empty string."""
    return {key: value for key, value in values.items() if value is not None}


def _clamp_limit(limit: int | None) -> int | None:
    """Keep ``limit`` inside the range the API accepts (1-200)."""
    if limit is None:
        return None
    return max(1, min(int(limit), MAX_LIMIT))


def _id_list(value: int | Sequence[int] | None) -> list[int] | None:
    """Normalise a repeatable id filter to a list, capped at the API maximum."""
    if value is None:
        return None
    ids = [int(value)] if isinstance(value, int) else [int(item) for item in value]
    return ids[:MAX_PLAYER_IDS] or None


class LiveTennisClient:
    """Synchronous client for the Live Tennis API.

    Args:
        api_key: Live Tennis API key. Falls back to the ``LIVETENNISAPI_KEY``
            environment variable. A request without a key is answered with
            HTTP 401.
        base_url: Override the API root. Mainly for testing against a local
            fake; falls back to ``LIVETENNISAPI_BASE_URL``.
        timeout: Per-request timeout in seconds.
        max_retries: Retries for 429 and 5xx only. A 401 or a 403 is never
            retried - a bad key or an unentitled tier cannot start working, and
            retrying only burns the rate limit.
        client: An existing ``httpx.Client`` to use. Supply one with an
            ``httpx.MockTransport`` to test without network access.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> None:
        """Store configuration and build the underlying transport."""
        self.api_key = (
            api_key if api_key is not None else os.environ.get(API_KEY_ENV_VAR, "")
        )
        self.base_url = (
            base_url or os.environ.get(BASE_URL_ENV_VAR) or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        """Close the transport, if this client created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        """Enter a context manager that closes the transport on exit."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the transport."""
        self.close()

    # -- transport ------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "langchain-livetennis",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return retry_after
        return min(8.0, 0.5 * (2**attempt)) * (0.5 + random.random())  # noqa: S311

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Issue a GET, retrying only on 429 and 5xx."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        last: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.get(
                    url, params=params or {}, headers=self._headers()
                )
            except httpx.HTTPError as exc:
                last = LiveTennisServerError(f"could not reach {url}: {exc}")
                if attempt >= self.max_retries:
                    raise last from exc
                time.sleep(self._backoff(attempt, None))
                continue

            if _is_retryable(response) and attempt < self.max_retries:
                time.sleep(
                    self._backoff(attempt, _retry_after_seconds(response.headers))
                )
                continue

            _raise_for_status(response)
            try:
                return response.json()
            except ValueError as exc:
                msg = f"Live Tennis API returned a non-JSON body for {path}"
                raise LiveTennisAPIError(msg) from exc

        raise last or LiveTennisServerError(f"request to {url} failed")

    # -- endpoints ------------------------------------------------------------

    def list_matches(
        self,
        status: str = "live",
        *,
        tour: str | None = None,
        player: int | Sequence[int] | None = None,
        country: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int | None = None,
    ) -> Any:
        """``GET /matches`` - matches by lifecycle status.

        Args:
            status: ``live``, ``upcoming`` or ``completed`` (BASIC+).
            tour: One of ``atp``, ``wta``, ``challenger``, ``itf``, ``juniors``.
            player: Player id(s); a match qualifies when the id is either
                participant. Repeatable, max 50.
            country: Lowercase 3-letter IOC-style code (e.g. ``ned``, ``sui``)
                matched against either participant's country.
            from_date: Earliest play date, ``YYYY-MM-DD`` or ISO-8601 UTC.
            to_date: Latest play date; must not precede ``from_date``.
            limit: Page size, clamped to 1-200.
        """
        return self._get(
            "/matches",
            _query(
                status=status,
                tour=tour,
                player=_id_list(player),
                country=country,
                limit=_clamp_limit(limit),
                **{"from": from_date, "to": to_date},
            ),
        )

    def get_match(self, match_id: int) -> Any:
        """``GET /matches/{id}`` - full match detail."""
        return self._get(f"/matches/{int(match_id)}")

    def get_match_score(self, match_id: int) -> Any:
        """``GET /matches/{id}/score`` - current score only."""
        return self._get(f"/matches/{int(match_id)}/score")

    def search_players(
        self, search: str | None = None, *, limit: int | None = None
    ) -> Any:
        """``GET /players`` - search players by name."""
        return self._get("/players", _query(search=search, limit=_clamp_limit(limit)))

    def get_player(self, player_id: int) -> Any:
        """``GET /players/{id}`` - one player's bio, ranking and cached stats."""
        return self._get(f"/players/{int(player_id)}")

    def list_fixtures(
        self, *, tour: str | None = None, limit: int | None = None
    ) -> Any:
        """``GET /fixtures`` - upcoming scheduled fixtures, earliest first."""
        return self._get("/fixtures", _query(tour=tour, limit=_clamp_limit(limit)))

    def get_h2h(self, p1: str, p2: str) -> Any:
        """``GET /h2h`` - head-to-head record between two players (BASIC+).

        Names are the keys (min 3 chars each); a fragment matching more than
        one player is refused with the candidate list rather than guessed.
        """
        return self._get("/h2h", _query(p1=p1, p2=p2))

    def list_archive_matches(
        self,
        *,
        tour: str | None = None,
        name: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        round_code: str | None = None,
        level: str | None = None,
        limit: int | None = None,
    ) -> Any:
        """``GET /history/archive/matches`` - 1968-2022 results (BASIC+).

        Args:
            tour: ``atp`` or ``wta`` - the archive covers those two.
            name: Case-insensitive substring on either player's name (min 3).
            from_date: Earliest tournament start date, ``YYYY-MM-DD``.
            to_date: Latest tournament start date.
            round_code: Round, e.g. ``F``, ``SF``, ``QF``, ``R16``.
            level: Source tier code (``G`` grand slam, ``M`` masters, ``A``
                tour, ``C`` challenger, ...).
            limit: Page size, clamped to 1-200.
        """
        return self._get(
            "/history/archive/matches",
            _query(
                tour=tour,
                name=name,
                level=level,
                limit=_clamp_limit(limit),
                **{"from": from_date, "to": to_date, "round": round_code},
            ),
        )

    def list_archive_players(
        self,
        *,
        name: str | None = None,
        tour: str | None = None,
        limit: int | None = None,
    ) -> Any:
        """``GET /history/archive/players`` - archive player bios (BASIC+)."""
        return self._get(
            "/history/archive/players",
            _query(name=name, tour=tour, limit=_clamp_limit(limit)),
        )

    def get_archive_career(self, name: str) -> Any:
        """``GET /history/archive/career`` - career aggregates (BASIC+).

        The name fragment (min 3 chars) must resolve to exactly one archive
        person; an ambiguous fragment is refused with candidates.
        """
        return self._get("/history/archive/career", _query(name=name))

    def list_rankings(
        self,
        system: str,
        *,
        as_of: str | None = None,
        limit: int | None = None,
    ) -> Any:
        """``GET /rankings`` in listing mode - the full published table (PRO).

        Args:
            system: Exactly one of ``atp``, ``wta``, ``itf_jt``, ``itf_mt``,
                ``itf_wt``. UTR has no listing - it is a rating, not a ranking.
            as_of: ``YYYY-MM-DD``; returns the newest week at or before it.
            limit: Page size, clamped to 1-200.
        """
        return self._get(
            "/rankings", _query(system=system, as_of=as_of, limit=_clamp_limit(limit))
        )

    def get_player_rankings(
        self,
        player: int | Sequence[int],
        *,
        system: str | Sequence[str] | None = None,
        as_of: str | None = None,
    ) -> Any:
        """``GET /rankings`` in per-player mode - as-of records (ULTRA).

        Returns, per system, the newest record effective on or before
        ``as_of`` - the point-in-time answer, not today's rank.

        Args:
            player: Player id(s), repeatable, max 50.
            system: Restrict to one or more systems (including ``utr``).
                Omit for all.
            as_of: ``YYYY-MM-DD``. Omit for the latest known record.
        """
        systems = [system] if isinstance(system, str) else system
        return self._get(
            "/rankings",
            _query(
                player=_id_list(player),
                system=list(systems) if systems else None,
                as_of=as_of,
            ),
        )

    def get_match_statistics(self, match_id: int) -> Any:
        """``GET /matches/{id}/statistics`` - in-play statistics (ULTRA)."""
        return self._get(f"/matches/{int(match_id)}/statistics")

    def get_charting_player(self, name: str, *, gender: str | None = None) -> Any:
        """``GET /charting/players`` - career shot-level aggregate (ULTRA).

        ``name`` (min 3 chars) must resolve to one charted person;
        ``gender`` (``men``/``women``) disambiguates.
        """
        return self._get("/charting/players", _query(name=name, gender=gender))

    def get_charting_match(self, charting_match_id: int) -> Any:
        """``GET /charting/matches/{id}`` - one charted match (ULTRA)."""
        return self._get(f"/charting/matches/{int(charting_match_id)}")
