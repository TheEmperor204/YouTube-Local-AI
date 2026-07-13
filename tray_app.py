#!/usr/bin/env python3
from schedule_manager import calculate_wait, get_next_post_description, load_schedule_config, save_schedule_config
"""
YouTube Shorts Auto-Poster Tray Widget
Shorts auto-uploader with tray app.
Dropdown popup with tabs: Last Post, History, Settings, Duplicates
"""

import os
import sys
import json
import random
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv
import keyring
from duplicates_tab import DuplicatesTab
from explicit_tab import ExplicitTab
from music_tab import MusicTab
from schedule_tab import ScheduleTab
from progress_tab import ProgressTab

KEYRING_SERVICE = "youtube-poster"
KEYRING_KEY = "ig_password"
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QFileDialog, QGroupBox,
    QFormLayout, QMessageBox, QTabWidget, QScrollArea, QFrame, QCheckBox, QTextEdit
)
from PyQt6.QtCore import QTimer, Qt, QProcess, QPointF, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPolygonF

APP_DIR = Path(__file__).parent.resolve()
ENV_FILE = APP_DIR / ".env"
POSTER_SCRIPT = str(APP_DIR / "poster.py")
SHORTS_POSTER_SCRIPT = str(APP_DIR / "yt_shorts_poster.py")
VENV_PYTHON = str(APP_DIR / "youtubee-env" / "bin" / "python")


class ConfigManager:
    def __init__(self):
        self.path = ENV_FILE
        self.load()

    def load(self):
        self.settings = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    self.settings[key.strip()] = val.strip()

    def get(self, key, default=""):
        return self.settings.get(key, default)

    def save(self, updates):
        self.settings.update({k: str(v) for k, v in updates.items()})
        lines = []
        written = set()
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    key = s.split("=", 1)[0].strip()
                    if key in updates:
                        lines.append(f"{key}={updates[key]}")
                        written.add(key)
                    elif key in self.settings:
                        lines.append(f"{key}={self.settings[key]}")
                        written.add(key)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
        for key, val in updates.items():
            if key not in written:
                lines.append(f"{key}={val}")
        self.path.write_text("\n".join(lines) + "\n")
        self.load()


