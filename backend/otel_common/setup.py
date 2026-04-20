"""No-op OTel setup for local dev."""
from typing import Any


class _NoopProviders:
    def shutdown(self) -> None:
        pass


def init_otel(service_name: str, app: Any = None, **kwargs) -> _NoopProviders:
    return _NoopProviders()


def shutdown_otel(providers: _NoopProviders | None = None) -> None:
    if providers is not None:
        providers.shutdown()
