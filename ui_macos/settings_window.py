import json
import threading
from dataclasses import replace

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBox,
    NSBoxSeparator,
    NSButton,
    NSColor,
    NSControlStateValueOn,
    NSFont,
    NSFontWeightSemibold,
    NSGridView,
    NSImage,
    NSImageLeading,
    NSImageSymbolConfiguration,
    NSLayoutConstraint,
    NSLayoutAttributeLeading,
    NSMakeRect,
    NSNoTabsNoBorder,
    NSPopUpButton,
    NSRightTextAlignment,
    NSSecureTextField,
    NSSlider,
    NSStackView,
    NSStackViewDistributionFill,
    NSSwitch,
    NSTabView,
    NSTabViewItem,
    NSTextField,
    NSTextFieldRoundedBezel,
    NSToolbar,
    NSToolbarDisplayModeIconAndLabel,
    NSToolbarFlexibleSpaceItemIdentifier,
    NSToolbarItem,
    NSToolbarSizeModeRegular,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSUserInterfaceLayoutOrientationVertical,
    NSView,
    NSWindow,
    NSWorkspace,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
    NSWindowToolbarStylePreference,
)
from Foundation import NSObject, NSURL
from PyObjCTools import AppHelper

from core.connection_tests import (
    test_funasr_connection,
    test_translation_connection,
)
from core.urls import is_local_url
from ui_macos.settings_localization import (
    INTERFACE_LANGUAGES,
    INTERFACE_LANGUAGE_TITLES,
    settings_text,
)


TRANSLATION_PROVIDERS = {
    "DeepSeek": {
        "id": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-flash",
        "extra_body": "",
    },
    "Gemini": {
        "id": "google",
        "base_url": (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        ),
        "model": "gemini-3-flash-preview",
        "extra_body": '{"reasoning_effort": "minimal"}',
    },
    "Custom": {
        "id": "custom",
        "base_url": "",
        "model": "",
        "extra_body": "",
    },
}
PROVIDER_TITLES = {
    values["id"]: title
    for title, values in TRANSLATION_PROVIDERS.items()
}
PROVIDER_ORDER = tuple(TRANSLATION_PROVIDERS)
PROVIDER_TITLE_KEYS = {
    "DeepSeek": "provider.deepseek",
    "Gemini": "provider.gemini",
    "Custom": "provider.custom",
}
THINKING_OPTIONS = ("false", "true", "auto")
THINKING_TITLE_KEYS = {
    "false": "thinking.false",
    "true": "thinking.true",
    "auto": "thinking.auto",
}
FUNASR_API_KEY_GUIDES = {
    "china": "https://help.aliyun.com/zh/model-studio/get-api-key",
    "international": (
        "https://www.alibabacloud.com/help/en/model-studio/get-api-key"
    ),
}
SAVED_KEY_PLACEHOLDER = "••••••••••••"
CONTROL_WIDTH = 360
FORM_LABEL_WIDTH = 150
PANE_CONTENT_WIDTH = 560
TAB_TOP_INSET = 8
TAB_FOOTER_GAP = 10
FOOTER_HEIGHT = 52
PANE_CONTENT_INSET = 18
MIN_SETTINGS_HEIGHT = 320
SETTINGS_PANES = {
    "settings.transcription": {
        "title_key": "pane.transcription.title",
        "symbol": "waveform",
        "description_key": "pane.transcription.description",
        "index": 0,
    },
    "settings.translation": {
        "title_key": "pane.translation.title",
        "symbol": "character.bubble",
        "description_key": "pane.translation.description",
        "index": 1,
    },
    "settings.display": {
        "title_key": "pane.display.title",
        "symbol": "textformat.size",
        "description_key": "pane.display.description",
        "index": 2,
    },
}


def _label(text: str):
    label = NSTextField.labelWithString_(text)
    label.setFont_(NSFont.systemFontOfSize_(13))
    label.setTextColor_(NSColor.labelColor())
    return label


def _form_label(text: str):
    label = _label(text)
    label.setAlignment_(NSRightTextAlignment)
    label.setTextColor_(NSColor.secondaryLabelColor())
    return label


def _section_title(text: str):
    label = NSTextField.labelWithString_(text)
    label.setFont_(
        NSFont.systemFontOfSize_weight_(
            13,
            NSFontWeightSemibold,
        )
    )
    label.setTextColor_(NSColor.labelColor())
    return label


def _body_label(text: str):
    label = NSTextField.wrappingLabelWithString_(text)
    label.setFont_(NSFont.systemFontOfSize_(12))
    label.setTextColor_(NSColor.secondaryLabelColor())
    label.setPreferredMaxLayoutWidth_(PANE_CONTENT_WIDTH)
    return label


def _separator():
    separator = NSBox.alloc().initWithFrame_(
        NSMakeRect(0, 0, PANE_CONTENT_WIDTH, 1)
    )
    separator.setBoxType_(NSBoxSeparator)
    separator.heightAnchor().constraintEqualToConstant_(1).setActive_(True)
    return separator


def _open_external_url(url: str) -> None:
    NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))


def _text_field(placeholder: str = "", *, width: int = CONTROL_WIDTH):
    field = NSTextField.alloc().initWithFrame_(
        NSMakeRect(0, 0, width, 24)
    )
    field.setBezelStyle_(NSTextFieldRoundedBezel)
    field.setPlaceholderString_(placeholder)
    field.widthAnchor().constraintEqualToConstant_(width).setActive_(True)
    return field


def _secure_field(*, width: int = CONTROL_WIDTH):
    field = NSSecureTextField.alloc().initWithFrame_(
        NSMakeRect(0, 0, width, 24)
    )
    field.setBezelStyle_(NSTextFieldRoundedBezel)
    return field


def _credential_control(target, action, *, width: int = CONTROL_WIDTH):
    secure = _secure_field(width=width)
    revealed = _text_field(width=width)
    secure.setDelegate_(target)
    revealed.setDelegate_(target)
    revealed.setHidden_(True)

    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
        "eye",
        "Show API key",
    )
    visibility = NSButton.buttonWithImage_target_action_(
        image,
        target,
        action,
    )
    visibility.setBordered_(False)
    visibility.setToolTip_("Show API key")
    visibility.setAccessibilityLabel_("Show API key")

    field_row = NSView.alloc().initWithFrame_(
        NSMakeRect(0, 0, width, 24)
    )
    for control in (secure, revealed, visibility):
        control.setTranslatesAutoresizingMaskIntoConstraints_(False)
        field_row.addSubview_(control)
    NSLayoutConstraint.activateConstraints_(
        [
            field_row.widthAnchor().constraintEqualToConstant_(
                width
            ),
            field_row.heightAnchor().constraintEqualToConstant_(24),
            secure.leadingAnchor().constraintEqualToAnchor_(
                field_row.leadingAnchor()
            ),
            secure.topAnchor().constraintEqualToAnchor_(field_row.topAnchor()),
            secure.bottomAnchor().constraintEqualToAnchor_(
                field_row.bottomAnchor()
            ),
            secure.trailingAnchor().constraintEqualToAnchor_constant_(
                visibility.leadingAnchor(),
                -6,
            ),
            revealed.leadingAnchor().constraintEqualToAnchor_(
                field_row.leadingAnchor()
            ),
            revealed.topAnchor().constraintEqualToAnchor_(
                field_row.topAnchor()
            ),
            revealed.bottomAnchor().constraintEqualToAnchor_(
                field_row.bottomAnchor()
            ),
            revealed.trailingAnchor().constraintEqualToAnchor_constant_(
                visibility.leadingAnchor(),
                -6,
            ),
            visibility.trailingAnchor().constraintEqualToAnchor_(
                field_row.trailingAnchor()
            ),
            visibility.centerYAnchor().constraintEqualToAnchor_(
                field_row.centerYAnchor()
            ),
            visibility.widthAnchor().constraintEqualToConstant_(24),
            visibility.heightAnchor().constraintEqualToConstant_(24),
        ]
    )

    status = NSTextField.labelWithString_("")
    status.setFont_(NSFont.systemFontOfSize_(11))
    status.setTextColor_(NSColor.secondaryLabelColor())
    stack = NSStackView.stackViewWithViews_([field_row, status])
    stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    stack.setAlignment_(NSLayoutAttributeLeading)
    stack.setSpacing_(2)
    return stack, secure, revealed, visibility, status


