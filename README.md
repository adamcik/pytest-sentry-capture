# pytest-sentry-capture

Capture and inspect Sentry events in pytest without sending them over the network.
Requires Python 3.12 or newer.

```sh
pip install pytest-sentry-capture
```

Pytest discovers the plugin automatically. Do not also add it to `pytest_plugins`. The
plugin does not initialize Sentry until a fixture is requested.

```python
import sentry_sdk
import pytest_sentry_capture as capture


def test_error(sentry_capture: capture.SentryCapture) -> None:
    sentry_sdk.add_breadcrumb(message="starting", level="info")
    sentry_sdk.capture_message("hello")

    event = next(sentry_capture.get_events())
    assert event["message"] == "hello"
    assert sentry_capture.find_breadcrumb_by_message("starting")["level"] == "info"
```

## Fixtures and inspection

- `sentry_capture`: isolated client with in-memory transport and full transaction
  sampling; yields a `SentryCapture`.
- `sentry_transport`: a `FakeTransport` you can inject into application setup.
- `sentry_isolation_scope`: an isolated, blank client for tests that own SDK setup.

Use `get_events`, `get_transactions`, `get_spans`, `get_breadcrumbs`, and
`get_exceptions` to iterate captured data. Reads flush the active client and do not
consume captured envelopes. The `find_*` methods return the first match or raise
`LookupError`. Each test receives fresh envelopes.

Fixture teardown closes its own client inside the isolated scope and restores the
enclosing scope. If application code creates another client, it owns that client's
cleanup. These fixtures isolate the SDK scope, not process-global logging handlers or
arbitrary framework instrumentation. Use xdist for process-level parallelism; concurrent
SDK reconfiguration within a worker is unsupported.

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
