"""Shared KIS API constants and client-facing helpers."""

DOMAIN = "https://openapi.koreainvestment.com:9443"
VIRTUAL_DOMAIN = "https://openapivts.koreainvestment.com:29443"
CONTENT_TYPE = "application/json"
AUTH_TYPE = "Bearer"


class KISApiError(RuntimeError):
    """Raised when a KIS API request fails."""
