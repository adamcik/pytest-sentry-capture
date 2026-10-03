from collections.abc import Callable
from dataclasses import dataclass

import pytest
import sentry_sdk

import pytest_sentry_capture as capture


def test_events_and_breadcrumbs(sentry_capture: capture.SentryCapture) -> None:
    sentry_sdk.set_user({"id": "user-42"})
    sentry_sdk.set_tag("test", "capture")
    sentry_sdk.add_breadcrumb(message="started", level="info")
    sentry_sdk.capture_message("hello")
    event = next(sentry_capture.get_events())
    assert event["message"] == "hello"
    assert event["user"]["id"] == "user-42"
    assert event["tags"]["test"] == "capture"
    assert sentry_capture.find_breadcrumb_by_message("started")["level"] == "info"
    assert sentry_capture.find_breadcrumb_by_level("info")["message"] == "started"
    assert list(sentry_capture.get_events()) == [event]


def test_exception_chain(sentry_capture: capture.SentryCapture) -> None:
    try:
        try:
            raise ValueError("first")
        except ValueError as error:
            raise TypeError("second") from error
    except TypeError:
        sentry_sdk.capture_exception()
    assert len(list(sentry_capture.get_exceptions())) == 2
    assert sentry_capture.find_exception_by_type("ValueError")["value"] == "first"
    assert sentry_capture.find_exception_by_type("TypeError")["value"] == "second"


def test_transactions_and_spans(sentry_capture: capture.SentryCapture) -> None:
    with sentry_sdk.start_transaction(name="request", op="test"):
        with sentry_sdk.start_span(op="work"):
            pass
    assert (
        sentry_capture.find_transaction_by_name("request")["contexts"]["trace"]["op"]
        == "test"
    )
    assert sentry_capture.find_span_by_op("work")["op"] == "work"


@dataclass(frozen=True)
class MissingCase:
    lookup: Callable[[capture.SentryCapture], object]


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            MissingCase(lookup=lambda c: c.find_transaction_by_name("x")),
            id="transaction",
        ),
        pytest.param(MissingCase(lookup=lambda c: c.find_span_by_op("x")), id="span"),
        pytest.param(
            MissingCase(lookup=lambda c: c.find_breadcrumb_by_message("x")),
            id="message",
        ),
        pytest.param(
            MissingCase(lookup=lambda c: c.find_breadcrumb_by_level("x")), id="level"
        ),
        pytest.param(
            MissingCase(lookup=lambda c: c.find_exception_by_type("x")), id="exception"
        ),
    ],
)
def test_missing_lookup(
    case: MissingCase, sentry_capture: capture.SentryCapture
) -> None:
    with pytest.raises(LookupError, match="not found"):
        case.lookup(sentry_capture)


@pytest.mark.parametrize("iteration", range(2))
def test_each_test_starts_empty(
    iteration: int, sentry_capture: capture.SentryCapture
) -> None:
    assert list(sentry_capture.get_events()) == []
    sentry_sdk.capture_message(str(iteration))
    assert len(list(sentry_capture.get_events())) == 1


def test_transport_can_be_injected(sentry_transport: capture.FakeTransport) -> None:
    with sentry_sdk.isolation_scope():
        client = sentry_sdk.Client(
            transport=sentry_transport, default_integrations=False
        )
        sentry_sdk.get_isolation_scope().set_client(client)
        try:
            sentry_sdk.capture_message("injected")
        finally:
            client.close()
    view = capture.SentryCapture(sentry_transport.captured_envelopes)
    assert next(view.get_events())["message"] == "injected"
