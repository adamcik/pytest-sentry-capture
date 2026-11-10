from textwrap import dedent

import pytest

pytest_plugins = ["pytester"]


@pytest.mark.parametrize("client_first", [False, True])
def test_application_can_override_only_initialization(
    pytester: pytest.Pytester, client_first: bool
) -> None:
    pytester.makeconftest(
        """
        import pytest
        import sentry_sdk

        initialized = []

        @pytest.fixture(scope="session", autouse=True)
        def check_application_client_cleanup():
            yield
            [client] = initialized
            assert client.transport is None

        @pytest.fixture
        def initialize_sentry_client(sentry_transport, sentry_isolation_scope):
            def before_send(event, hint):
                event.setdefault("tags", {})["application"] = "configured"
                return event

            sentry_sdk.init(
                transport=sentry_transport,
                release="application@1.0",
                before_send=before_send,
                enable_logs=True,
                default_integrations=False,
            )
            initialized.append(sentry_sdk.get_client())
        """
    )
    fixtures = (
        "sentry_client, sentry_capture, sentry_transport"
        if client_first
        else "sentry_capture, sentry_transport, sentry_client"
    )
    pytester.makepyfile(
        f"""
        import sentry_sdk
        from sentry_sdk import logger

        def test_application({fixtures}):
            assert sentry_capture.transport is sentry_transport
            assert sentry_capture.client is sentry_client is sentry_sdk.get_client()
            sentry_sdk.capture_message("application event")
            logger.info("application log")
            [event] = sentry_capture.flush().get_events()
            assert event["release"] == "application@1.0"
            assert event["tags"]["application"] == "configured"
            [log] = sentry_capture.get_logs()
            assert log["body"] == "application log"
        """
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=1)


def test_installed_plugin_restores_outer_client_after_failure(
    pytester: pytest.Pytester,
) -> None:
    pytester.makeconftest(
        """
        import pytest
        import sentry_sdk
        from pytest_sentry_capture import FakeTransport

        @pytest.fixture(scope="session", autouse=True)
        def outer_client():
            transport = FakeTransport()
            scope = sentry_sdk.get_global_scope()
            previous = scope.client
            client = sentry_sdk.Client(transport=transport, default_integrations=False)
            scope.set_client(client)
            try:
                yield client
                assert sentry_sdk.get_client() is client
                assert client.is_active()
                assert client.transport is transport
                before = len(transport.captured_envelopes)
                sentry_sdk.capture_message("outer still works")
                assert len(transport.captured_envelopes) == before + 1
            finally:
                client.close()
                scope.set_client(previous)
        """
    )
    pytester.makepyfile(
        """
        import sentry_sdk

        def test_transport_is_passive(outer_client, sentry_transport):
            assert sentry_sdk.get_client() is outer_client
            assert list(sentry_transport.capture.get_events()) == []
            sentry_sdk.capture_message("still the outer client")
            assert list(sentry_transport.capture.get_events()) == []

        def test_capture_initializes_sentry(sentry_capture):
            assert sentry_capture.client is sentry_sdk.get_client()
            assert sentry_capture.client.is_active()
            assert sentry_capture.client.transport is sentry_capture.transport

        def test_failure(sentry_client, sentry_capture):
            sentry_sdk.capture_message("first")
            assert False, "intentional failure"

        def test_next(sentry_client, sentry_capture):
            assert list(sentry_capture.get_events()) == []
            sentry_sdk.capture_message("second")
            assert next(sentry_capture.get_events())["message"] == "second"
        """
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=3, failed=1)


@pytest.mark.parametrize("failure", ["none", "assertion", "setup", "close"])
def test_installed_fixture_client_ownership_and_scope_restoration(
    pytester: pytest.Pytester, failure: str
) -> None:
    # Observe the real SDK initializer; inject failures only at the close seam.
    pytester.makeconftest(
        f"FAILURE = {failure!r}\n"
        + dedent("""
        import pytest
        import sentry_sdk
        from sentry_sdk import scope as sdk_scope
        from pytest_sentry_capture import FakeTransport

        RealClient = sentry_sdk.Client
        application_clients = []

        @pytest.fixture(scope="session", autouse=True)
        def enclosing_environment():
            global_scope = sentry_sdk.get_global_scope()
            previous_client = global_scope.client
            outer = [
                RealClient(transport=FakeTransport(), default_integrations=False)
                for _ in range(3)
            ]
            owned = []

            real_init = sentry_sdk.init

            def initialize(*args, **kwargs):
                result = real_init(*args, **kwargs)
                client = sentry_sdk.get_client()
                client.close_calls = 0
                owned.append(client)
                real_close = client.close

                def close(*args, **kwargs):
                    client.close_calls += 1
                    real_close(*args, **kwargs)
                    if FAILURE == "close":
                        raise RuntimeError("client close failed")
                client.close = close
                return result

            global_scope.set_client(outer[0])
            try:
                with (
                    sdk_scope.use_isolation_scope(sentry_sdk.Scope()),
                    sdk_scope.use_scope(sentry_sdk.Scope()),
                ):
                    isolation = sentry_sdk.get_isolation_scope()
                    current = sentry_sdk.get_current_scope()
                    isolation.set_client(outer[1])
                    current.set_client(outer[2])
                    global_scope.set_tag("global", "outer")
                    isolation.set_tag("isolation", "outer")
                    current.set_tag("current", "outer")
                    with pytest.MonkeyPatch.context() as patch:
                        patch.setattr(sentry_sdk, "init", initialize)
                        yield

                    assert len(owned) == 1
                    assert owned[0].close_calls == 1
                    assert owned[0].transport is None
                    assert all(client.transport is not None for client in outer)
                    assert sentry_sdk.get_global_scope() is global_scope
                    assert sentry_sdk.get_isolation_scope() is isolation
                    assert sentry_sdk.get_current_scope() is current
                    assert global_scope.client is outer[0]
                    assert isolation.client is outer[1]
                    assert current.client is outer[2]
                    assert all(
                        client.transport is not None for client in application_clients
                    )
                    sentry_sdk.capture_message("restored")
                    event = outer[2].transport.captured_envelopes[0].get_event()
                    assert event["tags"] == {
                        "global": "outer", "isolation": "outer", "current": "outer"
                    }
            finally:
                for client in application_clients + outer:
                    client.close()
                global_scope.client = previous_client

        @pytest.fixture
        def application(sentry_client):
            client = RealClient(transport=FakeTransport(), default_integrations=False)
            application_clients.append(client)
            sentry_sdk.get_global_scope().set_client(client)
            if FAILURE == "setup":
                raise RuntimeError("application setup failed")
            return client
        """)
    )
    pytester.makepyfile(
        """
        from conftest import FAILURE

        def test_application(application):
            assert FAILURE != "assertion", "intentional assertion failure"
        """
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(
        passed=int(failure in {"none", "close"}),
        failed=int(failure == "assertion"),
        errors=int(failure in {"setup", "close"}),
    )