def create_youtube_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # YouTube red rounded rectangle
    p.setBrush(QColor(255, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    rect = pixmap.rect().adjusted(6, 14, -6, -14)
    p.drawRoundedRect(rect, 12, 12)
    # White play triangle
    p.setBrush(QColor(255, 255, 255))
    cx, cy = rect.center().x(), rect.center().y()
    tri = QPolygonF([
        QPointF(cx - 7, cy - 9),
        QPointF(cx - 7, cy + 9),
        QPointF(cx + 9, cy)
    ])
    p.drawPolygon(tri)
    p.end()
    return QIcon(pixmap)


class TrayPopup(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumSize(440, 520)
        self.setMaximumHeight(660)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet("background-color: #C13584; border-radius: 8px 8px 0 0;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 0, 8, 0)
        title = QLabel("YouTube Shorts Auto-Poster")
        title.setStyleSheet("color: white; font-size: 13px; font-weight: bold;")
        hl.addWidget(title)
        hl.addStretch()
        close_btn = QPushButton("X")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: white; border: none; font-size: 14px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.2); border-radius: 4px; }"
        )
        close_btn.clicked.connect(self.hide)
        hl.addWidget(close_btn)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.last_post_widget = self._build_last_post_tab()
        self.tabs.addTab(ProgressTab(), "📊 Progress")
        self.tabs.addTab(self.last_post_widget, "Last Post")
        self.tabs.addTab(self._build_history_tab(), "History")
        self.tabs.addTab(self._build_settings_tab(), "Settings")
        self.tabs.addTab(DuplicatesTab(), "Duplicates")
        self.tabs.addTab(ExplicitTab(), "🚫 Explicits")
        self.tabs.addTab(BleepWordManager(), "Bleep Words")
        self.tabs.addTab(MusicTab(), "Music")
        self.tabs.addTab(ScheduleTab(), "Schedule")
        layout.addWidget(self.tabs)

    def _build_last_post_tab(self):
        widget = QWidget()
        self.last_post_layout = QVBoxLayout(widget)
        self.last_post_layout.setContentsMargins(8, 8, 8, 8)
        self.last_post_layout.addStretch()
        return widget

    def _build_history_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        self.history_layout = QVBoxLayout(scroll_content)
        self.history_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        return widget

    def _build_settings_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        btn_browse = QPushButton("Browse")

        grp_reel_sched = QGroupBox("Short Posting Schedule")
        rl = QFormLayout(grp_reel_sched)
        self.reel_boot_delay = QSpinBox()
        self.reel_boot_delay.setRange(0, 60)
        self.reel_boot_delay.setSuffix(" min")
        self.reel_boot_delay.setValue(int(self.config.get("REEL_DELAY_AFTER_BOOT_MINUTES", "2")))
        self.reel_min_hours = QSpinBox()
        self.reel_min_hours.setRange(1, 24)
        self.reel_min_hours.setSuffix(" hr")
        self.reel_min_hours.setValue(int(self.config.get("REEL_MIN_INTERVAL_HOURS", "4")))
        self.reel_max_hours = QSpinBox()
        self.reel_max_hours.setRange(1, 48)
        self.reel_max_hours.setSuffix(" hr")
        self.reel_max_hours.setValue(int(self.config.get("REEL_MAX_INTERVAL_HOURS", "8")))
        rl.addRow("Delay after boot:", self.reel_boot_delay)
        rl.addRow("Min interval:", self.reel_min_hours)
        rl.addRow("Max interval:", self.reel_max_hours)
        scroll_layout.addWidget(grp_reel_sched)

        from PyQt6.QtWidgets import QComboBox
        grp_sort = QGroupBox("Media Sort Order")
        sol = QFormLayout(grp_sort)
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Oldest first (by date created)", "oldest")
        self.sort_combo.addItem("Newest first (by date created)", "newest")
        self.sort_combo.addItem("Alphabetical A-Z", "name_asc")
        self.sort_combo.addItem("Alphabetical Z-A", "name_desc")
        current_sort = self.config.get("SORT_ORDER", "oldest")
        for i in range(self.sort_combo.count()):
            if self.sort_combo.itemData(i) == current_sort:
                self.sort_combo.setCurrentIndex(i)
                break
        sol.addRow("Order:", self.sort_combo)
        scroll_layout.addWidget(grp_sort)

        # === DRY RUN / TEST MODE ===
        grp_dry = QGroupBox("Test Mode (Dry Run)")
        dl = QVBoxLayout(grp_dry)
        self.dry_run_checkbox = QCheckBox("Enable Dry Run — save outputs locally instead of uploading")
        self.dry_run_checkbox.setChecked(self.config.get("YT_DRY_RUN", "false").lower() == "true")
        dl.addWidget(self.dry_run_checkbox)
        hint = QLabel("When ON: full pipeline runs but nothing posts to YouTube.\nDuplicate detection is bypassed.\nOutputs saved to YT_TEST_OUTPUT/")
        hint.setStyleSheet("font-size: 10px; color: #aaa;")
        hint.setWordWrap(True)
        dl.addWidget(hint)
        scroll_layout.addWidget(grp_dry)

        # === GPU GUARD ===
        grp_gpu = QGroupBox("GPU Guard")
        gl = QVBoxLayout(grp_gpu)
        self.gpu_guard_checkbox = QCheckBox("Enable GPU/CPU load check before processing")
        self.gpu_guard_checkbox.setChecked(self.config.get("GPU_GUARD", "true").lower() == "true")
        gl.addWidget(self.gpu_guard_checkbox)
        gpu_hint = QLabel("When ON: waits for GPU/CPU to be idle before starting each cycle.")
        gpu_hint.setStyleSheet("font-size: 10px; color: #aaa;")
        gpu_hint.setWordWrap(True)
        gl.addWidget(gpu_hint)
        scroll_layout.addWidget(grp_gpu)
        # === PHONE NOTIFICATIONS ===
        grp_ntfy = QGroupBox("Phone Notifications (ntfy.sh)")
        nl = QVBoxLayout(grp_ntfy)
        self.ntfy_enable = QCheckBox("Enable phone notifications")
        self.ntfy_enable.setChecked(bool(self.config.get("NTFY_TOPIC", "")))
        nl.addWidget(self.ntfy_enable)
        nl.addWidget(QLabel("ntfy topic name:"))
        self.ntfy_topic = QLineEdit(self.config.get("NTFY_TOPIC", ""))
        self.ntfy_topic.setPlaceholderText("Your ntfy topic name")
        nl.addWidget(self.ntfy_topic)
        ntfy_hint = QLabel("Install the ntfy app on your phone and subscribe to this topic name.")
        ntfy_hint.setStyleSheet("font-size: 10px; color: #aaa;")
        ntfy_hint.setWordWrap(True)
        nl.addWidget(ntfy_hint)
        scroll_layout.addWidget(grp_ntfy)


        grp_folders = QGroupBox("Video Folders")
        fl = QFormLayout(grp_folders)
        self.upload_folder_input = QLineEdit(self.config.get("VIDEO_FOLDER", "videos_to_upload"))
        btn_browse1 = QPushButton("Browse...")
        btn_browse1.clicked.connect(lambda: self._browse_folder(self.upload_folder_input, "Select Upload Folder"))
        row1 = QHBoxLayout()
        row1.addWidget(self.upload_folder_input)
        row1.addWidget(btn_browse1)
        fl.addRow("Upload folder:", row1)
        self.archive_folder_input = QLineEdit(self.config.get("POSTED_SHORTS_DIR", "youtube_posted_archive"))
        btn_browse2 = QPushButton("Browse...")
        btn_browse2.clicked.connect(lambda: self._browse_folder(self.archive_folder_input, "Select Archive Folder"))
        row2 = QHBoxLayout()
        row2.addWidget(self.archive_folder_input)
        row2.addWidget(btn_browse2)
        fl.addRow("Archive folder:", row2)
        scroll_layout.addWidget(grp_folders)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self._save_settings)
        layout.addWidget(btn_save)
        layout.addStretch()
        return widget

    def _browse_folder(self, line_edit, title):
        folder = QFileDialog.getExistingDirectory(self, title)
        if folder:
            line_edit.setText(folder)

    def _save_settings(self):
        try:
            if self.reel_max_hours.value() < self.reel_min_hours.value():
                QMessageBox.warning(self, "Invalid", "Short max interval must be >= min interval")
                return
            self.config.save({
                "SORT_ORDER": self.sort_combo.currentData(),
                "YT_DRY_RUN": "true" if self.dry_run_checkbox.isChecked() else "false",
                "VIDEO_FOLDER": self.upload_folder_input.text(),
                "POSTED_SHORTS_DIR": self.archive_folder_input.text(),
                "NTFY_TOPIC": self.ntfy_topic.text(),
                "GPU_GUARD": "true" if self.gpu_guard_checkbox.isChecked() else "false",
                "REEL_DELAY_AFTER_BOOT_MINUTES": str(self.reel_boot_delay.value()),
        "REEL_MIN_INTERVAL_HOURS": str(self.reel_min_hours.value()),
        "REEL_MAX_INTERVAL_HOURS": str(self.reel_max_hours.value()),
            })
            QMessageBox.information(self, "Saved", "Settings saved!")
            self.config.load()
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Save Error", str(e))

    def _get_youtube_account(self):
        try:
            import pickle
            token_path = Path(__file__).parent / "yt_token.pickle"
            if not token_path.exists():
                return "Not authenticated"
            with open(token_path, "rb") as t:
                creds = pickle.load(t)
            if not creds or not creds.valid:
                return "Token expired"
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
            resp = youtube.channels().list(part="snippet", mine=True).execute(num_retries=3)
            items = resp.get("items", [])
            if items:
                return items[0]["snippet"]["title"]
            return "Unknown"
        except Exception:
            return "Not authenticated"

    def refresh_data(self):
        self._clear_layout(self.last_post_layout)
        self._clear_layout(self.history_layout)

        shorts_log = APP_DIR / "posted_shorts.json"
        shorts_data = {"videos": {}, "last_post_time": None}
        if shorts_log.exists():
            try:
                shorts_data = json.loads(shorts_log.read_text())
            except Exception:
                pass

        video_folder = Path(self.config.get("VIDEO_FOLDER", "videos_to_upload"))
        remaining_videos = 0
        if video_folder.exists():
            remaining_videos = sum(1 for f in video_folder.iterdir()
                                   if f.is_file() and f.suffix.lower() in {".mp4", ".mov", ".avi"})

        temp_seg = Path(self.config.get("TEMP_SEGMENTS_DIR", "temp_segments"))
        remaining_segments = 0
        if temp_seg.exists():
            remaining_segments = sum(1 for f in temp_seg.iterdir()
                                     if f.is_file() and f.suffix.lower() in {".mp4", ".mov", ".avi"})

        account = self._get_youtube_account()
        if account:
            al = QLabel("YouTube: " + account)
            al.setStyleSheet("font-size: 12px; font-weight: bold; padding: 6px; color: #4285F4;")
            self.last_post_layout.addWidget(al)

        stats_text = "Shorts: " + str(len(shorts_data.get("videos", {}))) + " processed | " + str(remaining_videos) + " in queue"
        if remaining_segments > 0:
            stats_text += " | " + str(remaining_segments) + " segments pending"
        stats = QLabel(stats_text)
        stats.setStyleSheet("font-size: 12px; font-weight: bold; padding: 6px;")
        self.last_post_layout.addWidget(stats)

        next_times = []
        if "next_short_time" in shorts_data:
            try:
                next_dt = datetime.fromisoformat(shorts_data["next_short_time"])
                next_times.append(("Short", next_dt))
            except (ValueError, KeyError):
                pass

        for label, dt in next_times:
            next_str = dt.strftime("%B %d at %I:%M %p")
            nl = QLabel(label + " next: " + next_str)
            nl.setStyleSheet("font-size: 12px; padding: 2px 6px; color: #FF0000;")
            self.last_post_layout.addWidget(nl)

        entries = []
        for vkey, vdata in shorts_data.get("videos", {}).items():
            if vdata.get("first_posted_at"):
                try:
                    t = datetime.fromisoformat(vdata["first_posted_at"])
                    entries.append((t, vkey, vdata))
                except (ValueError, KeyError):
                    pass
        entries.sort(key=lambda x: x[0], reverse=True)

        if entries:
            self._populate_last_reel(entries[0][2])

        for timestamp, vkey, vdata in entries[:20]:
            self._add_reel_history_item(timestamp, vdata)

        if not entries:
            empty = QLabel("No videos posted yet")
            empty.setStyleSheet("color: #888; padding: 10px;")
            self.history_layout.addWidget(empty)

    def _populate_last_reel(self, vdata):
        type_label = QLabel("SHORT")
        type_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #FF0000; padding: 2px;")
        self.last_post_layout.addWidget(type_label)

        name_label = QLabel("Video: " + vdata.get("video_name", "Unknown"))
        name_label.setStyleSheet("font-size: 11px; color: #aaa; padding: 2px;")
        self.last_post_layout.addWidget(name_label)

        seg_info = "Segments: " + str(vdata.get("segments_posted", 0)) + "/" + str(vdata.get("segments_total", 1))
        if vdata.get("status") == "complete":
            seg_info += " OK"
        elif vdata.get("status") == "posting":
            seg_info += " ..."
        seg_label = QLabel(seg_info)
        seg_label.setStyleSheet("font-size: 12px; padding: 2px;")
        self.last_post_layout.addWidget(seg_label)

        try:
            t = datetime.fromisoformat(vdata.get("first_posted_at", ""))
            time_str = t.strftime("%B %d, %Y at %I:%M %p")
        except Exception:
            time_str = vdata.get("first_posted_at", "Unknown")
        time_label = QLabel("First posted: " + time_str)
        time_label.setStyleSheet("font-size: 12px; padding: 2px;")
        self.last_post_layout.addWidget(time_label)

        dur = vdata.get("duration", 0)
        if dur:
            dur_label = QLabel("Duration: " + str(round(dur, 1)) + "s")
            dur_label.setStyleSheet("font-size: 12px; color: #aaa; padding: 2px;")
            self.last_post_layout.addWidget(dur_label)

    def _add_reel_history_item(self, timestamp, vdata):
        item = QFrame()
        item.setFrameShape(QFrame.Shape.StyledPanel)
        item.setStyleSheet(
            "QFrame { margin: 2px; padding: 4px; border-radius: 4px; "
            "background: rgba(255,0,0,0.08); }"
        )
        il = QHBoxLayout(item)

        info_layout = QVBoxLayout()
        time_str = timestamp.strftime("%b %d, %I:%M %p")
        status_icon = "OK" if vdata.get("status") == "complete" else "..."
        name = vdata.get("video_name", "Unknown")
        seg_p = str(vdata.get("segments_posted", 0))
        seg_t = str(vdata.get("segments_total", 1))
        info_label = QLabel("<b>" + name + "</b> " + status_icon + "<br/>" + time_str + " - " + seg_p + "/" + seg_t + " parts")
        info_label.setTextFormat(Qt.TextFormat.RichText)
        info_layout.addWidget(info_label)

        dur = vdata.get("duration", 0)
        dur_label = QLabel(str(int(dur)) + "s")
        dur_label.setStyleSheet("color: #888; font-size: 11px;")
        info_layout.addWidget(dur_label)

        il.addLayout(info_layout)
        il.addStretch()
        self.history_layout.addWidget(item)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowDeactivate:
            if not QApplication.activeModalWidget():
                self.hide()
        super().changeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()

    def show_near_tray(self, tray_icon):
        self.refresh_data()
        self.adjustSize()
        w = max(self.minimumWidth(), self.sizeHint().width())
        h = max(self.minimumHeight(), self.sizeHint().height())
        if w > 500:
            w = 500
        if h > 660:
            h = 660
        self.resize(w, h)
        from PyQt6.QtGui import QCursor
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        x = cursor_pos.x() - w + 20
        y = cursor_pos.y() + 8
        if x < screen_geo.left() + 8:
            x = screen_geo.left() + 8
        if x + w > screen_geo.right() - 8:
            x = screen_geo.right() - w - 8
        if y + h > screen_geo.bottom() - 8:
            y = cursor_pos.y() - h - 8
        if y < screen_geo.top() + 8:
            y = screen_geo.top() + 8
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

class TrayApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setApplicationName("YouTube Shorts Auto-Poster")
        self.setQuitOnLastWindowClosed(False)
        self.config = ConfigManager()
        self.popup = TrayPopup(self.config)

        self.shorts_process = None
        self.is_posting_short = False

        self.tray = QSystemTrayIcon(self._create_youtube_icon(), self)
        self.tray.setToolTip("YouTube Shorts Auto-Poster")

        menu = QMenu()
        menu.addAction("Post Short Now", self.post_short_now)
        menu.addSeparator()
        menu.addAction("Status", self.show_status)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

        shorts_boot_min = int(self.config.get("REEL_DELAY_AFTER_BOOT_MINUTES", "2"))
        QTimer.singleShot(shorts_boot_min * 60 * 1000, self.run_shorts_poster)
        self._save_next_short_time(shorts_boot_min / 60.0)

        self.shorts_timer = QTimer(self)
        self.shorts_timer.setSingleShot(True)
        self.shorts_timer.timeout.connect(self.run_shorts_poster)

    def _create_youtube_icon(self):
        icon = QIcon()
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#FF0000"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(2, 4, 28, 24, 6, 6)
        painter.setBrush(QColor("#FFFFFF"))
        triangle = QPolygonF([QPointF(12, 10), QPointF(12, 22), QPointF(24, 16)])
        painter.drawPolygon(triangle)
        painter.end()
        icon.addPixmap(pixmap)
        return icon

    def _save_next_short_time(self, wait_hours):
        next_time = datetime.now() + timedelta(hours=wait_hours)
        log_path = APP_DIR / "posted_shorts.json"
        try:
            data = {"videos": {}, "last_post_time": None}
            if log_path.exists():
                data = json.loads(log_path.read_text())
            data["next_short_time"] = next_time.isoformat()
            log_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _update_tooltip(self):
        parts = []
        if self.is_posting_short:
            parts.append("posting...")
        if not parts:
            parts.append("Idle")
        self.tray.setToolTip(f"YouTube Shorts Auto-Poster ({' | '.join(parts)})")

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.popup.isVisible():
                self.popup.hide()
            else:
                self.popup.show_near_tray(self.tray)

    def show_status(self):
        shorts_log = APP_DIR / "posted_shorts.json"
        video_folder = Path(self.config.get("VIDEO_FOLDER", "videos_to_upload"))
        video_count = 0
        if video_folder.exists():
            video_count = sum(1 for f in video_folder.iterdir()
                             if f.is_file() and f.suffix.lower() in {".mp4", ".mov", ".avi"})
        temp_seg = Path(self.config.get("TEMP_SEGMENTS_DIR", "temp_segments"))
        seg_count = 0
        if temp_seg.exists():
            seg_count = sum(1 for f in temp_seg.iterdir()
                           if f.is_file() and f.suffix.lower() in {".mp4", ".mov", ".avi"})
        short_count = 0
        if shorts_log.exists():
            try:
                sdata = json.loads(shorts_log.read_text())
                short_count = len(sdata.get("videos", {}))
            except Exception:
                pass
        status = "Status\n\nYouTube Shorts:\n  In queue: " + str(video_count) + "\n  Processed: " + str(short_count) + "\n  Segments pending: " + str(seg_count) + "\n"
        if self.is_posting_short:
            status += "\nCurrently posting Short..."
        QMessageBox.information(None, "YouTube Shorts Auto-Poster", status)

    def post_short_now(self):
        if self.is_posting_short:
            QMessageBox.information(None, "Busy", "A Short post is already in progress.")
            return
        self.run_shorts_poster(force=True)

    def run_shorts_poster(self, force=False):
        if self.is_posting_short:
            return
        self.is_posting_short = True
        self._update_tooltip()
        self.tray.showMessage("YouTube Shorts Auto-Poster", "Starting Short processing...", QSystemTrayIcon.MessageIcon.Information, 5000)
        cmd = [VENV_PYTHON, SHORTS_POSTER_SCRIPT]
        if force:
            cmd.append("--force")
        self.shorts_process = QProcess(self)
        self.shorts_process.setWorkingDirectory(str(APP_DIR))
        self.shorts_process.finished.connect(self._on_shorts_finished)
        self.shorts_process.start(cmd[0], cmd[1:])

    def _on_shorts_finished(self, exit_code, exit_status):
        self.is_posting_short = False
        self._update_tooltip()
        self.popup.refresh_data()
        if exit_code == 0:
            self.tray.showMessage("YouTube Shorts Auto-Poster", "Short uploaded to YouTube!", QSystemTrayIcon.MessageIcon.Information, 8000)
            min_h = int(self.config.get("REEL_MIN_INTERVAL_HOURS", "4"))
            max_h = int(self.config.get("REEL_MAX_INTERVAL_HOURS", "8"))
            wait_h = calculate_wait(min_h, max_h)
            self._save_next_short_time(wait_h)
            self.shorts_timer.start(int(wait_h * 3600 * 1000))
            next_dt = datetime.now() + timedelta(hours=wait_h)
            next_str = next_dt.strftime("%B %d at %I:%M %p")
            self.tray.showMessage("YouTube Shorts Auto-Poster", f"Next Short: {next_str}", QSystemTrayIcon.MessageIcon.Information, 5000)
        elif exit_code == 2:
            self._save_next_short_time(1.0)
            self.shorts_timer.start(60 * 60 * 1000)
        else:
            self.tray.showMessage("YouTube Shorts Auto-Poster", "Short post failed - will retry in 30 min", QSystemTrayIcon.MessageIcon.Warning, 5000)
            self._save_next_short_time(0.5)
            self.shorts_timer.start(30 * 60 * 1000)


