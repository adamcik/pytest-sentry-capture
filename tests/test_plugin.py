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
