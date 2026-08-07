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
    free key (100 requests/day) at https://livetennisapi.com/subscribe/free.
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

    The API has two ordinary rate limits: a per-minute window (retry once
    ``retry_after`` has passed) and a per-day quota. A daily 429 carries
    ``resets_at``, the exact ISO-8601 instant the day quota resets - wait for
    that instant; retrying sooner cannot succeed.

    Attributes:
        retry_after: Seconds to wait before retrying, when the API sent a
            ``Retry-After`` header. ``None`` when it did not.
        resets_at: ISO-8601 instant the daily quota resets, when this 429 is
            the daily cap. ``None`` for a per-minute 429.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        resets_at: str | None = None,
    ) -> None:
        """Record the retry delay and daily reset alongside the message.

        Args:
            message: Human-readable description of the failure.
            retry_after: Seconds from the ``Retry-After`` header, if present.
            resets_at: ISO-8601 reset instant from a daily-cap 429 body.
        """
        super().__init__(message)
        self.retry_after = retry_after
        self.resets_at = resets_at


class LiveTennisAbuseThrottled(LiveTennisRateLimited):
    """HTTP 429 ``abuse_throttled`` - a 24-hour block for chronic over-cap use.

    Raised when a client has kept hammering past its quota, typically a retry
    loop that never backs off. Fix the loop; do not retry the request. The
    block lifts at ``retry_at_epoch``.

    Attributes:
        retry_at_epoch: Unix epoch seconds at which the block lifts, when the
            API supplied it.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        retry_at_epoch: int | None = None,
    ) -> None:
        """Record when the abuse block lifts alongside the message.

        Args:
            message: Human-readable description of the failure.
            retry_after: Seconds from the ``Retry-After`` header, if present.
            retry_at_epoch: Unix epoch seconds from the 429 body, if present.
        """
        super().__init__(message, retry_after=retry_after)
        self.retry_at_epoch = retry_at_epoch


class LiveTennisServerError(LiveTennisAPIError):
    """HTTP 5xx, or the request never reached the API."""
