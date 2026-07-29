"""Mac Live Subtitle — unified floating subtitle window for macOS."""

import html
import os
import sys
import time
import signal
import configparser

from keyring.errors import KeyringError
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QScrollArea, QToolButton, QSizePolicy,
    QGraphicsDropShadowEffect, QComboBox, QLineEdit, QFormLayout,
    QPushButton, QListView, QAbstractItemView, QProxyStyle, QStyle, QStyleOptionComboBox,
    QDoubleSpinBox, QStyleOptionSpinBox, QAbstractSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint, QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen

from core.config import Config, config, is_local_url
from core.credentials import (
    ASR_DASHSCOPE_ACCOUNT,
    credential_store,
    translation_account,
)
from core.paths import resource_path

# macOS native integration
try:
    import objc
    from ctypes import c_void_p
    HAS_OBJC = True
except ImportError:
    HAS_OBJC = False


# ---------------------------------------------------------------------------
# SubtitleItem — single subtitle entry
# ---------------------------------------------------------------------------
class SubtitleItem(QFrame):
    """A single subtitle entry showing original text and translation."""

    def __init__(self, chunk_id: int, timestamp: str, original: str, translated: str = "", *, asr_only: bool = False, orig_font_size: int = 13, trans_font_size: int = 17):
        super().__init__()
        self.chunk_id = chunk_id
        self._asr_only = asr_only
        self.setStyleSheet("background: transparent;")

        orig_size = orig_font_size
        trans_size = trans_font_size

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(3)
        self.setLayout(layout)

        self.original_label = QLabel("")
        self.original_label.setTextFormat(Qt.TextFormat.RichText)
        self.original_label.setWordWrap(True)
        if asr_only:
            self.original_label.setStyleSheet(
                f"color: #1D1D1F; font-family: 'Helvetica Neue', Arial; font-size: {trans_size}px; background: transparent;"
            )
        else:
            self.original_label.setStyleSheet(
                f"color: #86868B; font-family: 'Helvetica Neue', Arial; font-size: {orig_size}px; background: transparent;"
            )
        layout.addWidget(self.original_label)

        self.translated_label = QLabel(translated or "...")
        self.translated_label.setWordWrap(True)
        self.translated_label.setStyleSheet(
            f"color: #1D1D1F; font-family: 'Helvetica Neue', Arial; font-size: {trans_size}px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(self.translated_label)
        if asr_only:
            self.translated_label.hide()

        self.update_original(original)

    def _build_original_html(self, *, timestamp: str, confirmed: str, interim: str) -> str:
        ts = html.escape(timestamp or "")
        confirmed_html = html.escape(confirmed or "")
        interim_html = html.escape(interim or "")

        base = f"<span>[{ts}]</span> " + confirmed_html
        if interim_html:
            base += (
                f"<span style=\"color: #AEAEB2; font-style: italic;\">{interim_html}</span>"
            )
        return base

    def update_original(self, text: str):
        ts = time.strftime("%H:%M:%S")
        self.original_label.setText(
            self._build_original_html(timestamp=ts, confirmed=text or "", interim="")
        )

    def update_original_parts(self, confirmed: str, interim: str):
        ts = time.strftime("%H:%M:%S")
        self.original_label.setText(
            self._build_original_html(timestamp=ts, confirmed=confirmed or "", interim=interim or "")
        )

    def update_translated(self, text: str):
        self.translated_label.setText(text)


# ---------------------------------------------------------------------------
# SubtitleDisplay — scrolling subtitle area
# ---------------------------------------------------------------------------
class SubtitleDisplay(QWidget):
    """Scrolling subtitle display area with placeholder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.setLayout(layout)

        # Banner (errors / status)
        self._banner_error_qss = (
            "QLabel {"
            "  background: rgba(255,59,48,0.10); color: #FF3B30;"
            "  border-radius: 8px; padding: 6px 10px;"
            "  font-size: 12px; font-family: 'Helvetica Neue', Arial;"
            "}"
        )
        self._banner_info_qss = (
            "QLabel {"
            "  background: rgba(0,122,255,0.10); color: #007AFF;"
            "  border-radius: 8px; padding: 6px 10px;"
            "  font-size: 12px; font-family: 'Helvetica Neue', Arial;"
            "}"
        )
        self.banner = QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet(self._banner_info_qss)
        self.banner.hide()
        layout.addWidget(self.banner)

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.timeout.connect(self.banner.hide)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #C7C7CC; border-radius: 3px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.container = QFrame()
        self.container.setStyleSheet("background: transparent;")
        self.container_layout = QVBoxLayout()
        self.container_layout.setContentsMargins(20, 10, 20, 10)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.container.setLayout(self.container_layout)

        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area)

        # Placeholder
        self.placeholder = QLabel("Press \u25B6 to begin")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet(
            "color: #AEAEB2; font-size: 15px; font-family: 'Helvetica Neue', Arial; background: transparent;"
        )
        self.container_layout.addWidget(self.placeholder)

        self.items: list[tuple[int, SubtitleItem]] = []
        self.transcript_data: dict[int, dict] = {}
        self.translation_enabled = True

        # Follow-tail scrolling: stick to the bottom on ANY content growth —
        # new items, a live line wrapping taller, translations arriving — as
        # long as the user hasn't scrolled up. Scrolling back to the bottom
        # resumes following.
        self._follow_tail = True
        vbar = self.scroll_area.verticalScrollBar()
        vbar.valueChanged.connect(self._on_scroll_value_changed)
        vbar.rangeChanged.connect(self._on_scroll_range_changed)

        # Runtime display state (used by SubtitleItem, updated by preview/config)
        self.original_font_size = config.original_font_size
        self.translated_font_size = config.translated_font_size

    def _show_banner(self, message: str, *, timeout_ms: int = 2000):
        msg = (message or "").strip()
        if not msg:
            self.banner.hide()
            return
        self.banner.setText(msg)
        self.banner.show()
        self._banner_timer.stop()
        if timeout_ms > 0:
            self._banner_timer.start(timeout_ms)

    def show_error(self, message: str, *, timeout_ms: int = 8000):
        self.banner.setStyleSheet(self._banner_error_qss)
        self._show_banner(message, timeout_ms=timeout_ms)

    def show_status(self, message: str, *, timeout_ms: int = 2000):
        self.banner.setStyleSheet(self._banner_info_qss)
        self._show_banner(message, timeout_ms=timeout_ms)

    def update_text(self, chunk_id: int, original_text: str, translated_text: str):
        """Create or update subtitle item."""
        if self.placeholder.isVisible() and original_text.strip():
            self.placeholder.hide()

        if translated_text == " ":
            translated_text = ""

        if chunk_id not in self.transcript_data:
            self.transcript_data[chunk_id] = {
                "timestamp": time.strftime("%H:%M:%S"),
                "original": original_text,
                "translated": translated_text,
            }
        else:
            if original_text:
                self.transcript_data[chunk_id]["timestamp"] = time.strftime("%H:%M:%S")
                self.transcript_data[chunk_id]["original"] = original_text
            if translated_text:
                self.transcript_data[chunk_id]["translated"] = translated_text

        existing = None
        for cid, widget in self.items:
            if cid == chunk_id:
                existing = widget
                break

        if existing:
            if original_text:
                existing.update_original(original_text)
            if translated_text:
                existing.update_translated(translated_text)
        else:
            ts = self.transcript_data[chunk_id]["timestamp"]
            new_widget = SubtitleItem(chunk_id, ts, original_text, translated_text, asr_only=not self.translation_enabled, orig_font_size=self.original_font_size, trans_font_size=self.translated_font_size)
            insert_idx = len(self.items)
            for i, (cid, _) in enumerate(self.items):
                if cid > chunk_id:
                    insert_idx = i
                    break
            self.items.insert(insert_idx, (chunk_id, new_widget))
            self.container_layout.insertWidget(insert_idx, new_widget)
            if len(self.items) > 200:
                old_chunk_id, old_widget = self.items.pop(0)
                self.container_layout.removeWidget(old_widget)
                old_widget.setParent(None)
                old_widget.deleteLater()
                self.transcript_data.pop(old_chunk_id, None)
            QTimer.singleShot(10, self._scroll_to_bottom)

    def update_live_text(self, chunk_id: int, confirmed_text: str, interim_text: str):
        """Update the live (in-progress) subtitle line with confirmed + draft parts."""
        combined = ((confirmed_text or "") + (interim_text or "")).strip()
        if self.placeholder.isVisible() and combined:
            self.placeholder.hide()

        if chunk_id not in self.transcript_data:
            self.transcript_data[chunk_id] = {
                "timestamp": time.strftime("%H:%M:%S"),
                "original": combined,
                "translated": "",
            }
        else:
            self.transcript_data[chunk_id]["timestamp"] = time.strftime("%H:%M:%S")
            self.transcript_data[chunk_id]["original"] = combined

        existing = None
        for cid, widget in self.items:
            if cid == chunk_id:
                existing = widget
                break

        if existing:
            existing.update_original_parts(confirmed_text or "", interim_text or "")
        else:
            ts = self.transcript_data[chunk_id]["timestamp"]
            new_widget = SubtitleItem(chunk_id, ts, combined, " " if self.translation_enabled else "", asr_only=not self.translation_enabled, orig_font_size=self.original_font_size, trans_font_size=self.translated_font_size)
            new_widget.update_original_parts(confirmed_text or "", interim_text or "")

            insert_idx = len(self.items)
            for i, (cid, _) in enumerate(self.items):
                if cid > chunk_id:
                    insert_idx = i
                    break
            self.items.insert(insert_idx, (chunk_id, new_widget))
            self.container_layout.insertWidget(insert_idx, new_widget)
            if len(self.items) > 200:
                old_chunk_id, old_widget = self.items.pop(0)
                self.container_layout.removeWidget(old_widget)
                old_widget.setParent(None)
                old_widget.deleteLater()
                self.transcript_data.pop(old_chunk_id, None)
            QTimer.singleShot(10, self._scroll_to_bottom)

    def _on_scroll_value_changed(self, value: int):
        vbar = self.scroll_area.verticalScrollBar()
        self._follow_tail = value >= vbar.maximum() - 30

    def _on_scroll_range_changed(self, _minimum: int, maximum: int):
        # Content height changed (new item, growing live line, translation
        # appended). Re-stick only when the user is already at the bottom.
        if self._follow_tail:
            self.scroll_area.verticalScrollBar().setValue(maximum)

    def _scroll_to_bottom(self):
        if not self._follow_tail:
            return
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def save_transcript(self) -> str | None:
        """Save transcript to file, return filename or None."""
        if not self.transcript_data:
            return None
        os.makedirs("transcripts", exist_ok=True)
        filename = f"transcripts/transcript_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        sorted_ids = sorted(self.transcript_data.keys())
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"Transcript saved at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            for cid in sorted_ids:
                d = self.transcript_data[cid]
                f.write(f"[{d['timestamp']}] (ID: {cid})\n")
                f.write(f"Original: {d['original']}\n")
                if d.get("translated"):
                    f.write(f"Translation: {d['translated']}\n")
                f.write(f"{'-' * 30}\n")
        return filename

    def clear(self):
        """Remove all subtitle items and show placeholder."""
        for _, widget in self.items:
            widget.setParent(None)
            widget.deleteLater()
        self.items.clear()
        self.transcript_data.clear()
        self._follow_tail = True
        self.placeholder.show()


class ChevronComboBox(QComboBox):
    """QComboBox with a reliably drawn chevron indicator (macOS-friendly)."""

    def paintEvent(self, event):
        super().paintEvent(event)

        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        arrow_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            opt,
            QStyle.SubControl.SC_ComboBoxArrow,
            self,
        )
        if not arrow_rect.isValid():
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(Qt.BrushStyle.NoBrush)

        color = QColor("#6E6E73") if self.isEnabled() else QColor("#AEAEB2")
        pen = QPen(color)
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        cx = arrow_rect.center().x()
        cy = arrow_rect.center().y()
        w = max(4.0, min(8.0, arrow_rect.width() - 6.0))
        h = max(3.0, min(5.0, arrow_rect.height() - 10.0))

        left = QPointF(cx - (w / 2.0), cy - (h / 2.0))
        mid = QPointF(cx, cy + (h / 2.0))
        right = QPointF(cx + (w / 2.0), cy - (h / 2.0))
        p.drawLine(left, mid)
        p.drawLine(mid, right)


class EyeToggleButton(QToolButton):
    """QToolButton that draws an eye icon (avoids emoji rendering issues)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(24, 20)
        self.setStyleSheet("QToolButton { background: transparent; border: none; padding: 0; }")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(Qt.BrushStyle.NoBrush)

        if not self.isEnabled():
            color = QColor("#AEAEB2")
        elif self.isChecked():
            color = QColor("#0A84FF")
        else:
            color = QColor("#6E6E73")

        pen = QPen(color)
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        r = QRectF(self.rect()).adjusted(5.0, 6.0, -5.0, -6.0)
        if r.width() <= 2.0 or r.height() <= 2.0:
            return

        p.drawEllipse(r)

        pupil_r = max(1.2, min(r.width(), r.height()) * 0.18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(r.center(), pupil_r, pupil_r)

        if not self.isChecked():
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(r.bottomLeft(), r.topRight())



class ChevronDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox with reliably drawn step chevrons (macOS-friendly)."""

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.buttonSymbols() != QAbstractSpinBox.ButtonSymbols.UpDownArrows:
            return

        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        up_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            opt,
            QStyle.SubControl.SC_SpinBoxUp,
            self,
        )
        down_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            opt,
            QStyle.SubControl.SC_SpinBoxDown,
            self,
        )
        if not up_rect.isValid() and not down_rect.isValid():
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(Qt.BrushStyle.NoBrush)

        base_color = QColor("#6E6E73") if self.isEnabled() else QColor("#AEAEB2")
        disabled_color = QColor("#C7C7CC")

        pen = QPen(base_color)
        pen.setWidthF(1.35)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        try:
            step_enabled = opt.stepEnabled
        except Exception:
            step_enabled = (
                QAbstractSpinBox.StepEnabledFlag.StepUpEnabled
                | QAbstractSpinBox.StepEnabledFlag.StepDownEnabled
            )
        up_enabled = bool(step_enabled & QAbstractSpinBox.StepEnabledFlag.StepUpEnabled)
        down_enabled = bool(step_enabled & QAbstractSpinBox.StepEnabledFlag.StepDownEnabled)

        def _draw_chevron(rect, direction: str, enabled: bool):
            if not rect.isValid():
                return
            cx = rect.center().x()
            cy = rect.center().y()
            w = max(4.0, min(7.0, rect.width() - 8.0))
            h = max(3.0, min(4.0, rect.height() - 6.0))
            if w <= 2.0 or h <= 2.0:
                return

            if not enabled:
                pen.setColor(disabled_color)
                p.setPen(pen)
            else:
                pen.setColor(base_color)
                p.setPen(pen)

            if direction == "up":
                left = QPointF(cx - (w / 2.0), cy + (h / 2.0))
                mid = QPointF(cx, cy - (h / 2.0))
                right = QPointF(cx + (w / 2.0), cy + (h / 2.0))
            else:
                left = QPointF(cx - (w / 2.0), cy - (h / 2.0))
                mid = QPointF(cx, cy + (h / 2.0))
                right = QPointF(cx + (w / 2.0), cy - (h / 2.0))

            p.drawLine(left, mid)
            p.drawLine(mid, right)

        _draw_chevron(up_rect, "up", up_enabled)
        _draw_chevron(down_rect, "down", down_enabled)


# ---------------------------------------------------------------------------
# SettingsPopover — popup settings panel
# ---------------------------------------------------------------------------
class SettingsPopover(QFrame):
    """macOS System Settings-style popup panel."""

    settings_saved = pyqtSignal()
    display_changed = pyqtSignal(int, int)  # (orig_font, trans_font)

    # Translation LLM presets: name -> (base_url, model, extra_body_json_or_None)
    _TRANSLATION_PROVIDERS = {
        "DeepSeek": (
            "https://api.deepseek.com/v1",
            "deepseek-v4-flash",
            None,
        ),
        "Google": (
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "gemini-3-flash-preview",
            '{"reasoning_effort": "minimal"}',
        ),
        "Custom": (
            "",
            "",
            None,
        ),
    }
    _TRANSLATION_PROVIDER_IDS = {
        "DeepSeek": "deepseek",
        "Google": "google",
        "Custom": "custom",
    }

    # ASR provider presets: name -> (model_options, backend)
    _PROVIDERS = {
        "FunASR": ([
            "fun-asr-realtime",
        ], "funasr_realtime"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings_loaded = False
        self._loading_settings = False
        self._asr_key_dirty = False
        self._migrate_legacy_asr_key = False
        self._active_translation_provider = "deepseek"
        self._translation_key_drafts: dict[str, str] = {}
        self._translation_key_dirty_accounts: set[str] = set()
        self._legacy_translation_accounts: set[str] = set()
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFixedWidth(340)
        self.setStyleSheet("SettingsPopover { background: #F2F2F7; border: none; }")
        self._setup_ui()

    # ---- UI helpers ----

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #86868B; font-size: 11px; font-weight: normal;"
            "background: transparent; padding-left: 8px;"
        )
        return lbl

    def _card(self) -> QFrame:
        """A rounded white card that holds settings rows."""
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #FFFFFF; border-radius: 10px; }"
        )
        return card

    def _row(
        self,
        label_text: str,
        widget: QWidget,
        parent_layout: QVBoxLayout,
        last: bool = False,
        hint: str | None = None,
    ):
        """Add a label-control row (with optional hint) to a card layout."""
        grid = QGridLayout()
        vpad = 10 if hint else 8
        grid.setContentsMargins(14, vpad, 14, vpad)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4 if hint else 0)
        grid.setColumnStretch(1, 1)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #1D1D1F; font-size: 13px; background: transparent;")
        lbl.setFixedWidth(70)
        grid.addWidget(lbl, 0, 0, alignment=Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(widget, 0, 1)
        if hint:
            indent = widget.property("hintIndent")
            indent = int(indent) if isinstance(indent, (int, float)) else 0
            hint_lbl = QLabel(hint)
            hint_lbl.setWordWrap(True)
            hint_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            if indent:
                hint_lbl.setContentsMargins(indent, 0, 0, 0)
            hint_lbl.setStyleSheet("color: #8E8E93; font-size: 11px; background: transparent;")
            grid.addWidget(hint_lbl, 1, 1)
        parent_layout.addLayout(grid)
        if not last:
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background: #E5E5EA; margin-left: 14px; margin-right: 14px;")
            parent_layout.addWidget(sep)
        return lbl  # return label so we can hide it if needed

    # Force non-native popup (avoids black frame + first-click-fails on macOS)
    class _ComboStyle(QProxyStyle):
        def styleHint(self, hint, option=None, widget=None, returnData=None):
            if hint == QStyle.StyleHint.SH_ComboBox_Popup:
                return 0
            return super().styleHint(hint, option, widget, returnData)

    _shared_combo_style = None

    def _combo(self, editable: bool = False) -> QComboBox:
        if SettingsPopover._shared_combo_style is None:
            SettingsPopover._shared_combo_style = SettingsPopover._ComboStyle()

        c = ChevronComboBox()
        c.setEditable(editable)
        c.setMaxVisibleItems(10)
        c.setStyle(SettingsPopover._shared_combo_style)

        c.setStyleSheet(
            "QComboBox {"
            "  background: #F2F2F7; color: #1D1D1F;"
            "  border: 1px solid rgba(60,60,67,0.16); border-radius: 8px;"
            "  padding: 4px 8px; min-height: 26px; font-size: 13px;"
            "}"
            "QComboBox:hover { background: #ECECF1; border: 1px solid rgba(60,60,67,0.24); }"
            "QComboBox::drop-down { border: none; width: 20px;"
            "  subcontrol-origin: padding; subcontrol-position: center right; }"
            "QComboBox::down-arrow { image: none; width: 0; height: 0; }"
            "QComboBox QAbstractItemView {"
            "  background: #FFFFFF; color: #1D1D1F;"
            "  border: 1px solid rgba(60,60,67,0.12); border-radius: 8px;"
            "  padding: 4px; outline: 0; font-size: 13px;"
            "}"
            "QComboBox QAbstractItemView::item {"
            "  min-height: 24px; padding: 5px 8px; border-radius: 6px;"
            "}"
            "QComboBox QAbstractItemView::item:hover { background: rgba(60,60,67,0.08); }"
            "QComboBox QAbstractItemView::item:selected { background: #0A84FF; color: #FFF; }"
            "QComboBox QLineEdit {"
            "  background: transparent; border: none; padding: 0;"
            "  color: #1D1D1F; font-size: 13px;"
            "}"
        )

        try:
            opt = QStyleOptionComboBox()
            c.initStyleOption(opt)
            edit_rect = c.style().subControlRect(
                QStyle.ComplexControl.CC_ComboBox,
                opt,
                QStyle.SubControl.SC_ComboBoxEditField,
                c,
            )
            if edit_rect.isValid():
                c.setProperty("hintIndent", edit_rect.x())
        except Exception:
            c.setProperty("hintIndent", 8)
        return c

    def _line_edit(self, placeholder: str = "") -> QLineEdit:
        le = QLineEdit()
        le.setPlaceholderText(placeholder)
        le.setProperty("hintIndent", 8)
        le.setStyleSheet(
            "QLineEdit { background: #F2F2F7; border: none; border-radius: 6px;"
            "  min-height: 26px;"
            "  padding: 4px 8px; color: #1D1D1F; font-size: 13px; }"
        )
        return le

    def _password_with_toggle(self, placeholder: str = "") -> tuple[QWidget, QLineEdit]:
        wrap = QFrame()
        wrap.setStyleSheet("QFrame { background: #F2F2F7; border: none; border-radius: 6px; }")
        wrap.setProperty("hintIndent", 8)
        lay = QHBoxLayout()
        lay.setContentsMargins(8, 5, 6, 5)
        lay.setSpacing(6)
        wrap.setLayout(lay)

        le = QLineEdit()
        le.setPlaceholderText(placeholder)
        le.setEchoMode(QLineEdit.EchoMode.Password)
        le.setStyleSheet(
            "QLineEdit { background: transparent; border: none; padding: 0;"
            "  color: #1D1D1F; font-size: 13px; }"
        )

        btn = EyeToggleButton()
        btn.setChecked(False)

        def _toggle_visibility():
            pos = le.cursorPosition()
            le.setEchoMode(
                QLineEdit.EchoMode.Normal if btn.isChecked() else QLineEdit.EchoMode.Password
            )
            le.setCursorPosition(pos)
            le.setFocus(Qt.FocusReason.OtherFocusReason)

        btn.clicked.connect(_toggle_visibility)

        lay.addWidget(le, 1)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        le._eye_toggle = btn
        return wrap, le

    def _spin(self, lo: float, hi: float, step: float, suffix: str):
        s = ChevronDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setSuffix(suffix)
        s.setProperty("hintIndent", 8)
        s.setStyleSheet(
            "QDoubleSpinBox { background: #F2F2F7; border: none; border-radius: 6px;"
            "  min-height: 26px;"
            "  padding: 4px 26px 4px 8px; color: #1D1D1F; font-size: 13px; }"
            "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {"
            "  subcontrol-origin: border; width: 18px; border: none;"
            "  background: rgba(60,60,67,0.06); border-radius: 5px;"
            "}"
            "QDoubleSpinBox::up-button { subcontrol-position: top right; margin: 2px 2px 1px 0px; }"
            "QDoubleSpinBox::down-button { subcontrol-position: bottom right; margin: 1px 2px 2px 0px; }"
            "QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: rgba(60,60,67,0.10); }"
            "QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed { background: rgba(60,60,67,0.14); }"
        )
        return s

    # ---- Build UI ----

    _TAB_NAMES = ["Transcription", "Translation", "Display"]

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(6)
        self.setLayout(layout)

        # ---- Segmented control ----
        seg_frame = QFrame()
        seg_frame.setFixedHeight(32)
        seg_frame.setStyleSheet(
            "QFrame { background: #E5E5EA; border: none; border-radius: 8px; }"
        )
        seg_bar = QHBoxLayout()
        seg_bar.setSpacing(1)
        seg_bar.setContentsMargins(2, 2, 2, 2)
        seg_frame.setLayout(seg_bar)
        self._tab_buttons: list[QPushButton] = []
        for i, name in enumerate(self._TAB_NAMES):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                "QPushButton {"
                "  border: none; border-radius: 6px;"
                "  background: transparent; color: #6E6E73; font-size: 12px; padding: 0 10px;"
                "}"
                "QPushButton:checked {"
                "  background: #007AFF; color: #FFF;"
                "}"
            )
            btn.clicked.connect(lambda _checked, idx=i: self._switch_tab(idx))
            seg_bar.addWidget(btn)
            self._tab_buttons.append(btn)
        layout.addWidget(seg_frame)

        # ---- Stacked pages ----
        from PyQt6.QtWidgets import QStackedWidget
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_transcription_page())
        self._stack.addWidget(self._build_translation_page())
        self._stack.addWidget(self._build_display_page())
        layout.addWidget(self._stack, 1)

        # ---- Save button ----
        layout.addSpacing(4)
        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(
            "QPushButton { background: #007AFF; color: #FFF; border: none;"
            "  padding: 8px; border-radius: 10px; font-size: 14px; font-weight: 500; }"
            "QPushButton:hover { background: #0066D6; }"
        )
        self.save_btn.clicked.connect(self._save_config)
        layout.addWidget(self.save_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #34C759; font-size: 11px; background: transparent;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Select first tab
        self._switch_tab(0)

    def _switch_tab(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._tab_buttons):
            btn.setChecked(i == index)

    # ---- Page builders ----

    def _build_transcription_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(6)
        page.setLayout(lay)

        # Audio source
        lay.addWidget(self._section_title("Audio"))
        audio_card = self._card()
        audio_lay = QVBoxLayout()
        audio_lay.setContentsMargins(0, 0, 0, 0)
        audio_lay.setSpacing(0)
        audio_card.setLayout(audio_lay)

        audio_source = QLabel("System Audio")
        audio_source.setStyleSheet(
            "color: #1D1D1F; font-size: 13px; background: transparent;"
        )
        self._row(
            "Source",
            audio_source,
            audio_lay,
            last=True,
            hint="Audio played by this Mac",
        )
        lay.addWidget(audio_card)

        # ASR provider
        lay.addWidget(self._section_title("Speech Recognition"))
        asr_card = self._card()
        asr_lay = QVBoxLayout()
        asr_lay.setContentsMargins(0, 0, 0, 0)
        asr_lay.setSpacing(0)
        asr_card.setLayout(asr_lay)

        self.provider_combo = self._combo()
        self.provider_combo.addItems(list(self._PROVIDERS.keys()))
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self._row("Provider", self.provider_combo, asr_lay)

        self.model_edit = self._line_edit("e.g. nova-3")
        self._row("Model", self.model_edit, asr_lay)

        api_key_wrap, self.api_key_edit = self._password_with_toggle("")
        self.api_key_edit.textEdited.connect(self._on_asr_key_edited)
        self._row(
            "API Key",
            api_key_wrap,
            asr_lay,
            hint="Stored in macOS Keychain; clear and Save to remove",
        )

        asr_test_wrap = QWidget()
        asr_test_wrap.setStyleSheet("background: transparent;")
        asr_test_lay = QHBoxLayout()
        asr_test_lay.setContentsMargins(0, 0, 0, 0)
        asr_test_lay.setSpacing(8)
        asr_test_wrap.setLayout(asr_test_lay)

        self.asr_test_btn = QPushButton("Test")
        self.asr_test_btn.setFixedWidth(50)
        self.asr_test_btn.setStyleSheet(
            "QPushButton { background: #007AFF; color: white; border: none;"
            "  border-radius: 6px; font-size: 12px; padding: 4px 0; }"
            "QPushButton:hover { background: #0066D6; }"
            "QPushButton:disabled { background: #B0B0B0; }"
        )
        self.asr_test_btn.clicked.connect(self._on_asr_test_clicked)

        self.asr_test_result = QLabel("")
        self.asr_test_result.setWordWrap(True)
        self.asr_test_result.setStyleSheet(
            "color: #8E8E93; font-size: 11px; background: transparent;"
        )

        asr_test_lay.addWidget(self.asr_test_btn, 0)
        asr_test_lay.addWidget(self.asr_test_result, 1)
        self._row("", asr_test_wrap, asr_lay, last=True)

        self._on_provider_changed(self.provider_combo.currentText())
        lay.addWidget(asr_card)

        lay.addStretch()
        return page

    def _build_translation_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(6)
        page.setLayout(lay)

        # Enable toggle
        self.trans_enabled_combo = self._combo()
        self.trans_enabled_combo.addItem("Enabled", True)
        self.trans_enabled_combo.addItem("Disabled", False)
        self.trans_enabled_combo.currentIndexChanged.connect(self._on_trans_enabled_changed)
        enable_card = self._card()
        enable_lay = QVBoxLayout()
        enable_lay.setContentsMargins(0, 0, 0, 0)
        enable_lay.setSpacing(0)
        enable_card.setLayout(enable_lay)
        self._row("Translate", self.trans_enabled_combo, enable_lay, last=True)
        lay.addWidget(enable_card)

        # Translation LLM
        lay.addWidget(self._section_title("LLM"))
        llm_card = self._card()
        llm_lay = QVBoxLayout()
        llm_lay.setContentsMargins(0, 0, 0, 0)
        llm_lay.setSpacing(0)
        llm_card.setLayout(llm_lay)

        self.trans_provider_combo = self._combo()
        self.trans_provider_combo.addItems(list(self._TRANSLATION_PROVIDERS.keys()))
        self.trans_provider_combo.currentTextChanged.connect(self._on_trans_provider_changed)
        self._row("Provider", self.trans_provider_combo, llm_lay)

        self.trans_base_url_edit = self._line_edit("https://api.openai.com/v1")
        self._row("Base URL", self.trans_base_url_edit, llm_lay)

        self.trans_model_edit = self._line_edit("e.g. deepseek-v4-flash")
        self._row("Model", self.trans_model_edit, llm_lay)

        # DeepSeek V4 thinking mode (ignored by non-DeepSeek providers when Auto)
        self.thinking_combo = self._combo()
        self.thinking_combo.addItem("Disabled", False)
        self.thinking_combo.addItem("Enabled", True)
        self.thinking_combo.addItem("Auto (omit)", None)
        self._row("Thinking", self.thinking_combo, llm_lay, hint="DeepSeek V4 thinking mode; Auto omits the parameter")

        trans_key_wrap, self.trans_api_key_edit = self._password_with_toggle("")
        self.trans_api_key_edit.textEdited.connect(self._on_translation_key_edited)
        self._row(
            "API Key",
            trans_key_wrap,
            llm_lay,
            hint="Stored per provider in macOS Keychain; clear and Save to remove",
        )

        # Test row
        test_wrap = QWidget()
        test_wrap.setStyleSheet("background: transparent;")
        test_hlay = QHBoxLayout()
        test_hlay.setContentsMargins(0, 0, 0, 0)
        test_hlay.setSpacing(8)
        test_wrap.setLayout(test_hlay)

        self.trans_test_btn = QPushButton("Test")
        self.trans_test_btn.setFixedWidth(50)
        self.trans_test_btn.setStyleSheet(
            "QPushButton { background: #007AFF; color: white; border: none;"
            "  border-radius: 6px; font-size: 12px; padding: 4px 0; }"
            "QPushButton:hover { background: #0066D6; }"
            "QPushButton:disabled { background: #B0B0B0; }"
        )
        self.trans_test_btn.clicked.connect(self._on_trans_test_clicked)

        self.trans_test_result = QLabel("")
        self.trans_test_result.setWordWrap(True)
        self.trans_test_result.setStyleSheet("color: #8E8E93; font-size: 11px; background: transparent;")

        test_hlay.addWidget(self.trans_test_btn, 0)
        test_hlay.addWidget(self.trans_test_result, 1)
        self._row("", test_wrap, llm_lay, last=True)

        self._on_trans_provider_changed(self.trans_provider_combo.currentText())
        lay.addWidget(llm_card)

        # Target language + temperature
        lay.addWidget(self._section_title("Output"))
        out_card = self._card()
        out_lay = QVBoxLayout()
        out_lay.setContentsMargins(0, 0, 0, 0)
        out_lay.setSpacing(0)
        out_card.setLayout(out_lay)

        self.target_lang_combo = self._combo()
        self.target_lang_combo.addItems(
            ["Simplified Chinese", "English", "Japanese", "French", "Spanish", "German", "Korean", "Custom..."]
        )
        self.target_lang_combo.setEditable(False)
        self.target_lang_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._target_lang_last_valid_text = self.target_lang_combo.currentText()
        self._target_lang_last_valid_index = self.target_lang_combo.currentIndex()
        self._target_lang_pre_custom_text = self._target_lang_last_valid_text
        self._target_lang_pre_custom_index = self._target_lang_last_valid_index
        self._target_lang_custom_mode = False
        self.target_lang_combo.activated.connect(self._on_target_lang_activated)
        self._row("Target", self.target_lang_combo, out_lay, hint="Language for translation output")

        self.temperature_spin = self._spin(0.0, 2.0, 0.1, "")
        self._row("Temp", self.temperature_spin, out_lay, last=True, hint="LLM sampling temperature")
        lay.addWidget(out_card)

        lay.addStretch()
        return page

    def _build_display_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(6)
        page.setLayout(lay)

        lay.addWidget(self._section_title("Font Size"))
        font_card = self._card()
        font_lay = QVBoxLayout()
        font_lay.setContentsMargins(0, 0, 0, 0)
        font_lay.setSpacing(0)
        font_card.setLayout(font_lay)

        self.original_font_spin = self._spin(10, 30, 1, " px")
        self.original_font_spin.setDecimals(0)
        self._row("Original", self.original_font_spin, font_lay, hint="Source text font size")

        self.translated_font_spin = self._spin(10, 30, 1, " px")
        self.translated_font_spin.setDecimals(0)
        self._row("Translated", self.translated_font_spin, font_lay, last=True, hint="Translation font size")
        lay.addWidget(font_card)

        # Live preview
        for spin in (self.original_font_spin, self.translated_font_spin):
            spin.valueChanged.connect(self._emit_display_changed)

        lay.addStretch()
        return page

    def _emit_display_changed(self):
        self.display_changed.emit(
            int(self.original_font_spin.value()),
            int(self.translated_font_spin.value()),
        )

    @staticmethod
    def _reset_secret_visibility(field: QLineEdit) -> None:
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field._eye_toggle.setChecked(False)

    def _set_secret_text(self, field: QLineEdit, value: str) -> None:
        field.setText(value)
        self._reset_secret_visibility(field)

    def _set_status_error(self, message: str) -> None:
        self.status_label.setStyleSheet(
            "color: #FF3B30; font-size: 11px; background: transparent;"
        )
        self.status_label.setText(message)

    def _read_credential(self, account: str) -> str | None:
        try:
            return credential_store.get(account)
        except KeyringError as exc:
            self._set_status_error(f"Keychain: {exc}")
            return None

    def _translation_provider_id(self, provider_name: str | None = None) -> str:
        name = provider_name or self.trans_provider_combo.currentText()
        return self._TRANSLATION_PROVIDER_IDS[name]

    def _on_asr_key_edited(self, _text: str) -> None:
        self._asr_key_dirty = True

    def _on_translation_key_edited(self, text: str) -> None:
        provider_id = self._translation_provider_id()
        self._translation_key_drafts[provider_id] = text
        self._translation_key_dirty_accounts.add(provider_id)

    def _on_provider_changed(self, provider_name: str):
        """Auto-fill the model when the provider changes."""
        preset = self._PROVIDERS.get(provider_name)
        if not preset:
            return
        models, _backend = preset

        if models:
            self.model_edit.setText(models[0])
        else:
            self.model_edit.setText("")
        self.api_key_edit.setPlaceholderText("Enter API key")

    def _on_trans_enabled_changed(self, _index: int):
        """Enable/disable translation-specific fields based on enabled state."""
        enabled = self.trans_enabled_combo.currentData()
        for w in (self.target_lang_combo, self.temperature_spin, self.thinking_combo):
            w.setEnabled(bool(enabled))

    def _on_trans_provider_changed(self, preset_name: str):
        """Auto-fill translation LLM fields when provider changes."""
        preset = self._TRANSLATION_PROVIDERS.get(preset_name)
        if not preset:
            return
        base_url, model, _extra_body = preset

        # Custom: keep current field values.
        if preset_name != "Custom":
            self.trans_base_url_edit.setText(base_url)
            self.trans_model_edit.setText(model)

        self.trans_api_key_edit.setPlaceholderText("Enter API key")

        if self._settings_loaded and not self._loading_settings:
            provider_id = self._translation_provider_id(preset_name)
            self._active_translation_provider = provider_id
            if provider_id not in self._translation_key_drafts:
                stored = self._read_credential(translation_account(provider_id))
                self._translation_key_drafts[provider_id] = stored or ""
            self._set_secret_text(
                self.trans_api_key_edit,
                self._translation_key_drafts[provider_id],
            )

    def _set_target_lang_custom_mode(self, enabled: bool, prefill: str | None = None, focus: bool = True):
        if enabled:
            self._target_lang_custom_mode = True
            if not self.target_lang_combo.isEditable():
                self.target_lang_combo.setEditable(True)
                self.target_lang_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

            le = self.target_lang_combo.lineEdit()
            if le:
                le.setPlaceholderText("Type language name")
                if getattr(self, "_target_lang_line_edit", None) is not le:
                    try:
                        le.editingFinished.disconnect(self._on_target_lang_editing_finished)
                    except Exception:
                        pass
                    le.editingFinished.connect(self._on_target_lang_editing_finished)
                    self._target_lang_line_edit = le

            self.target_lang_combo.setEditText(prefill or "")
            if focus and le:
                le.selectAll()
                le.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self._target_lang_custom_mode = False
            if self.target_lang_combo.isEditable():
                self.target_lang_combo.setEditable(False)
            self._target_lang_line_edit = None

    def _on_target_lang_activated(self, index: int):
        text = self.target_lang_combo.itemText(index)
        if text == "Custom...":
            self._target_lang_pre_custom_text = self._target_lang_last_valid_text
            self._target_lang_pre_custom_index = self._target_lang_last_valid_index
            self._set_target_lang_custom_mode(True)
            return

        self._set_target_lang_custom_mode(False)
        self._target_lang_last_valid_text = text
        self._target_lang_last_valid_index = index

    def _on_target_lang_editing_finished(self):
        if not self._target_lang_custom_mode or not self.target_lang_combo.isEditable():
            return

        value = (self.target_lang_combo.currentText() or "").strip()
        if value and value != "Custom...":
            self._target_lang_last_valid_text = value
            self._target_lang_last_valid_index = -1
            return

        # Empty / invalid: revert to the last valid selection.
        if self._target_lang_pre_custom_index is not None and self._target_lang_pre_custom_index >= 0:
            self._set_target_lang_custom_mode(False)
            self.target_lang_combo.setCurrentIndex(self._target_lang_pre_custom_index)
            self._target_lang_last_valid_text = self.target_lang_combo.currentText()
            self._target_lang_last_valid_index = self.target_lang_combo.currentIndex()
        else:
            fallback = (self._target_lang_pre_custom_text or "Simplified Chinese").strip()
            self._set_target_lang_custom_mode(True, prefill=fallback, focus=False)
            self._target_lang_last_valid_text = fallback
            self._target_lang_last_valid_index = -1

    def load_from_config(self, cfg: Config):
        """Populate fields from current config."""
        self._settings_loaded = False
        self._loading_settings = True
        self.status_label.setStyleSheet(
            "color: #34C759; font-size: 11px; background: transparent;"
        )
        self.status_label.setText("")

        # Detect provider from backend (FunASR is currently the only backend)
        self.provider_combo.setCurrentText("FunASR")
        self.model_edit.setText(cfg.funasr_realtime_model or "fun-asr-realtime")

        # API key: show the Keychain value as bullets. A legacy config.ini
        # value is shown once and moves to Keychain on Save.
        stored_asr_key = self._read_credential(ASR_DASHSCOPE_ACCOUNT)
        asr_key = stored_asr_key or cfg.legacy_funasr_realtime_api_key
        self._set_secret_text(self.api_key_edit, asr_key)
        self._asr_key_dirty = False
        self._migrate_legacy_asr_key = bool(cfg.legacy_funasr_realtime_api_key)

        # Translation enabled
        en_idx = self.trans_enabled_combo.findData(cfg.translation_enabled)
        if en_idx >= 0:
            self.trans_enabled_combo.setCurrentIndex(en_idx)
        self._on_trans_enabled_changed(0)

        # Translation LLM
        matched_preset = next(
            (
                name
                for name, provider_id in self._TRANSLATION_PROVIDER_IDS.items()
                if provider_id == cfg.translation_provider
            ),
            "Custom",
        )
        self.trans_provider_combo.setCurrentText(matched_preset)
        if matched_preset == "Custom":
            self.trans_base_url_edit.setText(cfg.api_base_url or "")
        self.trans_model_edit.setText(cfg.model or "")

        provider_id = self._translation_provider_id(matched_preset)
        stored_translation_key = self._read_credential(
            translation_account(provider_id)
        )
        translation_key = (
            stored_translation_key or cfg.legacy_translation_api_key
        )
        self._translation_key_drafts = {provider_id: translation_key}
        self._translation_key_dirty_accounts.clear()
        self._legacy_translation_accounts = (
            {provider_id} if cfg.legacy_translation_api_key else set()
        )
        self._active_translation_provider = provider_id
        self._set_secret_text(self.trans_api_key_edit, translation_key)

        # Subtitle settings
        target = (cfg.target_lang or "").strip()
        if target == "Chinese":
            target = "Simplified Chinese"
        if not target or target == "Custom...":
            target = "Simplified Chinese"

        idx = self.target_lang_combo.findText(target)
        if idx >= 0 and target != "Custom...":
            self._set_target_lang_custom_mode(False)
            self.target_lang_combo.setCurrentIndex(idx)
            self._target_lang_last_valid_text = self.target_lang_combo.currentText()
            self._target_lang_last_valid_index = self.target_lang_combo.currentIndex()
        else:
            custom_idx = self.target_lang_combo.findText("Custom...")
            if custom_idx >= 0:
                self.target_lang_combo.setCurrentIndex(custom_idx)
            self._set_target_lang_custom_mode(True, prefill=target, focus=False)
            self._target_lang_last_valid_text = target
            self._target_lang_last_valid_index = -1
        self._target_lang_pre_custom_text = self._target_lang_last_valid_text
        self._target_lang_pre_custom_index = self._target_lang_last_valid_index

        # Temperature
        self.temperature_spin.setValue(cfg.translation_temperature)

        # Thinking mode (DeepSeek V4): True/False/None -> combo index
        t_idx = self.thinking_combo.findData(cfg.translation_thinking)
        if t_idx >= 0:
            self.thinking_combo.setCurrentIndex(t_idx)

        # Display settings
        self.original_font_spin.setValue(cfg.original_font_size)
        self.translated_font_spin.setValue(cfg.translated_font_size)
        self._loading_settings = False
        self._settings_loaded = True

    # ---- API tests ----

    def _on_asr_test_clicked(self):
        api_key = (self.api_key_edit.text() or "").strip()
        if not api_key:
            self.asr_test_result.setStyleSheet(
                "color: #FF3B30; font-size: 11px; background: transparent;"
            )
            self.asr_test_result.setText("API key is not configured. Enter it above.")
            return

        self.asr_test_btn.setEnabled(False)
        self.asr_test_result.setStyleSheet(
            "color: #8E8E93; font-size: 11px; background: transparent;"
        )
        self.asr_test_result.setText("Testing…")

        self._asr_test_worker = FunASRKeyTestWorker(
            url=config.funasr_realtime_ws_url,
            api_key=api_key,
            parent=self,
        )
        self._asr_test_worker.ok.connect(self._on_asr_test_ok)
        self._asr_test_worker.err.connect(self._on_asr_test_err)
        self._asr_test_worker.finished.connect(
            lambda: self.asr_test_btn.setEnabled(True)
        )
        self._asr_test_worker.finished.connect(self._asr_test_worker.deleteLater)
        self._asr_test_worker.start()

    def _on_asr_test_ok(self, message: str):
        self.asr_test_result.setStyleSheet(
            "color: #34C759; font-size: 11px; background: transparent;"
        )
        self.asr_test_result.setText(message)

    def _on_asr_test_err(self, message: str):
        self.asr_test_result.setStyleSheet(
            "color: #FF3B30; font-size: 11px; background: transparent;"
        )
        self.asr_test_result.setText(message)

    def _resolve_translation_api_key_from_ui(self) -> str:
        key_input = (self.trans_api_key_edit.text() or "").strip()
        if key_input:
            return key_input
        base_url = (self.trans_base_url_edit.text() or "").strip()
        if is_local_url(base_url):
            return "dummy-key-for-local"
        raise ValueError("API key is not configured. Enter it above.")

    def _on_trans_test_clicked(self):
        try:
            base_url = (self.trans_base_url_edit.text() or "").strip() or None
            model = (self.trans_model_edit.text() or "").strip()
            if not model:
                raise ValueError("Model is required")
            api_key = self._resolve_translation_api_key_from_ui()
            target_lang = (self.target_lang_combo.currentText() or "").strip()
            if not target_lang or target_lang == "Custom...":
                target_lang = (getattr(self, "_target_lang_last_valid_text", "") or "Simplified Chinese").strip()
        except Exception as e:
            self.trans_test_result.setStyleSheet("color: #FF3B30; font-size: 11px; background: transparent;")
            self.trans_test_result.setText(str(e))
            return

        self.trans_test_btn.setEnabled(False)
        self.trans_test_result.setStyleSheet("color: #8E8E93; font-size: 11px; background: transparent;")
        self.trans_test_result.setText("Testing…")

        # Resolve extra_body from current provider preset
        extra_body = None
        preset = self._TRANSLATION_PROVIDERS.get(self.trans_provider_combo.currentText())
        if preset and preset[2]:
            try:
                import json
                extra_body = json.loads(preset[2])
            except Exception:
                pass

        self._trans_test_worker = TranslationTestWorker(
            base_url=base_url, api_key=api_key, model=model,
            target_lang=target_lang, extra_body=extra_body, parent=self,
        )
        self._trans_test_worker.ok.connect(self._on_trans_test_ok)
        self._trans_test_worker.err.connect(self._on_trans_test_err)
        self._trans_test_worker.finished.connect(
            lambda: self.trans_test_btn.setEnabled(True)
        )
        self._trans_test_worker.finished.connect(self._trans_test_worker.deleteLater)
        self._trans_test_worker.start()

    def _on_trans_test_ok(self, translated: str):
        self.trans_test_result.setStyleSheet("color: #34C759; font-size: 11px; background: transparent;")
        self.trans_test_result.setText(translated)

    def _on_trans_test_err(self, message: str):
        self.trans_test_result.setStyleSheet("color: #FF3B30; font-size: 11px; background: transparent;")
        self.trans_test_result.setText(message)

    def _save_config(self):
        """Write ordinary settings to config.ini and secrets to Keychain."""
        cp = configparser.ConfigParser()
        config_path = config.config_path
        cp.read(config_path)

        for section in ("translation", "transcription", "audio"):
            if not cp.has_section(section):
                cp.add_section(section)

        # Remove the legacy BlackHole/sounddevice selector.
        if cp.has_option("audio", "device_index"):
            cp.remove_option("audio", "device_index")

        # Provider / model / key
        provider = self.provider_combo.currentText()
        preset = self._PROVIDERS.get(
            provider,
            (["fun-asr-realtime"], "funasr_realtime"),
        )
        backend = preset[1]

        active_translation_provider = self._translation_provider_id()
        self._translation_key_drafts[active_translation_provider] = (
            self.trans_api_key_edit.text()
        )

        try:
            if self._asr_key_dirty or self._migrate_legacy_asr_key:
                asr_key = self.api_key_edit.text().strip()
                if asr_key:
                    credential_store.save(ASR_DASHSCOPE_ACCOUNT, asr_key)
                else:
                    credential_store.delete(ASR_DASHSCOPE_ACCOUNT)

            accounts_to_save = (
                self._translation_key_dirty_accounts
                | self._legacy_translation_accounts
            )
            for provider_id in accounts_to_save:
                account = translation_account(provider_id)
                key_value = self._translation_key_drafts[provider_id].strip()
                if key_value:
                    credential_store.save(account, key_value)
                else:
                    credential_store.delete(account)
        except KeyringError as exc:
            self._set_status_error(f"Keychain: {exc}")
            return

        cp.set("transcription", "backend", backend)

        if backend == "funasr_realtime":
            cp.set(
                "transcription",
                "funasr_realtime_model",
                self.model_edit.text().strip() or "fun-asr-realtime",
            )

            # Secrets live in Keychain.
            for opt in ("funasr_realtime_api_key", "funasr_realtime_api_key_env"):
                if cp.has_option("transcription", opt):
                    cp.remove_option("transcription", opt)

        # Translation enabled
        cp.set("translation", "enabled", "true" if self.trans_enabled_combo.currentData() else "false")
        # Remove legacy fields
        for legacy in ("mode", "use_llm_segmenter", "segmenter"):
            if cp.has_option("translation", legacy):
                cp.remove_option("translation", legacy)

        # Translation LLM
        trans_provider_name = self.trans_provider_combo.currentText()
        trans_provider = self._TRANSLATION_PROVIDERS.get(trans_provider_name)
        cp.set("translation", "provider", active_translation_provider)

        base_url = self.trans_base_url_edit.text().strip()
        trans_model = self.trans_model_edit.text().strip()
        if base_url:
            cp.set("translation", "base_url", base_url)
        elif cp.has_option("translation", "base_url"):
            cp.remove_option("translation", "base_url")
        if trans_model:
            cp.set("translation", "model", trans_model)

        # Write provider-specific request options.
        if trans_provider:
            _, _, extra_body_json = trans_provider
            if trans_provider_name != "Custom":
                if extra_body_json:
                    cp.set("translation", "extra_body", extra_body_json)
                else:
                    # Provider explicitly has no extra_body — clear it
                    if cp.has_option("translation", "extra_body"):
                        cp.remove_option("translation", "extra_body")

        if cp.has_option("translation", "api_key"):
            cp.remove_option("translation", "api_key")
        if cp.has_option("translation", "api_key_env"):
            cp.remove_option("translation", "api_key_env")

        # Target language
        target_lang = (self.target_lang_combo.currentText() or "").strip()
        if not target_lang or target_lang == "Custom...":
            target_lang = (getattr(self, "_target_lang_last_valid_text", "") or "Simplified Chinese").strip()
        cp.set("translation", "target_lang", target_lang)

        # Temperature
        cp.set("translation", "temperature", str(self.temperature_spin.value()))

        # Thinking mode (DeepSeek V4): True/False/None -> true/false/auto
        thinking_val = self.thinking_combo.currentData()
        cp.set("translation", "thinking", {True: "true", False: "false", None: "auto"}[thinking_val])

        # Display settings
        if not cp.has_section("display"):
            cp.add_section("display")
        cp.set("display", "original_font_size", str(int(self.original_font_spin.value())))
        cp.set("display", "translated_font_size", str(int(self.translated_font_spin.value())))

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with config_path.open("w", encoding="utf-8") as f:
                cp.write(f)
            config_path.chmod(0o600)
        except OSError as exc:
            self._set_status_error(f"Cannot save settings: {exc}")
            return

        self._asr_key_dirty = False
        self._migrate_legacy_asr_key = False
        self._translation_key_dirty_accounts.clear()
        self._legacy_translation_accounts.clear()
        self.status_label.setStyleSheet(
            "color: #34C759; font-size: 11px; background: transparent;"
        )
        self.status_label.setText("Saved! Restart to apply ASR/translation changes.")
        QTimer.singleShot(3000, lambda: self.status_label.setText(""))
        self.settings_saved.emit()

    def show_relative_to(self, widget: QWidget):
        """Position popover below the given widget, right-aligned."""
        pos = widget.mapToGlobal(QPoint(widget.width(), widget.height()))
        x = pos.x() - self.width()
        y = pos.y() + 4
        self.move(x, y)
        self.show()
        self._apply_rounded_corners()

    def hideEvent(self, event):
        self._settings_loaded = False
        self._set_secret_text(self.api_key_edit, "")
        self._set_secret_text(self.trans_api_key_edit, "")
        self._asr_key_dirty = False
        self._migrate_legacy_asr_key = False
        self._translation_key_drafts.clear()
        self._translation_key_dirty_accounts.clear()
        self._legacy_translation_accounts.clear()
        super().hideEvent(event)

    def _apply_rounded_corners(self):
        """Use PyObjC to round the native popup window corners."""
        if not HAS_OBJC:
            return
        try:
            nv = objc.objc_object(c_void_p=c_void_p(int(self.winId())))
            nw = nv.window()
            root_view = nw.contentView().superview()
            root_view.setWantsLayer_(True)
            root_view.layer().setCornerRadius_(12.0)
            root_view.layer().setMasksToBounds_(True)
            nw.setHasShadow_(True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# StartupWorker — background Pipeline init
# ---------------------------------------------------------------------------
class StartupWorker(QThread):
    """Initialize Pipeline on a background thread (model loading can be slow)."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self):
        try:
            from core.pipeline import Pipeline
            pipeline = Pipeline()
            self.succeeded.emit(pipeline)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            print(f"[StartupWorker] Error: {message}")
            import traceback
            traceback.print_exc()
            self.failed.emit(message)


# ---------------------------------------------------------------------------
# FunASRKeyTestWorker — one-shot authenticated WebSocket handshake
# ---------------------------------------------------------------------------
class FunASRKeyTestWorker(QThread):
    """Check a FunASR API key without starting capture or sending audio."""

    ok = pyqtSignal(str)
    err = pyqtSignal(str)

    def __init__(self, *, url, api_key, parent=None):
        super().__init__(parent)
        self.url = url
        self.api_key = api_key

    def run(self):
        import websocket

        connection = None
        try:
            connection = websocket.create_connection(
                self.url,
                header=[f"Authorization: Bearer {self.api_key}"],
                timeout=10,
            )
            self.ok.emit("API key accepted")
        except websocket.WebSocketBadStatusException as exc:
            if exc.status_code == 401:
                self.err.emit(
                    "Invalid API key (401). Check the key and endpoint region."
                )
            else:
                self.err.emit(f"WebSocket handshake failed ({exc.status_code}).")
        except Exception as exc:
            self.err.emit(f"{type(exc).__name__}: {exc}"[:300])
        finally:
            if connection is not None:
                connection.close()


# ---------------------------------------------------------------------------
# TranslationTestWorker — one-shot translation test
# ---------------------------------------------------------------------------
class TranslationTestWorker(QThread):
    """Send a single test translation request on a background thread."""

    ok = pyqtSignal(str)   # translated text
    err = pyqtSignal(str)  # error message

    def __init__(self, *, base_url, api_key, model, target_lang, extra_body=None, parent=None):
        super().__init__(parent)
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.target_lang = target_lang
        self.extra_body = extra_body if isinstance(extra_body, dict) else None

    def run(self):
        try:
            import re
            import httpx
            from openai import OpenAI

            from core.config import is_local_url
            http_client = httpx.Client(verify=not is_local_url(self.base_url))
            try:
                client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    http_client=http_client,
                )
                create_kwargs = dict(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": f"Translate the user's text to {self.target_lang}. Reply with translation only."},
                        {"role": "user", "content": "Hello. This is a translation test."},
                    ],
                    temperature=0,
                    max_tokens=80,
                    timeout=10.0,
                )
                if self.extra_body:
                    create_kwargs["extra_body"] = self.extra_body
                resp = client.chat.completions.create(**create_kwargs)
                text = (resp.choices[0].message.content or "").strip()
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
                if not text:
                    raise RuntimeError("Empty response")
                self.ok.emit(text)
            finally:
                http_client.close()
        except Exception as e:
            self.err.emit(f"{type(e).__name__}: {e}"[:400])


