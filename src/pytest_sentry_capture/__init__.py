"""Inspect telemetry handed to an injected Sentry transport in pytest."""

from ._capture import (
    CapturedAttachment,
    CapturedTelemetry,
    FakeTransport,
    SentryCapture,
)
from ._plugin import (
    initialize_sentry_client,
    sentry_capture,
    sentry_client,
    sentry_isolation_scope,
    sentry_transport,
)

__all__ = [
    "CapturedAttachment",
    "CapturedTelemetry",
    "FakeTransport",
    "SentryCapture",
    "initialize_sentry_client",
    "sentry_capture",
    "sentry_client",
    "sentry_isolation_scope",
    "sentry_transport",
]
