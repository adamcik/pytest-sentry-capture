"""Capture Sentry envelopes without sending telemetry over the network."""

from ._capture import FakeTransport, SentryCapture
from ._plugin import sentry_capture, sentry_isolation_scope, sentry_transport

__all__ = [
    "FakeTransport",
    "SentryCapture",
    "sentry_capture",
    "sentry_isolation_scope",
    "sentry_transport",
]
