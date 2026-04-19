import pytest

from kis_portfolio.adapters.mcp.server import submit_overseas_stock_order, submit_stock_order


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_domestic_order_tool_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("KIS_ENABLE_ORDER_TOOLS", raising=False)

    result = await submit_stock_order("005930", 1, 0, "buy")

    assert result["status"] == "disabled"
    assert result["source"] == "order_stub"


@pytest.mark.anyio
async def test_overseas_order_tool_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("KIS_ENABLE_ORDER_TOOLS", raising=False)

    result = await submit_overseas_stock_order("AAPL", 1, 150.0, "buy", "NASD")

    assert result["status"] == "disabled"
    assert result["source"] == "order_stub"
