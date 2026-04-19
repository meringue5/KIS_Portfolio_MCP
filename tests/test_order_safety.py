import pytest

from kis_mcp_server.app import order_overseas_stock, order_stock


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_domestic_order_tool_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("KIS_ENABLE_ORDER_TOOLS", raising=False)

    result = await order_stock("005930", 1, 0, "buy")

    assert result["status"] == "disabled"


@pytest.mark.anyio
async def test_overseas_order_tool_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("KIS_ENABLE_ORDER_TOOLS", raising=False)

    result = await order_overseas_stock("AAPL", 1, 150.0, "buy", "NASD")

    assert result["status"] == "disabled"
