#!/usr/bin/env python3
"""Bounded operator sample of public KIS overseas product classification fields."""

from __future__ import annotations

import argparse
import asyncio
import json

import httpx
from dotenv import load_dotenv

from kis_portfolio.account_registry import get_account, scoped_account_env
from kis_portfolio.services.overseas_instrument_info import fetch_overseas_instrument_info


async def _fetch(market: str, symbols: tuple[str, ...]):
    async with httpx.AsyncClient() as client:
        results = []
        for symbol in symbols:
            results.append(await fetch_overseas_instrument_info(
                market=market, symbol=symbol, client=client
            ))
        return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", required=True, choices=("NAS", "NYS", "AMS"))
    parser.add_argument("--account-label", default="brokerage")
    parser.add_argument("symbols", nargs="+")
    args = parser.parse_args()
    symbols = tuple(dict.fromkeys(item.strip().upper() for item in args.symbols if item.strip()))
    if not symbols or len(symbols) > 4:
        raise SystemExit("sample requires one to four unique symbols")
    load_dotenv()
    account = get_account(args.account_label)
    with scoped_account_env(account):
        rows = asyncio.run(_fetch(args.market, symbols))
    for item in rows:
        print(json.dumps({
            "market": item.market,
            "symbol": item.symbol,
            "product_class_code": item.product_class_code,
            "product_class_name": item.product_class_name,
            "stock_division_code": item.overseas_stock_division_code,
            "product_group": item.overseas_stock_product_group,
            "etf_risk": item.etf_risk_indicator_code,
            "tracking_multiple": item.tracking_multiple,
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
