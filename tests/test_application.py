import logging

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from pytest_sentry_capture import FakeTransport


def test_application_keeps_its_integrations_sampling_and_callbacks(
    sentry_transport: FakeTransport, sentry_isolation_scope: None
) -> None:
    sampled_events = []

    def error_sampler(event, hint):
        sampled_events.append(event["logentry"]["formatted"])
        return True

    def before_send(event, hint):
        event.setdefault("tags", {})["application_callback"] = "ran"
        return event

    # This is application-owned setup, not a modified sentry_capture client.
    sentry_sdk.init(
        transport=sentry_transport,
        default_integrations=False,
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
        ],
        traces_sample_rate=0.0,
        error_sampler=error_sampler,
        before_send=before_send,
        release="application-config-test@1.0",
    )
    client = sentry_sdk.get_client()
    logger = logging.getLogger("application-config-test")
    previous_level = logger.level
    try:
        logger.setLevel(logging.INFO)
        logger.info("operation started")
        logger.error("operation failed")
        with sentry_sdk.start_transaction(name="unsampled operation", op="test"):
            pass
        client.flush()

        capture = sentry_transport.capture
        [event] = capture.get_events()
        assert event["logentry"]["formatted"] == "operation failed"
        assert event["release"] == "application-config-test@1.0"
        assert event["tags"]["application_callback"] == "ran"
        assert sampled_events == ["operation failed"]
        assert capture.find_breadcrumb_by_message("operation started")
        assert list(capture.get_transactions()) == []
    finally:
        logger.setLevel(previous_level)
        client.close()
