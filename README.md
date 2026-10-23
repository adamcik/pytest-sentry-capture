# pytest-sentry-capture

Test what your application hands to Sentry's transport after SDK processing. Replace the
transport in your application's real Sentry initialization, exercise the application,
and inspect events, traces, SDK logs, and attachments in pytest.

Requires Python 3.12 or newer.

```sh
pip install pytest-sentry-capture
```

Pytest discovers the plugin automatically. Do not also add it to `pytest_plugins`.
Plugin discovery alone does not initialize Sentry.

## Test your application's Sentry configuration

The transport records; the client processes; scopes supply context. For an application
test, **keep your application's initialization, integrations, sampling, and callbacks**.
Replace only its transport. The following self-contained example includes illustrative
application setup; in your project, import and call the real setup function instead. The
redaction policy here belongs to the application, not this plugin.

```python
import sentry_sdk
import pytest_sentry_capture as capture


def initialize_application_sentry(*, transport):
    def before_send(event, hint):
        extra = event.get("extra", {})
        extra.pop("email", None)
        extra.pop("authorization", None)
        return event

    sentry_sdk.init(
        dsn="https://public@example.invalid/1",
        transport=transport,
        release="example-app@1.0",
        send_default_pii=False,
        before_send=before_send,
        enable_logs=True,
    )
    return sentry_sdk.get_client()


def test_application_privacy(
    sentry_transport: capture.FakeTransport, sentry_isolation_scope: None
) -> None:
    email = "invented-secret@example.invalid"
    authorization = "invented-bearer-secret-123"
    client = initialize_application_sentry(transport=sentry_transport)
    try:
        # In a real application test, invoke the application operation here.
        sentry_sdk.add_breadcrumb(message="checkout started")
        sentry_sdk.set_extra("email", email)
        sentry_sdk.set_extra("authorization", authorization)
        sentry_sdk.get_isolation_scope().add_attachment(
            bytes=b"order-42: payment declined", filename="diagnostic.txt"
        )
        sentry_sdk.capture_message("checkout failed", level="error")
        sentry_sdk.logger.info("checkout finished")

        # Finish transactions and await/join application work before flushing.
        client.flush()
        recorded = sentry_transport.capture
        [event] = recorded.get_events()
        assert event["message"] == "checkout failed"
        assert event["release"] == "example-app@1.0"
        assert recorded.find_breadcrumb_by_message("checkout started")
        assert any(log["body"] == "checkout finished" for log in recorded.get_logs())
        [attachment] = recorded.get_attachments()
        assert attachment.filename == "diagnostic.txt"
        assert attachment.data == b"order-42: payment declined"

        # Include ALL envelope headers and payloads, not just the event view.
        snapshot = tuple(envelope.serialize() for envelope in recorded.envelopes)
        assert snapshot  # Empty capture is not successful redaction.
        for serialized in snapshot:
            assert email.encode() not in serialized
            assert authorization.encode() not in serialized
    finally:
        client.close()
```

These positive assertions matter: a `before_send` callback that raises or returns `None`
may **drop the event**, not produce a safely redacted event. A test that only checks for
absent secrets could pass without testing any useful output.

The byte checks above detect the invented literal values in this example. Encoded,
compressed, or application-specific payloads need appropriate decoding and assertions;
this is not a general-purpose privacy scanner.

## Simpler SDK-level tests

Use `sentry_capture` when you want the fixture to create the client. It enables full
transaction sampling but does **not** exercise your application's initialization,
configuration, or hooks.

```python
import sentry_sdk
import pytest_sentry_capture as capture


def test_sdk_message(sentry_capture: capture.SentryCapture) -> None:
    sentry_sdk.add_breadcrumb(message="starting", level="info")
    sentry_sdk.capture_message("hello")
    sentry_capture.flush()

    [event] = sentry_capture.get_events()
    assert event["message"] == "hello"
    assert sentry_capture.find_breadcrumb_by_message("starting")["level"] == "info"
```

## Inspection coverage

All readers are passive, non-consuming views of telemetry already captured. They do not
flush, enable SDK features, change sampling, or complete unfinished work.

| Data                                                                            | Convenient inspection                  | Limits                                                                                                              |
| ------------------------------------------------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Error events and messages                                                       | `get_events()`, `get_exceptions()`     | Only captured event items; dropped/unsampled events are absent.                                                     |
| Transactions and root spans                                                     | `get_transactions()`                   | Completed, sampled transactions; root trace data is in `contexts.trace`.                                            |
| Transaction child spans                                                         | `get_spans()`                          | Embedded child spans only, not roots or standalone span items.                                                      |
| Breadcrumbs                                                                     | `get_breadcrumbs()`                    | Breadcrumbs embedded in captured error/message events, not a standalone stream.                                     |
| Structured SDK logs                                                             | `get_logs()`                           | Individual log dictionaries flattened from batches; enable logs and flush their client. Not Python logging records. |
| Attachments                                                                     | `get_attachments()`                    | `CapturedAttachment` values with `filename`, `content_type`, and `data: bytes`; no content decoding.                |
| Other items, including sessions, profiles, standalone spans, and client reports | Raw `envelopes` / `captured_envelopes` | Inspect SDK item headers and payloads directly. No dedicated helpers.                                               |

