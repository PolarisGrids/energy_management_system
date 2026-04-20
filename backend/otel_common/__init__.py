"""
Vendored no-op shim for the shared `otel_common` package.

The real implementation lives in `repos/mdms/otel-common-py/` and is injected
by the production Dockerfile / Jenkins buildspec via a sibling-context pip
install. This shim is only used in local dev and test environments where that
install step isn't available — it makes every hook a no-op so the app boots
cleanly without OTel / audit-Kafka plumbing.

When the Jenkins build runs, this directory is shadowed by the real package
installed into the site-packages path. Keep the public surface in sync with
`repos/mdms/otel-common-py/otel_common/__init__.py`.
"""
