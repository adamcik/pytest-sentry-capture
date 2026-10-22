"""Opt-in fixtures: plugin discovery itself does not initialize the SDK."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager

import pytest
import sentry_sdk
from sentry_sdk.scope import use_isolation_scope, use_scope

from ._capture import FakeTransport, SentryCapture


@pytest.fixture
def sentry_isolation_scope() -> Iterator[None]:
    """A clean SDK test environment, including global-client restoration.

    Application-created clients remain application-owned. Scope context is reset,
    but process-global integrations and concurrent SDK reconfiguration are not
    isolated. Despite the historical name, this changes the global scope too.
    """
    with _sdk_test_environment():
        yield


@pytest.fixture
def sentry_transport() -> FakeTransport:
    """Record application-owned telemetry; does not initialize or isolate Sentry."""
    return FakeTransport()


@pytest.fixture
def sentry_capture(
    sentry_transport: FakeTransport, sentry_isolation_scope: None
) -> Iterator[SentryCapture]:
    """Own a client in a clean SDK test environment, with full trace sampling."""
    scope = sentry_sdk.get_global_scope()
    previous = scope.client
    client = sentry_sdk.Client(
        transport=sentry_transport,
        traces_sample_rate=1.0,
    )
    scope.set_client(client)
    try:
        yield SentryCapture(sentry_transport.captured_envelopes)
    finally:
        try:
            client.close()
        finally:
            scope.set_client(previous)


@contextmanager
def _sdk_test_environment() -> Generator[None]:
    scope = sentry_sdk.get_global_scope()
    previous = scope.fork()
    with use_isolation_scope(sentry_sdk.Scope()), use_scope(sentry_sdk.Scope()):
        scope.clear()
        scope.set_client(None)
        try:
            yield
        finally:
            scope.clear()
            scope.client = previous.client
            scope.update_from_scope(previous)
