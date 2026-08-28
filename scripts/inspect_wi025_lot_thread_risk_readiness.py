#!/usr/bin/env python3
"""Print aggregate-only WI-025 readiness without mutating the warehouse."""

from __future__ import annotations

import json

from dotenv import load_dotenv

from kis_portfolio.application.lot_thread_risk import inspect_lot_thread_risk_readiness
from kis_portfolio.db.connection import close_connection, get_connection


def main() -> None:
    load_dotenv()
    connection = get_connection()
    try:
        print(json.dumps(
            inspect_lot_thread_risk_readiness(connection),
            ensure_ascii=False,
            sort_keys=True,
        ))
    finally:
        close_connection()


if __name__ == "__main__":
    main()
