import unittest

from AppKit import NSApplication

from core.application_controller import ApplicationState
from ui_macos.status_popover import StatusPopover


class FakeController:
    def __init__(self):
        self.state = ApplicationState.IDLE


class FakePanel:
    def __init__(self):
        self.visible = False
        self.shows = 0

    def is_visible(self):
        return self.visible

    def show(self):
        self.visible = True
        self.shows += 1


class StatusPopoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = NSApplication.sharedApplication()

    def setUp(self):
        self.controller = FakeController()
        self.panel = FakePanel()
        self.opened = 0
        self.quit = 0
        self.popover = StatusPopover.alloc().init().configure(
            controller=self.controller,
            subtitle_panel=self.panel,
            open_settings=lambda: setattr(self, "opened", self.opened + 1),
            quit_application=lambda: setattr(self, "quit", self.quit + 1),
            create_status_item=False,
        )

    def test_menu_contains_only_settings_subtitle_and_quit_actions(self):
        items = [
            item
            for item in self.popover.menu.itemArray()
            if not item.isSeparatorItem()
        ]

        self.assertEqual(
            [item.title() for item in items],
            ["Subtitle Window", "Settings…", "Quit"],
        )
        self.assertEqual(self.popover.settings_item.keyEquivalent(), "")
        self.assertEqual(self.popover.quit_item.keyEquivalent(), "")

    def test_refresh_accepts_application_state_without_transport_controls(self):
        self.popover.refresh(ApplicationState.RUNNING)
        self.popover.refresh(ApplicationState.PAUSED)
        self.popover.refresh(ApplicationState.STARTING)
        self.assertFalse(hasattr(self.popover, "primary_button"))
        self.assertFalse(hasattr(self.popover, "stop_button"))

    def test_actions_open_windows_and_quit(self):
        self.popover.showSubtitles_(None)
        self.popover.openSettings_(None)
        self.popover.quitApplication_(None)

        self.assertTrue(self.panel.visible)
        self.assertEqual(self.panel.shows, 1)
        self.assertEqual(self.opened, 1)
        self.assertEqual(self.quit, 1)


if __name__ == "__main__":
    unittest.main()
