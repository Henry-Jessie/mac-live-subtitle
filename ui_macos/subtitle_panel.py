import time

from AppKit import (
    NSAppearance,
    NSAppearanceNameDarkAqua,
    NSBackingStoreBuffered,
    NSBezelStyleInline,
    NSBezierPath,
    NSButton,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSFontManager,
    NSFontWeightMedium,
    NSForegroundColorAttributeName,
    NSImage,
    NSImageSymbolConfiguration,
    NSItalicFontMask,
    NSLayoutAttributeLeading,
    NSLayoutConstraint,
    NSLineBreakByWordWrapping,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSScrollView,
    NSStackView,
    NSStackViewDistributionFill,
    NSStackViewDistributionGravityAreas,
    NSTextField,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSUserInterfaceLayoutOrientationVertical,
    NSView,
    NSViewFrameDidChangeNotification,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWindowTitleHidden,
    NSFloatingWindowLevel,
    NSNormalWindowLevel,
)
from Foundation import (
    NSMutableAttributedString,
    NSNotificationCenter,
    NSObject,
)
from PyObjCTools import AppHelper

from core.application_controller import ApplicationState


def _white(alpha: float = 1.0):
    return NSColor.whiteColor().colorWithAlphaComponent_(alpha)


class DraggableView(NSView):
    def mouseDownCanMoveWindow(self):
        return True


class NonDraggableView(NSView):
    def mouseDownCanMoveWindow(self):
        return False


class FlippedView(NonDraggableView):
    def isFlipped(self):
        return True


class SubtitleBackgroundView(NonDraggableView):
    opacity = 0.82

    def drawRect_(self, rect) -> None:
        NSColor.blackColor().colorWithAlphaComponent_(
            self.opacity
        ).setFill()
        NSBezierPath.fillRect_(rect)


def _wrapping_label(text: str = ""):
    label = NSTextField.labelWithString_(text)
    label.setSelectable_(True)
    label.setLineBreakMode_(NSLineBreakByWordWrapping)
    label.setUsesSingleLineMode_(False)
    label.setMaximumNumberOfLines_(0)
    return label


def _symbol_image(
    symbol: str,
    description: str,
    tint=None,
):
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
        symbol,
        description,
    )
    configuration = (
        NSImageSymbolConfiguration.configurationWithPointSize_weight_(
            14,
            NSFontWeightMedium,
        )
    )
    if tint is not None:
        configuration = configuration.configurationByApplyingConfiguration_(
            NSImageSymbolConfiguration.configurationWithHierarchicalColor_(
                tint
            )
        )
    image = image.imageWithSymbolConfiguration_(configuration)
    image.setTemplate_(tint is None)
    return image


def _toolbar_button(
    symbol: str,
    description: str,
    target,
    action: str,
    tint=None,
):
    image = _symbol_image(symbol, description, tint)
    button = NSButton.buttonWithImage_target_action_(
        image,
        target,
        action,
    )
    button.setBezelStyle_(NSBezelStyleInline)
    button.setShowsBorderOnlyWhileMouseInside_(True)
    button.setContentTintColor_(tint or _white(0.78))
    button.setToolTip_(description)
    button.setAccessibilityLabel_(description)
    button.widthAnchor().constraintEqualToConstant_(28).setActive_(True)
    button.heightAnchor().constraintEqualToConstant_(28).setActive_(True)
    return button


class SubtitleToolbarTarget(NSObject):
    def primaryAction_(self, _sender) -> None:
        self.panel.toggle_running()

    def stopAction_(self, _sender) -> None:
        self.panel.stop()

    def togglePin_(self, _sender) -> None:
        pinned = not self.panel.always_on_top
        self.panel.set_always_on_top(pinned)
        self.panel.pin_changed(pinned)

    def openSettings_(self, _sender) -> None:
        self.panel.open_settings()


