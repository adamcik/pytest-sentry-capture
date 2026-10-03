"""Opt-in fixtures: plugin discovery itself does not initialize the SDK."""

from collections.abc import Iterator

import pytest
import sentry_sdk

from ._capture import FakeTransport, SentryCapture


@pytest.fixture
def sentry_isolation_scope() -> Iterator[None]:
    """Restore the enclosing scope and close only the client this fixture owns."""
    with sentry_sdk.isolation_scope():
        scope = sentry_sdk.get_global_scope()
        previous = scope.client
        client = sentry_sdk.Client(dsn="", default_integrations=False)
        scope.set_client(client)
        try:
            yield
        finally:
            try:
                client.close()
            finally:
                scope.set_client(previous)


@pytest.fixture
def sentry_transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def sentry_capture(
    sentry_transport: FakeTransport, sentry_isolation_scope: None
) -> Iterator[SentryCapture]:
    """Capture events and all sampled transactions in an isolated SDK scope."""
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
