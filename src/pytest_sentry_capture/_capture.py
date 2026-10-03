"""Envelope-backed capture; reads flush the active SDK client first."""

from collections.abc import Iterator
from typing import Any, cast, override

import sentry_sdk
from sentry_sdk import envelope, transport


class FakeTransport(transport.Transport):
    """An in-memory transport suitable for injection into application setup."""

    def __init__(self) -> None:
        super().__init__()
        self.captured_envelopes: list[envelope.Envelope] = []

    @override
    def capture_envelope(self, envelope: envelope.Envelope) -> None:
        self.captured_envelopes.append(envelope)


class SentryCapture:
    """A live view of envelopes, preserving their capture order on each read."""

    def __init__(self, envelopes: list[envelope.Envelope]) -> None:
        self.envelopes = envelopes

    def get_events(self) -> Iterator[dict[str, Any]]:
        sentry_sdk.flush()
        for item in self.envelopes:
            event = item.get_event()
            if event is not None:
                yield cast(dict[str, Any], event)

    def get_transactions(self) -> Iterator[dict[str, Any]]:
        sentry_sdk.flush()
        for item in self.envelopes:
            event = item.get_transaction_event()
            if event is not None:
                yield cast(dict[str, Any], event)

    def get_spans(self) -> Iterator[dict[str, Any]]:
        for transaction in self.get_transactions():
            for span in transaction.get("spans", []):
                if isinstance(span, dict):
                    yield span

    def get_breadcrumbs(self) -> Iterator[dict[str, Any]]:
        for event in self.get_events():
            yield from event.get("breadcrumbs", {}).get("values", [])

    def get_exceptions(self) -> Iterator[dict[str, Any]]:
        for event in self.get_events():
            yield from event.get("exception", {}).get("values", [])

    def find_transaction_by_name(self, name: str) -> dict[str, Any]:
        for transaction in self.get_transactions():
            if transaction.get("transaction") == name:
                return transaction
        raise LookupError(f"Transaction with transaction='{name}' not found.")

    def find_span_by_op(self, op: str) -> dict[str, Any]:
        for span in self.get_spans():
            if span.get("op") == op:
                return span
        raise LookupError(f"Span with op='{op}' not found.")

    def find_breadcrumb_by_message(self, message: str) -> dict[str, Any]:
        for crumb in self.get_breadcrumbs():
            if crumb.get("message") == message:
                return crumb
        raise LookupError(f"Breadcrumb with message='{message}' not found.")

    def find_breadcrumb_by_level(self, level: str) -> dict[str, Any]:
        for crumb in self.get_breadcrumbs():
            if crumb.get("level") == level:
                return crumb
        raise LookupError(f"Breadcrumb with level='{level}' not found.")

    def find_exception_by_type(self, exception_type: str) -> dict[str, Any]:
        for exception in self.get_exceptions():
            if exception.get("type") == exception_type:
                return exception
        raise LookupError(f"Exception with type='{exception_type}' not found.")