class SubtitleRow:
    def __init__(
        self,
        chunk_id: int,
        *,
        translation_enabled: bool,
        original_font_size: int,
        translated_font_size: int,
    ):
        self.chunk_id = chunk_id
        self.timestamp = time.strftime("%H:%M:%S")
        self.original = ""
        self.translated = ""
        self.translation_enabled = translation_enabled
        self.original_font_size = original_font_size
        self.translated_font_size = translated_font_size

        self.source_label = _wrapping_label()
        self.translation_label = _wrapping_label()
        self.view = NSStackView.stackViewWithViews_(
            [self.source_label, self.translation_label]
        )
        self.view.setOrientation_(
            NSUserInterfaceLayoutOrientationVertical
        )
        self.view.setAlignment_(NSLayoutAttributeLeading)
        self.view.setDistribution_(NSStackViewDistributionFill)
        self.view.setSpacing_(4)
        self.source_label.widthAnchor().constraintEqualToAnchor_(
            self.view.widthAnchor()
        ).setActive_(True)
        self.translation_label.widthAnchor().constraintEqualToAnchor_(
            self.view.widthAnchor()
        ).setActive_(True)
        self.apply_fonts(original_font_size, translated_font_size)

    def apply_fonts(
        self,
        original_font_size: int,
        translated_font_size: int,
    ) -> None:
        self.original_font_size = original_font_size
        self.translated_font_size = translated_font_size
        if self.translation_enabled:
            self.source_label.setFont_(
                NSFont.systemFontOfSize_(original_font_size)
            )
            self.source_label.setTextColor_(_white(0.72))
        else:
            self.source_label.setFont_(
                NSFont.systemFontOfSize_(translated_font_size)
            )
            self.source_label.setTextColor_(_white())
        self.translation_label.setFont_(
            NSFont.boldSystemFontOfSize_(translated_font_size)
        )
        self.translation_label.setTextColor_(_white())
        self.translation_label.setHidden_(not self.translation_enabled)
        self._render_final()

    def update_final(self, original: str, translated: str) -> None:
        if original:
            self.timestamp = time.strftime("%H:%M:%S")
            self.original = original
        if translated:
            self.translated = translated
        self._render_final()

    def update_live(self, confirmed: str, interim: str) -> None:
        self.timestamp = time.strftime("%H:%M:%S")
        self.original = f"{confirmed}{interim}".strip()
        prefix = f"[{self.timestamp}] "
        base_font = NSFont.systemFontOfSize_(
            self.original_font_size
            if self.translation_enabled
            else self.translated_font_size
        )
        base_color = (
            _white(0.72)
            if self.translation_enabled
            else _white()
        )
        text = NSMutableAttributedString.alloc().initWithString_attributes_(
            prefix + confirmed,
            {
                NSFontAttributeName: base_font,
                NSForegroundColorAttributeName: base_color,
            },
        )
        italic_font = NSFontManager.sharedFontManager().convertFont_toHaveTrait_(
            base_font,
            NSItalicFontMask,
        )
        draft = NSMutableAttributedString.alloc().initWithString_attributes_(
            interim,
            {
                NSFontAttributeName: italic_font,
                NSForegroundColorAttributeName: _white(0.48),
            },
        )
        text.appendAttributedString_(draft)
        self.source_label.setAttributedStringValue_(text)
        self._render_translation()

    def _render_final(self) -> None:
        self.source_label.setStringValue_(
            f"[{self.timestamp}] {self.original}".strip()
        )
        self._render_translation()

    def _render_translation(self) -> None:
        if not self.translation_enabled:
            self.translation_label.setHidden_(True)
            return
        self.translation_label.setHidden_(False)
        self.translation_label.setStringValue_(self.translated or "…")


