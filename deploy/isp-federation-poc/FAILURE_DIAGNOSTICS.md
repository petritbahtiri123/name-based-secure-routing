# Bounded supervisor failure diagnostics

The top-level failure line preserves `status=failed` and adds JSON containing a known exception type and the deepest supervisor-owned traceback location: fixed basename, function and line. A library exception points to its calling supervisor frame, not an external filesystem path. Unknown exception classes are labelled `Exception`; absence of a supervisor frame gives a null location.

The diagnostic does not render exception messages, exception arguments, traceback source text, locals, chained exceptions or runtime paths. It is intended to attribute a failed startup to a trusted call site without exposing credentials, key material or endpoint values. The literal RED privacy regression uses invalid JSON with a seeded secret in both path and document; GREEN must identify `read_json` and `JSONDecodeError` without that value.

This change does not identify or repair the r3 startup cause. The next controlled run must supply that evidence. Existing failed runs remain preserved.
