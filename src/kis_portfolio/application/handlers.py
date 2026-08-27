"""Small explicit handler registry; intentionally not a generic DI framework."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


Handler = Callable[[Any], Any]


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[type[Any], Handler] = {}

    def register(self, request_type: type[Any], handler: Handler) -> None:
        if request_type in self._handlers:
            raise ValueError(f"handler already registered for {request_type.__name__}")
        self._handlers[request_type] = handler

    def handle(self, request: Any) -> Any:
        try:
            handler = self._handlers[type(request)]
        except KeyError as exc:
            raise LookupError(f"no handler registered for {type(request).__name__}") from exc
        return handler(request)
