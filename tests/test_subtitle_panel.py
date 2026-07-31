import unittest
from unittest.mock import patch

from AppKit import (
    NSApplication,
    NSNormalWindowLevel,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskResizable,
)

from core.application_controller import ApplicationState
from ui_macos.subtitle_panel import SubtitlePanel


class SubtitlePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = NSApplication.sharedApplication()

    def setUp(self):
        self.panel = SubtitlePanel(autosave_name=None)

    def tearDown(self):
        self.panel.close()

    def test_rows_are_ordered_and_capped(self):
        with patch("ui_macos.subtitle_panel.AppHelper.callAfter"):
            self.panel.update_text(2, "second", "")
            self.panel.update_text(1, "first", "")
            for chunk_id in range(3, 202):
                self.panel.update_text(chunk_id, str(chunk_id), "")

        self.assertEqual(len(self.panel.ordered_ids), 200)
        self.assertEqual(self.panel.ordered_ids[0], 2)
        self.assertEqual(self.panel.ordered_ids[-1], 201)
        self.assertNotIn(1, self.panel.rows)

    def test_interim_and_final_update_one_row(self):
        with patch("ui_macos.subtitle_panel.AppHelper.callAfter"):
            self.panel.update_live_text(7, "", "growing")
            self.panel.update_text(7, "finished", "translated")

        self.assertEqual(self.panel.ordered_ids, [7])
        row = self.panel.rows[7]
        self.assertEqual(row.original, "finished")
        self.assertEqual(row.translated, "translated")

    def test_content_updates_grow_document_and_scroll_to_bottom(self):
        with patch(
            "ui_macos.subtitle_panel.AppHelper.callAfter",
            side_effect=lambda callback, *args: callback(*args),
        ):
            for chunk_id in range(20):
                self.panel.update_text(
                    chunk_id,
                    "source text " * 12,
                    "translated text " * 8,
                )

        clip = self.panel.scroll_view.contentView()
        bottom = max(
            0,
            self.panel.document_view.frame().size.height
            - clip.bounds().size.height,
        )
        self.assertGreater(bottom, 0)
        self.assertAlmostEqual(clip.bounds().origin.y, bottom)

    def test_window_is_movable_and_resizable(self):
        self.assertTrue(self.panel.window.isMovable())
        self.assertFalse(
            self.panel.window.isMovableByWindowBackground()
        )
        self.assertTrue(
            self.panel.window.styleMask()
            & NSWindowStyleMaskResizable
        )
        self.assertFalse(
            self.panel.window.styleMask()
            & NSWindowStyleMaskNonactivatingPanel
        )
        self.assertFalse(self.panel.window.becomesKeyOnlyIfNeeded())
        self.assertEqual(
            tuple(self.panel.window.contentMinSize()),
            (360.0, 140.0),
        )
        self.assertAlmostEqual(
            self.panel.window.backgroundColor().alphaComponent(),
            0.01,
        )
        self.assertFalse(self.panel.content_view.mouseDownCanMoveWindow())
        self.assertTrue(self.panel.drag_view.mouseDownCanMoveWindow())
        self.assertFalse(
            self.panel.background_view.mouseDownCanMoveWindow()
        )
        self.assertFalse(
            self.panel.document_view.mouseDownCanMoveWindow()
        )
        self.assertFalse(
            self.panel.document_view.translatesAutoresizingMaskIntoConstraints()
        )
        self.panel.window.contentView().layoutSubtreeIfNeeded()
        bounds = self.panel.content_view.bounds()
        drag_frame = self.panel.drag_view.frame()
        self.assertGreater(drag_frame.origin.x, bounds.origin.x)
        self.assertGreater(drag_frame.origin.y, bounds.origin.y)
        self.assertLess(
            drag_frame.origin.x + drag_frame.size.width,
            bounds.origin.x + bounds.size.width,
        )
        self.assertLess(
            drag_frame.origin.y + drag_frame.size.height,
            bounds.origin.y + bounds.size.height,
        )

    def test_display_preferences_update_existing_rows(self):
        with patch("ui_macos.subtitle_panel.AppHelper.callAfter"):
            self.panel.update_text(1, "source", "translation")
        self.panel.apply_display_preferences(
            original_font_size=15,
            translated_font_size=21,
            always_on_top=True,
            background_opacity=0.64,
        )

        row = self.panel.rows[1]
        self.assertEqual(row.original_font_size, 15)
        self.assertEqual(row.translated_font_size, 21)
        self.assertEqual(self.panel.background_opacity, 0.64)

    def test_toolbar_controls_follow_state_and_delegate_actions(self):
        events = []
        self.panel.configure_controls(
            toggle_running=lambda: events.append("toggle"),
            stop=lambda: events.append("stop"),
            open_settings=lambda: events.append("settings"),
            pin_changed=lambda enabled: events.append(("pin", enabled)),
        )

        self.panel.refresh_controls(ApplicationState.RUNNING)
        self.assertEqual(self.panel.primary_button.toolTip(), "Pause")
        self.assertTrue(self.panel.stop_button.isEnabled())

        self.panel.toolbar_target.primaryAction_(None)
        self.panel.toolbar_target.stopAction_(None)
        self.panel.toolbar_target.openSettings_(None)
        self.panel.toolbar_target.togglePin_(None)

        self.assertEqual(
            events,
            ["toggle", "stop", "settings", ("pin", False)],
        )
        self.assertFalse(self.panel.always_on_top)
        self.assertEqual(self.panel.window.level(), NSNormalWindowLevel)
        self.assertEqual(
            self.panel.pin_button.toolTip(),
            "Allow window behind other windows",
        )

        self.panel.refresh_controls(ApplicationState.PAUSED)
        self.assertEqual(self.panel.primary_button.toolTip(), "Resume")
        self.panel.refresh_controls(ApplicationState.STARTING)
        self.assertFalse(self.panel.primary_button.isEnabled())
        self.assertFalse(self.panel.stop_button.isEnabled())

    def test_black_background_and_white_subtitle_colors(self):
        self.assertAlmostEqual(self.panel.background_view.opacity, 0.82)

        with patch("ui_macos.subtitle_panel.AppHelper.callAfter"):
            self.panel.update_text(1, "source", "translation")
        row = self.panel.rows[1]
        self.assertAlmostEqual(
            row.source_label.textColor().alphaComponent(),
            0.72,
        )
        self.assertAlmostEqual(
            row.translation_label.textColor().alphaComponent(),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
