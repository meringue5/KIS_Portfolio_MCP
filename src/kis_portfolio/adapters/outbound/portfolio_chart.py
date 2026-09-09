"""Deterministic dependency-free PNG rendering for owner portfolio reports."""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass
from decimal import Decimal


WIDTH = 1200
HEIGHT = 1080
_BACKGROUND = (15, 23, 42)
_PANEL = (30, 41, 59)
_TEXT = (241, 245, 249)
_MUTED = (148, 163, 184)
_GREEN = (52, 211, 153)
_RED = (251, 113, 133)
_PALETTE = (
    (96, 165, 250),
    (167, 139, 250),
    (45, 212, 191),
    (251, 191, 36),
    (244, 114, 182),
)


@dataclass(frozen=True, slots=True)
class ChartAllocation:
    """One already-redacted allocation slice."""

    label: str
    value_krw: int
    percent: Decimal


@dataclass(frozen=True, slots=True)
class ChartContribution:
    """One safe holding contribution used by the diverging impact chart."""

    label: str
    change_krw: int
    impact_percent_points: Decimal


# Compact 5x7 ASCII glyphs keep the image deterministic and avoid runtime font dependencies.
_GLYPHS = {
    " ": ("00000",) * 7,
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ",": ("00000", "00000", "00000", "00000", "01100", "01100", "01000"),
    "%": ("11001", "11010", "00100", "01000", "10110", "00110", "00000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "/": ("00001", "00010", "00100", "01000", "10000", "00000", "00000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
}


class _Canvas:
    def __init__(self) -> None:
        self.pixels = bytearray(_BACKGROUND * (WIDTH * HEIGHT))

    def pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            offset = (y * WIDTH + x) * 3
            self.pixels[offset:offset + 3] = bytes(color)

    def rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
        x0, x1 = max(0, x), min(WIDTH, x + width)
        y0, y1 = max(0, y), min(HEIGHT, y + height)
        row = bytes(color) * max(0, x1 - x0)
        for py in range(y0, y1):
            offset = (py * WIDTH + x0) * 3
            self.pixels[offset:offset + len(row)] = row

    def text(self, x: int, y: int, value: str, *, scale: int, color: tuple[int, int, int]) -> None:
        cursor = x
        for character in value.upper():
            glyph = _GLYPHS.get(character, _GLYPHS[" "])
            for gy, row in enumerate(glyph):
                for gx, enabled in enumerate(row):
                    if enabled == "1":
                        self.rect(cursor + gx * scale, y + gy * scale, scale, scale, color)
            cursor += 6 * scale

    def donut(self, cx: int, cy: int, outer: int, inner: int, allocations: tuple[ChartAllocation, ...]) -> None:
        positive = tuple(item for item in allocations if item.value_krw > 0)
        total = sum(item.value_krw for item in positive)
        if total <= 0:
            return
        cumulative: list[tuple[float, tuple[int, int, int]]] = []
        end = 0.0
        for index, item in enumerate(positive):
            end += item.value_krw / total * math.tau
            cumulative.append((end, _PALETTE[index % len(_PALETTE)]))
        for y in range(cy - outer, cy + outer + 1):
            for x in range(cx - outer, cx + outer + 1):
                dx, dy = x - cx, y - cy
                radius_squared = dx * dx + dy * dy
                if inner * inner <= radius_squared <= outer * outer:
                    angle = (math.atan2(dy, dx) + math.tau) % math.tau
                    color = next(color for end_angle, color in cumulative if angle <= end_angle)
                    self.pixel(x, y, color)

    def png(self) -> bytes:
        raw = b"".join(
            b"\x00" + bytes(self.pixels[y * WIDTH * 3:(y + 1) * WIDTH * 3])
            for y in range(HEIGHT)
        )

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, level=9))
            + chunk(b"IEND", b"")
        )


def _money(value: int) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}KRW {abs(value):,}"


