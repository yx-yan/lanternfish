"""Floating usage panel, opened by the global hotkey when the menu bar icon is out of reach.

A non-activating panel (like Spotlight): it takes key focus without bringing
Lanternfish forward, so the app you were in stays active. Esc, the hotkey again,
or a click anywhere else closes it.
"""

from __future__ import annotations

from AppKit import (
    NSBackingStoreBuffered,
    NSColor,
    NSEvent,
    NSEventMaskLeftMouseDown,
    NSEventMaskRightMouseDown,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSStatusWindowLevel,
    NSView,
    NSVisualEffectView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
    NSWorkspace,
    NSWorkspaceDidActivateApplicationNotification,
)

from objc import super  # PyObjC needs its own super() in Objective-C subclasses

from .providers.base import Usage
from .views import WIDTH, footer_view, usage_rows

PADDING = 4   # cards bring their own spacing
RADIUS = 12
MATERIAL_MENU = 5
STATE_ACTIVE = 1


class _Panel(NSPanel):
    def canBecomeKeyWindow(self) -> bool:
        return True

    def cancelOperation_(self, _sender) -> None:   # Esc
        self.owner.hide()

    def resignKeyWindow(self) -> None:
        super().resignKeyWindow()
        self.owner.hide()


class _Flipped(NSView):
    def isFlipped(self) -> bool:
        return True


class UsagePanel:
    def __init__(self) -> None:
        self._panel = _Panel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, 100),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False)
        self._panel.setLevel_(NSStatusWindowLevel)
        self._panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary)
        self._panel.setOpaque_(False)
        self._panel.setBackgroundColor_(NSColor.clearColor())
        self._panel.setHasShadow_(True)
        self._panel.setHidesOnDeactivate_(False)
        self._panel.owner = self
        self._watchers: list = []

    @property
    def visible(self) -> bool:
        return bool(self._panel.isVisible())

    def toggle(self, usages: list[Usage], footer: str) -> None:
        if self.visible:
            self.hide()
            return
        self.update(usages, footer)
        self._place()
        self._panel.makeKeyAndOrderFront_(None)
        # A non-activating panel is not told when another app comes forward or the
        # user clicks elsewhere, so watch for both while it is open.
        clicks = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskLeftMouseDown | NSEventMaskRightMouseDown, lambda _event: self.hide())
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        switch = center.addObserverForName_object_queue_usingBlock_(
            NSWorkspaceDidActivateApplicationNotification, None, None, lambda _note: self.hide())
        self._watchers = [(clicks, switch)]

    def hide(self) -> None:
        self._panel.orderOut_(None)
        for clicks, switch in self._watchers:
            NSEvent.removeMonitor_(clicks)
            NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(switch)
        self._watchers = []

    def update(self, usages: list[Usage], footer: str) -> None:
        rows = [view for _key, _text, view in usage_rows(usages)] + [footer_view(footer)]
        height = sum(row.frame().size.height for row in rows) + 2 * PADDING
        frame = self._panel.frame()
        # Keep the top edge where it is when the content grows or shrinks.
        top = frame.origin.y + frame.size.height
        self._panel.setFrame_display_(NSMakeRect(frame.origin.x, top - height, WIDTH, height), False)

        background = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, height))
        background.setMaterial_(MATERIAL_MENU)
        background.setState_(STATE_ACTIVE)
        background.setWantsLayer_(True)
        background.layer().setCornerRadius_(RADIUS)
        background.layer().setMasksToBounds_(True)
        stack = _Flipped.alloc().initWithFrame_(background.bounds())
        y = PADDING
        for row in rows:
            row_height = row.frame().size.height
            row.setFrame_(NSMakeRect(0, y, WIDTH, row_height))
            stack.addSubview_(row)
            y += row_height
        background.addSubview_(stack)
        self._panel.setContentView_(background)

    def _place(self) -> None:
        """Centre on the screen under the mouse, a quarter of the way down."""
        mouse = NSEvent.mouseLocation()
        screen = next((s for s in NSScreen.screens() if _contains(s.frame(), mouse)), NSScreen.mainScreen())
        area = screen.visibleFrame()
        size = self._panel.frame().size
        x = area.origin.x + (area.size.width - size.width) / 2
        y = area.origin.y + area.size.height * 0.75 - size.height / 2
        self._panel.setFrameOrigin_((x, y))


def _contains(frame, point) -> bool:
    return (frame.origin.x <= point.x < frame.origin.x + frame.size.width
            and frame.origin.y <= point.y < frame.origin.y + frame.size.height)
