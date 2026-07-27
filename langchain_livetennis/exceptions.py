"""Exceptions raised by the Live Tennis API client.

Every exception inherits from :class:`LiveTennisAPIError`, so a caller that only
wants "the tennis call failed" can catch one class, while a caller that needs to
tell a bad key from an unentitled tier can catch the specific subclass.
"""

from __future__ import annotations


class LiveTennisAPIError(Exception):
    """Base class for every error raised by this package."""


class LiveTennisAuthError(LiveTennisAPIError):
    """HTTP 401 - the key is missing, unknown, or disabled.

    The API answers a keyless request with ``{"error": "unauthorized"}``. Get a
    free key (1,000 requests/day) at https://livetennisapi.com/subscribe/free.
    """


class LiveTennisUpgradeRequired(LiveTennisAPIError):
    """HTTP 403 - the key is valid but the plan does not unlock this call.

    ``status="completed"`` on ``/matches`` is the case a FREE key hits first: it
    is part of the paid History product and needs BASIC or above.
    """


class LiveTennisNotFound(LiveTennisAPIError):
    """HTTP 404 - no such match or player, or no data for it yet."""


class LiveTennisBadRequest(LiveTennisAPIError):
    """HTTP 400 - a query parameter was rejected.

    An unrecognised ``tour`` is a 400 rather than a silent pass-through, so a
    caller never receives a tour it did not ask for.
    """


class LiveTennisRateLimited(LiveTennisAPIError):
    """HTTP 429 - the plan's request allowance is exhausted.

    Attributes:
        retry_after: Seconds to wait before retrying, when the API sent a
            ``Retry-After`` header. ``None`` when it did not.
    """

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        """Record the retry delay alongside the message.

        Args:
            message: Human-readable description of the failure.
            retry_after: Seconds from the ``Retry-After`` header, if present.
        """
        super().__init__(message)
        self.retry_after = retry_after


class LiveTennisServerError(LiveTennisAPIError):
    """HTTP 5xx, or the request never reached the API."""
