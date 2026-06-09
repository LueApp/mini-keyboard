#!/usr/bin/env python3
"""MiniPad HUD — always-on-top panel showing the macro pad's live key map,
with an in-panel remap editor.

View mode: reads the active mode from `keyd listen` and the key map from the
keyd config (via configmodel), highlighting the live mode.

Edit mode (click ✎): click a key to remap it (presets + custom), add/rename/
delete modes, set each mode's activation chord, then Save — which writes the
config via `pkexec /usr/local/sbin/minipad-apply` (validates + reloads + rolls
back on error). KDE Plasma 6 / Wayland, PyQt6.
"""
from __future__ import annotations

import os
import re
import shutil
import struct
import sys

from PyQt6.QtCore import (
    Qt, QProcess, QTimer, QObject, QSocketNotifier, pyqtSignal,
)
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

import configmodel
import presets

PHYS = configmodel.PHYS
CONFIG_PATHS = [
    "/etc/keyd/default.conf",
    os.path.join(os.path.dirname(__file__), "..", "config", "default.conf"),
]
APPLY_HELPER = "/usr/local/sbin/minipad-apply"

# Compact glyphs for the grid (override the wordier preset labels).
GLYPH = {
    "up": "↑", "down": "↓", "left": "←", "right": "→", "enter": "Enter",
    "backspace": "⌫", "C-c": "Copy", "C-v": "Paste", "C-x": "Cut", "C-z": "Undo",
    "C-S-z": "Redo", "C-s": "Save", "C-a": "All", "C-f": "Find", "C-w": "Close",
    "A-tab": "Switch", "C-t": "Tab+", "C-S-t": "Reopen", "playpause": "⏯",
    "nextsong": "⏭", "previoussong": "⏮", "volumeup": "Vol+",
    "volumedown": "Vol−", "mute": "Mute",
}


def label(value: str) -> str:
    if not value:
        return "·"
    return GLYPH.get(value, presets.label_for(value))


def load_config() -> configmodel.Config:
    path = next((p for p in CONFIG_PATHS if os.path.isfile(p)), None)
    if not path:
        return configmodel.Config(modes=[configmodel.Mode("apps")])
    try:
        return configmodel.parse(open(path, encoding="utf-8").read())
    except Exception:
        return configmodel.Config(modes=[configmodel.Mode("apps")])


# ── key editor dialog ────────────────────────────────────────────────────────
class KeyEditDialog(QDialog):
    def __init__(self, parent, mode_name, phys, current):
        super().__init__(parent)
        self.setWindowTitle(f"Remap  ·  {mode_name}  ·  key {phys}")
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"What should key <b>{phys}</b> do in "
                             f"<b>{mode_name}</b> mode?"))

        self.combo = QComboBox()
        self.combo.addItem("— pick a preset —", None)
        for group, items in presets.PRESETS:
            self.combo.addItem(f"——  {group}  ——", None)
            self.combo.model().item(self.combo.count() - 1).setEnabled(False)
            for lab, val in items:
                self.combo.addItem(f"   {lab}   ({val})", val)
        self.combo.activated.connect(self._pick)
        lay.addWidget(self.combo)

        self.field = QLineEdit(current or "")
        self.field.setPlaceholderText("keyd value: C-c · up · 5 · macro(hi enter)")
        lay.addWidget(self.field)
        hint = QLabel("Leave empty to unassign the key.")
        hint.setStyleSheet("color:#8b90a0;font-size:10px;")
        lay.addWidget(hint)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pick(self, idx):
        val = self.combo.itemData(idx)
        if val is not None:
            self.field.setText(val)

    def value(self) -> str:
        return self.field.text().strip()


