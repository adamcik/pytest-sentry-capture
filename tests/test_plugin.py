from textwrap import dedent

import pytest

pytest_plugins = ["pytester"]


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
                yield
                assert sentry_sdk.get_client() is client
                assert client.is_active()
                assert client.transport is transport
                sentry_sdk.capture_message("outer still works")
                assert len(transport.captured_envelopes) == 1
            finally:
                client.close()
                scope.set_client(previous)
        """
    )
    pytester.makepyfile(
        """
        import sentry_sdk

        def test_failure(sentry_capture):
            sentry_sdk.capture_message("first")
            assert False, "intentional failure"

        def test_next(sentry_capture):
            assert list(sentry_capture.get_events()) == []
            sentry_sdk.capture_message("second")
            assert next(sentry_capture.get_events())["message"] == "second"
        """
    )
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=1, failed=1)


@pytest.mark.parametrize("failure", ["none", "assertion", "setup", "binding", "close"])
def test_installed_fixture_client_ownership_and_scope_restoration(
    pytester: pytest.Pytester, failure: str
) -> None:
    # Observe real client lifetime; only inject failures at the SDK bind/close seams.
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

            class FixtureClient(RealClient):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.close_calls = 0
                    owned.append(self)

                def close(self, *args, **kwargs):
                    self.close_calls += 1
                    super().close(*args, **kwargs)
                    if FAILURE == "close":
                        raise RuntimeError("client close failed")

            real_set_client = sentry_sdk.Scope.set_client

            def set_client(self, client=None):
                real_set_client(self, client)
                if FAILURE == "binding" and isinstance(client, FixtureClient):
                    raise RuntimeError("client binding failed")

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
                        patch.setattr(sentry_sdk, "Client", FixtureClient)
                        patch.setattr(sentry_sdk.Scope, "set_client", set_client)
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
        def application(sentry_capture):
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
        errors=int(failure in {"setup", "binding", "close"}),
    )