class SubtitlePanel:
    def __init__(
        self,
        *,
        original_font_size: int = 13,
        translated_font_size: int = 17,
        always_on_top: bool = True,
        background_opacity: float = 0.82,
        autosave_name: str | None = "MacLiveSubtitlePanel",
    ):
        self.original_font_size = original_font_size
        self.translated_font_size = translated_font_size
        self.always_on_top = always_on_top
        self.background_opacity = background_opacity
        self.translation_enabled = True
        self.rows = {}
        self.ordered_ids = []
        self.banner_generation = 0
        self.visibility_changed = None
        self.toggle_running = None
        self.stop = None
        self.open_settings = None
        self.pin_changed = None

        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskFullSizeContentView
        )
        self.window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 720, 250),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setReleasedWhenClosed_(False)
        self.window.setTitleVisibility_(NSWindowTitleHidden)
        self.window.setTitlebarAppearsTransparent_(True)
        self.window.setMovable_(True)
        self.window.setMovableByWindowBackground_(False)
        self.window.setFloatingPanel_(True)
        self.window.setHidesOnDeactivate_(False)
        self.window.setBecomesKeyOnlyIfNeeded_(False)
        self.window.setContentMinSize_((360, 140))
        self.window.setLevel_(
            NSFloatingWindowLevel
            if self.always_on_top
            else NSNormalWindowLevel
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(
            NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.01)
        )
        self.window.setAppearance_(
            NSAppearance.appearanceNamed_(NSAppearanceNameDarkAqua)
        )
        self.window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        restored = False
        if autosave_name is not None:
            self.window.setFrameAutosaveName_(autosave_name)
            restored = self.window.setFrameUsingName_(autosave_name)
        if not restored:
            self._set_initial_frame()

        self.content_view = NonDraggableView.alloc().initWithFrame_(
            self.window.contentView().bounds()
        )
        self.content_view.setAutoresizingMask_(
            NSViewWidthSizable | NSViewHeightSizable
        )
        self.window.setContentView_(self.content_view)

        self.background_view = SubtitleBackgroundView.alloc().initWithFrame_(
            self.content_view.bounds()
        )
        self.background_view.setAutoresizingMask_(
            NSViewWidthSizable | NSViewHeightSizable
        )
        self.content_view.addSubview_(self.background_view)
        self.set_background_opacity(self.background_opacity)

        self.drag_view = DraggableView.alloc().initWithFrame_(
            self.content_view.bounds()
        )
        self.drag_view.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.content_view.addSubview_(self.drag_view)
        NSLayoutConstraint.activateConstraints_(
            [
                self.drag_view.leadingAnchor().constraintEqualToAnchor_constant_(
                    self.content_view.leadingAnchor(),
                    6,
                ),
                self.drag_view.trailingAnchor().constraintEqualToAnchor_constant_(
                    self.content_view.trailingAnchor(),
                    -6,
                ),
                self.drag_view.topAnchor().constraintEqualToAnchor_constant_(
                    self.content_view.topAnchor(),
                    6,
                ),
                self.drag_view.heightAnchor().constraintEqualToConstant_(30),
            ]
        )

        self.toolbar_target = SubtitleToolbarTarget.alloc().init()
        self.toolbar_target.panel = self
        self.primary_button = _toolbar_button(
            "play.fill",
            "Start",
            self.toolbar_target,
            "primaryAction:",
        )
        self.stop_button = _toolbar_button(
            "stop.fill",
            "Stop",
            self.toolbar_target,
            "stopAction:",
            NSColor.systemRedColor(),
        )
        self.pin_button = _toolbar_button(
            "pin.fill",
            "Keep window on top",
            self.toolbar_target,
            "togglePin:",
        )
        self.settings_button = _toolbar_button(
            "gearshape",
            "Settings",
            self.toolbar_target,
            "openSettings:",
        )
        self.toolbar = NSStackView.stackViewWithViews_(
            [
                self.primary_button,
                self.stop_button,
                self.pin_button,
                self.settings_button,
            ]
        )
        self.toolbar.setOrientation_(
            NSUserInterfaceLayoutOrientationHorizontal
        )
        self.toolbar.setSpacing_(3)
        self.toolbar.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.content_view.addSubview_(self.toolbar)
        NSLayoutConstraint.activateConstraints_(
            [
                self.toolbar.trailingAnchor().constraintEqualToAnchor_constant_(
                    self.content_view.trailingAnchor(),
                    -10,
                ),
                self.toolbar.topAnchor().constraintEqualToAnchor_constant_(
                    self.content_view.topAnchor(),
                    6,
                ),
            ]
        )
        self.refresh_controls(ApplicationState.IDLE)

        self.banner = _wrapping_label()
        self.banner.setAlignment_(1)
        self.banner.setHidden_(True)

        self.scroll_view = NSScrollView.alloc().initWithFrame_(
            self.content_view.bounds()
        )
        self.scroll_view.setDrawsBackground_(False)
        self.scroll_view.setHasVerticalScroller_(True)
        self.scroll_view.setAutohidesScrollers_(True)

        self.document_view = FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, 680, 200)
        )
        self.document_view.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.rows_stack = NSStackView.alloc().initWithFrame_(
            self.document_view.bounds()
        )
        self.rows_stack.setOrientation_(
            NSUserInterfaceLayoutOrientationVertical
        )
        self.rows_stack.setAlignment_(NSLayoutAttributeLeading)
        self.rows_stack.setDistribution_(
            NSStackViewDistributionGravityAreas
        )
        self.rows_stack.setSpacing_(14)
        self.rows_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.document_view.addSubview_(self.rows_stack)
        self.scroll_view.setDocumentView_(self.document_view)

        NSLayoutConstraint.activateConstraints_(
            [
                self.rows_stack.leadingAnchor().constraintEqualToAnchor_constant_(
                    self.document_view.leadingAnchor(),
                    16,
                ),
                self.rows_stack.trailingAnchor().constraintEqualToAnchor_constant_(
                    self.document_view.trailingAnchor(),
                    -16,
                ),
                self.rows_stack.topAnchor().constraintEqualToAnchor_constant_(
                    self.document_view.topAnchor(),
                    12,
                ),
                self.rows_stack.bottomAnchor().constraintEqualToAnchor_constant_(
                    self.document_view.bottomAnchor(),
                    -12,
                ),
                self.document_view.widthAnchor().constraintEqualToAnchor_(
                    self.scroll_view.contentView().widthAnchor()
                ),
                self.document_view.heightAnchor().constraintGreaterThanOrEqualToAnchor_(
                    self.scroll_view.contentView().heightAnchor()
                ),
            ]
        )

        self.placeholder = _wrapping_label("Press play to begin")
        self.placeholder.setAlignment_(1)
        self.placeholder.setTextColor_(_white(0.62))
        self.placeholder.setFont_(NSFont.systemFontOfSize_(15))
        self.rows_stack.addArrangedSubview_(self.placeholder)
        self.placeholder.widthAnchor().constraintEqualToAnchor_(
            self.rows_stack.widthAnchor()
        ).setActive_(True)

        content_stack = NSStackView.stackViewWithViews_(
            [self.banner, self.scroll_view]
        )
        content_stack.setOrientation_(
            NSUserInterfaceLayoutOrientationVertical
        )
        content_stack.setAlignment_(NSLayoutAttributeLeading)
        content_stack.setDistribution_(NSStackViewDistributionFill)
        content_stack.setSpacing_(8)
        content_stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.content_view.addSubview_(content_stack)
        self.banner.widthAnchor().constraintEqualToAnchor_(
            content_stack.widthAnchor()
        ).setActive_(True)
        self.scroll_view.widthAnchor().constraintEqualToAnchor_(
            content_stack.widthAnchor()
        ).setActive_(True)
        NSLayoutConstraint.activateConstraints_(
            [
                content_stack.leadingAnchor().constraintEqualToAnchor_constant_(
                    self.content_view.leadingAnchor(),
                    14,
                ),
                content_stack.trailingAnchor().constraintEqualToAnchor_constant_(
                    self.content_view.trailingAnchor(),
                    -14,
                ),
                content_stack.topAnchor().constraintEqualToAnchor_constant_(
                    self.content_view.topAnchor(),
                    42,
                ),
                content_stack.bottomAnchor().constraintEqualToAnchor_constant_(
                    self.content_view.bottomAnchor(),
                    -12,
                ),
            ]
        )

        clip_view = self.scroll_view.contentView()
        clip_view.setPostsFrameChangedNotifications_(True)
        self.viewport_observer = (
            NSNotificationCenter.defaultCenter()
            .addObserverForName_object_queue_usingBlock_(
                NSViewFrameDidChangeNotification,
                clip_view,
                None,
                self._viewport_frame_changed,
            )
        )

    def configure_controls(
        self,
        *,
        toggle_running,
        stop,
        open_settings,
        pin_changed,
    ):
        self.toggle_running = toggle_running
        self.stop = stop
        self.open_settings = open_settings
        self.pin_changed = pin_changed
        return self

    def refresh_controls(self, state: ApplicationState) -> None:
        if state is ApplicationState.RUNNING:
            symbol = "pause.fill"
            description = "Pause"
        elif state is ApplicationState.PAUSED:
            symbol = "play.fill"
            description = "Resume"
        else:
            symbol = "play.fill"
            description = "Start"
        self._set_button_symbol(
            self.primary_button,
            symbol,
            description,
        )
        self.primary_button.setEnabled_(
            state
            not in {
                ApplicationState.STARTING,
                ApplicationState.STOPPING,
            }
        )
        self.stop_button.setEnabled_(
            state in {ApplicationState.RUNNING, ApplicationState.PAUSED}
        )
        self._refresh_pin_button()

    def set_always_on_top(self, enabled: bool) -> None:
        self.always_on_top = enabled
        self.window.setLevel_(
            NSFloatingWindowLevel if enabled else NSNormalWindowLevel
        )
        self._refresh_pin_button()

    def set_background_opacity(self, opacity: float) -> None:
        self.background_opacity = opacity
        self.background_view.opacity = opacity
        self.background_view.setNeedsDisplay_(True)

    def _refresh_pin_button(self) -> None:
        symbol = "pin.fill" if self.always_on_top else "pin"
        description = (
            "Keep window on top"
            if self.always_on_top
            else "Allow window behind other windows"
        )
        self._set_button_symbol(
            self.pin_button,
            symbol,
            description,
            NSColor.controlAccentColor()
            if self.always_on_top
            else None,
        )

    def _set_button_symbol(
        self,
        button,
        symbol: str,
        description: str,
        tint=None,
    ) -> None:
        image = _symbol_image(symbol, description, tint)
        button.setImage_(image)
        button.setContentTintColor_(tint or _white(0.78))
        button.setToolTip_(description)
        button.setAccessibilityLabel_(description)

    def _set_initial_frame(self) -> None:
        screen = NSScreen.mainScreen()
        if screen is None:
            return
        visible = screen.visibleFrame()
        width = min(720, visible.size.width * 0.7)
        height = min(250, visible.size.height * 0.3)
        x = visible.origin.x + (visible.size.width - width) / 2
        y = visible.origin.y + 60
        self.window.setFrame_display_(
            NSMakeRect(x, y, width, height),
            False,
        )

    def show(self) -> None:
        self.window.orderFrontRegardless()
        if self.visibility_changed is not None:
            self.visibility_changed(True)

    def hide(self) -> None:
        self.window.orderOut_(None)
        if self.visibility_changed is not None:
            self.visibility_changed(False)

    def toggle(self) -> None:
        if self.is_visible():
            self.hide()
        else:
            self.show()

    def close(self) -> None:
        NSNotificationCenter.defaultCenter().removeObserver_(
            self.viewport_observer
        )
        self.window.close()

    def is_visible(self) -> bool:
        return bool(self.window.isVisible())

    def set_translation_enabled(self, enabled: bool) -> None:
        self.translation_enabled = enabled
        for row in self.rows.values():
            row.translation_enabled = enabled
            row.apply_fonts(
                self.original_font_size,
                self.translated_font_size,
            )
        self._content_changed()

    def apply_display_preferences(
        self,
        *,
        original_font_size: int,
        translated_font_size: int,
        always_on_top: bool,
        background_opacity: float,
    ) -> None:
        self.original_font_size = original_font_size
        self.translated_font_size = translated_font_size
        self.set_always_on_top(always_on_top)
        self.set_background_opacity(background_opacity)
        for row in self.rows.values():
            row.apply_fonts(original_font_size, translated_font_size)
        self._content_changed()

    def update_text(
        self,
        chunk_id: int,
        original_text: str,
        translated_text: str,
    ) -> None:
        translated = "" if translated_text == " " else translated_text
        row = self._row(chunk_id)
        row.update_final(original_text, translated)
        self._content_changed()

    def update_live_text(
        self,
        chunk_id: int,
        confirmed_text: str,
        interim_text: str,
    ) -> None:
        row = self._row(chunk_id)
        row.update_live(confirmed_text or "", interim_text or "")
        self._content_changed()

    def _row(self, chunk_id: int) -> SubtitleRow:
        existing = self.rows.get(chunk_id)
        if existing is not None:
            return existing
        if self.placeholder.superview() is not None:
            self.rows_stack.removeArrangedSubview_(self.placeholder)
            self.placeholder.removeFromSuperview()

        row = SubtitleRow(
            chunk_id,
            translation_enabled=self.translation_enabled,
            original_font_size=self.original_font_size,
            translated_font_size=self.translated_font_size,
        )
        insert_index = len(self.ordered_ids)
        for index, existing_id in enumerate(self.ordered_ids):
            if existing_id > chunk_id:
                insert_index = index
                break
        self.ordered_ids.insert(insert_index, chunk_id)
        self.rows[chunk_id] = row
        self.rows_stack.insertArrangedSubview_atIndex_(
            row.view,
            insert_index,
        )
        row.view.widthAnchor().constraintEqualToAnchor_(
            self.rows_stack.widthAnchor()
        ).setActive_(True)

        if len(self.ordered_ids) > 200:
            oldest_id = self.ordered_ids.pop(0)
            oldest = self.rows.pop(oldest_id)
            self.rows_stack.removeArrangedSubview_(oldest.view)
            oldest.view.removeFromSuperview()
        return row

    def clear(self) -> None:
        for row in self.rows.values():
            self.rows_stack.removeArrangedSubview_(row.view)
            row.view.removeFromSuperview()
        self.rows.clear()
        self.ordered_ids.clear()
        if self.placeholder.superview() is None:
            self.rows_stack.addArrangedSubview_(self.placeholder)
        self._content_changed()

    def show_error(self, message: str, *, timeout_ms: int = 8000) -> None:
        self.banner.setTextColor_(NSColor.systemRedColor())
        self._show_banner(message, timeout_ms)

    def show_status(self, message: str, *, timeout_ms: int = 2000) -> None:
        self.banner.setTextColor_(NSColor.controlAccentColor())
        self._show_banner(message, timeout_ms)

    def _show_banner(self, message: str, timeout_ms: int) -> None:
        self.banner_generation += 1
        generation = self.banner_generation
        normalized = message.strip()
        if not normalized:
            self.banner.setHidden_(True)
            return
        self.banner.setStringValue_(normalized)
        self.banner.setHidden_(False)
        if timeout_ms > 0:
            AppHelper.callLater(
                timeout_ms / 1000,
                self._hide_banner,
                generation,
            )

    def _hide_banner(self, generation: int) -> None:
        if generation == self.banner_generation:
            self.banner.setHidden_(True)

    def _viewport_frame_changed(self, _notification) -> None:
        self._content_changed()

    def _content_changed(self) -> None:
        AppHelper.callAfter(self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        self.window.contentView().layoutSubtreeIfNeeded()
        clip = self.scroll_view.contentView()
        viewport_width = clip.bounds().size.width
        viewport_height = clip.bounds().size.height
        self.document_view.setFrameSize_(
            (
                viewport_width,
                max(
                    viewport_height,
                    self.document_view.frame().size.height,
                ),
            )
        )
        self.window.contentView().layoutSubtreeIfNeeded()
        document_height = max(
            viewport_height,
            self.rows_stack.fittingSize().height + 24,
        )
        self.document_view.setFrameSize_(
            (viewport_width, document_height)
        )
        self.window.contentView().layoutSubtreeIfNeeded()
        document_height = self.document_view.frame().size.height
        clip.scrollToPoint_(
            (0, max(0, document_height - viewport_height))
        )
        self.scroll_view.reflectScrolledClipView_(clip)
