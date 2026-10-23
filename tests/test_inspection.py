from pathlib import Path

import sentry_sdk
from sentry_sdk.envelope import Envelope, Item, PayloadRef

from pytest_sentry_capture import CapturedAttachment, FakeTransport, SentryCapture


def test_logs_are_flattened_in_capture_order(sentry_isolation_scope: None) -> None:
    transport = FakeTransport()
    client = sentry_sdk.Client(
        transport=transport, enable_logs=True, default_integrations=False
    )
    sentry_sdk.get_global_scope().set_client(client)
    try:
        sentry_sdk.capture_message("an event, not a log")
        sentry_sdk.logger.info("first")
        sentry_sdk.logger.warning("second")
        client.flush()
        sentry_sdk.logger.error("third")
        client.flush()
        assert [log["body"] for log in transport.capture.get_logs()] == [
            "first",
            "second",
            "third",
        ]
        assert len(list(transport.capture.get_events())) == 1
        assert list(transport.capture.get_attachments()) == []
    finally:
        client.close()


def test_attachment_metadata_and_binary_payloads(
    sentry_capture: SentryCapture, tmp_path: Path
) -> None:
    path = tmp_path / "diagnostic.txt"
    path.write_bytes(b"file-backed diagnostic")
    scope = sentry_sdk.get_isolation_scope()
    scope.add_attachment(
        bytes=b"\x00\xff\n", filename="binary.bin", content_type="application/custom"
    )
    scope.add_attachment(path=str(path))
    sentry_sdk.capture_message("with attachments")
    sentry_capture.flush()

    binary, file = sentry_capture.get_attachments()
    assert binary == CapturedAttachment(
        "binary.bin", "application/custom", b"\x00\xff\n"
    )
    assert file.filename == "diagnostic.txt"
    assert file.content_type == "text/plain"
    assert file.data == b"file-backed diagnostic"
    assert list(sentry_capture.get_logs()) == []
    assert len(list(sentry_capture.get_events())) == 1


def test_live_views_and_opt_in_serialized_snapshot(
    sentry_capture: SentryCapture,
) -> None:
    sentry_sdk.capture_message("original")
    [event] = sentry_capture.get_events()
    snapshot = tuple(envelope.serialize() for envelope in sentry_capture.envelopes)
    event["message"] = "mutated"
    assert next(sentry_capture.get_events()) is event
    assert next(sentry_capture.get_events())["message"] == "mutated"
    assert b"original" in snapshot[0]
    assert b"mutated" not in snapshot[0]


def test_existing_selectors_keep_first_match_behavior(
    sentry_capture: SentryCapture,
) -> None:
    sentry_sdk.add_breadcrumb(message="duplicate", level="info")
    sentry_sdk.add_breadcrumb(message="duplicate", level="warning")
    sentry_sdk.capture_message("breadcrumbs")
    assert sentry_capture.find_breadcrumb_by_message("duplicate")["level"] == "info"


def test_unknown_items_remain_available_in_raw_envelopes() -> None:
    transport = FakeTransport()
    captured = Envelope(
        headers={"custom": "envelope metadata"},
        items=[Item(type="future-item", payload=b"invented-secret")],
    )
    transport.capture_envelope(captured)
    assert transport.capture.envelopes == [captured]
    assert list(transport.capture.get_events()) == []
    assert list(transport.capture.get_logs()) == []
    assert list(transport.capture.get_attachments()) == []
    assert b"invented-secret" in captured.serialize()


def test_all_readers_are_non_consuming_partial_views() -> None:
    captured = Envelope(
        headers={"test-header": "invented-header-secret"},
        items=[
            Item(
                type="event",
                payload=PayloadRef(
                    json={
                        "message": "diagnostic",
                        "breadcrumbs": {"values": [{"message": "started"}]},
                        "exception": {"values": [{"type": "ValueError"}]},
                    }
                ),
            ),
            Item(
                type="transaction",
                payload=PayloadRef(
                    json={
                        "transaction": "operation",
                        "spans": [{"op": "work"}],
                    }
                ),
            ),
            Item(
                type="log",
                payload=PayloadRef(
                    json={
                        "items": [{"body": "structured diagnostic"}],
                    }
                ),
            ),
            Item(type="attachment", filename="test.txt", payload=b"diagnostic bytes"),
        ],
    )
    capture = SentryCapture([captured])
    snapshot = captured.serialize()
    for reader in (
        capture.get_events,
        capture.get_transactions,
        capture.get_spans,
        capture.get_breadcrumbs,
        capture.get_exceptions,
        capture.get_logs,
        capture.get_attachments,
    ):
        first = list(reader())
        assert len(first) == 1
        assert list(reader()) == first
    assert capture.envelopes == [captured]
    assert captured.serialize() == snapshot
    assert b"invented-header-secret" in snapshot
    assert b"diagnostic bytes" in snapshot
