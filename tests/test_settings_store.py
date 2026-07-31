import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ui_macos.settings_store import (
    BUNDLE_ID,
    INITIALIZED_KEY,
    INTERFACE_LANGUAGE_KEY,
    SettingsStore,
)


class FakeDefaults:
    def __init__(self):
        self.registered = {}
        self.values = {}

    def registerDefaults_(self, values):
        self.registered.update(values)

    def boolForKey_(self, key):
        return bool(self.values.get(key, self.registered.get(key, False)))

    def integerForKey_(self, key):
        return int(self.values.get(key, self.registered.get(key, 0)))

    def doubleForKey_(self, key):
        return float(self.values.get(key, self.registered.get(key, 0.0)))

    def stringForKey_(self, key):
        return self.values.get(key, self.registered.get(key))

    def setBool_forKey_(self, value, key):
        self.values[key] = bool(value)

    def setObject_forKey_(self, value, key):
        self.values[key] = value


class FakeCredentials:
    def __init__(self):
        self.values = {
            "asr.dashscope": "asr-secret",
            "translation.deepseek": "translation-secret",
        }
        self.get_calls = []
        self.exists_calls = []
        self.save_calls = []
        self.delete_calls = []

    def get(self, account):
        self.get_calls.append(account)
        return self.values.get(account)

    def exists(self, account):
        self.exists_calls.append(account)
        return account in self.values

    def save(self, account, value):
        self.save_calls.append((account, value))
        self.values[account] = value

    def delete(self, account):
        self.delete_calls.append(account)
        self.values.pop(account, None)


class SettingsStoreTests(unittest.TestCase):
    def test_packaged_app_uses_standard_user_defaults(self):
        defaults = FakeDefaults()
        with (
            patch("ui_macos.settings_store.NSBundle") as bundle_class,
            patch(
                "ui_macos.settings_store.NSUserDefaults"
            ) as defaults_class,
        ):
            bundle_class.mainBundle.return_value.bundleIdentifier.return_value = (
                BUNDLE_ID
            )
            defaults_class.standardUserDefaults.return_value = defaults

            store = SettingsStore(
                config_path=Path("/nonexistent/config.ini"),
                credentials=FakeCredentials(),
            )

        self.assertIs(store.defaults, defaults)
        defaults_class.standardUserDefaults.assert_called_once_with()
        defaults_class.alloc.assert_not_called()

    def test_source_run_uses_named_user_defaults_suite(self):
        defaults = FakeDefaults()
        with (
            patch("ui_macos.settings_store.NSBundle") as bundle_class,
            patch(
                "ui_macos.settings_store.NSUserDefaults"
            ) as defaults_class,
        ):
            bundle_class.mainBundle.return_value.bundleIdentifier.return_value = (
                "org.python.python"
            )
            defaults_class.alloc.return_value.initWithSuiteName_.return_value = (
                defaults
            )

            store = SettingsStore(
                config_path=Path("/nonexistent/config.ini"),
                credentials=FakeCredentials(),
            )

        self.assertIs(store.defaults, defaults)
        defaults_class.alloc.return_value.initWithSuiteName_.assert_called_once_with(
            BUNDLE_ID
        )
        defaults_class.standardUserDefaults.assert_not_called()

    def test_imports_existing_ini_once(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.ini"
            config_path.write_text(
                "[translation]\n"
                "enabled = false\n"
                "base_url = http://127.0.0.1:8000/v1\n"
                "model = local-model\n"
                "target_lang = Japanese\n"
                "\n[transcription]\n"
                "backend = funasr_realtime\n"
                "funasr_realtime_model = imported-asr\n"
                "\n[audio]\n"
                "sample_rate = 16000\n"
                "\n[display]\n"
                "original_font_size = 15\n"
                "background_opacity = 0.66\n",
                encoding="utf-8",
            )
            defaults = FakeDefaults()
            store = SettingsStore(
                defaults=defaults,
                config_path=config_path,
                credentials=FakeCredentials(),
            )

            preferences = store.load()
            self.assertTrue(defaults.values[INITIALIZED_KEY])
            self.assertFalse(preferences.translation_enabled)
            self.assertEqual(preferences.model, "local-model")
            self.assertEqual(preferences.target_lang, "Japanese")
            self.assertEqual(
                preferences.funasr_realtime_model,
                "imported-asr",
            )
            self.assertEqual(preferences.original_font_size, 15)
            self.assertEqual(preferences.background_opacity, 0.66)

            config_path.write_text(
                "[translation]\nmodel = changed-later\n",
                encoding="utf-8",
            )
            second = SettingsStore(
                defaults=defaults,
                config_path=config_path,
                credentials=FakeCredentials(),
            )
            self.assertEqual(second.load().model, "local-model")

    def test_pipeline_settings_use_credential_store_and_never_defaults(self):
        defaults = FakeDefaults()
        credentials = FakeCredentials()
        store = SettingsStore(
            defaults=defaults,
            config_path=Path("/nonexistent/config.ini"),
            credentials=credentials,
        )

        settings = store.pipeline_settings()

        self.assertEqual(settings.api_key, "translation-secret")
        self.assertEqual(settings.funasr_realtime_api_key, "asr-secret")
        self.assertNotIn("translation-secret", defaults.values.values())
        self.assertNotIn("asr-secret", defaults.values.values())

    def test_save_round_trip(self):
        defaults = FakeDefaults()
        store = SettingsStore(
            defaults=defaults,
            config_path=Path("/nonexistent/config.ini"),
            credentials=FakeCredentials(),
        )
        current = store.load()
        updated = replace(
            current,
            translated_font_size=21,
            translation_provider="google",
            background_opacity=0.7,
        )
        store.save(updated)

        saved = store.load()
        self.assertEqual(saved.translated_font_size, 21)
        self.assertEqual(saved.translation_provider, "google")
        self.assertEqual(saved.background_opacity, 0.7)

    def test_interface_language_defaults_to_english_and_persists(self):
        defaults = FakeDefaults()
        store = SettingsStore(
            defaults=defaults,
            config_path=Path("/nonexistent/config.ini"),
            credentials=FakeCredentials(),
        )

        self.assertEqual(store.interface_language(), "en")

        store.save_interface_language("zh")

        self.assertEqual(store.interface_language(), "zh")
        self.assertEqual(
            defaults.values[INTERFACE_LANGUAGE_KEY],
            "zh",
        )


if __name__ == "__main__":
    unittest.main()
