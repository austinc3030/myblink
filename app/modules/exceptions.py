"""
Custom exceptions for MyBlink application.

Defines specific exception types for different error scenarios.
"""


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class AuthenticationError(Exception):
    """Raised when authentication with Blink fails."""
    pass


class TwoFactorAuthenticationError(AuthenticationError):
    """Raised when 2FA authentication fails or times out."""
    pass