# ── mode settings dialog (add / rename / chord / delete) ─────────────────────
class ModeDialog(QDialog):
    def __init__(self, parent, cfg: configmodel.Config, mode=None):
        super().__init__(parent)
        self.cfg = cfg
        self.mode = mode
        self.deleted = False
        is_base = mode is not None and mode.name == cfg.base
        self.setWindowTitle("Add mode" if mode is None else f"Mode · {mode.name}")
        self.setModal(True)
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("Mode name"))
        self.name = QLineEdit("" if mode is None else mode.name)
        lay.addWidget(self.name)

        lay.addWidget(QLabel("Activation chord (two keys pressed together)"))
        row = QHBoxLayout()
        self.k1, self.k2 = QComboBox(), QComboBox()
        for c in (self.k1, self.k2):
            c.addItems(PHYS)
        ch = (mode.chord if mode and len(mode.chord) == 2 else ["1", "3"])
        self.k1.setCurrentText(ch[0]); self.k2.setCurrentText(ch[1])
        row.addWidget(self.k1); row.addWidget(QLabel("+")); row.addWidget(self.k2)
        row.addStretch(1)
        lay.addLayout(row)

        if is_base:
            note = QLabel("This is the base mode (always on). It can't be deleted.")
            note.setStyleSheet("color:#8b90a0;font-size:10px;")
            lay.addWidget(note)

        bb = QDialogButtonBox()
        bb.addButton(QDialogButtonBox.StandardButton.Ok)
        bb.addButton(QDialogButtonBox.StandardButton.Cancel)
        if mode is not None and not is_base:
            delbtn = bb.addButton("Delete mode", QDialogButtonBox.ButtonRole.DestructiveRole)
            delbtn.clicked.connect(self._delete)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _delete(self):
        self.deleted = True
        self.accept()

    def _ok(self):
        name = self.name.text().strip()
        if not configmodel.NAME_RE.match(name):
            QMessageBox.warning(self, "Invalid",
                                "Mode name must be letters, digits, _ or - (max 32).")
            return
        if name.lower() in configmodel.RESERVED:
            QMessageBox.warning(self, "Invalid",
                                f"'{name}' is reserved by keyd — pick another name.")
            return
        if any(m.name == name and m is not self.mode for m in self.cfg.modes):
            QMessageBox.warning(self, "Invalid", f"A mode named '{name}' already exists.")
            return
        k1, k2 = self.k1.currentText(), self.k2.currentText()
        if k1 == k2:
            QMessageBox.warning(self, "Invalid", "Chord needs two different keys.")
            return
        pair = frozenset([k1, k2])
        clash = next((m for m in self.cfg.modes
                      if m is not self.mode and len(m.chord) == 2
                      and frozenset(m.chord) == pair), None)
        if clash:
            QMessageBox.warning(self, "Invalid",
                                f"Chord {k1}+{k2} is already used by '{clash.name}'.")
            return
        self.accept()

    def apply_to(self):
        """Mutate cfg per the dialog result. Returns the affected mode name."""
        if self.deleted and self.mode is not None:
            self.cfg.modes.remove(self.mode)
            return self.cfg.base
        chord = [self.k1.currentText(), self.k2.currentText()]
        name = self.name.text().strip()
        if self.mode is None:
            self.cfg.modes.append(configmodel.Mode(name=name, chord=chord, keys={}))
        else:
            old = self.mode.name
            self.mode.name = name
            self.mode.chord = chord
            if old == self.cfg.base:
                self.cfg.base = name
        return name


# ── key cell ─────────────────────────────────────────────────────────────────
class KeyCell(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, phys: str):
        super().__init__()
        self.phys = phys
        self.setObjectName("cell")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(0)
        self.idx = QLabel(phys)
        self.idx.setObjectName("idx")
        self.idx.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.act = QLabel("")
        self.act.setObjectName("act")
        self.act.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.act.setWordWrap(True)
        lay.addWidget(self.idx)
        lay.addWidget(self.act, 1)

    def set_action(self, text: str):
        self.act.setText(text)

    def mousePressEvent(self, ev):
        self.clicked.emit(self.phys)
        ev.accept()


