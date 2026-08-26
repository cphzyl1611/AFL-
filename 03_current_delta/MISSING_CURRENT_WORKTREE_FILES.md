# Current working-tree files NOT embedded in this package

The latest independent review records these two untracked files in the user's
working tree, but they were not separately available as raw files in the active
artifact runtime when this handoff package was assembled.

Do **not** reconstruct them from audit prose. The receiving AI must read the
actual repository copies first and verify their hashes.

## Expected identities from the latest review

### `scripts/run_alfresco_bounded_feedback.py`

```text
SHA256 = e9a61a0160c9601460219ed7e146728614fae8ead378aaccaca15e2dd119d546
size   = 168 lines / 4284 bytes
```

### `tests/test_alfresco_bounded_feedback.py`

```text
SHA256 = 9a7103982f73950afe6f43e1750c932c6e13bd20872f235b92dfbf40087e7516
size   = 748 lines / 24548 bytes
```

Latest source review characterized the bounded runner `main()` as a credential
presence stub that did not yet connect run-root preparation, node resolution,
runtime config rendering, preflight semantics, or AFL launch. This is
**historical review evidence**, not a substitute for reading the current file.