class BleepWordManager(QWidget):
    """UI to manage bleep word list."""
    def __init__(self):
        super().__init__()
        self.load_config()
        self.load_ban_config()
        self.init_ui()

    def load_config(self):
        try:
            data = json.loads(Path("bleep_words.json").read_text())
            self.enabled_state = data.get("enabled", True)
            self.words_list = data.get("words", [])
        except Exception:
            self.enabled_state = True
            self.words_list = []

    def _make_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep
    def save_config(self):
        try:
            data = {"enabled": self.enabled_state, "words": self.words_list}
            Path("bleep_words.json").write_text(json.dumps(data, indent=2))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Toggle
        row = QHBoxLayout()
        self.enable_cb = QCheckBox("Enable automatic bleeping")
        self.enable_cb.setChecked(self.enabled_state)
        self.enable_cb.stateChanged.connect(self._on_toggle)
        btn_refresh = QPushButton("Apply to running poster")
        btn_refresh.clicked.connect(lambda: self._reload_for_poster())
        row.addWidget(self.enable_cb)
        row.addStretch()
        row.addWidget(btn_refresh)
        layout.addLayout(row)

        # Word list header
        h = QHBoxLayout()
        h.addWidget(QLabel("Bleep words (one per row):"))
        h.addStretch()
        layout.addLayout(h)

        # Text area for words
        self.word_text = QTextEdit()
        self.word_text.setPlainText(chr(10).join(self.words_list))
        self.word_text.setMaximumHeight(250)
        layout.addWidget(self.word_text)

        # Buttons
        ctrl_row = QHBoxLayout()
        btnSave = QPushButton("Save List")
        btnSave.clicked.connect(self._save_words)
        btnAdd = QPushButton("Add Selected")
        btnAdd.clicked.connect(self._add_selected)
        btnClearSel = QPushButton("Clear Selection")
        btnClearSel.clicked.connect(lambda: self.word_text.clearSelection())
        ctrl_row.addWidget(btnSave)
        ctrl_row.addWidget(btnAdd)
        ctrl_row.addWidget(btnClearSel)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Instructions
        info = QLabel("Tip: Double-click a line to select it, then click Add Selected. \\nEach line becomes one bleep word.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666;")
        layout.addWidget(info)

        # ===== BAN LIST SECTION =====
        layout.addWidget(self._make_separator())

        ban_header = QHBoxLayout()
        ban_header.addWidget(QLabel("<b>Ban Words (flag for manual review)</b>"))
        ban_header.addStretch()
        layout.addLayout(ban_header)

        ban_toggle_row = QHBoxLayout()
        self.ban_enable_cb = QCheckBox("Enable ban list checking")
        self.ban_enable_cb.setChecked(self.ban_enabled)
        self.ban_enable_cb.stateChanged.connect(self._on_ban_toggle)
        ban_toggle_row.addWidget(self.ban_enable_cb)
        ban_toggle_row.addStretch()
        layout.addLayout(ban_toggle_row)

        ban_label = QLabel("One word per line. Each line is a banned word.")
        ban_label.setStyleSheet("color: #666;")
        ban_label.setWordWrap(True)
        layout.addWidget(ban_label)

        self.ban_word_text = QTextEdit()
        ban_lines = self.ban_words
        self.ban_word_text.setPlainText(chr(10).join(ban_lines))
        self.ban_word_text.setMinimumHeight(200)
        layout.addWidget(self.ban_word_text)

        ban_btn_row = QHBoxLayout()
        btnBanSave = QPushButton("Save Ban List")
        btnBanSave.clicked.connect(self._save_ban_words)
        ban_btn_row.addWidget(btnBanSave)
        ban_btn_row.addStretch()
        layout.addLayout(ban_btn_row)


    def _on_toggle(self, state):
        self.enabled_state = state == Qt.Checked
        self.save_config()

    def _reload_for_poster(self):
        # Reload config by triggering signal/log message; actual reload happens next cycle
        # config reload handled by next run
        QMessageBox.information(self, "Info", "Config updated. The poster process will pick up changes on next run.")

    def _save_words(self):
        text = self.word_text.toPlainText()
        lines = [l.strip().lower() for l in text.split(chr(10)) if l.strip()]
        seen = set()
        unique_lines = []
        for line in lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)
        self.words_list = unique_lines
        self.save_config()
        QMessageBox.information(self, "Saved", f"{len(unique_lines)} words saved.")

    def _add_selected(self):
        cursor = self.word_text.textCursor()
        sel = cursor.selectedText()
        if not sel.strip():
            QMessageBox.warning(self, "Nothing selected", "Select some text first.")
            return
        # Parse selection as comma-separated or newline-separated words
        import re
        tokens = [t.strip().lower() for t in re.split(r"[,\s+\n]+", sel) if t.strip()]
        added = []
        for tok in tokens:
            if tok and tok not in self.words_list:
                self.words_list.append(tok)
                added.append(tok)
        if added:
            self.save_config()
            self.word_text.setPlainText(chr(10).join(self.words_list))
            QMessageBox.information(self, "Added", f"Added {len(added)} word(s).")
        else:
            QMessageBox.information(self, "No new words", "All selected words already in list.")



    # ===== BAN WORDS SECTION =====
    def load_ban_config(self):
        try:
            data = json.loads(Path("ban_words.json").read_text())
            self.ban_enabled = data.get("enabled", True)
            self.ban_words = data.get("words", [])
        except Exception:
            self.ban_enabled = True
            self.ban_words = []

    def save_ban_config(self):
        try:
            data = {"enabled": self.ban_enabled, "words": self.ban_words}
            Path("ban_words.json").write_text(json.dumps(data, indent=2))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save ban list: {e}")

    def _save_ban_words(self):
        text = self.ban_word_text.toPlainText()
        self.ban_words = []
        for line in text.split(chr(10)):
            line = line.strip().lower()
            if line:
                self.ban_words.append(line)
        self.save_ban_config()
        QMessageBox.information(self, "Saved", f"{len(self.ban_words)} ban words saved.")

    def _on_ban_toggle(self, state):
        self.ban_enabled = state == Qt.Checked
        self.save_ban_config()


if __name__ == "__main__":
    app = TrayApp(sys.argv)
    sys.exit(app.exec())