# ── main panel ───────────────────────────────────────────────────────────────
class Hud(QWidget):
    # emitted when edit mode is entered/left (controller keeps it shown while True)
    editingChanged = pyqtSignal(bool)
    # emitted on any direct interaction with the panel (hover/click) — counts as
    # activity so the panel doesn't idle-hide while you're reading or dragging it
    interacted = pyqtSignal()

    BALL_D = 46                        # mini-ball diameter (idle/collapsed form)

    def __init__(self, cfg: configmodel.Config):
        super().__init__()
        self.cfg = cfg
        self.editing = False
        # visual state ("hidden"/"ball"/"panel") + current form; set before
        # _build()/refresh() because refresh() reads self._form.
        self._state = "hidden"
        self._form = "panel"
        self._interactive = False
        self.live_mode = cfg.base
        self.edit_mode = cfg.base          # which mode the editor is showing
        self.apply_proc = None
        try:
            op = float(os.environ.get("MINIPAD_OPACITY", "0.70"))
        except ValueError:
            op = 0.70
        self.bg_alpha = max(0, min(255, round(op * 255)))
        self.setWindowTitle("MiniPad HUD")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.pills: dict[str, QLabel] = {}
        self._build()
        self.refresh()
        self._init_visibility()

    # ----- construction -----
    def _build(self):
        # All panel content lives in self.body so it can be hidden in one move
        # when the HUD collapses to its mini-ball form.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.body = QWidget()
        outer.addWidget(self.body)

        root = QVBoxLayout(self.body)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.title = QLabel("mini pad")
        self.title.setObjectName("title")
        head.addWidget(self.title)
        head.addStretch(1)
        self.pills_box = QHBoxLayout()
        self.pills_box.setSpacing(4)
        head.addLayout(self.pills_box)
        self.edit_btn = QLabel("✎")
        self.edit_btn.setObjectName("tool")
        self.edit_btn.mousePressEvent = lambda e: self.toggle_edit()
        head.addSpacing(4)
        head.addWidget(self.edit_btn)
        close = QLabel("✕")
        close.setObjectName("tool")
        close.mousePressEvent = lambda e: QApplication.quit()
        head.addWidget(close)
        root.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(6)
        self.cells = {}
        for i, phys in enumerate(PHYS):
            cell = KeyCell(phys)
            cell.clicked.connect(self.on_cell_clicked)
            self.cells[phys] = cell
            grid.addWidget(cell, i // 3, i % 3)
        root.addLayout(grid)

        # edit toolbar (hidden in view mode)
        self.toolbar = QWidget()
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(6)
        self.mode_btn = QPushButton("⚙ Mode")
        self.mode_btn.clicked.connect(lambda: self.mode_settings(self.edit_mode))
        self.add_btn = QPushButton("＋ Mode")
        self.add_btn.clicked.connect(self.add_mode)
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("save")
        self.save_btn.clicked.connect(self.save)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_edit)
        for w in (self.mode_btn, self.add_btn):
            tb.addWidget(w)
        tb.addStretch(1)
        tb.addWidget(self.cancel_btn)
        tb.addWidget(self.save_btn)
        self.toolbar.setVisible(False)
        root.addWidget(self.toolbar)

        self.foot = QLabel("")
        self.foot.setObjectName("foot")
        self.foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.foot.setWordWrap(True)
        root.addWidget(self.foot)

        self.setStyleSheet(self._qss())
        self.setFixedWidth(300)

    def _qss(self) -> str:
        return """
        QWidget { background: transparent; color: #e8e8ec;
                  font-family: 'Inter','Noto Sans',sans-serif; }
        #title { font-size: 12px; font-weight: 600; color: #9aa0b0;
                 letter-spacing: 1px; }
        #pill { font-size: 10px; font-weight: 700; padding: 2px 7px;
                border-radius: 8px; color: #8b90a0; background: rgba(42,45,58,0.55); }
        #pill[active="true"] { color: #11131a; background: #7aa2f7; }
        #pill[edit="true"]   { color: #11131a; background: #9ece6a; }
        #tool { color: #6b7080; font-size: 12px; padding: 0 3px; }
        #tool:hover { color: #c0caf5; }
        #cell { background: rgba(35,38,52,0.45); border: 1px solid rgba(60,66,90,0.5);
                border-radius: 9px; min-height: 46px; }
        #cell[active="true"] { border: 1px solid #3a4368;
                               background: rgba(46,52,76,0.6); }
        #cell[edit="true"]   { border: 1px solid #9ece6a; }
        #idx { color: #565c70; font-size: 9px; font-weight: 700; }
        #act { color: #e8e8ec; font-size: 13px; font-weight: 600; }
        #foot { color: #565c70; font-size: 10px; }
        QPushButton { background: rgba(42,45,58,0.8); color:#c0caf5; border:0;
                      border-radius:7px; padding:4px 9px; font-size:11px; }
        QPushButton:hover { background: rgba(60,66,90,0.9); }
        QPushButton#save { background:#7aa2f7; color:#11131a; font-weight:700; }
        QPushButton#save:disabled { background:#3a4368; color:#8b90a0; }
        """

    def paintEvent(self, ev):
        from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
        from PyQt6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._form == "ball":
            d = min(self.width(), self.height())
            p.setBrush(QBrush(QColor(24, 26, 34, max(self.bg_alpha, 205))))
            p.setPen(QPen(QColor(122, 162, 247, 235), 2))     # 'pad ready' ring
            p.drawEllipse(QRectF(2, 2, d - 4, d - 4))
            p.setPen(QColor(210, 216, 248))
            f = self.font(); f.setPixelSize(int(d * 0.40)); f.setBold(True)
            p.setFont(f)
            letter = self.live_mode[:1].upper() if self.live_mode else "•"
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, letter)
            return
        edge = QColor(158, 206, 106, 220) if self.editing else \
            QColor(58, 63, 88, min(self.bg_alpha + 30, 255))
        p.setBrush(QBrush(QColor(24, 26, 34, self.bg_alpha)))
        p.setPen(edge)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 14, 14)
        super().paintEvent(ev)

    # ----- pills -----
    def rebuild_pills(self):
        while self.pills_box.count():
            w = self.pills_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.pills = {}
        for m in self.cfg.modes:
            pill = QLabel(m.name.upper())
            pill.setObjectName("pill")
            pill.setProperty("active", False)
            pill.setProperty("edit", False)
            pill.mousePressEvent = lambda e, n=m.name: self.on_pill(n)
            self.pills[m.name] = pill
            self.pills_box.addWidget(pill)

    def _restyle(self, w):
        w.style().unpolish(w)
        w.style().polish(w)

    def highlight(self):
        for name, pill in self.pills.items():
            pill.setProperty("active", (not self.editing) and name == self.live_mode)
            pill.setProperty("edit", self.editing and name == self.edit_mode)
            self._restyle(pill)

    # ----- rendering -----
    def render_keys(self, keys: dict[str, str]):
        for phys, cell in self.cells.items():
            cell.set_action(label(keys.get(phys, "")))
            cell.setProperty("active", (not self.editing) and phys in keys)
            cell.setProperty("edit", self.editing)
            self._restyle(cell)

    def refresh(self):
        """Rebuild pills + grid + footer from the current state."""
        self.rebuild_pills()
        if self.editing:
            self.title.setText("EDIT")
            mode = self.cfg.mode(self.edit_mode) or (self.cfg.modes[0] if self.cfg.modes else None)
            self.edit_mode = mode.name if mode else self.cfg.base
            self.render_keys(mode.keys if mode else {})
            self.foot.setText("click a key to remap · ⚙ rename/chord/delete · ＋ add")
            self.toolbar.setVisible(True)
        else:
            self.title.setText("mini pad")
            mode = self.cfg.mode(self.live_mode)
            self.render_keys(mode.keys if mode else {})
            hint = " · ".join(f"{'+'.join(m.chord)} {m.name}"
                              for m in self.cfg.modes if len(m.chord) == 2)
            self.foot.setText(hint)
            self.toolbar.setVisible(False)
        self.highlight()
        if self._form == "panel":
            self.adjustSize()
        else:
            self.update()              # repaint the ball (e.g. mode initial)

    # ----- live mode (view) -----
    def set_mode(self, name: str):
        self.live_mode = name
        if not self.editing:
            self.refresh()

    # ----- edit interactions -----
    def toggle_edit(self):
        if self.editing:
            self.cancel_edit()
        else:
            self.cfg = load_config()        # start from the on-disk truth
            self.editing = True
            self.edit_mode = self.cfg.base
            self.refresh()
            self.editingChanged.emit(True)

    def cancel_edit(self):
        self.editing = False
        self.cfg = load_config()
        self.refresh()
        self.editingChanged.emit(False)

    def on_pill(self, name):
        if self.editing:
            self.edit_mode = name
            self.refresh()

    def on_cell_clicked(self, phys):
        if not self.editing:
            return
        mode = self.cfg.mode(self.edit_mode)
        if not mode:
            return
        dlg = KeyEditDialog(self, mode.name, phys, mode.keys.get(phys, ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            val = dlg.value()
            if val and not configmodel.value_ok(val):
                QMessageBox.warning(self, "Not allowed",
                                    "That value has a control character or a command() "
                                    "action and was rejected.")
                return
            if val:
                mode.keys[phys] = val
            else:
                mode.keys.pop(phys, None)
            self.refresh()

    def add_mode(self):
        dlg = ModeDialog(self, self.cfg, None)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.edit_mode = dlg.apply_to()
            self.refresh()

    def mode_settings(self, name):
        mode = self.cfg.mode(name)
        if not mode:
            return
        dlg = ModeDialog(self, self.cfg, mode)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.edit_mode = dlg.apply_to()
            self.refresh()

    # ----- save via pkexec -----
    def save(self):
        if self.apply_proc is not None:          # a save is already in flight
            return
        if not os.path.exists(APPLY_HELPER):
            QMessageBox.warning(
                self, "Setup needed",
                "The apply helper isn't installed.\n\nRun  ./install.sh  once "
                "to enable saving from the panel (it installs\n" + APPLY_HELPER + ").")
            return
        try:
            text = configmodel.generate(self.cfg)
        except ValueError as e:                  # validation backstop
            QMessageBox.warning(self, "Can't save", str(e))
            return
        try:
            cache = os.path.expanduser("~/.cache/minipad")
            os.makedirs(cache, exist_ok=True)
            staged = os.path.join(cache, "staged.conf")
            with open(staged, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as e:
            QMessageBox.critical(self, "Can't save", f"Could not stage the config:\n{e}")
            return

        self.save_btn.setEnabled(False)
        self.save_btn.setText("Saving…")
        self.apply_proc = QProcess(self)
        self.apply_proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.apply_proc.finished.connect(lambda code, _st: self._saved(code))
        self.apply_proc.errorOccurred.connect(self._save_failed)
        self.apply_proc.start("pkexec", [APPLY_HELPER, staged])

    def _save_failed(self, err):
        # pkexec could not even start; finished() won't fire — recover here.
        if err == QProcess.ProcessError.FailedToStart and self.apply_proc is not None:
            self.apply_proc = None
            self.save_btn.setEnabled(True)
            self.save_btn.setText("Save")
            QMessageBox.critical(self, "Can't save",
                                 "Could not launch pkexec to apply the change.")

    def _saved(self, code):
        if self.apply_proc is None:
            return
        out = bytes(self.apply_proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.apply_proc = None
        self.save_btn.setEnabled(True)
        self.save_btn.setText("Save")
        if code == 0:
            was_editing = self.editing      # user may have left edit mid-save
            self.editing = False
            self.cfg = load_config()
            self.refresh()
            if self.window_listener:
                self.window_listener.set_modes(self.cfg)
            if was_editing:
                self.editingChanged.emit(False)
        elif code == 126 or code == 127:
            QMessageBox.information(self, "Cancelled",
                                   "Authentication cancelled — nothing changed.")
        else:
            QMessageBox.critical(self, "Rejected",
                                 "keyd rejected the config; rolled back.\n\n" + out[-800:])

    # ----- window plumbing -----
    window_listener = None

    def mousePressEvent(self, ev):
        if self._interactive:
            self.interacted.emit()
        if ev.button() == Qt.MouseButton.LeftButton:
            wh = self.windowHandle()
            if wh:
                wh.startSystemMove()

    def enterEvent(self, ev):
        # Hovering the full panel counts as activity so it won't collapse while
        # you read it. In ball form, hovering is NOT activity (so a mouse-sweep
        # over the ball doesn't pop it open) — only a click expands the ball.
        if self._interactive and self._form == "panel":
            self.interacted.emit()
        super().enterEvent(ev)

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        act = QAction("Edit…" if not self.editing else "Stop editing", self)
        act.triggered.connect(self.toggle_edit)
        menu.addAction(act)
        q = QAction("Quit", self)
        q.triggered.connect(QApplication.quit)
        menu.addAction(q)
        menu.exec(ev.globalPos())

    # ----- visual state: hidden / ball / panel -----
    # KWin/Wayland IGNORES windowOpacity AND setMask() for ARGB (translucent)
    # windows — verified on this box — so the only reliable hide is unmap via
    # hide(). The common idle transition is panel<->ball: both stay mapped and
    # just resize, so the dragged position is preserved. The window only truly
    # unmaps when the pad is unplugged (rare; a re-placement on replug is fine).
    def _init_visibility(self):
        self._interactive = False     # window mapped + accepting input?

    def _set_form(self, form: str):
        """Switch between the full 'panel' and the collapsed 'ball' (resizes)."""
        if form == self._form:
            return
        self._form = form
        if form == "ball":
            self.body.setVisible(False)
            self.setFixedSize(self.BALL_D, self.BALL_D)
        else:                          # panel: release the ball's fixed size
            self.body.setVisible(True)
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.setFixedWidth(300)
            self.adjustSize()          # height from content
        self.update()                  # repaint (circle vs rounded rect)

    def set_state(self, state: str):
        """state in {'hidden','ball','panel'} — driven by VisibilityController."""
        if state == self._state:
            return
        self._state = state
        if state == "hidden":
            self._interactive = False
            self.hide()
        else:
            self._set_form("ball" if state == "ball" else "panel")
            self._interactive = True
            if not self.isVisible():
                self.show()
            self.raise_()


# ── keyd listen -> active mode ───────────────────────────────────────────────
class Listener(QWidget):
    mode_changed = pyqtSignal(str)

    def __init__(self, cfg: configmodel.Config):
        super().__init__()
        self.keyd = shutil.which("keyd.rvaiya") or shutil.which("keyd")
        self.active: set[str] = set()
        self.set_modes(cfg)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_out)
        self.proc.finished.connect(
            lambda *_: (self.active.clear(), QTimer.singleShot(1000, self._start)))
        self._start()

    def set_modes(self, cfg: configmodel.Config):
        self.base = cfg.base
        self.nonbase = [m.name for m in cfg.modes if m.name != cfg.base]
        self.active = {n for n in self.active if n in self.nonbase}

    def _start(self):
        if self.keyd and self.proc.state() == QProcess.ProcessState.NotRunning:
            if shutil.which("sg"):
                self.proc.start("sg", ["keyd", "-c", f"exec {self.keyd} listen"])
            else:
                self.proc.start(self.keyd, ["listen"])

    def _current(self) -> str:
        for n in reversed(self.nonbase):     # one non-base active at a time
            if n in self.active:
                return n
        return self.base

    def _on_out(self):
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            sign, name = line[0], line[1:]
            if sign == "+" and name in self.nonbase:
                self.active.add(name)
            elif sign == "-" and name in self.nonbase:
                self.active.discard(name)
            elif sign == "/" and (name in self.nonbase or name == self.base):
                self.mode_changed.emit(name)
                continue
            self.mode_changed.emit(self._current())


# ── device presence (USB plug/unplug) ────────────────────────────────────────
def device_targets(cfg: configmodel.Config) -> list[tuple[str, str]]:
    """(vendor, product) hex pairs to look for in /proc/bus/input/devices,
    parsed from the keyd [ids] lines (e.g. 'k:4132:2107'). keyd class prefixes
    ('k:'/'m:'/'a:') and wildcards/excludes are ignored. An empty result means
    'can't pinpoint a device' — the watcher then treats the pad as always
    present (so connect-gating degrades to always-on rather than never-on)."""
    out: list[tuple[str, str]] = []
    for raw in cfg.ids:
        tok = raw.strip()
        if not tok or tok.startswith(("*", "-")):
            continue
        if len(tok) >= 2 and tok[1] == ":" and tok[0].isalpha():
            tok = tok[2:]                        # drop a 'k:' / 'm:' / 'a:' prefix
        parts = tok.split(":")
        if (len(parts) >= 2
                and re.fullmatch(r"[0-9a-fA-F]{1,4}", parts[0])
                and re.fullmatch(r"[0-9a-fA-F]{1,4}", parts[1])):
            out.append((parts[0].lower().zfill(4), parts[1].lower().zfill(4)))
    return out


class DeviceWatcher(QObject):
    """Polls /proc/bus/input/devices and reports the pad's connect/disconnect.
    Pure stdlib, no root. Polling (vs. udev) is fine: disconnect latency is the
    poll interval, and the first keypress after a plug shows the panel instantly
    via ActivityWatcher + an on-demand check()."""
    presenceChanged = pyqtSignal(bool)
    _I = re.compile(r"Vendor=([0-9a-fA-F]{4})\s+Product=([0-9a-fA-F]{4})")

    def __init__(self, targets, interval_ms: int = 1500, parent=None):
        super().__init__(parent)
        self.targets = set(targets)
        self.present: bool | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.check)

    def start(self):
        self.check()
        self.timer.start()

    def _scan(self) -> bool:
        if not self.targets:
            return True                          # can't pinpoint -> assume present
        try:
            with open("/proc/bus/input/devices", encoding="utf-8",
                      errors="replace") as fh:
                for line in fh:
                    if line.startswith("I:"):
                        m = self._I.search(line)
                        if m and (m.group(1).lower(), m.group(2).lower()) in self.targets:
                            return True
        except OSError:
            return bool(self.present)            # transient read error: hold state
        return False

    def check(self) -> bool:
        now = self._scan()
        if now != self.present:
            self.present = now
            self.presenceChanged.emit(now)
        return now


# ── pad activity (keyd virtual keyboard output) ──────────────────────────────
class ActivityWatcher(QObject):
    """Emits `activity` on every key-down from the 'keyd virtual keyboard'.
    Only the pad is grabbed by keyd, so its emitted keys are exactly the pad's
    activity. Event-driven via QSocketNotifier (no thread, no polling). Needs
    membership in the `input` group; if the device can't be opened, `available`
    stays False and the caller falls back to connect-only visibility."""
    activity = pyqtSignal()
    EV_KEY = 0x01
    FMT = "@llHHi"                               # input_event, 24 bytes
    SZ = struct.calcsize(FMT)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fd = -1
        self.notifier: QSocketNotifier | None = None
        self.available = False
        self.buf = b""
        self.retry = QTimer(self)
        self.retry.setInterval(3000)
        self.retry.timeout.connect(self._open)

    def start(self):
        self._open()
        if not self.available:
            self.retry.start()                  # keyd may not be up yet

    @staticmethod
    def _find_dev() -> str | None:
        try:
            with open("/proc/bus/input/devices", encoding="utf-8",
                      errors="replace") as fh:
                block = ""
                for line in fh:
                    if line.strip() == "":
                        if 'Name="keyd virtual keyboard"' in block:
                            for tok in block.split():
                                if tok.startswith("event"):
                                    return "/dev/input/" + tok
                        block = ""
                    else:
                        block += line
        except OSError:
            return None
        return None

    def _open(self):
        if self.available:
            return
        path = self._find_dev()
        if not path:
            return
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return
        self.fd = fd
        self.buf = b""
        self.notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._readable)
        self.available = True
        self.retry.stop()

    def _close(self):
        if self.notifier is not None:
            self.notifier.setEnabled(False)
            self.notifier.deleteLater()
            self.notifier = None
        if self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = -1
        self.available = False
        self.buf = b""

    def _readable(self):
        try:
            data = os.read(self.fd, self.SZ * 64)
        except BlockingIOError:
            return
        except OSError:                          # device error -> re-find later
            self._close()
            self.retry.start()
            return
        if not data:                             # EOF: keyd restarted/removed it
            self._close()
            self.retry.start()
            return
        self.buf += data
        n = len(self.buf) - (len(self.buf) % self.SZ)
        chunk, self.buf = self.buf[:n], self.buf[n:]
        hit = False
        for off in range(0, n, self.SZ):
            _, _, etype, _code, value = struct.unpack(self.FMT, chunk[off:off + self.SZ])
            if etype == self.EV_KEY and value == 1:    # key down
                hit = True
        if hit:
            self.activity.emit()


# ── visibility state machine ─────────────────────────────────────────────────
class VisibilityController(QObject):
    """Drives the HUD's visual state from pad presence + activity:

        disconnected                       -> hidden
        connected & idle                   -> mini ball
        connected & recently active        -> full panel
        editing                            -> full panel (even if disconnected)

    Activity = a pad key-down, a mode switch, or a click on the ball/panel. The
    ball re-expands the moment the pad is used (or you click it); the panel
    collapses back to the ball after MINIPAD_IDLE_SECS of no activity. With
    auto-hide off (or no activity source), it stays a full panel while connected.
    Tunables: MINIPAD_IDLE_SECS, MINIPAD_AUTOHIDE."""

    def __init__(self, hud: Hud, dev: DeviceWatcher, act: ActivityWatcher,
                 listener: Listener, parent=None):
        super().__init__(parent)
        self.hud = hud
        self.dev = dev
        self.present = False
        self.editing = False
        self.active_recent = False

        self.autohide = os.environ.get("MINIPAD_AUTOHIDE", "1").lower() \
            not in ("0", "false", "no", "off")
        try:
            secs = float(os.environ.get("MINIPAD_IDLE_SECS", "10"))
        except ValueError:
            secs = 10.0
        self.idle_ms = max(1000, int(secs * 1000))
        if self.autohide and not act.available:
            # No per-key signal would mean idle auto-hide gets stuck hidden.
            print("minipad-hud: can't read the keyd virtual keyboard "
                  "(are you in the 'input' group?) — idle auto-hide disabled; "
                  "panel will stay up while the pad is connected.",
                  file=sys.stderr)
            self.autohide = False

        self.idle = QTimer(self)
        self.idle.setSingleShot(True)
        self.idle.timeout.connect(self._idle_timeout)

        dev.presenceChanged.connect(self.on_presence)
        act.activity.connect(self.on_activity)
        listener.mode_changed.connect(self._on_mode)
        hud.interacted.connect(self.on_activity)
        hud.editingChanged.connect(self.on_editing)

    def _on_mode(self, _name):
        self.on_activity()

    def _arm_idle(self):
        self.active_recent = True
        if self.autohide:
            self.idle.start(self.idle_ms)

    def on_presence(self, present: bool):
        self.present = present
        if present:
            self._arm_idle()                     # a fresh plug counts as activity
        else:
            self.active_recent = False
            self.idle.stop()
        self._update()

    def on_activity(self):
        if not self.present:
            self.dev.check()                     # may flip present -> on_presence
            if not self.present:
                return                           # activity without the pad: ignore
        self._arm_idle()
        self._update()

    def on_editing(self, editing: bool):
        if editing == self.editing:         # ignore duplicate transitions
            return
        self.editing = editing
        if editing:
            self.idle.stop()
        elif self.present:
            self._arm_idle()
        self._update()

    def _idle_timeout(self):
        self.active_recent = False
        self._update()

    def _update(self):
        # editing -> full panel (never collapse mid-edit, even if unplugged);
        # connected & recently active -> panel; connected & idle -> mini ball;
        # disconnected -> hidden. (autohide off / no activity source -> panel.)
        if self.editing:
            state = "panel"
        elif self.present:
            state = "panel" if (not self.autohide or self.active_recent) else "ball"
        else:
            state = "hidden"
        self.hud.set_state(state)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("minipad-hud")
    app.setDesktopFileName("minipad-hud")

    cfg = load_config()
    hud = Hud(cfg)
    listener = Listener(cfg)
    hud.window_listener = listener
    listener.mode_changed.connect(hud.set_mode)

    dev = DeviceWatcher(device_targets(cfg), parent=hud)
    act = ActivityWatcher(parent=hud)
    act.start()
    # Keep a reference AND parent it to hud: an unreferenced, unparented QObject
    # gets garbage-collected, silently killing every signal connection that
    # drives the show/hide state machine. (parent= alone keeps it alive.)
    controller = VisibilityController(hud, dev, act, listener, parent=hud)

    # No unconditional show(): the controller maps the window (panel/ball) only
    # when the pad is present, and unmaps it when absent. The first presence
    # check drives the initial state.
    dev.start()
    assert controller is not None       # (referenced for the app's lifetime)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
