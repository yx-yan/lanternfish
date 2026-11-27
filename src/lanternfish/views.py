"""Custom menu rows drawn as one card per provider: a header with the brand icon and plan,
then a compact row per usage window (label, bar, % left, reset countdown).

Each row is an NSView set on a plain NSMenuItem (or stacked in the panel). A card is
several rows; each row draws its own slice of the card background, rounding the top on
the header and the bottom on the last row. Colors are semantic system colors or brand
colors, so the rows follow light and dark mode on their own.
"""

from __future__ import annotations

from pathlib import Path

from AppKit import (
    NSBezierPath,
    NSColor,
    NSCompositingOperationSourceAtop,
    NSCompositingOperationSourceOver,
    NSFont,
    NSFontAttributeName,
    NSFontWeightMedium,
    NSFontWeightSemibold,
    NSForegroundColorAttributeName,
    NSImage,
    NSMakeRect,
    NSRectFillUsingOperation,
    NSView,
    NSViewWidthSizable,
    NSZeroRect,
)
from Foundation import NSAttributedString, NSData

from .format import error_line, header_line, left, money, money_line, plan_text, until, window_line
from .providers.base import Money, Usage, Window

WIDTH = 300
MARGIN = 10          # menu or panel edge to card
PAD = 12             # card edge to content
RADIUS = 10
CARD_GAP = 8         # space above each card
HEADER_H = 34
ROW_H = 26
SUB_H = 20
NOTE_H = 22
BAR_H = 5
ICON = 16
LABEL_W = 52         # label column; the bar starts after it
PCT_W = 40           # % column, right-aligned before the countdown
RESET_W = 50         # countdown column at the right edge
DIM = 0.45           # alpha for a secondary group's bars

ICONS = Path(__file__).parent / "icons"


def _rgb(hex_: str):
    v = int(hex_, 16)
    return NSColor.colorWithSRGBRed_green_blue_alpha_((v >> 16) / 255, (v >> 8 & 255) / 255, (v & 255) / 255, 1)


# Provider name -> (Simple Icons file, brand color; None = label color, black or white).
BRANDS = {
    "Claude": ("claude.svg", "D97757"),
    "Codex": ("openai.svg", None),
    "Gemini": ("googlegemini.svg", "8E75B2"),
    "Anthropic API": ("anthropic.svg", None),
    "OpenAI API": ("openai.svg", None),
    "DeepSeek API": ("deepseek.svg", "5786FE"),
}


def brand_color(name: str):
    hex_ = BRANDS.get(name, (None, None))[1]
    return _rgb(hex_) if hex_ else NSColor.labelColor()


_icon_cache: dict[str, object] = {}


def brand_icon(name: str):
    """The provider's icon tinted with its brand color, redrawn for the current appearance;
    None for a provider without one."""
    if name in _icon_cache:
        return _icon_cache[name]
    file = BRANDS.get(name, (None, None))[0]
    source = NSImage.alloc().initWithData_(NSData.dataWithContentsOfFile_(str(ICONS / file))) if file else None
    icon = None
    if source is not None:
        color = brand_color(name)

        def draw(rect) -> bool:
            source.drawInRect_fromRect_operation_fraction_(rect, NSZeroRect, NSCompositingOperationSourceOver, 1.0)
            color.set()
            NSRectFillUsingOperation(rect, NSCompositingOperationSourceAtop)
            return True

        icon = NSImage.imageWithSize_flipped_drawingHandler_((ICON, ICON), False, draw)
    _icon_cache[name] = icon
    return icon


def _text(string: str, size: float, color, weight: float = 0.0, mono: bool = False) -> NSAttributedString:
    font = (NSFont.monospacedDigitSystemFontOfSize_weight_(size, weight) if mono
            else NSFont.systemFontOfSize_weight_(size, weight))
    return NSAttributedString.alloc().initWithString_attributes_(
        string, {NSFontAttributeName: font, NSForegroundColorAttributeName: color})


def low_color(remaining: float):
    """Orange or red once a window runs low; None while it is fine."""
    if remaining < 10:
        return NSColor.systemRedColor()
    if remaining <= 20:
        return NSColor.systemOrangeColor()
    return None


def _rounded(rect, radius: float):
    return NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)


class _Row(NSView):
    """Flipped view: a slice of a card, then text items, an icon, pills and bars.

    texts: (attributed string, x, y, align) with x measured from the content edge
    (align "right": x is the distance from the right content edge to the text's end).
    """

    def isFlipped(self) -> bool:
        return True

    def drawRect_(self, _rect) -> None:
        width = self.bounds().size.width
        height = self.bounds().size.height
        top = self.top_gap
        # Views no longer clip to their bounds by default (macOS 14), and the translucent
        # card slices must not overlap their neighbours.
        NSBezierPath.clipRect_(self.bounds())
        # Card slice; extending past the view edge squares off the corners there.
        reach_up = 0 if self.round_top else RADIUS
        reach_down = 0 if self.round_bottom else RADIUS
        card = NSMakeRect(MARGIN, top - reach_up, width - 2 * MARGIN, height - top + reach_up + reach_down)
        NSColor.labelColor().colorWithAlphaComponent_(0.05).setFill()
        _rounded(card, RADIUS).fill()

        left, right = MARGIN + PAD, width - MARGIN - PAD
        if self.icon is not None:
            self.icon.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
                NSMakeRect(left, top + 9, ICON, ICON), NSZeroRect, NSCompositingOperationSourceOver, 1.0, True, None)
        for y, w, h, color in self.pills:   # right-aligned capsules behind the plan text
            color.colorWithAlphaComponent_(0.14).setFill()
            _rounded(NSMakeRect(right - w, top + y, w, h), h / 2).fill()
        for text, x, y, align in self.texts:
            size = text.size()
            text.drawAtPoint_((left + x if align == "left" else right - x - size.width, top + y))
        for x0, x1_from_right, y, fraction, color in self.bars:
            x1 = right - x1_from_right
            track = NSMakeRect(left + x0, top + y, x1 - left - x0, BAR_H)
            NSColor.quaternaryLabelColor().setFill()
            _rounded(track, BAR_H / 2).fill()
            if fraction > 0:
                color.setFill()
                filled = NSMakeRect(track.origin.x, track.origin.y, max(BAR_H, track.size.width * fraction), BAR_H)
                _rounded(filled, BAR_H / 2).fill()


