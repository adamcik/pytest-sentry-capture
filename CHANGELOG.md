# Release notes

## 0.2.0 (unreleased)

### Breaking changes

- **Readers are passive.** Inspection no longer implicitly flushes the active SDK
  client. Finish transactions, await tasks, or join background work, then flush before
  inspecting buffered telemetry. Flushing does not finish application work.
- **Flushing has an explicit owner.** Use `sentry_capture.flush()` for the
  fixture-created client, or `application_client.flush()` when injecting
  `sentry_transport`. A transport-only capture has no bound client and raises
  `RuntimeError` on `.flush()`; it never flushes an unrelated active client.
- **Scope initialization is clean.** `sentry_isolation_scope` no longer inherits scope
  context or creates a blank client. It starts without an active client, tags, or
  breadcrumbs, and restores enclosing SDK scope context and clients on exit. Tests that
  relied on inherited context must explicitly establish their test context.

### Inspection and ownership

- Application-owned initialization can use `sentry_transport.capture` for the same
  inspection helpers as `sentry_capture`, without replacing application configuration.
- `get_logs()` flattens structured SDK log batches; `get_attachments()` returns
  `CapturedAttachment` values with filename, content type, and payload bytes.
- Existing constructor calls, readers, live mutable views, and first-match selectors
  remain supported. Raw envelopes remain available for exhaustive header/payload
  inspection; convenient readers are partial views.
- Fixture-created clients are closed by their fixture. Application-created and
  pre-existing clients remain their owners' responsibility.
- Scope restoration preserves the original scope objects and session-tracking policy,
  including nested and failed setup. Fixture client cleanup also runs if binding fails.
- The README privacy example requires useful diagnostics as well as absent invented
  secrets. Dropped events are not evidence of successful redaction.

These fixtures are not a process-wide network sandbox. Global integrations and
concurrent SDK reconfiguration within a worker remain outside the isolation contract.