**Every convenient reader is partial.** Use `sentry_transport.capture.envelopes` (also
available as `sentry_transport.captured_envelopes`) for exhaustive inspection. Each SDK
envelope is iterable over items; inspect `item.headers` and `item.get_bytes()`, or use
`envelope.serialize()` to include both headers and payloads as in the privacy example.

Envelopes and event/log dictionaries are live mutable references. A tuple of serialized
envelope bytes gives you an opt-in stable snapshot at the time of serialization; there
is no automatic copy. File-backed attachments are read lazily: inspect or serialize them
before changing or removing their source files. Serialization uses the SDK's payload
handling, including its handling of unreadable files; assert expected content.

Existing `find_*` methods return the **first** match or raise `LookupError`. When a test
requires exactly one result, filter with ordinary Python and unpack a one-element list,
as `[event] = recorded.get_events()` does above.

## Setup, ownership, and isolation

| Fixture                  | Responsibility                                                                                                                                                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `sentry_transport`       | Fresh in-memory recorder with `.capture` inspection. Does not initialize or isolate Sentry, infer a client, or close application clients.                                                        |
| `sentry_isolation_scope` | Clean SDK test environment for application-owned initialization. Clears inherited scope context and active clients; restores enclosing current/isolation scopes and global scope context/client. |
| `sentry_capture`         | Uses that clean environment, creates a client with full transaction sampling, and yields a `SentryCapture` bound to that client for flushing. Closes its own client at teardown.                 |

The historical name `sentry_isolation_scope` means more than a context-local scope: it
temporarily replaces the **global** scope as well. Nested environments restore the
original scope objects, including their clients and session-tracking policy. Application
code owns the flushing and closing of clients it creates, including cleanup when
application setup fails. The fixtures never close a pre-existing client or an
application-created replacement.

Finish transactions, await async tasks, and join background work **before** flushing and
inspecting. `sentry_capture.flush(timeout=...)` always flushes its bound client, even if
application code has since replaced the active client. For application tests, flush the
actual application client. Calling `.flush()` on a transport-only capture raises
`RuntimeError` because there is no bound client. Manually constructed
`SentryCapture(envelopes, client=client)` views can also bind explicit flushing; views
never own client cleanup.

This supports sequential tests within a worker, not concurrent SDK reconfiguration.
Threads and async tasks must finish while their intended test environment is active;
context propagation follows the SDK/Python rules, not a plugin-managed task sandbox. Use
xdist's separate worker processes for process-level parallelism. Global event
processors, logging handlers, integration installation, and arbitrary framework
instrumentation are not reset or undone by these fixtures.

The SDK has no public global-scope context manager, so this fixture temporarily replaces
its internal global-scope reference. Code that cached an enclosing scope object can
still mutate or use that object: cached references are not redirected to the test's
scope. Use SDK scope accessors inside the active test environment.

## What capture proves—and does not prove

`FakeTransport.capture_envelope` records what the SDK hands to **this transport** after
applicable SDK processing and callbacks. Different telemetry types have different hooks:
`before_send` is not an all-item privacy filter. With an injected transport, you can
test your application's actual SDK configuration rather than a substitute client's
configuration.

Capture does not prove delivery to Sentry, HTTP wire encoding, server-side processing,
or the absence of traffic from another client, an integration's separate network path,
or other application code. This plugin is neither a runtime redaction library nor a
process-wide network sandbox.

## Compatibility changes in 0.2.0

- Readers no longer implicitly flush the active client. Flush the appropriate client
  explicitly before inspecting buffered telemetry such as SDK logs.
- `sentry_isolation_scope` starts with clean scope context and no active client rather
  than inheriting context or constructing a blank SDK client.
- Existing imports, constructor calls, partial readers, mutable event views, and
  first-match selectors remain supported. Log/attachment readers, transport `.capture`,
  and explicitly bound flushing are additive.

See [the 0.2.0 release notes](CHANGELOG.md) for migration guidance.

## Development

```sh
nix develop
pytest -q
basedpyright
nix fmt
nix flake check
nix build
```

`uv.lock` fixes the development environment. Published dependency ranges are separate
compatibility contracts. See [RELEASING.md](RELEASING.md) for repository setup and PyPI
trusted publishing.

## License

Licensed under the [Apache License 2.0](LICENSE).