# ---------------------------------------------------------------------------
# PinButton — custom-painted pushpin toggle
# ---------------------------------------------------------------------------
class PinButton(QToolButton):
    """Pushpin toggle button drawn with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(32, 30)
        self._hovered = False

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        checked = self.isChecked()

        # Rounded-rect background
        if checked:
            bg = QColor(0, 122, 255, 51) if self._hovered else QColor(0, 122, 255, 30)
        else:
            bg = QColor(209, 209, 214) if self._hovered else QColor(229, 229, 234)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(self.rect(), 6, 6)

        color = QColor("#007AFF") if checked else QColor("#8E8E93")
        cx = self.width() / 2
        cy = self.height() / 2

        # Head: small filled circle
        head_cy = cy - 6
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(cx, head_cy), 2.2, 2.2)

        # Body: filled trapezoid widening downward
        body = QPainterPath()
        body_top = head_cy + 2.2
        body_bot = cy + 1.5
        body.moveTo(cx - 1.8, body_top)
        body.lineTo(cx + 1.8, body_top)
        body.lineTo(cx + 4.5, body_bot)
        body.lineTo(cx - 4.5, body_bot)
        body.closeSubpath()
        p.drawPath(body)

        # Needle: thin line from body bottom
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, body_bot), QPointF(cx, cy + 7.5))

        p.end()


# ---------------------------------------------------------------------------
# SubtitleWindow — the unified main window
# ---------------------------------------------------------------------------
class SubtitleWindow(QMainWindow):
    """Mac Live Subtitle main window with clean macOS-native appearance."""

    def __init__(self):
        super().__init__()
        self.pipeline = None
        self.startup_worker = None
        self.is_running = False
        self._paused = False  # True when paused (display preserved)
        self.is_pinned = config.always_on_top
        self._popover: SettingsPopover | None = None
        self._last_pipeline_error = ""

        self._setup_window()
        self._setup_central()

    # ---- Window setup ----

    def _setup_window(self):
        self.setWindowTitle("Mac Live Subtitle")

        screen = QApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.5)
        h = int(screen.height() * 0.2)
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + screen.height() - h - 60
        self.setGeometry(x, y, w, h)
        self.setMinimumSize(300, 120)

        if self.is_pinned:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        # Light background matching macOS standard window
        self.setStyleSheet("QMainWindow { background-color: #FFFFFF; }")

    def _setup_central(self):
        """Build central widget: button bar on top, subtitle area below."""
        central = QWidget()
        central.setStyleSheet("background: #FFFFFF;")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        central.setLayout(layout)

        # ---- Button bar ----
        btn_bar = QWidget()
        btn_bar.setStyleSheet("background: transparent;")
        btn_bar.setFixedHeight(34)
        bar_layout = QHBoxLayout()
        bar_layout.setContentsMargins(12, 4, 12, 4)
        bar_layout.setSpacing(6)
        btn_bar.setLayout(bar_layout)

        bar_layout.addStretch()

        # Play / Pause button
        self.play_btn = QToolButton()
        self.play_btn.setFixedSize(32, 30)
        self.play_btn.clicked.connect(self._on_play_clicked)
        bar_layout.addWidget(self.play_btn)

        # Stop button
        self.stop_btn = QToolButton()
        self.stop_btn.setText("\u25A0")  # filled square
        self.stop_btn.setFixedSize(32, 30)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        bar_layout.addWidget(self.stop_btn)

        self._style_transport_buttons(state="idle")

        # Settings button (gear)
        self.settings_btn = QToolButton()
        self.settings_btn.setText("\u2699\uFE0E")
        self.settings_btn.setFixedSize(32, 30)
        self.settings_btn.clicked.connect(self._on_settings_clicked)
        self.settings_btn.setStyleSheet(
            "QToolButton { background: #E5E5EA; border-radius: 6px;"
            "  color: #3A3A3C; font-size: 23px; border: none; }"
            "QToolButton:hover { background: #D1D1D6; }"
        )
        bar_layout.addWidget(self.settings_btn)

        # Pin button
        self.pin_btn = PinButton()
        self.pin_btn.setChecked(self.is_pinned)
        self.pin_btn.clicked.connect(self._on_pin_clicked)
        bar_layout.addWidget(self.pin_btn)

        layout.addWidget(btn_bar)

        # ---- Subtitle display ----
        self.subtitle_display = SubtitleDisplay()
        layout.addWidget(self.subtitle_display)

        self.setCentralWidget(central)

    # ---- macOS native ----

    def _apply_all_spaces(self):
        """Make window visible on all macOS Spaces/Desktops."""
        if not HAS_OBJC:
            return
        try:
            from AppKit import (
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
            )
            win_id = int(self.winId())
            ns_view = objc.objc_object(c_void_p=c_void_p(win_id))
            ns_window = ns_view.window()
            ns_window.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
            )
        except Exception as e:
            print(f"[SubtitleWindow] All-spaces error: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, self._apply_all_spaces)

    # ---- Button handlers ----

    def _on_play_clicked(self):
        if self.is_running:
            # Pause: soft-pause when supported, otherwise stop pipeline.
            if self.pipeline and getattr(self.pipeline, "supports_soft_pause", False):
                try:
                    self.pipeline.pause()
                except Exception:
                    self._kill_pipeline()
            else:
                self._kill_pipeline()
            self.is_running = False
            self._paused = True
            self._style_transport_buttons(state="paused")
            return

        # Resume from soft-pause without reinitializing the pipeline.
        if self._paused and self.pipeline and getattr(self.pipeline, "supports_soft_pause", False):
            try:
                self.pipeline.resume()
                self.is_running = True
                self._paused = False
                self._style_transport_buttons(state="running")
                return
            except Exception:
                self._kill_pipeline()

        self._start_pipeline()

    def _on_stop_clicked(self):
        # Full stop: kill pipeline + clear display
        self._kill_pipeline()
        self.is_running = False
        self._paused = False
        self.subtitle_display.clear()
        self._style_transport_buttons(state="idle")

    def _start_pipeline(self):
        self.play_btn.setEnabled(False)
        self._style_transport_buttons(state="loading")
        self.subtitle_display.show_status("Starting…", timeout_ms=0)

        # Only clear display on fresh start, not on resume from pause
        if not self._paused:
            self.subtitle_display.clear()
        self._paused = False

        self.startup_worker = StartupWorker()
        self.startup_worker.succeeded.connect(self._on_pipeline_ready)
        self.startup_worker.failed.connect(self._on_pipeline_init_failed)
        self.startup_worker.start()

    def _on_pipeline_ready(self, pipeline):
        self.pipeline = pipeline
        self._last_pipeline_error = ""
        self.subtitle_display.translation_enabled = getattr(pipeline, "translation_enabled", True)
        self.subtitle_display.show_status("Starting…", timeout_ms=0)
        self.pipeline.signals.update_text.connect(
            lambda *args, p=pipeline: self._on_pipeline_update_text(p, *args)
        )
        try:
            self.pipeline.signals.update_live_text.connect(
                lambda *args, p=pipeline: self._on_pipeline_update_live_text(p, *args)
            )
        except Exception:
            pass
        try:
            self.pipeline.signals.error.connect(lambda msg, p=pipeline: self._on_pipeline_error(p, msg))
            self.pipeline.signals.status.connect(
                lambda msg, timeout_ms, p=pipeline: self._on_pipeline_status(p, msg, timeout_ms)
            )
            self.pipeline.signals.stopped.connect(lambda p=pipeline: self._on_pipeline_stopped(p))
        except Exception:
            pass
        self.pipeline.start()

        self.is_running = True
        self.play_btn.setEnabled(True)
        self._style_transport_buttons(state="running")
        if not getattr(self.pipeline, "supports_soft_pause", False):
            self.subtitle_display.show_status("Started", timeout_ms=1200)

    def _on_pipeline_init_failed(self, message: str):
        self.play_btn.setEnabled(True)
        self._style_transport_buttons(state="idle")
        self.subtitle_display.show_error(
            f"Initialization failed: {message}",
            timeout_ms=0,
        )

    def _on_pipeline_update_text(self, pipeline, *args):
        # Text signals from a retired pipeline (late translations, queued
        # executor jobs) must not reach the display — chunk ids restart at 1
        # each round and would collide with the new round's items.
        if pipeline is not self.pipeline:
            return
        self.subtitle_display.update_text(*args)

    def _on_pipeline_update_live_text(self, pipeline, *args):
        if pipeline is not self.pipeline:
            return
        self.subtitle_display.update_live_text(*args)

    def _on_pipeline_status(self, pipeline, message: str, timeout_ms: int):
        if pipeline is not self.pipeline:
            return
        self.subtitle_display.show_status(message, timeout_ms=timeout_ms)

    def _on_pipeline_error(self, pipeline, message: str):
        if pipeline is not self.pipeline:
            return
        msg = (message or "").strip()
        if not msg:
            return
        self._last_pipeline_error = msg
        self.subtitle_display.show_error(f"Pipeline error: {msg}", timeout_ms=8000)

    def _on_pipeline_stopped(self, pipeline):
        if pipeline is not self.pipeline:
            return

        self.subtitle_display.show_status("")
        self.pipeline = None
        self.is_running = False
        self._paused = False
        self.play_btn.setEnabled(True)
        self._style_transport_buttons(state="idle")
        if self._last_pipeline_error:
            self.subtitle_display.show_error(
                f"Stopped: {self._last_pipeline_error} (click \u25B6 to restart)",
                timeout_ms=0,
            )

    def _kill_pipeline(self):
        """Stop pipeline without changing UI state."""
        if self.pipeline:
            self.pipeline.stop()
            self.pipeline = None

    def _on_settings_clicked(self):
        if self._popover is None:
            self._popover = SettingsPopover()
            self._popover.settings_saved.connect(self._on_settings_saved)
            self._popover.display_changed.connect(self._on_display_preview)

        from core.config import config
        self._popover.load_from_config(config)
        self._popover.show_relative_to(self.settings_btn)

    def _on_display_preview(self, orig_font: int, trans_font: int):
        """Live preview of display settings."""
        self.subtitle_display.original_font_size = orig_font
        self.subtitle_display.translated_font_size = trans_font
        for _, widget in self.subtitle_display.items:
            if widget._asr_only:
                widget.original_label.setStyleSheet(
                    f"color: #1D1D1F; font-family: 'Helvetica Neue', Arial; font-size: {trans_font}px; background: transparent;"
                )
            else:
                widget.original_label.setStyleSheet(
                    f"color: #86868B; font-family: 'Helvetica Neue', Arial; font-size: {orig_font}px; background: transparent;"
                )
                widget.translated_label.setStyleSheet(
                    f"color: #1D1D1F; font-family: 'Helvetica Neue', Arial; font-size: {trans_font}px; font-weight: bold; background: transparent;"
                )

    def _on_settings_saved(self):
        from core.config import config
        config.reload()

    def _on_pin_clicked(self):
        self.is_pinned = self.pin_btn.isChecked()
        if HAS_OBJC:
            try:
                win_id = int(self.winId())
                ns_view = objc.objc_object(c_void_p=c_void_p(win_id))
                ns_window = ns_view.window()
                ns_window.setLevel_(3 if self.is_pinned else 0)
            except Exception:
                pass
        else:
            geo = self.geometry()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.is_pinned)
            self.setGeometry(geo)
            self.show()

    # ---- Button styles ----

    def _style_transport_buttons(self, state: str):
        """Style play/stop buttons. state: 'idle', 'loading', 'running', 'paused'."""
        stop_disabled_style = (
            "QToolButton { background: #F2F2F7; border-radius: 6px;"
            "  color: #C7C7CC; font-size: 12px; border: none; }"
        )
        stop_enabled_style = (
            "QToolButton { background: #FF3B30; border-radius: 6px;"
            "  color: white; font-size: 12px; border: none; }"
            "QToolButton:hover { background: #E0332B; }"
        )

        if state == "running":
            self.play_btn.setText("\u23F8")  # ⏸
            self.play_btn.setStyleSheet(
                "QToolButton { background: #FF9500; border-radius: 6px;"
                "  color: white; font-size: 14px; border: none; }"
                "QToolButton:hover { background: #E08600; }"
            )
            self.stop_btn.setEnabled(True)
            self.stop_btn.setStyleSheet(stop_enabled_style)
        elif state == "paused":
            # Play triangle (green, ready to resume), stop still active
            self.play_btn.setText("\u25B6")  # ▶
            self.play_btn.setStyleSheet(
                "QToolButton { background: #34C759; border-radius: 6px;"
                "  color: white; font-size: 13px; border: none; }"
                "QToolButton:hover { background: #2DB84D; }"
            )
            self.stop_btn.setEnabled(True)
            self.stop_btn.setStyleSheet(stop_enabled_style)
        elif state == "loading":
            self.play_btn.setText("\u22EF")  # ⋯
            self.play_btn.setStyleSheet(
                "QToolButton { background: #E5E5EA; border-radius: 6px;"
                "  color: #86868B; font-size: 14px; border: none; }"
            )
            self.stop_btn.setEnabled(False)
            self.stop_btn.setStyleSheet(stop_disabled_style)
        else:  # idle
            self.play_btn.setText("\u25B6")  # ▶
            self.play_btn.setStyleSheet(
                "QToolButton { background: #34C759; border-radius: 6px;"
                "  color: white; font-size: 13px; border: none; }"
                "QToolButton:hover { background: #2DB84D; }"
            )
            self.stop_btn.setEnabled(False)
            self.stop_btn.setStyleSheet(stop_disabled_style)

    # ---- Lifecycle ----

    def closeEvent(self, event):
        self._kill_pipeline()
        QApplication.quit()
        event.accept()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    signal.signal(signal.SIGINT, lambda *_: os._exit(0))

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    app.setApplicationName("Mac Live Subtitle")
    app.setOrganizationName("Henry Jessie")
    app.setOrganizationDomain("henryjessie.com")

    icon_path = resource_path("assets", "icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = SubtitleWindow()
    window.show()

    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
