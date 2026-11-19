"""Errors raised by the Extend AI client.

Hierarchy
---------
ExtendError (base)
  ExtendRunFailed   — the API returned status FAILED
  ExtendTimeout     — polling exceeded the timeout
  ExtendUnavailable — network error or 5xx response
  ExtendAuthError   — 401/403 from the API
"""


class ExtendError(Exception):
    """Base class for all Extend-related errors."""

    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class ExtendRunFailed(ExtendError):
    """The Extend extract or parse run ended with status FAILED."""

    def __init__(self, failure_reason: str) -> None:
        super().__init__(failure_reason, retryable=False)
        self.failure_reason = failure_reason


class ExtendTimeout(ExtendError):
    """Polling for a run result exceeded the configured timeout."""

    def __init__(self) -> None:
        super().__init__("Extend run timed out", retryable=True)


class ExtendUnavailable(ExtendError):
    """Extend was unreachable (network error or 5xx response)."""

    def __init__(self, reason: str = "Extend service unavailable") -> None:
        super().__init__(reason, retryable=True)


class ExtendAuthError(ExtendError):
    """The API rejected our credentials (401/403)."""

    def __init__(self, reason: str = "Extend authentication failed") -> None:
        super().__init__(reason, retryable=False)
