"""Re-export otel-common-py for SMOC service convenience."""
try:
    from otel_common.setup import init_otel, shutdown_otel
    from otel_common.logging import configure_logging
    from otel_common.audit import init_audit, shutdown_audit, audit
except ImportError:
    async def audit(**kwargs): pass
    def init_otel(*a, **kw): return (None, None)
    def shutdown_otel(*a, **kw): pass
    def configure_logging(*a, **kw): pass
    async def init_audit(*a, **kw): pass
    async def shutdown_audit(*a, **kw): pass

__all__ = ["init_otel", "shutdown_otel", "configure_logging", "init_audit", "shutdown_audit", "audit"]
