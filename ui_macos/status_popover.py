import objc
from AppKit import (
    NSFontWeightMedium,
    NSImage,
    NSImageSymbolConfiguration,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject

from core.application_controller import ApplicationState


class StatusPopover(NSObject):
    @objc.python_method
    def configure(
        self,
        *,
        controller,
        subtitle_panel,
        open_settings,
        quit_application,
        create_status_item: bool = True,
    ):
        self.controller = controller
        self.subtitle_panel = subtitle_panel
        self.open_settings = open_settings
        self.quit_application = quit_application
        self.status_item = None
        self.status_button = None

        self.menu = NSMenu.alloc().initWithTitle_("Mac Live Subtitle")
        self.menu.setAutoenablesItems_(False)
        self.menu.setDelegate_(self)

        self.subtitle_item = self._menu_item(
            "Subtitle Window",
            "showSubtitles:",
        )
        self.settings_item = self._menu_item(
            "Settings…",
            "openSettings:",
        )
        self.quit_item = self._menu_item(
            "Quit",
            "quitApplication:",
        )
        self.menu.addItem_(self.subtitle_item)
        self.menu.addItem_(self.settings_item)
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.menu.addItem_(self.quit_item)

        if create_status_item:
            self.status_item = (
                NSStatusBar.systemStatusBar()
                .statusItemWithLength_(NSVariableStatusItemLength)
            )
            self.status_button = self.status_item.button()
            self.status_button.setToolTip_("Mac Live Subtitle")
            self.status_item.setMenu_(self.menu)
        self.refresh(self.controller.state)
        return self

    @objc.python_method
    def _menu_item(
        self,
        title: str,
        action: str,
    ):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title,
            action,
            "",
        )
        item.setTarget_(self)
        return item

    @objc.python_method
    def refresh(self, state: ApplicationState) -> None:
        self._set_status_image(running=state is ApplicationState.RUNNING)

    @objc.python_method
    def _set_status_image(self, *, running: bool) -> None:
        if self.status_button is None:
            return
        symbol = "captions.bubble.fill" if running else "captions.bubble"
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            symbol,
            "Live subtitles",
        )
        if image is None:
            self.status_button.setTitle_("CC")
            return
        configuration = (
            NSImageSymbolConfiguration.configurationWithPointSize_weight_(
                16,
                NSFontWeightMedium,
            )
        )
        image = image.imageWithSymbolConfiguration_(configuration)
        image.setTemplate_(True)
        self.status_button.setTitle_("")
        self.status_button.setImage_(image)

    def menuWillOpen_(self, _menu) -> None:
        self.refresh(self.controller.state)

    def showSubtitles_(self, _sender) -> None:
        self.subtitle_panel.show()

    def openSettings_(self, _sender) -> None:
        self.open_settings()

    def quitApplication_(self, _sender) -> None:
        self.quit_application()

    @objc.python_method
    def close(self) -> None:
        if self.status_item is not None:
            self.status_item.setMenu_(None)
            NSStatusBar.systemStatusBar().removeStatusItem_(self.status_item)
            self.status_item = None
            self.status_button = None
