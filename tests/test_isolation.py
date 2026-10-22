"""Exercise the environment's nested lifetime independently of pytest scheduling."""

import pytest
import sentry_sdk
from sentry_sdk.scope import use_isolation_scope, use_scope

from pytest_sentry_capture import FakeTransport, SentryCapture
from pytest_sentry_capture._plugin import _sdk_test_environment


def test_environment_clears_and_restores_all_scope_context() -> None:
    with _sdk_test_environment():
        transport = FakeTransport()
        client = sentry_sdk.Client(transport=transport, default_integrations=False)
        sentry_sdk.get_global_scope().set_client(client)
        try:
            sentry_sdk.get_global_scope().set_tag("global", "outer")
            with use_isolation_scope(sentry_sdk.Scope()), use_scope(sentry_sdk.Scope()):
                current = sentry_sdk.get_current_scope()
                isolation = sentry_sdk.get_isolation_scope()
                current.set_client(client)
                isolation.set_client(client)
                current.set_tag("current", "outer")
                isolation.set_tag("isolation", "outer")
                sentry_sdk.add_breadcrumb(message="outer breadcrumb")

                with _sdk_test_environment():
                    assert not sentry_sdk.get_client().is_active()
                    inner_transport = FakeTransport()
                    inner = sentry_sdk.Client(
                        transport=inner_transport, default_integrations=False
                    )
                    sentry_sdk.get_global_scope().set_client(inner)
                    try:
                        sentry_sdk.capture_message("clean")
                        [event] = SentryCapture(
                            inner_transport.captured_envelopes
                        ).get_events()
                        assert not event.get("tags")
                        assert not event.get("breadcrumbs", {}).get("values")
                        sentry_sdk.set_tag("inner", "must not escape")
                    finally:
                        inner.close()

                assert sentry_sdk.get_current_scope() is current
                assert sentry_sdk.get_isolation_scope() is isolation
                assert sentry_sdk.get_client() is client
                sentry_sdk.capture_message("restored")
                [event] = SentryCapture(transport.captured_envelopes).get_events()
                assert event["tags"] == {
                    "global": "outer",
                    "current": "outer",
                    "isolation": "outer",
                }
                assert (
                    event["breadcrumbs"]["values"][0]["message"] == "outer breadcrumb"
                )
        finally:
            client.close()


def test_environment_restores_after_application_initialization_failure() -> None:
    with _sdk_test_environment():
        outer = sentry_sdk.Client(transport=FakeTransport(), default_integrations=False)
        sentry_sdk.get_global_scope().set_client(outer)
        application = None
        try:
            with pytest.raises(RuntimeError, match="application setup"):
                with _sdk_test_environment():
                    sentry_sdk.init(
                        transport=FakeTransport(), default_integrations=False
                    )
                    application = sentry_sdk.get_client()
                    raise RuntimeError("application setup")
            assert sentry_sdk.get_client() is outer
            assert outer.is_active()
            assert application is not None and application.is_active()
        finally:
            if application is not None:
                application.close()
            outer.close()


def test_environment_restores_when_sdk_initialization_raises() -> None:
    with _sdk_test_environment():
        outer = sentry_sdk.Client(transport=FakeTransport(), default_integrations=False)
        sentry_sdk.get_global_scope().set_client(outer)
        try:
            with pytest.raises(sentry_sdk.utils.BadDsn):
                with _sdk_test_environment():
                    sentry_sdk.init(dsn="invalid", default_integrations=False)
            assert sentry_sdk.get_client() is outer
            assert outer.is_active()
        finally:
            outer.close()


def test_environment_preserves_absence_of_global_client() -> None:
    with _sdk_test_environment():
        scope = sentry_sdk.get_global_scope()
        scope.client = None
        with _sdk_test_environment():
            assert not sentry_sdk.get_client().is_active()
        assert scope.client is None