def render_portfolio_chart(
    *,
    total_asset_krw: int,
    change_krw: int,
    change_percent: Decimal,
    asset_allocations: tuple[ChartAllocation, ...],
    account_allocations: tuple[ChartAllocation, ...],
    contributions: tuple[ChartContribution, ...] = (),
) -> bytes:
    """Render an exact-value portfolio allocation dashboard as deterministic PNG bytes."""
    if total_asset_krw <= 0:
        raise ValueError("total_asset_krw must be positive")
    canvas = _Canvas()
    canvas.rect(32, 28, 1136, 1024, _PANEL)
    canvas.text(64, 58, "TOTAL ASSET", scale=6, color=_TEXT)
    canvas.text(64, 120, _money(total_asset_krw), scale=6, color=_TEXT)
    change_prefix = "+" if change_krw > 0 else ""
    change_color = _GREEN if change_krw >= 0 else _RED
    canvas.text(
        64,
        182,
        f"D/D {change_prefix}{_money(change_krw)} ({change_prefix}{change_percent:.2f}%)",
        scale=3,
        color=change_color,
    )

    canvas.text(64, 265, "ASSET MIX", scale=4, color=_MUTED)
    canvas.donut(235, 500, 150, 82, asset_allocations)
    for index, item in enumerate(asset_allocations[:5]):
        y = 340 + index * 58
        color = _PALETTE[index % len(_PALETTE)]
        canvas.rect(410, y, 24, 24, color)
        canvas.text(450, y, item.label[:16], scale=3, color=_TEXT)
        canvas.text(450, y + 30, f"{_money(item.value_krw)}  {item.percent:.2f}%", scale=2, color=_MUTED)

    canvas.text(690, 265, "BY ACCOUNT ALIAS", scale=4, color=_MUTED)
    maximum = max((item.value_krw for item in account_allocations), default=1)
    for index, item in enumerate(account_allocations[:5]):
        y = 335 + index * 78
        canvas.text(690, y, item.label[:14], scale=3, color=_TEXT)
        canvas.text(930, y, f"{item.percent:.2f}%", scale=3, color=_TEXT)
        canvas.rect(690, y + 34, 420, 18, (51, 65, 85))
        width = max(2, round(420 * item.value_krw / maximum)) if item.value_krw > 0 else 0
        canvas.rect(690, y + 34, width, 18, _PALETTE[index % len(_PALETTE)])
        canvas.text(690, y + 58, _money(item.value_krw), scale=2, color=_MUTED)

    canvas.rect(64, 752, 1072, 2, (51, 65, 85))
    canvas.text(64, 782, "TOP 5 TOTAL-ASSET IMPACT", scale=4, color=_MUTED)
    canvas.text(64, 824, "HOLDING", scale=2, color=_MUTED)
    canvas.text(260, 824, "KRW CHANGE", scale=2, color=_MUTED)
    canvas.text(970, 824, "IMPACT", scale=2, color=_MUTED)
    center_x = 740
    canvas.rect(center_x, 850, 2, 174, (100, 116, 139))
    maximum_impact = max((abs(item.change_krw) for item in contributions), default=0)
    for index, item in enumerate(contributions[:5]):
        y = 855 + index * 34
        color = _GREEN if item.change_krw >= 0 else _RED
        canvas.text(64, y, f"{index + 1} {item.label[:14]}", scale=2, color=_TEXT)
        sign = "+" if item.change_krw > 0 else ""
        canvas.text(260, y, f"{sign}{_money(item.change_krw)}", scale=2, color=color)
        width = max(2, round(190 * abs(item.change_krw) / maximum_impact)) if maximum_impact else 0
        if item.change_krw >= 0:
            canvas.rect(center_x + 2, y + 2, width, 10, color)
        else:
            canvas.rect(center_x - width, y + 2, width, 10, color)
        impact_sign = "+" if item.impact_percent_points > 0 else ""
        canvas.text(
            970, y, f"{impact_sign}{item.impact_percent_points:.2f}%P", scale=2, color=color,
        )
    if not contributions:
        canvas.text(430, 910, "NO MATERIAL HOLDING CHANGE", scale=3, color=_MUTED)
    return canvas.png()


def render_photo_transport_smoke_chart() -> bytes:
    """Render a finance-free image that exercises the same PNG transport path."""
    canvas = _Canvas()
    canvas.rect(32, 28, 1136, 1024, _PANEL)
    canvas.text(105, 210, "KIS PORTFOLIO", scale=10, color=_TEXT)
    canvas.text(165, 340, "PHOTO TRANSPORT", scale=7, color=_PALETTE[0])
    canvas.text(260, 455, "NO FINANCIAL DATA", scale=5, color=_MUTED)
    canvas.rect(250, 565, 700, 24, (51, 65, 85))
    canvas.rect(250, 565, 700, 24, _GREEN)
    canvas.text(485, 625, "READY", scale=6, color=_GREEN)
    return canvas.png()
