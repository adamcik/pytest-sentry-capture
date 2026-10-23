import pytest
import sentry_sdk

from pytest_sentry_capture import FakeTransport


@pytest.mark.parametrize("raises", [False, True], ids=["drop", "callback-error"])
def test_before_send_failure_is_not_successful_redaction(
    sentry_transport: FakeTransport, sentry_isolation_scope: None, raises: bool
) -> None:
    def before_send(event, hint):
        if raises:
            raise RuntimeError("broken redaction")
        return None

    sentry_sdk.init(
        transport=sentry_transport,
        default_integrations=False,
        before_send=before_send,
    )
    client = sentry_sdk.get_client()
    try:
        sentry_sdk.capture_message("expected diagnostic")
        client.flush()
        assert list(sentry_transport.capture.get_events()) == []
        # A privacy test must require the diagnostic, not only absence of secrets.
        with pytest.raises(ValueError, match="not enough values"):
            [event] = sentry_transport.capture.get_events()
    finally:
        client.close()


def test_before_send_is_not_an_attachment_or_log_filter(
    sentry_transport: FakeTransport, sentry_isolation_scope: None
) -> None:
    secret = "invented-secret-outside-event"

    def before_send(event, hint):
        event.get("extra", {}).pop("secret", None)
        return event

    sentry_sdk.init(
        transport=sentry_transport,
        default_integrations=False,
        enable_logs=True,
        before_send=before_send,
    )
    client = sentry_sdk.get_client()
    try:
        sentry_sdk.set_extra("secret", secret)
        sentry_sdk.get_isolation_scope().add_attachment(
            bytes=secret.encode(), filename="leaking.txt"
        )
        sentry_sdk.capture_message("useful safe event")
        sentry_sdk.logger.info(secret)
        client.flush()

        capture = sentry_transport.capture
        [event] = capture.get_events()
        assert event["message"] == "useful safe event"
        assert secret not in str(event)
        [attachment] = capture.get_attachments()
        assert secret.encode() in attachment.data
        assert any(log["body"] == secret for log in capture.get_logs())
        assert any(
            secret.encode() in envelope.serialize() for envelope in capture.envelopes
        )
    finally:
        client.close()
