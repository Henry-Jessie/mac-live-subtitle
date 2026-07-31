import signal
from dataclasses import replace

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
)
from Foundation import NSLog, NSObject
from PyObjCTools import AppHelper

from core.application_controller import ApplicationState
from ui_macos.controller import NativeApplicationController
from ui_macos.settings_store import SettingsStore
from ui_macos.settings_window import SettingsWindow
from ui_macos.status_popover import StatusPopover
from ui_macos.subtitle_panel import SubtitlePanel


class ApplicationDelegate(NSObject):
    @objc.python_method
    def configure(
        self,
        *,
        settings_store=None,
        create_status_item: bool = True,
        panel_autosave_name: str | None = "MacLiveSubtitlePanel",
    ):
        self.settings_store = settings_store
        self.create_status_item = create_status_item
        self.panel_autosave_name = panel_autosave_name
        self.started = False
        return self

    def applicationDidFinishLaunching_(self, _notification) -> None:
        self.start()

    @objc.python_method
    def start(self) -> None:
        if self.started:
            return
        if self.settings_store is None:
            self.settings_store = SettingsStore()
        preferences = self.settings_store.load()
        self.subtitle_panel = SubtitlePanel(
            original_font_size=preferences.original_font_size,
            translated_font_size=preferences.translated_font_size,
            always_on_top=preferences.always_on_top,
            background_opacity=preferences.background_opacity,
            autosave_name=self.panel_autosave_name,
        )
        self.controller = NativeApplicationController(
            self.settings_store,
            self.subtitle_panel,
        )
        self.settings_window = SettingsWindow.alloc().init().configure(
            store=self.settings_store,
            saved_callback=self.settings_saved,
        )
        self.status_popover = StatusPopover.alloc().init().configure(
            controller=self.controller,
            subtitle_panel=self.subtitle_panel,
            open_settings=self.open_settings,
            quit_application=self.quit_application,
            create_status_item=self.create_status_item,
        )
        self.subtitle_panel.configure_controls(
            toggle_running=self.controller.toggle_running,
            stop=self.controller.stop,
            open_settings=self.open_settings,
            pin_changed=self.subtitle_pin_changed,
        )
        self.controller.state_changed = self.application_state_changed
        self.subtitle_panel.visibility_changed = (
            lambda _visible: self.status_popover.refresh(
                self.controller.state
            )
        )
        self.started = True
        self.subtitle_panel.show()
        NSLog("Mac Live Subtitle initialized")

    @objc.python_method
    def application_state_changed(self, state: ApplicationState) -> None:
        self.status_popover.refresh(state)
        self.subtitle_panel.refresh_controls(state)

    @objc.python_method
    def open_settings(self) -> None:
        NSApp.activateIgnoringOtherApps_(True)
        self.settings_window.show()

    @objc.python_method
    def subtitle_pin_changed(self, enabled: bool) -> None:
        preferences = replace(
            self.settings_store.load(),
            always_on_top=enabled,
        )
        self.settings_store.save(preferences)
        self.settings_window.set_always_on_top(enabled)

    @objc.python_method
    def settings_saved(self, preferences, persisted: bool) -> None:
        self.subtitle_panel.apply_display_preferences(
            original_font_size=preferences.original_font_size,
            translated_font_size=preferences.translated_font_size,
            always_on_top=preferences.always_on_top,
            background_opacity=preferences.background_opacity,
        )
        if persisted:
            self.status_popover.refresh(self.controller.state)

    @objc.python_method
    def quit_application(self) -> None:
        if self.controller.state in {
            ApplicationState.IDLE,
            ApplicationState.FAILED,
        }:
            NSApp.terminate_(None)
            return
        self.controller.stop(
            completion=lambda: NSApp.terminate_(None)
        )

    def applicationShouldHandleReopen_hasVisibleWindows_(
        self,
        _application,
        _has_visible_windows,
    ):
        self.subtitle_panel.show()
        self.status_popover.refresh(self.controller.state)
        return True

    def applicationWillTerminate_(self, _notification) -> None:
        if not self.started:
            return
        self.status_popover.close()
        self.subtitle_panel.close()


_delegate = None


def main() -> None:
    global _delegate
    application = NSApplication.sharedApplication()
    application.setActivationPolicy_(
        NSApplicationActivationPolicyAccessory
    )
    _delegate = ApplicationDelegate.alloc().init().configure()
    application.setDelegate_(_delegate)
    signal.signal(
        signal.SIGINT,
        lambda *_: AppHelper.callAfter(_delegate.quit_application),
    )
    AppHelper.runEventLoop()
