"""Thin HTTP client for the Live Tennis API public v1 surface.

Only the endpoints the tools expose are implemented. Everything is a ``GET``;
the API is read-only.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any

import httpx
from typing_extensions import Self

from .exceptions import (
    LiveTennisAPIError,
    LiveTennisAuthError,
    LiveTennisBadRequest,
    LiveTennisNotFound,
    LiveTennisRateLimited,
    LiveTennisServerError,
    LiveTennisUpgradeRequired,
)

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

#: The API rejects a ``limit`` above this.
MAX_LIMIT = 200

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
        raise LiveTennisRateLimited(
            message, retry_after=_retry_after_seconds(response.headers)
        )
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

            if response.status_code in _RETRY_STATUSES and attempt < self.max_retries:
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
        limit: int | None = None,
    ) -> Any:
        """``GET /matches`` - matches by lifecycle status."""
        return self._get(
            "/matches", _query(status=status, tour=tour, limit=_clamp_limit(limit))
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

    def list_fixtures(self, *, limit: int | None = None) -> Any:
        """``GET /fixtures`` - upcoming scheduled fixtures, earliest first."""
        return self._get("/fixtures", _query(limit=_clamp_limit(limit)))
