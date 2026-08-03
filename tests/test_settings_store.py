import unittest
from dataclasses import replace
from unittest.mock import patch

from ui_macos.settings_store import (
    BUNDLE_ID,
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

            store = SettingsStore(credentials=FakeCredentials())

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

            store = SettingsStore(credentials=FakeCredentials())

        self.assertIs(store.defaults, defaults)
        defaults_class.alloc.return_value.initWithSuiteName_.assert_called_once_with(
            BUNDLE_ID
        )
        defaults_class.standardUserDefaults.assert_not_called()

    def test_pipeline_settings_use_credential_store_and_never_defaults(self):
        defaults = FakeDefaults()
        credentials = FakeCredentials()
        store = SettingsStore(
            defaults=defaults,
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
            credentials=FakeCredentials(),
        )
        current = store.load()
        updated = replace(
            current,
            audio_capture_backend="blackhole",
            translated_font_size=21,
            translation_provider="google",
            background_opacity=0.7,
        )
        store.save(updated)

        saved = store.load()
        self.assertEqual(saved.audio_capture_backend, "blackhole")
        self.assertEqual(saved.translated_font_size, 21)
        self.assertEqual(saved.translation_provider, "google")
        self.assertEqual(saved.background_opacity, 0.7)

    def test_interface_language_defaults_to_english_and_persists(self):
        defaults = FakeDefaults()
        store = SettingsStore(
            defaults=defaults,
            credentials=FakeCredentials(),
        )

        self.assertEqual(store.interface_language(), "en")

        store.save_interface_language("zh")

        self.assertEqual(store.interface_language(), "zh")
        self.assertEqual(
            defaults.values[INTERFACE_LANGUAGE_KEY],
            "zh",
        )

    def test_audio_capture_backend_defaults_to_native(self):
        store = SettingsStore(
            defaults=FakeDefaults(),
            credentials=FakeCredentials(),
        )

        self.assertEqual(store.load().audio_capture_backend, "native")
        self.assertEqual(
            store.pipeline_settings().audio_capture_backend,
            "native",
        )

    def test_default_thinking_maps_to_omitted_runtime_setting(self):
        defaults = FakeDefaults()
        defaults.values["translation.thinking"] = "auto"
        store = SettingsStore(
            defaults=defaults,
            credentials=FakeCredentials(),
        )

        self.assertIsNone(
            store.pipeline_settings().translation_thinking
        )


if __name__ == "__main__":
    unittest.main()
