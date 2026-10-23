import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
import sentry_sdk

from pytest_sentry_capture import FakeTransport, SentryCapture


class ObservedClient(sentry_sdk.Client):
    """Observe explicit flushes without racing the SDK's automatic batch timer."""

    def __init__(self, **options):
        self.flush_timeouts = []
        super().__init__(**options)

    def flush(self, timeout=None, callback=None):
        self.flush_timeouts.append(timeout)
        super().flush(timeout=timeout, callback=callback)


def test_reads_are_passive_and_flush_targets_bound_client(
    sentry_isolation_scope: None,
) -> None:
    owner_transport = FakeTransport()
    other_transport = FakeTransport()
    owner = ObservedClient(
        transport=owner_transport, enable_logs=True, default_integrations=False
    )
    other = ObservedClient(
        transport=other_transport, enable_logs=True, default_integrations=False
    )
    capture = SentryCapture(owner_transport.captured_envelopes, client=owner)
    try:
        sentry_sdk.get_global_scope().set_client(owner)
        sentry_sdk.logger.info("owner buffered log")
        sentry_sdk.get_global_scope().set_client(other)
        sentry_sdk.logger.info("other buffered log")

        assert list(capture.get_events()) == []
        assert list(capture.get_transactions()) == []
        assert list(capture.get_spans()) == []
        assert list(capture.get_breadcrumbs()) == []
        assert list(capture.get_exceptions()) == []
        list(capture.get_logs())
        assert list(capture.get_attachments()) == []
        assert owner.flush_timeouts == []
        assert other.flush_timeouts == []

        capture.flush(timeout=0.5)
        assert owner.flush_timeouts == [0.5]
        assert owner_transport.captured_envelopes
        assert other.flush_timeouts == []
        other.flush()
        assert other_transport.captured_envelopes
    finally:
        other.close()
        owner.close()


def test_fixture_flush_does_not_flush_replacement_client(
    sentry_capture: SentryCapture,
) -> None:
    transport = FakeTransport()
    replacement = ObservedClient(
        transport=transport, enable_logs=True, default_integrations=False
    )
    try:
        sentry_sdk.get_global_scope().set_client(replacement)
        sentry_sdk.logger.info("replacement buffered log")
        sentry_capture.flush()
        assert replacement.flush_timeouts == []
        replacement.flush()
        assert transport.captured_envelopes
    finally:
        replacement.close()


def test_transport_only_capture_requires_explicit_client_flush(
    sentry_transport: FakeTransport,
) -> None:
    with pytest.raises(RuntimeError, match="application client"):
        sentry_transport.capture.flush()


def test_flush_does_not_finish_transaction(sentry_capture: SentryCapture) -> None:
    with sentry_sdk.start_transaction(name="unfinished", op="test"):
        sentry_capture.flush()
        assert list(sentry_capture.get_transactions()) == []
    sentry_capture.flush()
    [transaction] = sentry_capture.get_transactions()
    assert transaction["transaction"] == "unfinished"


def test_capture_after_awaiting_task(sentry_capture: SentryCapture) -> None:
    async def work() -> None:
        sentry_sdk.capture_message("async completed")

    async def run() -> None:
        task = asyncio.create_task(work())
        assert list(sentry_capture.get_events()) == []
        await task

    asyncio.run(run())
    sentry_capture.flush()
    [event] = sentry_capture.get_events()
    assert event["message"] == "async completed"


def test_capture_after_joining_background_work(sentry_capture: SentryCapture) -> None:
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(sentry_sdk.capture_message, "thread completed").result(
            timeout=5
        )
    sentry_capture.flush()
    [event] = sentry_capture.get_events()
    assert event["message"] == "thread completed"
