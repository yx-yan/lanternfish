"""Custom menu rows: a header with a plan tag, and a bar per usage window.

Each row is an NSView set on a plain NSMenuItem. Colors are semantic system colors,
so the rows follow light and dark mode on their own.
"""

from __future__ import annotations

from AppKit import (
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSFontWeightMedium,
    NSFontWeightSemibold,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSView,
    NSViewWidthSizable,
)
from Foundation import NSAttributedString

from .format import (
    error_line, header_line, left, left_text, money, money_line, plan_text, resets_text, window_line,
)
from .providers.base import Money, Usage, Window

WIDTH = 260
INSET = 16           # left and right padding, lined up with standard menu text
BAR_HEIGHT = 6


def _text(string: str, size: float, color, weight: float = 0.0, mono: bool = False) -> NSAttributedString:
    font = (NSFont.monospacedDigitSystemFontOfSize_weight_(size, weight) if mono
            else NSFont.systemFontOfSize_weight_(size, weight))
    return NSAttributedString.alloc().initWithString_attributes_(
        string, {NSFontAttributeName: font, NSForegroundColorAttributeName: color})


def bar_color(remaining: float):
    if remaining > 50:
        return NSColor.systemGreenColor()
    if remaining > 20:
        return NSColor.systemOrangeColor()
    return NSColor.systemRedColor()


class _Row(NSView):
    """Flipped view that draws (attributed string, x, y, align) items and optional bars."""

    def isFlipped(self) -> bool:
        return True

    def drawRect_(self, _rect) -> None:
        width = self.bounds().size.width
        for text, y, align in self.texts:
            size = text.size()
            x = INSET if align == "left" else width - INSET - size.width
            text.drawAtPoint_((x, y))
        for y, fraction, color in self.bars:
            track = NSMakeRect(INSET, y, width - 2 * INSET, BAR_HEIGHT)
            NSColor.quaternaryLabelColor().setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(track, BAR_HEIGHT / 2, BAR_HEIGHT / 2).fill()
            if fraction > 0:
                filled = NSMakeRect(INSET, y, max(BAR_HEIGHT, track.size.width * fraction), BAR_HEIGHT)
                color.setFill()
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(filled, BAR_HEIGHT / 2, BAR_HEIGHT / 2).fill()


def _row(height: float, texts: list, bars: list | None = None) -> _Row:
    view = _Row.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, height))
    view.setAutoresizingMask_(NSViewWidthSizable)
    view.texts = texts
    view.bars = bars or []
    return view


def header_view(usage: Usage) -> NSView:
    texts = [(_text(usage.name, 13, NSColor.labelColor(), NSFontWeightSemibold), 6, "left")]
    if plan_text(usage):
        texts.append((_text(plan_text(usage), 11, NSColor.secondaryLabelColor(), NSFontWeightMedium), 8, "right"))
    return _row(24, texts)


def window_view(window: Window) -> NSView:
    remaining = left(window)
    color = bar_color(remaining)
    return _row(52, [
        (_text(window.label, 12, NSColor.labelColor()), 2, "left"),
        (_text(left_text(window), 12, NSColor.labelColor(), NSFontWeightSemibold, mono=True), 2, "right"),
        (_text(resets_text(window), 10.5, NSColor.secondaryLabelColor(), mono=True), 30, "left"),
    ], [(21, remaining / 100, color)])


def money_view(value: Money) -> NSView:
    amount = money(value)
    return _row(22, [
        (_text(value.label, 12, NSColor.labelColor()), 2, "left"),
        (_text(amount, 12, NSColor.labelColor(), NSFontWeightSemibold, mono=True), 2, "right"),
    ])


def note_view(message: str) -> NSView:
    return _row(22, [(_text(message, 11, NSColor.secondaryLabelColor()), 2, "left")])


def usage_rows(usages: list[Usage]):
    """(key, plain text, view) for every info row, shared by the menu and the panel."""
    for usage in usages:
        yield f"{usage.name}:header", header_line(usage), header_view(usage)
        if usage.error:
            message = error_line(usage)
            yield f"{usage.name}:error", message, note_view(message)
        for i, window in enumerate(usage.windows):
            yield f"{usage.name}:{i}", window_line(window), window_view(window)
        for i, value in enumerate(usage.money):
            yield f"{usage.name}:money{i}", money_line(value), money_view(value)
