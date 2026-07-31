import unittest
from pathlib import Path

from AppKit import NSApplication

from tests.test_settings_store import FakeCredentials, FakeDefaults
from ui_macos.application import ApplicationDelegate
from ui_macos.settings_store import SettingsStore


class ApplicationDelegateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = NSApplication.sharedApplication()

    def setUp(self):
        store = SettingsStore(
            defaults=FakeDefaults(),
            config_path=Path("/nonexistent/mac-live-subtitle-config.ini"),
            credentials=FakeCredentials(),
        )
        self.delegate = ApplicationDelegate.alloc().init().configure(
            settings_store=store,
            create_status_item=False,
            panel_autosave_name=None,
        )
        self.delegate.start()

    def tearDown(self):
        self.delegate.status_popover.close()
        self.delegate.subtitle_panel.close()
        self.delegate.settings_window.window.close()

    def test_launch_builds_ui_and_shows_subtitle_panel(self):
        self.assertIsNotNone(self.delegate.controller)
        self.assertIsNotNone(self.delegate.subtitle_panel)
        self.assertIsNotNone(self.delegate.settings_window)
        self.assertIsNotNone(self.delegate.status_popover)
        self.assertTrue(self.delegate.subtitle_panel.is_visible())

    def test_saved_display_preferences_update_panel(self):
        preferences = self.delegate.settings_store.load()
        from dataclasses import replace

        updated = replace(
            preferences,
            original_font_size=16,
            translated_font_size=22,
            background_opacity=0.61,
        )
        self.delegate.settings_saved(updated, True)

        self.assertEqual(
            self.delegate.subtitle_panel.original_font_size,
            16,
        )
        self.assertEqual(
            self.delegate.subtitle_panel.translated_font_size,
            22,
        )
        self.assertEqual(
            self.delegate.subtitle_panel.background_opacity,
            0.61,
        )

    def test_subtitle_toolbar_pin_persists_and_syncs_settings(self):
        self.delegate.subtitle_panel.toolbar_target.togglePin_(None)

        preferences = self.delegate.settings_store.load()
        self.assertFalse(preferences.always_on_top)
        self.assertEqual(
            self.delegate.settings_window.always_on_top.state(),
            0,
        )


if __name__ == "__main__":
    unittest.main()
