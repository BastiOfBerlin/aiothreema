"""Exceptions raised by the Threema Gateway client."""

from __future__ import annotations


class ThreemaGatewayError(Exception):
    """Base class for all errors raised by this library."""


class ThreemaConnectionError(ThreemaGatewayError):
    """Raised for network or transport failures talking to the Gateway."""


class ThreemaAuthError(ThreemaGatewayError):
    """Raised when the Gateway ID or API secret is rejected (HTTP 401)."""


class ThreemaSendError(ThreemaGatewayError):
    """Raised when sending a message or resolving a recipient key fails."""
