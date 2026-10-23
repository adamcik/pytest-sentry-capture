"""Inspect telemetry handed to an injected Sentry transport in pytest."""

from ._capture import CapturedAttachment, FakeTransport, SentryCapture
from ._plugin import sentry_capture, sentry_isolation_scope, sentry_transport

__all__ = [
    "CapturedAttachment",
    "FakeTransport",
    "SentryCapture",
    "sentry_capture",
    "sentry_isolation_scope",
    "sentry_transport",
]
