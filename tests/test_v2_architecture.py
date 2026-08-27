from __future__ import annotations

import ast
from pathlib import Path

import pytest

from kis_portfolio.application import HandlerRegistry
from kis_portfolio.modules.core import Money, QualityStatus


ROOT = Path(__file__).parents[1]


def test_domain_and_application_do_not_import_infrastructure() -> None:
    forbidden = {"duckdb", "httpx", "mcp", "starlette", "uvicorn", "google"}
    checked = [ROOT / "src/kis_portfolio/modules", ROOT / "src/kis_portfolio/application", ROOT / "src/kis_portfolio/ports"]
    violations: list[str] = []
    for directory in checked:
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if name.split(".")[0] in forbidden:
                        violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert violations == []


def test_shared_values_and_explicit_handler_registry() -> None:
    assert Money.__module__.startswith("kis_portfolio.modules")
    assert QualityStatus.PASS == "pass"
    registry = HandlerRegistry()
    registry.register(str, str.upper)
    assert registry.handle("hello") == "HELLO"
    with pytest.raises(ValueError):
        registry.register(str, str.lower)
    with pytest.raises(LookupError):
        registry.handle(1)