def _row(height: float, texts: list, *, first: bool = False, last: bool = False,
         bars: list | None = None, icon=None, pills: list | None = None) -> _Row:
    top_gap = CARD_GAP if first else 0
    bottom = PAD / 2 if last else 0
    view = _Row.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, top_gap + height + bottom))
    view.setAutoresizingMask_(NSViewWidthSizable)
    view.top_gap = top_gap
    view.round_top = first
    view.round_bottom = last
    view.texts = texts
    view.bars = bars or []
    view.icon = icon
    view.pills = pills or []
    return view


def header_view(usage: Usage, last: bool = False) -> NSView:
    brand = brand_color(usage.name)
    icon = brand_icon(usage.name)
    name_x = ICON + 6 if icon is not None else 0
    texts = [(_text(usage.name, 13, NSColor.labelColor(), NSFontWeightSemibold), name_x, 8, "left")]
    pills = []
    plan = plan_text(usage)
    if plan:
        pill = _text(plan, 10, brand, NSFontWeightMedium)
        pill_w = pill.size().width + 12
        pills.append((9, pill_w, 16, brand))
        texts.append((pill, 6, 10, "right"))
    # A card with nothing under the header: its bottom padding replaces the gap below the title.
    return _row(HEADER_H - PAD / 2 if last else HEADER_H, texts, first=True, last=last, icon=icon, pills=pills)


def window_view(window: Window, brand, last: bool = False) -> NSView:
    remaining = left(window)
    low = low_color(remaining)
    secondary = window.group is not None
    label_color = NSColor.secondaryLabelColor() if secondary else NSColor.labelColor()
    bar = low or (brand.colorWithAlphaComponent_(DIM) if secondary else brand)
    reset = until_text(window)
    texts = [
        (_text(window.label, 11.5, label_color), 0, 5, "left"),
        (_text(f"{remaining:.0f}%", 11.5, low or label_color, NSFontWeightSemibold, mono=True), RESET_W, 5, "right"),
        (_text(reset, 10.5, NSColor.secondaryLabelColor(), mono=True), 0, 6, "right"),
    ]
    bars = [(LABEL_W, RESET_W + PCT_W, (ROW_H - BAR_H) / 2, remaining / 100, bar)]
    return _row(ROW_H, texts, last=last, bars=bars)


def until_text(window: Window) -> str:
    return until(window.resets_at) if window.resets_at else "—"


def subtitle_view(group: str) -> NSView:
    return _row(SUB_H, [(_text(f"{group} models".upper(), 9.5, NSColor.secondaryLabelColor(),
                               NSFontWeightSemibold), 0, 5, "left")])


def money_view(value: Money, last: bool = False) -> NSView:
    return _row(ROW_H, [
        (_text(value.label, 11.5, NSColor.labelColor()), 0, 5, "left"),
        (_text(money(value), 11.5, NSColor.labelColor(), NSFontWeightSemibold, mono=True), 0, 5, "right"),
    ], last=last)


def note_view(message: str, last: bool = False) -> NSView:
    return _row(NOTE_H, [(_text(message, 10.5, NSColor.secondaryLabelColor()), 0, 4, "left")], last=last)


class _Plain(NSView):
    """A row outside any card: centred secondary text (the panel footer)."""

    def isFlipped(self) -> bool:
        return True

    def drawRect_(self, _rect) -> None:
        size = self.text.size()
        self.text.drawAtPoint_(((self.bounds().size.width - size.width) / 2, 6))


def footer_view(message: str) -> NSView:
    view = _Plain.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, 26))
    view.setAutoresizingMask_(NSViewWidthSizable)
    view.text = _text(message, 10.5, NSColor.secondaryLabelColor())
    return view


def usage_rows(usages: list[Usage]):
    """(key, plain text, view) for every info row, shared by the menu and the panel."""
    for usage in usages:
        brand = brand_color(usage.name)
        # (key, text, builder taking last) so the card's final row can round its bottom.
        rows = []
        if usage.error:
            message = error_line(usage)
            rows.append((f"{usage.name}:error", message, lambda last, m=message: note_view(m, last)))
        group = None
        for i, window in enumerate(usage.windows):
            if window.group != group and window.group is not None:
                rows.append((f"{usage.name}:group{i}", window.group,
                             lambda last, g=window.group: subtitle_view(g)))
            group = window.group
            rows.append((f"{usage.name}:{i}", window_line(window),
                         lambda last, w=window: window_view(w, brand, last)))
        for i, value in enumerate(usage.money):
            rows.append((f"{usage.name}:money{i}", money_line(value), lambda last, v=value: money_view(v, last)))
        yield f"{usage.name}:header", header_line(usage), header_view(usage, last=not rows)
        for n, (key, text, build) in enumerate(rows):
            yield key, text, build(n == len(rows) - 1)