def _popup(titles, *, width: int = CONTROL_WIDTH):
    popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(0, 0, width, 26),
        False,
    )
    popup.addItemsWithTitles_(titles)
    popup.widthAnchor().constraintEqualToConstant_(width).setActive_(True)
    return popup


def _checkbox():
    return NSButton.checkboxWithTitle_target_action_("", None, None)


def _disclosure_image(expanded: bool, description: str):
    symbol = "chevron.down" if expanded else "chevron.right"
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
        symbol,
        description,
    )
    image = image.imageWithSymbolConfiguration_(
        NSImageSymbolConfiguration.configurationWithPointSize_weight_(
            10,
            NSFontWeightSemibold,
        )
    )
    image.setTemplate_(True)
    return image


def _disclosure_button(
    target,
    identifier: str,
    *,
    title: str,
    description: str,
    tooltip: str,
):
    button = NSButton.buttonWithTitle_target_action_(
        title,
        target,
        "toggleAdvanced:",
    )
    button.setBordered_(False)
    button.setImage_(_disclosure_image(False, description))
    button.setImagePosition_(NSImageLeading)
    button.setIdentifier_(identifier)
    button.setToolTip_(tooltip)
    return button


class SettingsWindow(NSObject):
    @objc.python_method
    def configure(self, *, store, saved_callback):
        self.store = store
        self.saved_callback = saved_callback
        self.interface_language = self.store.interface_language()
        self.localized_bindings = []
        self.loading = False
        self.active_translation_provider = "deepseek"
        self.translation_key_drafts = {}
        self.translation_key_originals = {}
        self.translation_key_exists = {}
        self.translation_key_dirty = {}
        self.asr_key_original = None
        self.asr_key_exists = False
        self.asr_key_dirty = False
        self.pane_contents = {}
        self.tab_items = {}
        self.advanced_views = {}
        self.advanced_buttons = {}

        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 680, 560),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_(self._t("pane.transcription.title"))
        self.window.setToolbarStyle_(NSWindowToolbarStylePreference)
        self.window.setReleasedWhenClosed_(False)
        self.window.setDelegate_(self)
        self.window.setBackgroundColor_(NSColor.windowBackgroundColor())
        self.window.setOpaque_(True)
        self.window.center()

        root = NSView.alloc().initWithFrame_(
            self.window.contentView().bounds()
        )
        self.window.setContentView_(root)

        self.tab_view = NSTabView.alloc().initWithFrame_(root.bounds())
        self.tab_view.setTabViewType_(NSNoTabsNoBorder)
        self.tab_view.setTranslatesAutoresizingMaskIntoConstraints_(False)
        root.addSubview_(self.tab_view)

        self._build_transcription_tab()
        self._build_translation_tab()
        self._build_display_tab()

        self.save_button = NSButton.buttonWithTitle_target_action_(
            self._t("common.save"),
            self,
            "saveSettings:",
        )
        self._bind_text(self.save_button, "setTitle_", "common.save")
        self.save_button.setKeyEquivalent_("\r")
        self.save_button.setTranslatesAutoresizingMaskIntoConstraints_(False)
        root.addSubview_(self.save_button)

        self.status_label = NSTextField.labelWithString_("")
        self.status_label.setFont_(NSFont.systemFontOfSize_(11))
        self.status_label.setTextColor_(NSColor.secondaryLabelColor())
        self.status_label.setTranslatesAutoresizingMaskIntoConstraints_(False)
        root.addSubview_(self.status_label)

        self.footer_separator = NSBox.alloc().initWithFrame_(
            NSMakeRect(0, 0, 680, 1)
        )
        self.footer_separator.setBoxType_(NSBoxSeparator)
        self.footer_separator.setTranslatesAutoresizingMaskIntoConstraints_(
            False
        )
        root.addSubview_(self.footer_separator)

        NSLayoutConstraint.activateConstraints_(
            [
                self.tab_view.leadingAnchor().constraintEqualToAnchor_constant_(
                    root.leadingAnchor(),
                    20,
                ),
                self.tab_view.trailingAnchor().constraintEqualToAnchor_constant_(
                    root.trailingAnchor(),
                    -20,
                ),
                self.tab_view.topAnchor().constraintEqualToAnchor_constant_(
                    root.topAnchor(),
                    TAB_TOP_INSET,
                ),
                self.tab_view.bottomAnchor().constraintEqualToAnchor_constant_(
                    self.footer_separator.topAnchor(),
                    -TAB_FOOTER_GAP,
                ),
                self.footer_separator.leadingAnchor().constraintEqualToAnchor_(
                    root.leadingAnchor()
                ),
                self.footer_separator.trailingAnchor().constraintEqualToAnchor_(
                    root.trailingAnchor()
                ),
                self.footer_separator.bottomAnchor().constraintEqualToAnchor_constant_(
                    root.bottomAnchor(),
                    -FOOTER_HEIGHT,
                ),
                self.status_label.leadingAnchor().constraintEqualToAnchor_constant_(
                    root.leadingAnchor(),
                    22,
                ),
                self.status_label.centerYAnchor().constraintEqualToAnchor_(
                    self.save_button.centerYAnchor()
                ),
                self.status_label.trailingAnchor().constraintLessThanOrEqualToAnchor_constant_(
                    self.save_button.leadingAnchor(),
                    -12,
                ),
                self.save_button.trailingAnchor().constraintEqualToAnchor_constant_(
                    root.trailingAnchor(),
                    -20,
                ),
                self.save_button.bottomAnchor().constraintEqualToAnchor_constant_(
                    root.bottomAnchor(),
                    -13,
                ),
            ]
        )

        self.toolbar_items = {}
        self.toolbar = NSToolbar.alloc().initWithIdentifier_(
            "MacLiveSubtitleSettingsToolbar"
        )
        self.toolbar.setAllowsUserCustomization_(False)
        self.toolbar.setAutosavesConfiguration_(False)
        self.toolbar.setDisplayMode_(NSToolbarDisplayModeIconAndLabel)
        self.toolbar.setSizeMode_(NSToolbarSizeModeRegular)
        self.toolbar.setDelegate_(self)
        self.window.setToolbar_(self.toolbar)
        self.current_pane_identifier = next(iter(SETTINGS_PANES))
        self.toolbar.setSelectedItemIdentifier_(
            self.current_pane_identifier
        )
        return self

    @objc.python_method
    def _t(self, key: str) -> str:
        return settings_text(self.interface_language, key)

    @objc.python_method
    def _bind_text(self, control, setter: str, key: str):
        getattr(control, setter)(self._t(key))
        self.localized_bindings.append((control, setter, key))
        return control

    @objc.python_method
    def _localized_label(self, key: str):
        return self._bind_text(
            _label(self._t(key)),
            "setStringValue_",
            key,
        )

    @objc.python_method
    def _localized_form_label(self, key: str):
        return self._bind_text(
            _form_label(self._t(key)),
            "setStringValue_",
            key,
        )

    @objc.python_method
    def _localized_section_title(self, key: str):
        return self._bind_text(
            _section_title(self._t(key)),
            "setStringValue_",
            key,
        )

    @objc.python_method
    def _localized_body(self, key: str):
        return self._bind_text(
            _body_label(self._t(key)),
            "setStringValue_",
            key,
        )

    @objc.python_method
    def _localized_field_group(
        self,
        title_key: str,
        control,
        helper_key: str | None = None,
    ):
        views = [self._localized_label(title_key), control]
        if helper_key is not None:
            views.append(self._localized_body(helper_key))
        group = NSStackView.stackViewWithViews_(views)
        group.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        group.setAlignment_(NSLayoutAttributeLeading)
        group.setSpacing_(5)
        return group

    @objc.python_method
    def _localized_section_stack(self, title_key: str, views):
        section = NSStackView.stackViewWithViews_(
            [self._localized_section_title(title_key), *views]
        )
        section.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        section.setAlignment_(NSLayoutAttributeLeading)
        section.setSpacing_(10)
        return section

    @objc.python_method
    def _bind_tooltip(self, control, key: str) -> None:
        self._bind_text(control, "setToolTip_", key)

    @objc.python_method
    def _provider_popup_titles(self):
        return [
            self._t(PROVIDER_TITLE_KEYS[title])
            for title in PROVIDER_ORDER
        ]

    @objc.python_method
    def _thinking_popup_titles(self):
        return [
            self._t(THINKING_TITLE_KEYS[value])
            for value in THINKING_OPTIONS
        ]

    @objc.python_method
    def _replace_popup_titles(self, popup, titles) -> None:
        selected_index = popup.indexOfSelectedItem()
        popup.removeAllItems()
        popup.addItemsWithTitles_(titles)
        popup.selectItemAtIndex_(selected_index)

    @objc.python_method
    def _selected_provider_title(self) -> str:
        return PROVIDER_ORDER[
            self.translation_provider.indexOfSelectedItem()
        ]

    @objc.python_method
    def _apply_language(self) -> None:
        for control, setter, key in self.localized_bindings:
            getattr(control, setter)(self._t(key))

        self._replace_popup_titles(
            self.translation_provider,
            self._provider_popup_titles(),
        )
        self._replace_popup_titles(
            self.translation_thinking,
            self._thinking_popup_titles(),
        )
        self.interface_language_popup.selectItemAtIndex_(
            INTERFACE_LANGUAGES.index(self.interface_language)
        )

        for identifier, pane in SETTINGS_PANES.items():
            title = self._t(pane["title_key"])
            description = self._t(pane["description_key"])
            item = self.toolbar_items[identifier]
            item.setLabel_(title)
            item.setPaletteLabel_(title)
            item.setToolTip_(description)
            self.tab_items[identifier].setLabel_(title)

        for identifier, button in self.advanced_buttons.items():
            expanded = not self.advanced_views[identifier].isHidden()
            button.setTitle_(self._t("common.advanced"))
            button.setImage_(
                _disclosure_image(
                    expanded,
                    self._t("common.advanced_description"),
                )
            )
            button.setToolTip_(
                self._t(
                    "common.hide_advanced"
                    if expanded
                    else "common.show_advanced"
                )
            )

        self._set_visibility_button(
            self.asr_key_visibility,
            revealed=not self.asr_key_revealed.isHidden(),
        )
        self._set_visibility_button(
            self.translation_key_visibility,
            revealed=not self.translation_key_revealed.isHidden(),
        )
        self.asr_key_status.setStringValue_(
            self._credential_status(
                self.asr_key_exists,
                self._current_credential_value(
                    self.asr_key,
                    self.asr_key_revealed,
                ),
                self.asr_key_original,
                self.asr_key_dirty,
            )
        )
        provider = self.active_translation_provider
        self.translation_key_status.setStringValue_(
            self._credential_status(
                self.translation_key_exists[provider],
                self._current_credential_value(
                    self.translation_key,
                    self.translation_key_revealed,
                ),
                self.translation_key_originals[provider],
                self.translation_key_dirty[provider],
            )
        )
        self.asr_test_result.setStringValue_("")
        self.translation_test_result.setStringValue_("")
        self._set_status("", error=False)
        self.window.setTitle_(
            self._t(SETTINGS_PANES[
                self.current_pane_identifier
            ]["title_key"])
        )
        self.pane_contents[
            self.current_pane_identifier
        ].layoutSubtreeIfNeeded()
        self._resize_for_pane(
            self._height_for_pane(self.current_pane_identifier),
            animate=self.window.isVisible(),
        )
        self.window.makeFirstResponder_(None)

    def toolbarAllowedItemIdentifiers_(self, _toolbar):
        return [
            NSToolbarFlexibleSpaceItemIdentifier,
            *SETTINGS_PANES,
        ]

    def toolbarDefaultItemIdentifiers_(self, _toolbar):
        return [
            NSToolbarFlexibleSpaceItemIdentifier,
            *SETTINGS_PANES,
            NSToolbarFlexibleSpaceItemIdentifier,
        ]

    def toolbarSelectableItemIdentifiers_(self, _toolbar):
        return list(SETTINGS_PANES)

    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
        self,
        _toolbar,
        identifier,
        _will_insert,
    ):
        pane_identifier = str(identifier)
        pane = SETTINGS_PANES[pane_identifier]
        item = NSToolbarItem.alloc().initWithItemIdentifier_(identifier)
        title = self._t(pane["title_key"])
        item.setLabel_(title)
        item.setPaletteLabel_(title)
        item.setToolTip_(self._t(pane["description_key"]))
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            pane["symbol"],
            title,
        )
        image = image.imageWithSymbolConfiguration_(
            NSImageSymbolConfiguration.configurationWithPointSize_weight_(
                18,
                NSFontWeightSemibold,
            )
        )
        image.setTemplate_(True)
        item.setImage_(image)
        item.setTarget_(self)
        item.setAction_("selectSettingsPane:")
        self.toolbar_items[pane_identifier] = item
        return item

    def selectSettingsPane_(self, sender) -> None:
        self._select_pane(
            str(sender.itemIdentifier()),
            animate=self.window.isVisible(),
        )

    @objc.python_method
    def _select_pane(
        self,
        identifier: str,
        *,
        animate: bool,
    ) -> None:
        pane = SETTINGS_PANES[identifier]
        self.current_pane_identifier = identifier
        self.tab_view.selectTabViewItemAtIndex_(pane["index"])
        self.toolbar.setSelectedItemIdentifier_(identifier)
        self.window.setTitle_(self._t(pane["title_key"]))
        self._resize_for_pane(
            self._height_for_pane(identifier),
            animate=animate,
        )
        self.window.makeFirstResponder_(None)

    @objc.python_method
    def _height_for_pane(self, identifier: str) -> float:
        content = self.pane_contents[identifier]
        content.layoutSubtreeIfNeeded()
        content_height = content.fittingSize().height
        surrounding_height = (
            TAB_TOP_INSET
            + TAB_FOOTER_GAP
            + FOOTER_HEIGHT
            + (PANE_CONTENT_INSET * 2)
        )
        return max(
            MIN_SETTINGS_HEIGHT,
            content_height + surrounding_height,
        )

    @objc.python_method
    def _resize_for_pane(
        self,
        target_height: float,
        *,
        animate: bool,
    ) -> None:
        current_height = self.window.contentView().frame().size.height
        delta = target_height - current_height
        if abs(delta) < 1:
            return
        frame = self.window.frame()
        resized = NSMakeRect(
            frame.origin.x,
            frame.origin.y - delta,
            frame.size.width,
            frame.size.height + delta,
        )
        self.window.setFrame_display_animate_(
            resized,
            True,
            animate,
        )

    @objc.python_method
    def _build_transcription_tab(self) -> None:
        self.asr_model = _text_field("fun-asr-realtime")
        self.asr_url = _text_field(
            "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
        )
        (
            self.asr_key_control,
            self.asr_key,
            self.asr_key_revealed,
            self.asr_key_visibility,
            self.asr_key_status,
        ) = _credential_control(
            self,
            "toggleASRKeyVisibility:",
            width=PANE_CONTENT_WIDTH,
        )
        self.source_language = _text_field(
            "auto, zh, en, ja",
            width=PANE_CONTENT_WIDTH,
        )
        self._bind_tooltip(
            self.source_language,
            "transcription.source_language_help",
        )
        self.semantic_punctuation = _checkbox()
        self._bind_text(
            self.semantic_punctuation,
            "setTitle_",
            "transcription.semantic_punctuation",
        )
        self._bind_tooltip(
            self.semantic_punctuation,
            "transcription.semantic_punctuation_help",
        )
        self.max_silence = _text_field("0 or 200-6000")
        self._bind_tooltip(
            self.max_silence,
            "transcription.maximum_silence_help",
        )
        self.multi_threshold = _checkbox()
        self._bind_tooltip(
            self.multi_threshold,
            "transcription.multi_threshold_help",
        )
        self.interim_chars = _text_field("40")
        self._bind_tooltip(
            self.interim_chars,
            "transcription.interim_interval_help",
        )
        self._bind_tooltip(
            self.asr_model,
            "transcription.model_help",
        )
        self._bind_tooltip(
            self.asr_url,
            "transcription.websocket_url_help",
        )
        self.asr_test_button = NSButton.buttonWithTitle_target_action_(
            self._t("common.test_connection"),
            self,
            "testASR:",
        )
        self._bind_text(
            self.asr_test_button,
            "setTitle_",
            "common.test_connection",
        )
        self.asr_test_result = _label("")
        test_row = NSStackView.stackViewWithViews_(
            [self.asr_test_button, self.asr_test_result]
        )
        test_row.setOrientation_(
            NSUserInterfaceLayoutOrientationHorizontal
        )
        test_row.setDistribution_(NSStackViewDistributionFill)
        test_row.setSpacing_(8)

        self.asr_china_guide_button = (
            NSButton.buttonWithTitle_target_action_(
                self._t("transcription.china_guide"),
                self,
                "openChinaAPIKeyGuide:",
            )
        )
        self._bind_text(
            self.asr_china_guide_button,
            "setTitle_",
            "transcription.china_guide",
        )
        self._bind_tooltip(
            self.asr_china_guide_button,
            "transcription.china_guide_help",
        )
        self.asr_international_guide_button = (
            NSButton.buttonWithTitle_target_action_(
                self._t("transcription.international_guide"),
                self,
                "openInternationalAPIKeyGuide:",
            )
        )
        self._bind_text(
            self.asr_international_guide_button,
            "setTitle_",
            "transcription.international_guide",
        )
        self._bind_tooltip(
            self.asr_international_guide_button,
            "transcription.international_guide_help",
        )
        guide_buttons = NSStackView.stackViewWithViews_(
            [
                self.asr_china_guide_button,
                self.asr_international_guide_button,
            ]
        )
        guide_buttons.setOrientation_(
            NSUserInterfaceLayoutOrientationHorizontal
        )
        guide_buttons.setSpacing_(8)

        guide_header = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PANE_CONTENT_WIDTH, 28)
        )
        guide_title = self._localized_section_title(
            "transcription.title"
        )
        guide_title.setTranslatesAutoresizingMaskIntoConstraints_(False)
        guide_buttons.setTranslatesAutoresizingMaskIntoConstraints_(False)
        guide_header.addSubview_(guide_title)
        guide_header.addSubview_(guide_buttons)
        NSLayoutConstraint.activateConstraints_(
            [
                guide_header.heightAnchor().constraintEqualToConstant_(28),
                guide_title.leadingAnchor().constraintEqualToAnchor_(
                    guide_header.leadingAnchor()
                ),
                guide_title.centerYAnchor().constraintEqualToAnchor_(
                    guide_header.centerYAnchor()
                ),
                guide_buttons.trailingAnchor().constraintEqualToAnchor_(
                    guide_header.trailingAnchor()
                ),
                guide_buttons.centerYAnchor().constraintEqualToAnchor_(
                    guide_header.centerYAnchor()
                ),
                guide_title.trailingAnchor().constraintLessThanOrEqualToAnchor_constant_(
                    guide_buttons.leadingAnchor(),
                    -12,
                ),
            ]
        )
        guide_intro = NSStackView.stackViewWithViews_(
            [
                guide_header,
                self._localized_body("transcription.introduction"),
            ]
        )
        guide_intro.setOrientation_(
            NSUserInterfaceLayoutOrientationVertical
        )
        guide_intro.setAlignment_(NSLayoutAttributeLeading)
        guide_intro.setSpacing_(6)

        api_access = self._localized_section_stack(
            "common.api_access",
            [
                self._localized_field_group(
                    "common.api_key",
                    self.asr_key_control,
                    "transcription.api_key_help",
                ),
                test_row,
            ],
        )
        language_and_sentences = self._localized_section_stack(
            "transcription.language_section",
            [
                self._localized_field_group(
                    "transcription.source_language",
                    self.source_language,
                    "transcription.source_language_help",
                ),
                self.semantic_punctuation,
            ],
        )

        self._add_tab(
            "settings.transcription",
            [],
            leading_views=[
                guide_intro,
                _separator(),
                api_access,
                _separator(),
                language_and_sentences,
            ],
            advanced_rows=[
                ("transcription.model", self.asr_model),
                ("transcription.websocket_url", self.asr_url),
                (
                    "transcription.maximum_silence",
                    self.max_silence,
                ),
                (
                    "transcription.multi_threshold",
                    self.multi_threshold,
                ),
                (
                    "transcription.interim_interval",
                    self.interim_chars,
                ),
            ],
        )

    @objc.python_method
    def _build_translation_tab(self) -> None:
        self.translation_enabled = NSSwitch.alloc().initWithFrame_(
            NSMakeRect(0, 0, 42, 25)
        )
        self._bind_tooltip(
            self.translation_enabled,
            "translation.enable_help",
        )
        self.translation_provider = _popup(
            self._provider_popup_titles(),
            width=PANE_CONTENT_WIDTH,
        )
        self.translation_provider.setTarget_(self)
        self.translation_provider.setAction_("translationProviderChanged:")
        self.translation_base_url = _text_field(
            "https://api.openai.com/v1"
        )
        self._bind_tooltip(
            self.translation_base_url,
            "translation.base_url_help",
        )
        self.translation_model = _text_field("Model name")
        self._bind_tooltip(
            self.translation_model,
            "translation.model_help",
        )
        self.translation_thinking = _popup(
            self._thinking_popup_titles()
        )
        self._bind_tooltip(
            self.translation_thinking,
            "translation.thinking_help",
        )
        (
            self.translation_key_control,
            self.translation_key,
            self.translation_key_revealed,
            self.translation_key_visibility,
            self.translation_key_status,
        ) = _credential_control(
            self,
            "toggleTranslationKeyVisibility:",
            width=PANE_CONTENT_WIDTH,
        )
        self.target_language = _text_field(
            "Simplified Chinese",
            width=PANE_CONTENT_WIDTH,
        )
        self.temperature = _text_field("1.0")
        self._bind_tooltip(
            self.temperature,
            "translation.temperature_help",
        )
        self.translation_test_button = (
            NSButton.buttonWithTitle_target_action_(
                self._t("common.test_connection"),
                self,
                "testTranslation:",
            )
        )
        self._bind_text(
            self.translation_test_button,
            "setTitle_",
            "common.test_connection",
        )
        self.translation_test_result = _label("")
        test_row = NSStackView.stackViewWithViews_(
            [self.translation_test_button, self.translation_test_result]
        )
        test_row.setOrientation_(
            NSUserInterfaceLayoutOrientationHorizontal
        )
        test_row.setDistribution_(NSStackViewDistributionFill)
        test_row.setSpacing_(8)

        enabled_row = NSStackView.stackViewWithViews_(
            [
                self._localized_label("translation.enable"),
                self.translation_enabled,
            ]
        )
        enabled_row.setOrientation_(
            NSUserInterfaceLayoutOrientationHorizontal
        )
        enabled_row.setSpacing_(8)

        translation_header = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PANE_CONTENT_WIDTH, 28)
        )
        translation_title = self._localized_section_title(
            "translation.title"
        )
        translation_title.setTranslatesAutoresizingMaskIntoConstraints_(
            False
        )
        enabled_row.setTranslatesAutoresizingMaskIntoConstraints_(False)
        translation_header.addSubview_(translation_title)
        translation_header.addSubview_(enabled_row)
        NSLayoutConstraint.activateConstraints_(
            [
                translation_header.heightAnchor().constraintEqualToConstant_(
                    28
                ),
                translation_title.leadingAnchor().constraintEqualToAnchor_(
                    translation_header.leadingAnchor()
                ),
                translation_title.centerYAnchor().constraintEqualToAnchor_(
                    translation_header.centerYAnchor()
                ),
                enabled_row.trailingAnchor().constraintEqualToAnchor_(
                    translation_header.trailingAnchor()
                ),
                enabled_row.centerYAnchor().constraintEqualToAnchor_(
                    translation_header.centerYAnchor()
                ),
                translation_title.trailingAnchor().constraintLessThanOrEqualToAnchor_constant_(
                    enabled_row.leadingAnchor(),
                    -12,
                ),
            ]
        )
        translation_intro = NSStackView.stackViewWithViews_(
            [
                translation_header,
                self._localized_body("translation.introduction"),
            ]
        )
        translation_intro.setOrientation_(
            NSUserInterfaceLayoutOrientationVertical
        )
        translation_intro.setAlignment_(NSLayoutAttributeLeading)
        translation_intro.setSpacing_(6)

        service = self._localized_section_stack(
            "translation.service",
            [
                self._localized_field_group(
                    "translation.provider",
                    self.translation_provider,
                ),
                self._localized_field_group(
                    "translation.target_language",
                    self.target_language,
                    "translation.target_language_help",
                ),
            ],
        )
        api_access = self._localized_section_stack(
            "common.api_access",
            [
                self._localized_field_group(
                    "common.api_key",
                    self.translation_key_control,
                    "translation.api_key_help",
                ),
                test_row,
            ],
        )

        self._add_tab(
            "settings.translation",
            [],
            leading_views=[
                translation_intro,
                _separator(),
                service,
                _separator(),
                api_access,
            ],
            advanced_rows=[
                ("translation.base_url", self.translation_base_url),
                ("translation.model", self.translation_model),
                ("translation.thinking", self.translation_thinking),
                ("translation.temperature", self.temperature),
            ],
        )

    @objc.python_method
    def _build_display_tab(self) -> None:
        self.always_on_top = _checkbox()
        self.always_on_top.setTarget_(self)
        self.always_on_top.setAction_("previewDisplay:")

        self.background_opacity = (
            NSSlider.sliderWithValue_minValue_maxValue_target_action_(
                82,
                40,
                100,
                self,
                "previewDisplay:",
            )
        )
        self.background_opacity.setContinuous_(True)
        self.background_opacity.widthAnchor().constraintEqualToConstant_(
            245
        ).setActive_(True)
        self.background_opacity_value = _label("82%")
        self.background_opacity_value.widthAnchor().constraintEqualToConstant_(
            48
        ).setActive_(True)
        opacity_row = NSStackView.stackViewWithViews_(
            [self.background_opacity, self.background_opacity_value]
        )
        opacity_row.setOrientation_(
            NSUserInterfaceLayoutOrientationHorizontal
        )
        opacity_row.setSpacing_(10)

        self.original_font = NSSlider.sliderWithValue_minValue_maxValue_target_action_(
            13,
            10,
            30,
            self,
            "previewDisplay:",
        )
        self.original_font.setContinuous_(True)
        self.original_font.widthAnchor().constraintEqualToConstant_(
            245
        ).setActive_(True)
        self.original_font_value = _label("13 pt")
        self.original_font_value.widthAnchor().constraintEqualToConstant_(
            48
        ).setActive_(True)
        original_row = NSStackView.stackViewWithViews_(
            [self.original_font, self.original_font_value]
        )
        original_row.setOrientation_(
            NSUserInterfaceLayoutOrientationHorizontal
        )
        original_row.setSpacing_(10)

        self.translated_font = NSSlider.sliderWithValue_minValue_maxValue_target_action_(
            17,
            10,
            30,
            self,
            "previewDisplay:",
        )
        self.translated_font.setContinuous_(True)
        self.translated_font.widthAnchor().constraintEqualToConstant_(
            245
        ).setActive_(True)
        self.translated_font_value = _label("17 pt")
        self.translated_font_value.widthAnchor().constraintEqualToConstant_(
            48
        ).setActive_(True)
        translated_row = NSStackView.stackViewWithViews_(
            [self.translated_font, self.translated_font_value]
        )
        translated_row.setOrientation_(
            NSUserInterfaceLayoutOrientationHorizontal
        )
        translated_row.setSpacing_(10)

        self.interface_language_popup = _popup(
            INTERFACE_LANGUAGE_TITLES
        )
        self.interface_language_popup.selectItemAtIndex_(
            INTERFACE_LANGUAGES.index(self.interface_language)
        )
        self.interface_language_popup.setTarget_(self)
        self.interface_language_popup.setAction_(
            "interfaceLanguageChanged:"
        )
        self._bind_tooltip(
            self.interface_language_popup,
            "display.settings_language_help",
        )

        self._add_tab(
            "settings.display",
            [
                (
                    "display.window",
                    [
                        ("display.always_on_top", self.always_on_top),
                        (
                            "display.background_opacity",
                            opacity_row,
                        ),
                    ],
                ),
                (
                    "display.typography",
                    [
                        ("display.original_font", original_row),
                        (
                            "display.translated_font",
                            translated_row,
                        ),
                    ],
                ),
                (
                    "display.interface",
                    [
                        (
                            "display.settings_language",
                            self.interface_language_popup,
                        ),
                    ],
                ),
            ],
        )

    @objc.python_method
    def _add_tab(
        self,
        identifier: str,
        sections,
        *,
        leading_views=None,
        advanced_rows=None,
    ) -> None:
        pane = SETTINGS_PANES[identifier]
        page = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 620, 500))

        if leading_views is None:
            leading_views = [
                self._localized_body(pane["description_key"])
            ]
        else:
            leading_views = list(leading_views)
        full_width_views = list(leading_views)

        section_views = []
        for section_name, rows in sections:
            grid = NSGridView.gridViewWithViews_(
                [
                    [self._localized_form_label(label_key), control]
                    for label_key, control in rows
                ]
            )
            grid.setRowSpacing_(9)
            grid.setColumnSpacing_(16)
            grid.columnAtIndex_(0).setWidth_(FORM_LABEL_WIDTH)
            grid.columnAtIndex_(1).setWidth_(CONTROL_WIDTH)

            section = NSStackView.stackViewWithViews_(
                [self._localized_section_title(section_name), grid]
            )
            section.setOrientation_(
                NSUserInterfaceLayoutOrientationVertical
            )
            section.setAlignment_(NSLayoutAttributeLeading)
            section.setSpacing_(9)
            section_views.append(section)

        content_views = list(leading_views)
        for section in section_views:
            separator = _separator()
            content_views.extend([separator, section])
            full_width_views.extend([separator, section])

        advanced_view = None
        disclosure = None
        if advanced_rows:
            separator = _separator()
            disclosure = _disclosure_button(
                self,
                identifier,
                title=self._t("common.advanced"),
                description=self._t("common.advanced_description"),
                tooltip=self._t("common.show_advanced"),
            )
            advanced_view = NSGridView.gridViewWithViews_(
                [
                    [
                        self._localized_form_label(label_key),
                        control,
                    ]
                    for label_key, control in advanced_rows
                ]
            )
            advanced_view.setRowSpacing_(9)
            advanced_view.setColumnSpacing_(16)
            advanced_view.columnAtIndex_(0).setWidth_(FORM_LABEL_WIDTH)
            advanced_view.columnAtIndex_(1).setWidth_(CONTROL_WIDTH)
            content_views.extend([separator, disclosure, advanced_view])
            full_width_views.extend([separator, advanced_view])
            self.advanced_buttons[identifier] = disclosure
            self.advanced_views[identifier] = advanced_view

        content = NSStackView.stackViewWithViews_(
            content_views
        )
        content.setOrientation_(
            NSUserInterfaceLayoutOrientationVertical
        )
        content.setAlignment_(NSLayoutAttributeLeading)
        content.setSpacing_(14)
        content.setDetachesHiddenViews_(True)
        content.setTranslatesAutoresizingMaskIntoConstraints_(False)
        page.addSubview_(content)
        for view in full_width_views:
            view.widthAnchor().constraintEqualToAnchor_(
                content.widthAnchor()
            ).setActive_(True)
        if advanced_view is not None and disclosure is not None:
            content.setCustomSpacing_afterView_(8, disclosure)
            advanced_view.setHidden_(True)
        NSLayoutConstraint.activateConstraints_(
            [
                content.centerXAnchor().constraintEqualToAnchor_(
                    page.centerXAnchor()
                ),
                content.widthAnchor().constraintEqualToConstant_(
                    PANE_CONTENT_WIDTH
                ),
                content.topAnchor().constraintEqualToAnchor_constant_(
                    page.topAnchor(),
                    PANE_CONTENT_INSET,
                ),
            ]
        )
        self.pane_contents[identifier] = content
        item = NSTabViewItem.alloc().initWithIdentifier_(identifier)
        item.setLabel_(self._t(pane["title_key"]))
        item.setView_(page)
        self.tab_items[identifier] = item
        self.tab_view.addTabViewItem_(item)

    def openChinaAPIKeyGuide_(self, _sender) -> None:
        _open_external_url(FUNASR_API_KEY_GUIDES["china"])

    def openInternationalAPIKeyGuide_(self, _sender) -> None:
        _open_external_url(FUNASR_API_KEY_GUIDES["international"])

    def interfaceLanguageChanged_(self, _sender) -> None:
        if self.loading:
            return
        language = INTERFACE_LANGUAGES[
            self.interface_language_popup.indexOfSelectedItem()
        ]
        if language == self.interface_language:
            return
        self.interface_language = language
        self.store.save_interface_language(language)
        self._apply_language()

    def toggleAdvanced_(self, sender) -> None:
        identifier = str(sender.identifier())
        advanced_view = self.advanced_views[identifier]
        self._set_advanced_expanded(
            identifier,
            advanced_view.isHidden(),
            animate=self.window.isVisible(),
        )

    @objc.python_method
    def _set_advanced_expanded(
        self,
        identifier: str,
        expanded: bool,
        *,
        animate: bool,
    ) -> None:
        advanced_view = self.advanced_views[identifier]
        advanced_view.setHidden_(not expanded)
        button = self.advanced_buttons[identifier]
        button.setImage_(
            _disclosure_image(
                expanded,
                self._t("common.advanced_description"),
            )
        )
        button.setToolTip_(
            self._t(
                "common.hide_advanced"
                if expanded
                else "common.show_advanced"
            )
        )
        self.pane_contents[identifier].layoutSubtreeIfNeeded()
        if self.current_pane_identifier == identifier:
            self._resize_for_pane(
                self._height_for_pane(identifier),
                animate=animate,
            )

    @objc.python_method
    def show(self) -> None:
        self._load()
        self._select_pane(
            self.current_pane_identifier,
            animate=False,
        )
        self.window.makeKeyAndOrderFront_(None)
        self.window.makeFirstResponder_(None)

    @objc.python_method
    def set_always_on_top(self, enabled: bool) -> None:
        self.always_on_top.setState_(
            NSControlStateValueOn if enabled else 0
        )

    @objc.python_method
    def _load(self) -> None:
        self.loading = True
        preferences = self.store.load()
        self.asr_model.setStringValue_(
            preferences.funasr_realtime_model
        )
        self.asr_url.setStringValue_(
            preferences.funasr_realtime_ws_url
        )
        self.source_language.setStringValue_(preferences.source_language)
        self.semantic_punctuation.setState_(
            NSControlStateValueOn
            if preferences.funasr_realtime_semantic_punctuation
            else 0
        )
        self.max_silence.setIntegerValue_(
            preferences.funasr_realtime_max_sentence_silence
        )
        self.multi_threshold.setState_(
            NSControlStateValueOn
            if preferences.funasr_realtime_multi_threshold
            else 0
        )
        self.interim_chars.setIntegerValue_(
            preferences.funasr_interim_translate_chars
        )
        self.asr_key_exists = self.store.has_asr_key()
        self.asr_key_original = None
        self.asr_key_dirty = False
        self._display_credential(
            self.asr_key,
            self.asr_key_revealed,
            self.asr_key_visibility,
            self.asr_key_status,
            exists=self.asr_key_exists,
            value="",
            original=None,
        )

        self.translation_enabled.setState_(
            NSControlStateValueOn
            if preferences.translation_enabled
            else 0
        )
        provider_title = PROVIDER_TITLES.get(
            preferences.translation_provider,
            "Custom",
        )
        self.translation_provider.selectItemAtIndex_(
            PROVIDER_ORDER.index(provider_title)
        )
        self.active_translation_provider = (
            TRANSLATION_PROVIDERS[provider_title]["id"]
        )
        self.translation_base_url.setStringValue_(
            preferences.api_base_url
        )
        self.translation_model.setStringValue_(preferences.model)
        self.translation_thinking.selectItemAtIndex_(
            THINKING_OPTIONS.index(preferences.translation_thinking)
        )
        self.target_language.setStringValue_(preferences.target_lang)
        self.temperature.setDoubleValue_(
            preferences.translation_temperature
        )
        translation_key_exists = self.store.has_translation_key(
            self.active_translation_provider
        )
        self.translation_key_exists = {
            self.active_translation_provider: translation_key_exists
        }
        self.translation_key_drafts = {
            self.active_translation_provider: ""
        }
        self.translation_key_originals = {
            self.active_translation_provider: None
        }
        self.translation_key_dirty = {
            self.active_translation_provider: False
        }
        self._display_credential(
            self.translation_key,
            self.translation_key_revealed,
            self.translation_key_visibility,
            self.translation_key_status,
            exists=translation_key_exists,
            value="",
            original=None,
        )
        if provider_title == "Custom":
            self._set_advanced_expanded(
                "settings.translation",
                True,
                animate=False,
            )

        self.always_on_top.setState_(
            NSControlStateValueOn if preferences.always_on_top else 0
        )
        self.background_opacity.setDoubleValue_(
            preferences.background_opacity * 100
        )
        self.original_font.setIntegerValue_(
            preferences.original_font_size
        )
        self.translated_font.setIntegerValue_(
            preferences.translated_font_size
        )
        self.interface_language_popup.selectItemAtIndex_(
            INTERFACE_LANGUAGES.index(self.interface_language)
        )
        self._update_font_labels()
        self._set_status("", error=False)
        self.loading = False

    def translationProviderChanged_(self, _sender) -> None:
        if self.loading:
            return
        self._stash_translation_key()

        title = self._selected_provider_title()
        preset = TRANSLATION_PROVIDERS[title]
        provider = preset["id"]
        self.active_translation_provider = provider
        if title != "Custom":
            self.translation_base_url.setStringValue_(preset["base_url"])
            self.translation_model.setStringValue_(preset["model"])
        if provider not in self.translation_key_drafts:
            self.translation_key_exists[
                provider
            ] = self.store.has_translation_key(provider)
            self.translation_key_drafts[provider] = ""
            self.translation_key_originals[provider] = None
            self.translation_key_dirty[provider] = False
        self._display_credential(
            self.translation_key,
            self.translation_key_revealed,
            self.translation_key_visibility,
            self.translation_key_status,
            exists=self.translation_key_exists[provider],
            value=self.translation_key_drafts[provider],
            original=self.translation_key_originals[provider],
            dirty=self.translation_key_dirty[provider],
        )
        if title == "Custom":
            self._set_advanced_expanded(
                "settings.translation",
                True,
                animate=self.window.isVisible(),
            )

    @objc.python_method
    def _display_credential(
        self,
        secure,
        revealed,
        visibility,
        status,
        *,
        exists: bool,
        value: str,
        original: str | None,
        dirty: bool = False,
    ) -> None:
        revealed.setStringValue_("")
        revealed.setHidden_(True)
        secure.setHidden_(False)
        secure.setStringValue_(value)
        secure.setPlaceholderString_(
            SAVED_KEY_PLACEHOLDER
            if exists and not value and not dirty
            else ""
        )
        visibility.setEnabled_(exists or bool(value))
        self._set_visibility_button(visibility, revealed=False)
        status.setStringValue_(
            self._credential_status(exists, value, original, dirty)
        )

    @objc.python_method
    def _credential_status(
        self,
        exists: bool,
        value: str,
        original: str | None,
        dirty: bool,
    ) -> str:
        if dirty and not value and exists:
            return self._t("common.remove_key_on_save")
        if original is not None and value == original:
            return self._t("common.saved_locally")
        if value:
            if exists:
                return self._t("common.replace_saved_key")
            return self._t("common.save_new_key")
        if exists:
            return self._t("common.saved_locally")
        return ""

    @objc.python_method
    def _set_visibility_button(self, button, *, revealed: bool) -> None:
        symbol = "eye.slash" if revealed else "eye"
        description = self._t(
            "common.hide_api_key"
            if revealed
            else "common.show_api_key"
        )
        button.setImage_(
            NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                symbol,
                description,
            )
        )
        button.setToolTip_(description)
        button.setAccessibilityLabel_(description)

    @objc.python_method
    def _current_credential_value(self, secure, revealed) -> str:
        if revealed.isHidden():
            return secure.stringValue()
        return revealed.stringValue()

    @objc.python_method
    def _reveal_credential(self, secure, revealed, visibility) -> None:
        revealed.setStringValue_(secure.stringValue())
        secure.setStringValue_("")
        secure.setHidden_(True)
        revealed.setHidden_(False)
        self._set_visibility_button(visibility, revealed=True)
        self.window.makeFirstResponder_(revealed)

    @objc.python_method
    def _hide_credential(self, secure, revealed, visibility) -> None:
        secure.setStringValue_(revealed.stringValue())
        revealed.setStringValue_("")
        revealed.setHidden_(True)
        secure.setHidden_(False)
        self._set_visibility_button(visibility, revealed=False)
        self.window.makeFirstResponder_(secure)

    @objc.python_method
    def _stash_translation_key(self) -> None:
        provider = self.active_translation_provider
        value = self._current_credential_value(
            self.translation_key,
            self.translation_key_revealed,
        )
        original = self.translation_key_originals.get(provider)
        if original is not None and value == original:
            value = ""
            original = None
            self.translation_key_dirty[provider] = False
        self.translation_key_drafts[provider] = value
        self.translation_key_originals[provider] = original

    def toggleASRKeyVisibility_(self, _sender) -> None:
        if not self.asr_key_revealed.isHidden():
            value = self.asr_key_revealed.stringValue()
            self._hide_credential(
                self.asr_key,
                self.asr_key_revealed,
                self.asr_key_visibility,
            )
            if (
                self.asr_key_original is not None
                and value == self.asr_key_original
            ):
                self.asr_key_original = None
                self.asr_key_dirty = False
                self._display_credential(
                    self.asr_key,
                    self.asr_key_revealed,
                    self.asr_key_visibility,
                    self.asr_key_status,
                    exists=self.asr_key_exists,
                    value="",
                    original=None,
                )
            return
        if not self.asr_key.stringValue() and self.asr_key_exists:
            try:
                value = self.store.asr_key() or ""
            except Exception as exc:
                self._set_status(str(exc), error=True)
                return
            if not value:
                self.asr_key_exists = False
                self.asr_key_original = None
                self.asr_key_dirty = False
                self._display_credential(
                    self.asr_key,
                    self.asr_key_revealed,
                    self.asr_key_visibility,
                    self.asr_key_status,
                    exists=False,
                    value="",
                    original=None,
                )
                return
            self.asr_key_original = value
            self.asr_key.setStringValue_(value)
        if self.asr_key.stringValue():
            self._reveal_credential(
                self.asr_key,
                self.asr_key_revealed,
                self.asr_key_visibility,
            )

    def toggleTranslationKeyVisibility_(self, _sender) -> None:
        if not self.translation_key_revealed.isHidden():
            provider = self.active_translation_provider
            value = self.translation_key_revealed.stringValue()
            self._hide_credential(
                self.translation_key,
                self.translation_key_revealed,
                self.translation_key_visibility,
            )
            if (
                self.translation_key_originals[provider] is not None
                and value == self.translation_key_originals[provider]
            ):
                self.translation_key_originals[provider] = None
                self.translation_key_dirty[provider] = False
                self._display_credential(
                    self.translation_key,
                    self.translation_key_revealed,
                    self.translation_key_visibility,
                    self.translation_key_status,
                    exists=self.translation_key_exists[provider],
                    value="",
                    original=None,
                )
            return
        provider = self.active_translation_provider
        if (
            not self.translation_key.stringValue()
            and self.translation_key_exists[provider]
        ):
            try:
                value = self.store.translation_key(provider) or ""
            except Exception as exc:
                self._set_status(str(exc), error=True)
                return
            if not value:
                self.translation_key_exists[provider] = False
                self.translation_key_originals[provider] = None
                self.translation_key_dirty[provider] = False
                self._display_credential(
                    self.translation_key,
                    self.translation_key_revealed,
                    self.translation_key_visibility,
                    self.translation_key_status,
                    exists=False,
                    value="",
                    original=None,
                )
                return
            self.translation_key_originals[provider] = value
            self.translation_key.setStringValue_(value)
        if self.translation_key.stringValue():
            self._reveal_credential(
                self.translation_key,
                self.translation_key_revealed,
                self.translation_key_visibility,
            )

    def controlTextDidChange_(self, notification) -> None:
        field = notification.object()
        if field in (self.asr_key, self.asr_key_revealed):
            value = field.stringValue()
            self.asr_key_dirty = True
            self.asr_key.setPlaceholderString_("")
            self.asr_key_visibility.setEnabled_(
                self.asr_key_exists or bool(value)
            )
            self.asr_key_status.setStringValue_(
                self._credential_status(
                    self.asr_key_exists,
                    value,
                    self.asr_key_original,
                    self.asr_key_dirty,
                )
            )
        elif field in (
            self.translation_key,
            self.translation_key_revealed,
        ):
            provider = self.active_translation_provider
            value = field.stringValue()
            self.translation_key_dirty[provider] = True
            self.translation_key.setPlaceholderString_("")
            self.translation_key_visibility.setEnabled_(
                self.translation_key_exists[provider] or bool(value)
            )
            self.translation_key_status.setStringValue_(
                self._credential_status(
                    self.translation_key_exists[provider],
                    value,
                    self.translation_key_originals[provider],
                    self.translation_key_dirty[provider],
                )
            )

    def previewDisplay_(self, _sender) -> None:
        self._update_font_labels()
        if self.loading:
            return
        current = self.store.load()
        preview = replace(
            current,
            always_on_top=self.always_on_top.state()
            == NSControlStateValueOn,
            background_opacity=(
                self.background_opacity.doubleValue() / 100
            ),
            original_font_size=self.original_font.integerValue(),
            translated_font_size=self.translated_font.integerValue(),
        )
        self.saved_callback(preview, False)

    @objc.python_method
    def _update_font_labels(self) -> None:
        self.background_opacity_value.setStringValue_(
            f"{self.background_opacity.integerValue()}%"
        )
        self.original_font_value.setStringValue_(
            f"{self.original_font.integerValue()} pt"
        )
        self.translated_font_value.setStringValue_(
            f"{self.translated_font.integerValue()} pt"
        )

    def saveSettings_(self, _sender) -> None:
        try:
            preferences = self._preferences_from_fields()
            self.store.save(preferences)
            asr_value = self._current_credential_value(
                self.asr_key,
                self.asr_key_revealed,
            ).strip()
            if self.asr_key_dirty and not asr_value:
                if self.asr_key_exists:
                    self.store.save_asr_key("")
                    self.asr_key_exists = False
            elif asr_value and (
                self.asr_key_original is None
                or asr_value != self.asr_key_original
            ):
                self.store.save_asr_key(asr_value)
                self.asr_key_exists = True

            self._stash_translation_key()
            for provider, value in self.translation_key_drafts.items():
                normalized = value.strip()
                original = self.translation_key_originals.get(provider)
                if (
                    self.translation_key_dirty[provider]
                    and not normalized
                ):
                    if self.translation_key_exists[provider]:
                        self.store.save_translation_key(provider, "")
                        self.translation_key_exists[provider] = False
                elif normalized and (
                    original is None or normalized != original
                ):
                    self.store.save_translation_key(provider, normalized)
                    self.translation_key_exists[provider] = True
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return

        self.asr_key_original = None
        self.asr_key_dirty = False
        self._display_credential(
            self.asr_key,
            self.asr_key_revealed,
            self.asr_key_visibility,
            self.asr_key_status,
            exists=self.asr_key_exists,
            value="",
            original=None,
        )
        self.translation_key_drafts = {
            provider: ""
            for provider in self.translation_key_exists
        }
        self.translation_key_originals = {
            provider: None
            for provider in self.translation_key_exists
        }
        self.translation_key_dirty = {
            provider: False
            for provider in self.translation_key_exists
        }
        self._display_credential(
            self.translation_key,
            self.translation_key_revealed,
            self.translation_key_visibility,
            self.translation_key_status,
            exists=self.translation_key_exists[
                self.active_translation_provider
            ],
            value="",
            original=None,
        )
        self.saved_callback(preferences, True)
        self._set_status(
            self._t("common.saved_message"),
            error=False,
        )

    @objc.python_method
    def _preferences_from_fields(self):
        model = self.asr_model.stringValue().strip()
        url = self.asr_url.stringValue().strip()
        source_language = self.source_language.stringValue().strip() or "auto"
        max_silence = self.max_silence.integerValue()
        interim_chars = self.interim_chars.integerValue()
        translation_model = self.translation_model.stringValue().strip()
        target_language = self.target_language.stringValue().strip()
        temperature = self.temperature.doubleValue()
        if not model:
            raise ValueError(self._t("validation.funasr_model"))
        if not url.startswith(("wss://", "ws://")):
            raise ValueError(self._t("validation.websocket_url"))
        if max_silence != 0 and not 200 <= max_silence <= 6000:
            raise ValueError(self._t("validation.maximum_silence"))
        if interim_chars < 0:
            raise ValueError(self._t("validation.interim_interval"))
        if not translation_model:
            raise ValueError(self._t("validation.translation_model"))
        if not target_language:
            raise ValueError(self._t("validation.target_language"))
        if not 0 <= temperature <= 2:
            raise ValueError(self._t("validation.temperature"))

        current = self.store.load()
        provider_title = self._selected_provider_title()
        provider = TRANSLATION_PROVIDERS[provider_title]
        extra_body = (
            provider["extra_body"]
            if provider_title != "Custom"
            else current.translation_extra_body_json
        )
        if extra_body:
            parsed = json.loads(extra_body)
            if not isinstance(parsed, dict):
                raise ValueError(self._t("validation.extra_body"))
        return replace(
            current,
            funasr_realtime_model=model,
            funasr_realtime_ws_url=url,
            source_language=source_language,
            funasr_realtime_semantic_punctuation=(
                self.semantic_punctuation.state()
                == NSControlStateValueOn
            ),
            funasr_realtime_max_sentence_silence=max_silence,
            funasr_realtime_multi_threshold=(
                self.multi_threshold.state() == NSControlStateValueOn
            ),
            funasr_interim_translate_chars=interim_chars,
            translation_enabled=(
                self.translation_enabled.state()
                == NSControlStateValueOn
            ),
            translation_provider=provider["id"],
            api_base_url=self.translation_base_url.stringValue().strip(),
            model=translation_model,
            translation_thinking=THINKING_OPTIONS[
                self.translation_thinking.indexOfSelectedItem()
            ],
            target_lang=target_language,
            translation_temperature=temperature,
            translation_extra_body_json=extra_body,
            always_on_top=(
                self.always_on_top.state() == NSControlStateValueOn
            ),
            background_opacity=(
                self.background_opacity.doubleValue() / 100
            ),
            original_font_size=self.original_font.integerValue(),
            translated_font_size=self.translated_font.integerValue(),
        )

    def testASR_(self, _sender) -> None:
        url = self.asr_url.stringValue().strip()
        try:
            api_key = self._current_credential_value(
                self.asr_key,
                self.asr_key_revealed,
            ).strip()
            if not api_key and self.asr_key_exists:
                api_key = self.store.asr_key() or ""
        except Exception as exc:
            self._set_test_result(
                self.asr_test_result,
                str(exc),
                error=True,
            )
            return
        if not api_key:
            self._set_test_result(
                self.asr_test_result,
                self._t("common.enter_api_key"),
                error=True,
            )
            return
        self.asr_test_button.setEnabled_(False)
        self._set_test_result(
            self.asr_test_result,
            self._t("common.testing"),
            error=False,
        )

        def run():
            try:
                result = test_funasr_connection(url, api_key)
                AppHelper.callAfter(
                    self._finish_asr_test,
                    result,
                    False,
                )
            except Exception as exc:
                AppHelper.callAfter(
                    self._finish_asr_test,
                    f"{type(exc).__name__}: {exc}",
                    True,
                )

        threading.Thread(target=run, daemon=True).start()

    @objc.python_method
    def _finish_asr_test(self, message: str, error: bool) -> None:
        self.asr_test_button.setEnabled_(True)
        self._set_test_result(self.asr_test_result, message, error=error)

    def testTranslation_(self, _sender) -> None:
        try:
            preferences = self._preferences_from_fields()
            api_key = self._current_credential_value(
                self.translation_key,
                self.translation_key_revealed,
            ).strip()
            if (
                not api_key
                and self.translation_key_exists[
                    self.active_translation_provider
                ]
            ):
                api_key = (
                    self.store.translation_key(
                        self.active_translation_provider
                    )
                    or ""
                )
            if not api_key:
                if is_local_url(preferences.api_base_url):
                    api_key = "dummy-key-for-local"
                else:
                    raise ValueError(
                        self._t("common.enter_api_key")
                    )
            extra_body = (
                json.loads(preferences.translation_extra_body_json)
                if preferences.translation_extra_body_json
                else None
            )
        except Exception as exc:
            self._set_test_result(
                self.translation_test_result,
                str(exc),
                error=True,
            )
            return

        self.translation_test_button.setEnabled_(False)
        self._set_test_result(
            self.translation_test_result,
            self._t("common.testing"),
            error=False,
        )

        def run():
            try:
                result = test_translation_connection(
                    base_url=preferences.api_base_url or None,
                    api_key=api_key,
                    model=preferences.model,
                    target_lang=preferences.target_lang,
                    extra_body=extra_body,
                )
                AppHelper.callAfter(
                    self._finish_translation_test,
                    result,
                    False,
                )
            except Exception as exc:
                AppHelper.callAfter(
                    self._finish_translation_test,
                    f"{type(exc).__name__}: {exc}",
                    True,
                )

        threading.Thread(target=run, daemon=True).start()

    @objc.python_method
    def _finish_translation_test(
        self,
        message: str,
        error: bool,
    ) -> None:
        self.translation_test_button.setEnabled_(True)
        self._set_test_result(
            self.translation_test_result,
            message,
            error=error,
        )

    @objc.python_method
    def _set_test_result(self, label, message: str, *, error: bool) -> None:
        label.setTextColor_(
            NSColor.systemRedColor()
            if error
            else NSColor.secondaryLabelColor()
        )
        label.setStringValue_(message)

    @objc.python_method
    def _set_status(self, message: str, *, error: bool) -> None:
        self.status_label.setTextColor_(
            NSColor.systemRedColor()
            if error
            else NSColor.secondaryLabelColor()
        )
        self.status_label.setStringValue_(message)

    def windowWillClose_(self, _notification) -> None:
        self.asr_key.setStringValue_("")
        self.asr_key_revealed.setStringValue_("")
        self.asr_key_revealed.setHidden_(True)
        self.asr_key.setHidden_(False)
        self.translation_key.setStringValue_("")
        self.translation_key_revealed.setStringValue_("")
        self.translation_key_revealed.setHidden_(True)
        self.translation_key.setHidden_(False)
        self.asr_key_original = None
        self.asr_key_exists = False
        self.asr_key_dirty = False
        self.translation_key_drafts.clear()
        self.translation_key_originals.clear()
        self.translation_key_exists.clear()
        self.translation_key_dirty.clear()
