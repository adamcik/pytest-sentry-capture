"""Opt-in fixtures: plugin discovery itself does not initialize the SDK."""

from collections.abc import Generator, Iterator
from contextlib import closing, contextmanager

import pytest
import sentry_sdk
from sentry_sdk import client as sdk_client
from sentry_sdk import scope as sdk_scope

from ._capture import FakeTransport, SentryCapture


@pytest.fixture
def sentry_isolation_scope() -> Iterator[None]:
    """A clean SDK test environment, including global-client restoration.

    Isolation alone never closes clients; sentry_client owns successful setup.
    Scope context is reset, but process-global integrations and concurrent SDK
    reconfiguration are not isolated. This changes the global scope too.
    """
    with _sdk_test_environment():
        yield


@pytest.fixture
def sentry_transport() -> FakeTransport:
    """Record application-owned telemetry; does not initialize or isolate Sentry."""
    return FakeTransport()


@pytest.fixture
def sentry_capture(
    sentry_client: sdk_client.BaseClient, sentry_transport: FakeTransport
) -> SentryCapture:
    """Initialize Sentry for a test and expose explicit flushing and inspection."""
    return SentryCapture(client=sentry_client, transport=sentry_transport)


@pytest.fixture
def initialize_sentry(
    sentry_transport: FakeTransport, sentry_isolation_scope: None
) -> None:
    """Configure the test client; override this fixture with application setup.

    Keep the transport and isolation dependencies when overriding. Successful
    setup must leave an active sentry_sdk.get_client() whose transport is the
    supplied sentry_transport; the initializer's return value is unused. If setup
    raises after creating a client, clean up that partial setup locally.
    """
    sentry_sdk.init(transport=sentry_transport, traces_sample_rate=1.0)


@pytest.fixture
def sentry_client(
    sentry_transport: FakeTransport,
    initialize_sentry: None,
) -> Iterator[sdk_client.BaseClient]:
    """Validate and own the initialized client, including cleanup on rejection."""
    with closing(sentry_sdk.get_client()) as client:
        transport = getattr(client, "transport", None)
        # The SDK can still report is_active() after close() removes its transport.
        if not client.is_active() or transport is None:
            pytest.fail(
                "initialize_sentry must leave an active Sentry SDK client",
                pytrace=False,
            )
        if transport is not sentry_transport:
            pytest.fail(
                "initialize_sentry must use the supplied sentry_transport",
                pytrace=False,
            )
        yield client


@contextmanager
def _sdk_test_environment() -> Generator[None]:
    # The SDK has no public global-scope context manager. Replace its reference
    # rather than merging a snapshot: clear()/update_from_scope() lose state such
    # as session-tracking policy. Restore the original object without mutating it.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            sdk_scope, "_global_scope", sentry_sdk.Scope(ty=sdk_scope.ScopeType.GLOBAL)
        )
        with (
            sdk_scope.use_isolation_scope(
                sentry_sdk.Scope(ty=sdk_scope.ScopeType.ISOLATION)
            ),
            sdk_scope.use_scope(sentry_sdk.Scope(ty=sdk_scope.ScopeType.CURRENT)),
        ):
            yield
