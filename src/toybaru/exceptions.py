"""Custom exceptions for toybaru."""


class ToybaruError(Exception):
    """Base exception."""


class AuthenticationError(ToybaruError):
    """Authentication failed."""


class TokenExpiredError(ToybaruError):
    """Token has expired and could not be refreshed."""


class ApiError(ToybaruError):
    """API request failed."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"API error {status_code}: {message}")
