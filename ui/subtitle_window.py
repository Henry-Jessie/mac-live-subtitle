"""Mac Live Subtitle — unified floating subtitle window for macOS."""

import html
import os
import sys
import time
import signal
import configparser

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QScrollArea, QToolButton, QSizePolicy,
    QGraphicsDropShadowEffect, QComboBox, QLineEdit, QFormLayout,
    QPushButton, QListView, QAbstractItemView, QProxyStyle, QStyle, QStyleOptionComboBox,
    QDoubleSpinBox, QStyleOptionSpinBox, QAbstractSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint, QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen

from core.config import Config, config

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

    def __init__(self, chunk_id: int, timestamp: str, original: str, translated: str = ""):
        super().__init__()
        self.chunk_id = chunk_id
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(3)
        self.setLayout(layout)

        self.original_label = QLabel("")
        self.original_label.setTextFormat(Qt.TextFormat.RichText)
        self.original_label.setWordWrap(True)
        self.original_label.setStyleSheet(
            "color: #86868B; font-family: 'Helvetica Neue', Arial; font-size: 13px; background: transparent;"
        )
        layout.addWidget(self.original_label)

        self.translated_label = QLabel(translated or "...")
        self.translated_label.setWordWrap(True)
        self.translated_label.setStyleSheet(
            "color: #1D1D1F; font-family: 'Helvetica Neue', Arial; font-size: 17px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(self.translated_label)

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
            new_widget = SubtitleItem(chunk_id, ts, original_text, translated_text)
            insert_idx = len(self.items)
            for i, (cid, _) in enumerate(self.items):
                if cid > chunk_id:
                    insert_idx = i
                    break
            self.items.insert(insert_idx, (chunk_id, new_widget))
            self.container_layout.insertWidget(insert_idx, new_widget)
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
            # Live preview: translation is not available yet.
            new_widget = SubtitleItem(chunk_id, ts, combined, " ")
            new_widget.update_original_parts(confirmed_text or "", interim_text or "")

            insert_idx = len(self.items)
            for i, (cid, _) in enumerate(self.items):
                if cid > chunk_id:
                    insert_idx = i
                    break
            self.items.insert(insert_idx, (chunk_id, new_widget))
            self.container_layout.insertWidget(insert_idx, new_widget)
            QTimer.singleShot(10, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
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
                f.write(
                    f"[{d['timestamp']}] (ID: {cid})\n"
                    f"Original: {d['original']}\n"
                    f"Translation: {d['translated']}\n"
                    f"{'-' * 30}\n"
                )
        return filename

    def clear(self):
        """Remove all subtitle items and show placeholder."""
        for _, widget in self.items:
            widget.setParent(None)
            widget.deleteLater()
        self.items.clear()
        self.transcript_data.clear()
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

    # Translation LLM presets: name -> (base_url, api_key_env, model, extra_body_json_or_None)
    _TRANSLATION_PROVIDERS = {
        "DeepSeek": (
            "https://api.deepseek.com/v1",
            "DEEPSEEK_API_KEY",
            "deepseek-chat",
            None,
        ),
        "Google": (
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "GEMINI_API_KEY",
            "gemini-3-flash-preview",
            '{"reasoning_effort": "minimal"}',
        ),
        "Custom": (
            "",
            "OPENAI_API_KEY",
            "",
            None,
        ),
    }

    # ASR provider presets: name -> (api_key_env, model_options, backend)
    _PROVIDERS = {
        "Deepgram": ("DEEPGRAM_API_KEY", [
            "nova-3",
            "nova-3-medical",
        ], "deepgram_stream"),
        "Qwen ASR": ("DASHSCOPE_API_KEY", [
            "qwen3-asr-flash-realtime",
            "qwen3-asr-flash-realtime-2026-02-10",
            "qwen3-asr-flash-realtime-2025-10-27",
        ], "qwen3_asr_realtime"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
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

    def _line_edit(self, placeholder: str = "", password: bool = False) -> QLineEdit:
        le = QLineEdit()
        le.setPlaceholderText(placeholder)
        le.setProperty("hintIndent", 8)
        if password:
            le.setEchoMode(QLineEdit.EchoMode.Password)
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

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        self.setLayout(layout)

        # ---- Audio section ----
        layout.addWidget(self._section_title("Audio"))
        audio_card = self._card()
        audio_lay = QVBoxLayout()
        audio_lay.setContentsMargins(0, 0, 0, 0)
        audio_lay.setSpacing(0)
        audio_card.setLayout(audio_lay)

        import sounddevice as sd
        self.device_combo = self._combo()
        self.device_combo.addItem("Auto (Default)", "auto")
        try:
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0:
                    self.device_combo.addItem(f"[{i}] {d['name']}", i)
        except Exception:
            pass
        self._row(
            "Device",
            self.device_combo,
            audio_lay,
            last=True,
            hint="Audio input device for capture",
        )
        layout.addWidget(audio_card)

        # ---- Model section ----
        layout.addWidget(self._section_title("Model"))
        model_card = self._card()
        model_lay = QVBoxLayout()
        model_lay.setContentsMargins(0, 0, 0, 0)
        model_lay.setSpacing(0)
        model_card.setLayout(model_lay)

        self.provider_combo = self._combo()
        self.provider_combo.addItems(list(self._PROVIDERS.keys()))
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self._row(
            "Provider",
            self.provider_combo,
            model_lay,
            hint="API endpoint for speech recognition",
        )

        self.model_edit = self._line_edit("e.g. nova-3")
        self._row(
            "Model",
            self.model_edit,
            model_lay,
            hint="Model ID (provider-specific)",
        )

        api_key_wrap, self.api_key_edit = self._password_with_toggle("")
        self._row(
            "API Key",
            api_key_wrap,
            model_lay,
            last=True,
            hint="Empty uses env var",
        )
        self._on_provider_changed(self.provider_combo.currentText())
        layout.addWidget(model_card)

        # ---- Translation section ----
        layout.addWidget(self._section_title("Translation"))
        trans_card = self._card()
        trans_lay = QVBoxLayout()
        trans_lay.setContentsMargins(0, 0, 0, 0)
        trans_lay.setSpacing(0)
        trans_card.setLayout(trans_lay)

        self.trans_provider_combo = self._combo()
        self.trans_provider_combo.addItems(list(self._TRANSLATION_PROVIDERS.keys()))
        self.trans_provider_combo.currentTextChanged.connect(self._on_trans_provider_changed)
        self._row("Provider", self.trans_provider_combo, trans_lay, hint="Translation LLM provider")

        self.trans_base_url_edit = self._line_edit("https://api.openai.com/v1")
        self._row("Base URL", self.trans_base_url_edit, trans_lay)

        self.trans_model_edit = self._line_edit("e.g. deepseek-chat")
        self._row("Model", self.trans_model_edit, trans_lay)

        trans_key_wrap, self.trans_api_key_edit = self._password_with_toggle("")
        self._row("API Key", trans_key_wrap, trans_lay, hint="sk-... or $ENV_NAME")

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

        self._row("", test_wrap, trans_lay, last=True)

        self._on_trans_provider_changed(self.trans_provider_combo.currentText())
        layout.addWidget(trans_card)

        # ---- Subtitle section ----
        layout.addWidget(self._section_title("Subtitle"))
        sub_card = self._card()
        sub_lay = QVBoxLayout()
        sub_lay.setContentsMargins(0, 0, 0, 0)
        sub_lay.setSpacing(0)
        sub_card.setLayout(sub_lay)

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
        self._row(
            "Target",
            self.target_lang_combo,
            sub_lay,
            last=True,
            hint="Language for translation output",
        )
        layout.addWidget(sub_card)

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

    def _on_provider_changed(self, provider_name: str):
        """Auto-fill model and API key hint when provider changes."""
        preset = self._PROVIDERS.get(provider_name)
        if not preset:
            return
        api_key_env, models, _backend = preset

        # Model: set first preset model as default
        if models:
            self.model_edit.setText(models[0])
        else:
            self.model_edit.setText("")

        # API key hint
        if api_key_env:
            self.api_key_edit.setPlaceholderText(f"Auto from ${api_key_env} (or type manually)")
        else:
            self.api_key_edit.setPlaceholderText("Type API key (optional)")

    def _on_trans_provider_changed(self, preset_name: str):
        """Auto-fill translation LLM fields when provider changes."""
        preset = self._TRANSLATION_PROVIDERS.get(preset_name)
        if not preset:
            return
        base_url, api_key_env, model, _extra_body = preset

        # Custom: keep current field values, only update placeholder
        if preset_name != "Custom":
            self.trans_base_url_edit.setText(base_url)
            self.trans_model_edit.setText(model)

        if api_key_env:
            self.trans_api_key_edit.setPlaceholderText(f"Default: ${api_key_env}")
        else:
            self.trans_api_key_edit.setPlaceholderText("sk-... or $ENV_NAME")

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
        # Audio device
        if cfg.device_index is not None:
            idx = self.device_combo.findData(cfg.device_index)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)

        # Detect provider from backend
        if cfg.asr_backend == "deepgram_stream":
            self.provider_combo.setCurrentText("Deepgram")
            self.model_edit.setText(cfg.deepgram_model or "nova-3")
        elif cfg.asr_backend == "qwen3_asr_realtime":
            self.provider_combo.setCurrentText("Qwen ASR")
            self.model_edit.setText(cfg.qwen3_asr_realtime_model or "qwen3-asr-flash-realtime")
        else:
            self.provider_combo.setCurrentText("Deepgram")
            self.model_edit.setText(cfg.deepgram_model or "nova-3")

        # API key (show actual key if set directly, otherwise empty to use env)
        self.api_key_edit.setText("")

        # Translation LLM — match preset by base_url, fallback to Custom
        matched_preset = "Custom"
        for name, (url, _env, _model, _eb) in self._TRANSLATION_PROVIDERS.items():
            if name == "Custom":
                continue
            if url and cfg.api_base_url and url.rstrip("/") == cfg.api_base_url.rstrip("/"):
                matched_preset = name
                break
        self.trans_provider_combo.setCurrentText(matched_preset)
        if matched_preset == "Custom":
            self.trans_base_url_edit.setText(cfg.api_base_url or "")
        self.trans_model_edit.setText(cfg.model or "")
        # Show explicit key or $ENV_NAME; empty = use provider default env
        explicit_key = (cfg._get("translation", "api_key") or "").strip()
        if explicit_key:
            self.trans_api_key_edit.setText(explicit_key)
        else:
            custom_env = (cfg._get("translation", "api_key_env") or "").strip()
            matched = self._TRANSLATION_PROVIDERS.get(matched_preset)
            preset_env = matched[1] if matched else ""
            if custom_env and custom_env != preset_env:
                self.trans_api_key_edit.setText(f"${custom_env}")
            else:
                self.trans_api_key_edit.setText("")

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

    # ---- Translation test ----

    def _resolve_translation_api_key_from_ui(self) -> str:
        key_input = (self.trans_api_key_edit.text() or "").strip()
        if key_input.startswith("$") and len(key_input) > 1:
            env_name = key_input[1:].strip()
            val = (os.getenv(env_name) or "").strip()
            if not val:
                raise ValueError(f"Env var ${env_name} is not set")
            return val
        if key_input:
            return key_input
        preset = self._TRANSLATION_PROVIDERS.get(self.trans_provider_combo.currentText())
        env_name = (preset[1] if preset else "OPENAI_API_KEY") or "OPENAI_API_KEY"
        val = (os.getenv(env_name) or "").strip()
        # Fall back to dummy key for local servers (Ollama, LM Studio) that don't require auth
        return val or "dummy-key-for-local"

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
        if preset and preset[3]:
            try:
                import json
                extra_body = json.loads(preset[3])
            except Exception:
                pass

        self._trans_test_worker = TranslationTestWorker(
            base_url=base_url, api_key=api_key, model=model,
            target_lang=target_lang, extra_body=extra_body, parent=self,
        )
        self._trans_test_worker.ok.connect(self._on_trans_test_ok)
        self._trans_test_worker.err.connect(self._on_trans_test_err)
        self._trans_test_worker.finished.connect(lambda: self.trans_test_btn.setEnabled(True))
        self._trans_test_worker.finished.connect(self._trans_test_worker.deleteLater)
        self._trans_test_worker.start()

    def _on_trans_test_ok(self, translated: str):
        self.trans_test_result.setStyleSheet("color: #34C759; font-size: 11px; background: transparent;")
        self.trans_test_result.setText(translated)

    def _on_trans_test_err(self, message: str):
        self.trans_test_result.setStyleSheet("color: #FF3B30; font-size: 11px; background: transparent;")
        self.trans_test_result.setText(message)

    def _save_config(self):
        """Write settings to config.ini."""
        cp = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.ini")
        cp.read(config_path)

        for section in ("translation", "transcription", "audio"):
            if not cp.has_section(section):
                cp.add_section(section)

        # Audio
        idx = self.device_combo.currentData()
        cp.set("audio", "device_index", str(idx) if idx is not None else "auto")

        # Provider / model / key
        provider = self.provider_combo.currentText()
        preset = self._PROVIDERS.get(provider, ("DEEPGRAM_API_KEY", ["nova-3"], "deepgram_stream"))
        api_key_env = preset[0]
        backend = preset[2]

        cp.set("transcription", "backend", backend)

        if backend == "deepgram_stream":
            cp.set("transcription", "deepgram_model", self.model_edit.text().strip() or "nova-3")
        elif backend == "qwen3_asr_realtime":
            cp.set(
                "transcription",
                "qwen3_asr_realtime_model",
                self.model_edit.text().strip() or "qwen3-asr-flash-realtime",
            )

            # Clean up old key fields before writing new ones
            for opt in ("qwen3_asr_realtime_api_key", "qwen3_asr_realtime_api_key_env"):
                if cp.has_option("transcription", opt):
                    cp.remove_option("transcription", opt)

            if api_key_env:
                cp.set("transcription", "qwen3_asr_realtime_api_key_env", api_key_env)

            explicit_key = self.api_key_edit.text().strip()
            if explicit_key:
                cp.set("transcription", "qwen3_asr_realtime_api_key", explicit_key)

        # Translation LLM
        trans_provider_name = self.trans_provider_combo.currentText()
        trans_provider = self._TRANSLATION_PROVIDERS.get(trans_provider_name)

        base_url = self.trans_base_url_edit.text().strip()
        trans_model = self.trans_model_edit.text().strip()
        if base_url:
            cp.set("translation", "base_url", base_url)
        elif cp.has_option("translation", "base_url"):
            cp.remove_option("translation", "base_url")
        if trans_model:
            cp.set("translation", "model", trans_model)

        # Only write api_key_env / extra_body when a non-Custom provider is selected
        if trans_provider:
            _, api_key_env_trans, _, extra_body_json = trans_provider
            if trans_provider_name != "Custom":
                if api_key_env_trans:
                    cp.set("translation", "api_key_env", api_key_env_trans)
                if extra_body_json:
                    cp.set("translation", "extra_body", extra_body_json)
                else:
                    # Provider explicitly has no extra_body — clear it
                    if cp.has_option("translation", "extra_body"):
                        cp.remove_option("translation", "extra_body")

        # API Key: $ENV_NAME → write api_key_env; otherwise → write api_key
        key_input = self.trans_api_key_edit.text().strip()
        if key_input.startswith("$") and len(key_input) > 1:
            cp.set("translation", "api_key_env", key_input[1:])
            if cp.has_option("translation", "api_key"):
                cp.remove_option("translation", "api_key")
        elif key_input:
            cp.set("translation", "api_key", key_input)
        elif cp.has_option("translation", "api_key"):
            cp.remove_option("translation", "api_key")

        # Subtitle
        target_lang = (self.target_lang_combo.currentText() or "").strip()
        if not target_lang or target_lang == "Custom...":
            target_lang = (getattr(self, "_target_lang_last_valid_text", "") or "Simplified Chinese").strip()
        cp.set("translation", "target_lang", target_lang)

        with open(config_path, "w") as f:
            cp.write(f)

        self.status_label.setText("Saved! Click Start to apply.")
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

    def _apply_rounded_corners(self):
        """Use PyObjC to round the native popup window corners."""
        if not HAS_OBJC:
            return
        try:
            nv = objc.objc_object(c_void_p=c_void_p(int(self.winId())))
            nw = nv.window()
            # Round the window's root view layer
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

    finished = pyqtSignal(object)  # Pipeline or None

    def run(self):
        try:
            from core.pipeline import Pipeline
            pipeline = Pipeline()
            self.finished.emit(pipeline)
        except Exception as e:
            print(f"[StartupWorker] Error: {e}")
            import traceback
            traceback.print_exc()
            self.finished.emit(None)


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

            http_client = httpx.Client(verify=False)
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
        self.startup_worker.finished.connect(self._on_pipeline_ready)
        self.startup_worker.start()

    def _on_pipeline_ready(self, pipeline):
        if pipeline is None:
            self.play_btn.setEnabled(True)
            self._style_transport_buttons(state="idle")
            self.subtitle_display.show_status("")
            self.subtitle_display.placeholder.setText("Init failed — check console")
            self.subtitle_display.placeholder.setStyleSheet(
                "color: #FF3B30; font-size: 14px; background: transparent;"
            )
            self.subtitle_display.placeholder.show()
            return

        self.pipeline = pipeline
        self._last_pipeline_error = ""
        self.subtitle_display.show_status("Starting…", timeout_ms=0)
        self.pipeline.signals.update_text.connect(self.subtitle_display.update_text)
        try:
            self.pipeline.signals.update_live_text.connect(self.subtitle_display.update_live_text)
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

        from core.config import config
        self._popover.load_from_config(config)
        self._popover.show_relative_to(self.settings_btn)

    def _on_settings_saved(self):
        if self.pipeline:
            self._kill_pipeline()
            self.is_running = False
            self._paused = False
            self._style_transport_buttons(state="idle")
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

    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = SubtitleWindow()
    window.show()

    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
