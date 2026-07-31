import unittest
from pathlib import Path
from unittest.mock import call, patch

from AppKit import NSApplication, NSTextFieldRoundedBezel

from tests.test_settings_store import FakeCredentials, FakeDefaults
from ui_macos.settings_store import SettingsStore
from ui_macos.settings_window import (
    FUNASR_API_KEY_GUIDES,
    PANE_CONTENT_WIDTH,
    SAVED_KEY_PLACEHOLDER,
    SettingsWindow,
)


class FakeTextNotification:
    def __init__(self, field):
        self.field = field

    def object(self):
        return self.field


class SettingsWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = NSApplication.sharedApplication()

    def setUp(self):
        self.defaults = FakeDefaults()
        self.credentials = FakeCredentials()
        self.store = SettingsStore(
            defaults=self.defaults,
            config_path=Path("/nonexistent/mac-live-subtitle-config.ini"),
            credentials=self.credentials,
        )
        self.saved = []
        self.settings = SettingsWindow.alloc().init().configure(
            store=self.store,
            saved_callback=lambda preferences, persisted: self.saved.append(
                (preferences, persisted)
            ),
        )
        self.settings._load()

    def tearDown(self):
        self.settings.window.close()

    def test_load_and_save_native_controls(self):
        self.settings.translation_model.setStringValue_("updated-model")
        self.settings.translated_font.setIntegerValue_(22)
        self.settings.saveSettings_(None)

        preferences = self.store.load()
        self.assertEqual(preferences.model, "updated-model")
        self.assertEqual(preferences.translated_font_size, 22)
        self.assertTrue(self.saved[-1][1])

    def test_load_checks_key_presence_without_reading_secrets(self):
        self.assertEqual(self.credentials.get_calls, [])
        self.assertEqual(self.settings.asr_key.stringValue(), "")
        self.assertEqual(
            self.settings.asr_key.placeholderString(),
            SAVED_KEY_PLACEHOLDER,
        )
        self.assertEqual(
            self.settings.translation_key.placeholderString(),
            SAVED_KEY_PLACEHOLDER,
        )
        self.assertEqual(
            self.settings.asr_key_status.stringValue(),
            "Saved locally",
        )
        self.assertEqual(
            self.settings.translation_key_status.stringValue(),
            "Saved locally",
        )

    def test_saving_untouched_placeholders_does_not_write_keys(self):
        self.settings.saveSettings_(None)

        self.assertEqual(self.credentials.get_calls, [])
        self.assertEqual(self.credentials.save_calls, [])
        self.assertEqual(
            self.credentials.values["asr.dashscope"],
            "asr-secret",
        )
        self.assertEqual(
            self.credentials.values["translation.deepseek"],
            "translation-secret",
        )

    def test_eye_button_reads_and_rehides_key_on_demand(self):
        self.settings.toggleASRKeyVisibility_(None)

        self.assertEqual(
            self.credentials.get_calls,
            ["asr.dashscope"],
        )
        self.assertTrue(self.settings.asr_key.isHidden())
        self.assertFalse(self.settings.asr_key_revealed.isHidden())
        self.assertEqual(
            self.settings.asr_key_revealed.stringValue(),
            "asr-secret",
        )
        self.assertEqual(
            self.settings.asr_key_visibility.toolTip(),
            "Hide API key",
        )

        self.settings.toggleASRKeyVisibility_(None)

        self.assertFalse(self.settings.asr_key.isHidden())
        self.assertTrue(self.settings.asr_key_revealed.isHidden())
        self.assertEqual(
            self.settings.asr_key.stringValue(),
            "",
        )
        self.assertEqual(
            self.settings.asr_key.placeholderString(),
            SAVED_KEY_PLACEHOLDER,
        )
        self.assertEqual(
            self.settings.asr_key_revealed.stringValue(),
            "",
        )

    def test_clearing_a_revealed_key_removes_it_on_save(self):
        self.settings.toggleASRKeyVisibility_(None)
        self.settings.asr_key_revealed.setStringValue_("")
        self.settings.controlTextDidChange_(
            FakeTextNotification(self.settings.asr_key_revealed)
        )

        self.assertEqual(
            self.settings.asr_key_status.stringValue(),
            "Key will be removed when you save",
        )
        self.settings.saveSettings_(None)

        self.assertNotIn("asr.dashscope", self.credentials.values)
        self.assertEqual(
            self.credentials.delete_calls,
            ["asr.dashscope"],
        )
        self.assertEqual(self.settings.asr_key.placeholderString(), "")
        self.assertFalse(self.settings.asr_key_visibility.isEnabled())

    def test_provider_switch_only_checks_key_presence(self):
        self.settings.translation_provider.selectItemWithTitle_("Gemini")
        self.settings.translationProviderChanged_(None)

        self.assertEqual(self.credentials.get_calls, [])
        self.assertIn(
            "translation.google",
            self.credentials.exists_calls,
        )
        self.assertEqual(self.settings.translation_key.stringValue(), "")
        self.assertEqual(
            self.settings.translation_key.placeholderString(),
            "",
        )
        self.assertFalse(self.settings.translation_key_visibility.isEnabled())

    def test_provider_keys_remain_separate(self):
        self.settings.translation_key.setStringValue_("deepseek-updated")
        self.settings.translation_provider.selectItemWithTitle_("Gemini")
        self.settings.translationProviderChanged_(None)
        self.settings.translation_key.setStringValue_("gemini-updated")
        self.settings.saveSettings_(None)

        self.assertEqual(
            self.credentials.values["translation.deepseek"],
            "deepseek-updated",
        )
        self.assertEqual(
            self.credentials.values["translation.google"],
            "gemini-updated",
        )

    def test_display_slider_previews_without_persisting(self):
        before = self.store.load().translated_font_size
        self.settings.translated_font.setIntegerValue_(24)
        self.settings.background_opacity.setDoubleValue_(65)
        self.settings.previewDisplay_(None)

        self.assertEqual(self.store.load().translated_font_size, before)
        self.assertEqual(self.saved[-1][0].translated_font_size, 24)
        self.assertEqual(self.saved[-1][0].background_opacity, 0.65)
        self.assertEqual(
            self.settings.background_opacity_value.stringValue(),
            "65%",
        )
        self.assertFalse(self.saved[-1][1])

    def test_native_toolbar_switches_panes_and_resizes_window(self):
        item = self.settings.toolbar_items["settings.display"]
        self.settings.selectSettingsPane_(item)

        self.assertEqual(
            self.settings.current_pane_identifier,
            "settings.display",
        )
        self.assertEqual(
            self.settings.toolbar.selectedItemIdentifier(),
            "settings.display",
        )
        self.assertEqual(
            self.settings.tab_view.indexOfTabViewItem_(
                self.settings.tab_view.selectedTabViewItem()
            ),
            2,
        )
        self.assertEqual(self.settings.window.title(), "Display")
        self.assertAlmostEqual(
            self.settings.window.contentView().frame().size.height,
            self.settings._height_for_pane("settings.display"),
        )

    def test_advanced_settings_expand_and_resize_window(self):
        self.settings._select_pane(
            "settings.transcription",
            animate=False,
        )
        collapsed_height = (
            self.settings.window.contentView().frame().size.height
        )
        advanced = self.settings.advanced_views[
            "settings.transcription"
        ]
        self.assertTrue(advanced.isHidden())

        self.settings.toggleAdvanced_(
            self.settings.advanced_buttons["settings.transcription"]
        )

        self.assertFalse(advanced.isHidden())
        self.assertGreater(
            self.settings.window.contentView().frame().size.height,
            collapsed_height,
        )
        self.assertEqual(
            self.settings.advanced_buttons[
                "settings.transcription"
            ].toolTip(),
            "Hide advanced settings",
        )

    def test_custom_provider_reveals_advanced_settings(self):
        self.settings._select_pane(
            "settings.translation",
            animate=False,
        )
        advanced = self.settings.advanced_views["settings.translation"]
        self.assertTrue(advanced.isHidden())

        self.settings.translation_provider.selectItemWithTitle_("Custom")
        self.settings.translationProviderChanged_(None)

        self.assertFalse(advanced.isHidden())
        self.assertEqual(
            self.settings.translation_base_url.stringValue(),
            self.store.load().api_base_url,
        )

    def test_display_has_no_advanced_section(self):
        self.assertNotIn("settings.display", self.settings.advanced_views)
        self.assertEqual(
            self.settings.asr_test_button.title(),
            "Test Connection",
        )
        self.assertEqual(
            self.settings.translation_test_button.title(),
            "Test Connection",
        )

    def test_api_guide_buttons_open_official_pages(self):
        self.assertEqual(
            self.settings.asr_china_guide_button.title(),
            "China Guide",
        )
        self.assertEqual(
            self.settings.asr_international_guide_button.title(),
            "International Guide",
        )

        with patch(
            "ui_macos.settings_window._open_external_url"
        ) as open_url:
            self.settings.openChinaAPIKeyGuide_(None)
            self.settings.openInternationalAPIKeyGuide_(None)

        self.assertEqual(
            open_url.call_args_list,
            [
                call(FUNASR_API_KEY_GUIDES["china"]),
                call(FUNASR_API_KEY_GUIDES["international"]),
            ],
        )

    def test_translation_primary_fields_use_full_width_layout(self):
        for control in (
            self.settings.translation_provider,
            self.settings.target_language,
            self.settings.translation_key_control,
        ):
            self.assertGreaterEqual(
                control.fittingSize().width,
                PANE_CONTENT_WIDTH,
            )

    def test_interface_language_switches_immediately_and_persists(self):
        self.settings.target_language.setStringValue_("Japanese")
        self.settings.translation_provider.selectItemWithTitle_("Gemini")
        self.settings.translationProviderChanged_(None)
        self.settings.interface_language_popup.selectItemAtIndex_(1)

        self.settings.interfaceLanguageChanged_(None)

        self.assertEqual(self.settings.interface_language, "zh")
        self.assertEqual(
            self.settings.store.interface_language(),
            "zh",
        )
        self.assertEqual(self.settings.window.title(), "识别")
        self.assertEqual(self.settings.save_button.title(), "保存")
        self.assertEqual(
            self.settings.toolbar_items[
                "settings.translation"
            ].label(),
            "翻译",
        )
        self.assertEqual(
            self.settings.asr_china_guide_button.title(),
            "国内申请教程",
        )
        self.assertEqual(
            self.settings.translation_provider.itemTitleAtIndex_(2),
            "自定义",
        )
        self.assertEqual(
            self.settings.translation_provider.itemTitleAtIndex_(1),
            "Gemini",
        )
        self.assertEqual(
            self.settings.translation_thinking.itemTitleAtIndex_(0),
            "关闭",
        )
        self.assertEqual(
            self.settings.asr_key_status.stringValue(),
            "已保存在本机",
        )
        self.assertEqual(
            self.settings.target_language.stringValue(),
            "Japanese",
        )
        self.assertEqual(
            self.settings._preferences_from_fields().translation_provider,
            "google",
        )

    def test_text_inputs_use_rounded_bezels(self):
        for field in (
            self.settings.asr_key,
            self.settings.asr_key_revealed,
            self.settings.asr_model,
            self.settings.asr_url,
            self.settings.source_language,
            self.settings.max_silence,
            self.settings.interim_chars,
            self.settings.translation_key,
            self.settings.translation_key_revealed,
            self.settings.translation_base_url,
            self.settings.translation_model,
            self.settings.target_language,
            self.settings.temperature,
        ):
            self.assertEqual(
                field.bezelStyle(),
                NSTextFieldRoundedBezel,
            )

    def test_switching_panes_clears_text_input_focus(self):
        self.settings.window.makeKeyAndOrderFront_(None)
        self.assertTrue(
            self.settings.window.makeFirstResponder_(
                self.settings.source_language
            )
        )

        self.settings._select_pane(
            "settings.translation",
            animate=False,
        )

        self.assertIs(
            self.settings.window.firstResponder(),
            self.settings.window,
        )


if __name__ == "__main__":
    unittest.main()
