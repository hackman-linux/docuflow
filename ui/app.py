"""
DocuFlow Enterprise  ·  Word Processing Automation Module
PyQt6  ·  Cross-platform  ·  Green & White Enterprise Theme

Fixes
─────
1. Align Center/Right  — real Qt QTextBlockFormat paragraph alignment.
2. Add Separator       — inserted at the cursor line, not always at the bottom.
3. No scroll reset     — cursor + scroll position preserved after every action.
4. File upload ≤ 500 MB (txt, md, csv, html, json, xml, log, docx).
5. Optimised export    — same .docx extension, smaller file:
     • Images resampled/JPEG-encoded inside the zip (needs Pillow).
     • Unused XML parts stripped.
     • Full zlib recompression of every entry.
6. Responsive sidebar  — collapses to icon strip below 900 px window width.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QSplitter, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QMessageBox, QCheckBox, QStackedWidget, QFrame,
    QSizePolicy, QSpacerItem,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui  import (
    QFont, QTextBlockFormat, QTextCursor,
    QKeySequence, QShortcut, QResizeEvent,
)

from core import db
from core.processor import (
    align_left, align_center, align_right,
    remove_spaces, add_separator, add_separator_at, remove_separator,
    to_upper, to_lower, to_title, to_sentence,
    find_replace, stats,
)
from core.docx_io import (
    available as docx_ok, pillow_available,
    read_docx, write_docx,
    read_text_file,
    write_docx_optimised, optimise_existing_docx,
)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024   # 500 MB


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def ghost_btn(text, tooltip=""):
    b = QPushButton(text)
    b.setObjectName("ghost")
    if tooltip: b.setToolTip(tooltip)
    return b

def danger_btn(text):
    b = QPushButton(text); b.setObjectName("danger"); return b

def vline():
    f = QFrame(); f.setObjectName("VSep")
    f.setFrameShape(QFrame.Shape.VLine); return f

def make_label(text, obj=""):
    l = QLabel(text)
    if obj: l.setObjectName(obj)
    return l


# ═══════════════════════════════════════════════════════════════════════════════
#  EDITOR CURSOR / SCROLL UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _save_state(editor: QTextEdit):
    return editor.textCursor().position(), editor.verticalScrollBar().value()

def _restore_state(editor: QTextEdit, state):
    pos, scroll = state
    c = editor.textCursor()
    c.setPosition(min(pos, len(editor.toPlainText())))
    editor.setTextCursor(c)
    editor.verticalScrollBar().setValue(scroll)

def _apply_block_alignment(editor: QTextEdit, flag: Qt.AlignmentFlag):
    fmt = QTextBlockFormat(); fmt.setAlignment(flag)
    c = editor.textCursor()
    c.select(QTextCursor.SelectionType.Document)
    c.mergeBlockFormat(fmt)
    c.clearSelection(); editor.setTextCursor(c)

def _cursor_line(editor: QTextEdit) -> int:
    return editor.textCursor().blockNumber()


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR  (responsive)
# ═══════════════════════════════════════════════════════════════════════════════

COMPACT_WIDTH = 900

class Sidebar(QWidget):
    switched = pyqtSignal(str)
    PAGES = [
        ("editor",   "✦", "Editor"),
        ("sessions", "⊞", "Sessions & Backups"),
        ("log",      "≡", "Activity Log"),
    ]

    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self._btns: dict[str, QPushButton] = {}
        self._compact = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self._logo_wrap = QWidget(); self._logo_wrap.setObjectName("logo_wrap")
        lw = QVBoxLayout(self._logo_wrap)
        lw.setContentsMargins(22, 28, 22, 20); lw.setSpacing(3)
        self._logo_name = make_label("DocuFlow", "logo_name")
        self._logo_tag  = make_label("ENTERPRISE", "logo_tag")
        lw.addWidget(self._logo_name); lw.addWidget(self._logo_tag)
        lay.addWidget(self._logo_wrap)

        self._section = make_label("WORKSPACE", "nav_section_label")
        lay.addWidget(self._section)

        for key, icon, name in self.PAGES:
            btn = QPushButton(f"  {icon}   {name}")
            btn.setObjectName("NavBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._activate(k))
            self._btns[key] = btn; lay.addWidget(btn)

        lay.addStretch()
        self._footer = make_label("v1.1  ·  © 2025 Enterprise", "sidebar_footer")
        lay.addWidget(self._footer)
        self._activate("editor")

    def _activate(self, key):
        for k, b in self._btns.items():
            b.setProperty("active", "true" if k == key else "false")
            b.style().unpolish(b); b.style().polish(b)
        self.switched.emit(key)

    def set_compact(self, compact: bool):
        if compact == self._compact: return
        self._compact = compact
        self._logo_name.setVisible(not compact)
        self._logo_tag.setVisible(not compact)
        self._section.setVisible(not compact)
        self._footer.setVisible(not compact)
        for key, icon, name in self.PAGES:
            self._btns[key].setText(icon if compact else f"  {icon}   {name}")
        self.setFixedWidth(56 if compact else 210)


# ═══════════════════════════════════════════════════════════════════════════════
#  HEADER BAR
# ═══════════════════════════════════════════════════════════════════════════════

class Header(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Header"); self.setFixedHeight(58)
        lay = QHBoxLayout(self); lay.setContentsMargins(28, 0, 28, 0)
        self.title = make_label("Text Editor", "page_title")
        self.pill  = make_label("No session",  "session_pill")
        lay.addWidget(self.title); lay.addStretch(); lay.addWidget(self.pill)

    def set_title(self, t):   self.title.setText(t)
    def set_session(self, s): self.pill.setText(f"  ● {s}  " if s else "No session")


# ═══════════════════════════════════════════════════════════════════════════════
#  ACTION BAR
# ═══════════════════════════════════════════════════════════════════════════════

class ActionBar(QWidget):
    new_session      = pyqtSignal()
    import_docx_sig  = pyqtSignal()
    import_text_sig  = pyqtSignal()
    export_normal    = pyqtSignal()
    export_optimised = pyqtSignal()
    save_backup      = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("ActionBar"); self.setMinimumHeight(50)
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 4, 24, 4); lay.setSpacing(6)

        lay.addWidget(make_label("Session:"))
        self.combo = QComboBox(); self.combo.setPlaceholderText("Select a session…")
        self.combo.setMinimumWidth(140); lay.addWidget(self.combo)

        btn_new = ghost_btn("＋ New"); btn_new.clicked.connect(self.new_session)
        lay.addWidget(btn_new); lay.addWidget(vline())

        btn_imp = ghost_btn("⬆ Import .docx", "Import a Word document")
        btn_imp.clicked.connect(self.import_docx_sig); lay.addWidget(btn_imp)

        btn_txt = ghost_btn("⬆ Import File",
            "Import text file (txt, md, csv, html…) or .docx — up to 500 MB")
        btn_txt.clicked.connect(self.import_text_sig); lay.addWidget(btn_txt)

        lay.addWidget(vline())

        btn_exp = QPushButton("⬇ Export .docx")
        btn_exp.setToolTip("Export as standard Word document")
        btn_exp.clicked.connect(self.export_normal); lay.addWidget(btn_exp)

        tip = ("⬇ Export Optimised .docx\n\n"
               "Produces a standard .docx that opens in Word/LibreOffice,\n"
               "but with images resampled and all content recompressed —\n"
               "typically 60-90 % smaller than the original for image-heavy files.\n\n"
               + ("Pillow is installed ✔ — images will be resampled." if pillow_available()
                  else "Install Pillow for image optimisation: pip install Pillow"))
        btn_opt = ghost_btn("⬇ Export Optimised .docx", tip)
        btn_opt.clicked.connect(self.export_optimised); lay.addWidget(btn_opt)

        lay.addStretch()
        btn_bak = ghost_btn("🗄 Backup"); btn_bak.clicked.connect(self.save_backup)
        lay.addWidget(btn_bak)

    def refresh_sessions(self, sessions, active_id=None):
        self.combo.blockSignals(True); self.combo.clear()
        for s in sessions:
            self.combo.addItem(s["name"], userData=s["id"])
        if active_id is not None:
            for i in range(self.combo.count()):
                if self.combo.itemData(i) == active_id:
                    self.combo.setCurrentIndex(i); break
        self.combo.blockSignals(False)

    def current_session_id(self):
        i = self.combo.currentIndex()
        return self.combo.itemData(i) if i >= 0 else None

    def current_session_name(self):
        return self.combo.currentText() or ""


# ═══════════════════════════════════════════════════════════════════════════════
#  FORMAT BAR
# ═══════════════════════════════════════════════════════════════════════════════

class FormatBar(QWidget):
    acted = pyqtSignal(str)
    GROUPS = [
        ("ALIGN", [
            ("⬅ Left",   "align_left",   "Align all paragraphs left"),
            ("⊟ Center", "align_center", "Centre all paragraphs (real Qt alignment)"),
            ("➡ Right",  "align_right",  "Align all paragraphs right (real Qt alignment)"),
        ]),
        ("CLEAN", [
            ("⌫ Spaces",    "remove_spaces",   "Remove unnecessary spaces"),
            ("＋ Separator", "add_separator",   "Insert separator at cursor line"),
            ("✕ Separator", "remove_separator", "Remove all separator lines"),
        ]),
        ("CASE", [
            ("AA UPPER",    "to_upper",    "Convert to UPPERCASE"),
            ("aa lower",    "to_lower",    "Convert to lowercase"),
            ("Aa Title",    "to_title",    "Convert to Title Case"),
            ("A. Sentence", "to_sentence", "Convert to Sentence case"),
        ]),
    ]

    def __init__(self):
        super().__init__()
        self.setObjectName("FormatBar"); self.setMinimumHeight(48)
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(4)
        for i, (label, btns) in enumerate(self.GROUPS):
            lay.addWidget(make_label(label, "GroupLabel"))
            for name, key, tip in btns:
                b = QPushButton(name); b.setObjectName("FmtBtn")
                b.setToolTip(tip); b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _, k=key: self.acted.emit(k))
                lay.addWidget(b)
            if i < len(self.GROUPS) - 1:
                lay.addWidget(vline())
        lay.addStretch()


# ═══════════════════════════════════════════════════════════════════════════════
#  FIND & REPLACE BAR
# ═══════════════════════════════════════════════════════════════════════════════

class FindBar(QWidget):
    acted = pyqtSignal(str, str, bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("FindBar"); self.setFixedHeight(44)
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(8)
        lay.addWidget(make_label("FIND & REPLACE", "GroupLabel"))
        self.find_in    = QLineEdit(); self.find_in.setObjectName("FindInput")
        self.find_in.setPlaceholderText("Find text…")
        self.replace_in = QLineEdit(); self.replace_in.setObjectName("ReplaceInput")
        self.replace_in.setPlaceholderText("Replace with…")
        self.case_cb = QCheckBox("Match case"); self.case_cb.setObjectName("CaseCheck")
        btn = QPushButton("Replace All"); btn.setObjectName("ReplaceBtn")
        btn.clicked.connect(self._go); self.find_in.returnPressed.connect(self._go)
        lay.addWidget(self.find_in); lay.addWidget(make_label("→"))
        lay.addWidget(self.replace_in); lay.addWidget(self.case_cb)
        lay.addWidget(btn); lay.addStretch()

    def _go(self):
        self.acted.emit(self.find_in.text(), self.replace_in.text(), self.case_cb.isChecked())


# ═══════════════════════════════════════════════════════════════════════════════
#  STATUS BAR
# ═══════════════════════════════════════════════════════════════════════════════

class StatusBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("StatusBar"); self.setFixedHeight(30)
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(22)
        self._w  = make_label("Words: 0", "StatLabel")
        self._c  = make_label("Chars: 0", "StatLabel")
        self._l  = make_label("Lines: 1", "StatLabel")
        self._fl = make_label("",         "FlashLabel")
        for w in (self._w, self._c, self._l): lay.addWidget(w)
        lay.addStretch(); lay.addWidget(self._fl)
        self._timer = QTimer(singleShot=True)
        self._timer.timeout.connect(lambda: self._fl.setText(""))

    def update(self, text):
        s = stats(text)
        self._w.setText(f"Words: {s['words']}")
        self._c.setText(f"Chars: {s['chars']}")
        self._l.setText(f"Lines: {s['lines']}")

    def flash(self, msg, ms=3000):
        self._fl.setText(msg); self._timer.start(ms)


# ═══════════════════════════════════════════════════════════════════════════════
#  EDITOR PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class EditorPage(QWidget):
    session_changed = pyqtSignal(str)

    _ALIGN_MAP = {
        "align_left":   Qt.AlignmentFlag.AlignLeft,
        "align_center": Qt.AlignmentFlag.AlignCenter,
        "align_right":  Qt.AlignmentFlag.AlignRight,
    }

    def __init__(self, header: Header):
        super().__init__()
        self.setObjectName("PageArea")
        self._header     = header
        self._undo: list[str] = []
        self._active_id  = None
        self._source_path: str | None = None   # path of the last imported .docx

        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self.action_bar = ActionBar()
        self.action_bar.new_session.connect(self._new_session)
        self.action_bar.import_docx_sig.connect(self._import_docx)
        self.action_bar.import_text_sig.connect(self._import_text)
        self.action_bar.export_normal.connect(self._export_normal)
        self.action_bar.export_optimised.connect(self._export_optimised)
        self.action_bar.save_backup.connect(self._backup)
        self.action_bar.combo.currentIndexChanged.connect(self._session_selected)
        lay.addWidget(self.action_bar)

        self.fmt_bar = FormatBar()
        self.fmt_bar.acted.connect(self._format)
        lay.addWidget(self.fmt_bar)

        self.find_bar = FindBar()
        self.find_bar.acted.connect(self._find_replace)
        lay.addWidget(self.find_bar)

        self.editor = QTextEdit()
        self.editor.setObjectName("Editor")
        self.editor.setPlaceholderText(
            "Paste or type your text here — or import a file above.\n\n"
            "Use the toolbar to align, clean, or transform your text."
        )
        self.editor.textChanged.connect(self._text_changed)
        lay.addWidget(self.editor, stretch=1)

        self.status = StatusBar()
        lay.addWidget(self.status)
        self._refresh_sessions()

    # ── session ──────────────────────────────────────────────────────────────

    def _refresh_sessions(self, keep_id=None):
        sessions = db.get_sessions()
        self.action_bar.refresh_sessions(sessions, keep_id or self._active_id)
        if self._active_id is None and sessions:
            self._active_id = sessions[0]["id"]

    def _session_selected(self, idx):
        sid = self.action_bar.current_session_id()
        if sid is not None:
            self._active_id = sid
            name = self.action_bar.current_session_name()
            self._header.set_session(name)
            db.log("SESSION_SWITCHED", name, sid)

    def _new_session(self):
        dlg = NameDialog("New Session", "Session name:", self)
        if dlg.exec() and dlg.value().strip():
            name = dlg.value().strip()
            sid  = db.create_session(name)
            db.log("SESSION_CREATED", name, sid)
            self._active_id = sid
            self._refresh_sessions(sid)
            self._header.set_session(name)
            self.status.flash("✦ Session created")

    # ── undo / cursor-safe update ─────────────────────────────────────────────

    def _push_undo(self):
        self._undo.append(self.editor.toPlainText())
        if len(self._undo) > 60: self._undo.pop(0)

    def undo(self):
        if self._undo:
            st = _save_state(self.editor)
            self.editor.blockSignals(True)
            self.editor.setPlainText(self._undo.pop())
            self.editor.blockSignals(False)
            _restore_state(self.editor, st)
            self.status.update(self.editor.toPlainText())
            self.status.flash("↩ Undone")

    def _set_text(self, new_text: str):
        """Replace editor content preserving scroll + cursor position."""
        st = _save_state(self.editor)
        self.editor.blockSignals(True)
        self.editor.setPlainText(new_text)
        self.editor.blockSignals(False)
        _restore_state(self.editor, st)

    # ── format ───────────────────────────────────────────────────────────────

    FN = {
        "remove_spaces":    remove_spaces,
        "remove_separator": remove_separator,
        "to_upper":         to_upper,
        "to_lower":         to_lower,
        "to_title":         to_title,
        "to_sentence":      to_sentence,
    }

    def _format(self, key: str):
        text = self.editor.toPlainText()
        if not text.strip(): return
        self._push_undo()

        if key in self._ALIGN_MAP:
            _apply_block_alignment(self.editor, self._ALIGN_MAP[key])

        elif key == "add_separator":
            new = add_separator_at(text, _cursor_line(self.editor))
            self._set_text(new)
            self.status.update(new)

        else:
            new = self.FN[key](text)
            self._set_text(new)
            self.status.update(new)

        db.log("FORMAT", key, self._active_id)
        self.status.flash("✔ Applied")

    def _find_replace(self, find, replace, case):
        if not find: return
        text = self.editor.toPlainText()
        self._push_undo()
        new = find_replace(text, find, replace, case)
        self._set_text(new)
        self.status.update(new)
        db.log("REPLACE", f"'{find}' → '{replace}'", self._active_id)
        self.status.flash("✔ Replace done")

    def _text_changed(self):
        self.status.update(self.editor.toPlainText())

    # ── import ───────────────────────────────────────────────────────────────

    def _import_docx(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Word Document", "",
            "Word Documents (*.docx);;All Files (*)"
        )
        if not path: return
        if not docx_ok():
            QMessageBox.critical(self, "Error",
                "python-docx not installed.\nRun: pip install python-docx"); return
        try:
            self._push_undo()
            text = read_docx(path)
            self._source_path = path          # remember for optimised export
            self._set_text(text)
            db.log("IMPORT", os.path.basename(path), self._active_id)
            sz = os.path.getsize(path) / 1024
            self.status.flash(f"⬆ Imported: {os.path.basename(path)}  ({sz:.0f} KB)")
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))

    def _import_text(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import File", "",
            "Text & Document Files (*.txt *.md *.csv *.html *.htm *.json *.xml *.log *.docx);;"
            "All Files (*)"
        )
        if not path: return

        size = os.path.getsize(path)
        if size > MAX_UPLOAD_BYTES:
            QMessageBox.critical(self, "File too large",
                f"The selected file is {size / 1_048_576:.1f} MB.\n"
                "Maximum allowed size is 500 MB."); return

        ext = os.path.splitext(path)[1].lower()
        try:
            self._push_undo()
            if ext == ".docx" and docx_ok():
                text = read_docx(path)
                self._source_path = path
            else:
                text, images = read_text_file(path)
                self._source_path = None      # text-only; no image source file
                if images:
                    self.status.flash(f"  {len(images)} embedded image(s) found in file")
            self._set_text(text)
            db.log("IMPORT", os.path.basename(path), self._active_id)
            self.status.flash(
                f"⬆ Imported: {os.path.basename(path)}  ({size / 1024:.0f} KB)"
            )
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))

    # ── export ───────────────────────────────────────────────────────────────

    def _export_normal(self):
        text = self.editor.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "Nothing to export", "The editor is empty."); return
        if not docx_ok():
            QMessageBox.critical(self, "Error",
                "python-docx not installed.\nRun: pip install python-docx"); return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as Word Document", "document.docx",
            "Word Documents (*.docx)"
        )
        if not path: return
        try:
            write_docx(text, path)
            db.log("EXPORT", os.path.basename(path), self._active_id)
            sz = os.path.getsize(path) / 1024
            self.status.flash(f"⬇ Exported: {os.path.basename(path)}  ({sz:.0f} KB)")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _export_optimised(self):
        """
        Export an optimised .docx:
        - If the user imported a .docx, run optimise_existing_docx() on the
          original file — this preserves ALL embedded images and compresses them.
        - Otherwise (text typed / pasted / imported from txt), run
          write_docx_optimised() which builds a fresh doc and recompresses it.

        The result is always a valid .docx with the same extension.
        """
        text = self.editor.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "Nothing to export", "The editor is empty."); return
        if not docx_ok():
            QMessageBox.critical(self, "Error",
                "python-docx not installed.\nRun: pip install python-docx"); return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Optimised Word Document", "document_optimised.docx",
            "Word Documents (*.docx)"
        )
        if not path: return

        try:
            if self._source_path and os.path.exists(self._source_path):
                # Heavy path — original file has images; optimise it directly
                stats_d = optimise_existing_docx(self._source_path, path)
            else:
                # Light path — built from text only
                stats_d = write_docx_optimised(text, path)

            orig = stats_d["original_kb"]
            final = stats_d["final_kb"]
            imgs  = stats_d["images_processed"]
            saved_pct = max(0, (1 - final / orig) * 100) if orig else 0

            img_note = f", {imgs} image(s) resampled" if imgs else ""
            db.log("EXPORT_OPTIMISED",
                   f"{os.path.basename(path)} | {orig:.0f} KB → {final:.0f} KB{img_note}",
                   self._active_id)
            self.status.flash(
                f"⬇ Optimised: {os.path.basename(path)}  "
                f"{orig:.0f} KB → {final:.0f} KB  ({saved_pct:.0f}% smaller{img_note})"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    # ── backup ────────────────────────────────────────────────────────────────

    def _backup(self):
        sid = self._active_id
        if not sid:
            QMessageBox.information(self, "No session",
                "Create or select a session first."); return
        text = self.editor.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "Nothing to save", "The editor is empty."); return
        s = stats(text)
        label = f"{s['words']} words  ·  {s['lines']} lines"
        db.save_backup(sid, text, label)
        db.log("BACKUP", label, sid)
        self.status.flash("🗄 Backup saved")

    def load_text(self, text):
        self._push_undo(); self._set_text(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  SESSIONS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class SessionsPage(QWidget):
    restore = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("PageArea")
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 24, 24, 24); lay.setSpacing(20)

        left = QVBoxLayout(); left.setSpacing(10)
        left.addWidget(make_label("SESSIONS", "CardTitle"))
        self.sess_list = QListWidget(); self.sess_list.setObjectName("SessionList")
        self.sess_list.currentRowChanged.connect(self._session_selected)
        left.addWidget(self.sess_list)
        row = QHBoxLayout(); row.setSpacing(8)
        del_btn = danger_btn("🗑  Delete"); del_btn.clicked.connect(self._delete_session)
        ref_btn = ghost_btn("↺  Refresh"); ref_btn.clicked.connect(self.refresh)
        row.addWidget(del_btn); row.addWidget(ref_btn); left.addLayout(row)

        right = QVBoxLayout(); right.setSpacing(10)
        right.addWidget(make_label("BACKUPS  ·  SELECT TO PREVIEW & RESTORE", "CardTitle"))
        self.preview = QTextEdit(); self.preview.setObjectName("Editor")
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select a backup to preview its content…")
        self.preview.setMaximumHeight(180)
        self.backup_list = QListWidget(); self.backup_list.setObjectName("BackupList")
        self.backup_list.currentRowChanged.connect(self._backup_selected)
        restore_btn = QPushButton("↩  Restore Selected Backup to Editor")
        restore_btn.clicked.connect(self._restore)
        right.addWidget(self.backup_list)
        right.addWidget(make_label("PREVIEW", "CardTitle"))
        right.addWidget(self.preview)
        right.addWidget(restore_btn)

        lw = QWidget(); lw.setLayout(left)
        rw = QWidget(); rw.setLayout(right)
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(lw); sp.addWidget(rw); sp.setSizes([280, 620])
        lay.addWidget(sp)
        self.refresh()

    def refresh(self):
        self.sess_list.clear()
        for s in db.get_sessions():
            item = QListWidgetItem(f"  📁  {s['name']}   ·   {s['updated_at']}")
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.sess_list.addItem(item)

    def _session_selected(self, row):
        self.backup_list.clear(); self.preview.clear()
        item = self.sess_list.item(row)
        if not item: return
        for b in db.get_backups(item.data(Qt.ItemDataRole.UserRole)):
            bi = QListWidgetItem(f"  💾  {b['saved_at']}   ·   {b['label']}")
            bi.setData(Qt.ItemDataRole.UserRole, b["id"])
            self.backup_list.addItem(bi)

    def _backup_selected(self, row):
        item = self.backup_list.item(row)
        if not item: return
        b = db.get_backup(item.data(Qt.ItemDataRole.UserRole))
        if b:
            self.preview.setPlainText(
                b["content"][:800] + ("…" if len(b["content"]) > 800 else "")
            )

    def _restore(self):
        item = self.backup_list.currentItem()
        if not item: return
        b = db.get_backup(item.data(Qt.ItemDataRole.UserRole))
        if not b: return
        if QMessageBox.question(
            self, "Restore Backup", "Load this backup into the editor?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.restore.emit(b["content"])
            db.log("RESTORE", f"Backup {b['id']}")

    def _delete_session(self):
        item = self.sess_list.currentItem()
        if not item: return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(
            self, "Delete Session",
            "Delete this session and all its backups? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            db.delete_session(sid); db.log("SESSION_DELETED", f"id={sid}"); self.refresh()


# ═══════════════════════════════════════════════════════════════════════════════
#  LOG PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class LogPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("PageArea")
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 24, 24, 24); lay.setSpacing(12)
        hdr = QHBoxLayout()
        hdr.addWidget(make_label("ACTIVITY LOG", "CardTitle")); hdr.addStretch()
        ref = ghost_btn("↺  Refresh"); ref.clicked.connect(self.refresh); hdr.addWidget(ref)
        lay.addLayout(hdr)
        self.list = QListWidget(); self.list.setObjectName("LogList"); lay.addWidget(self.list)
        self.refresh()

    ICONS = {
        "FORMAT": "🔧", "IMPORT": "⬆", "EXPORT": "⬇", "EXPORT_OPTIMISED": "⬇✦",
        "BACKUP": "🗄", "RESTORE": "↩", "REPLACE": "✏",
        "SESSION_CREATED": "✦", "SESSION_DELETED": "🗑", "SESSION_SWITCHED": "⊞",
    }

    def refresh(self):
        self.list.clear()
        for l in db.get_logs():
            icon   = self.ICONS.get(l["action"], "·")
            detail = f"   {l['detail']}" if l["detail"] else ""
            self.list.addItem(QListWidgetItem(
                f"  {icon}  {l['at']}    {l['action']}{detail}"
            ))


# ═══════════════════════════════════════════════════════════════════════════════
#  NAME DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class NameDialog(QDialog):
    def __init__(self, title, label, parent=None):
        super().__init__(parent); self.setWindowTitle(title); self.setMinimumWidth(340)
        lay = QVBoxLayout(self); lay.setSpacing(12)
        lay.addWidget(QLabel(label))
        self._inp = QLineEdit(); lay.addWidget(self._inp)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def value(self): return self._inp.text()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DocuFlow Enterprise")
        self.resize(1300, 840); self.setMinimumSize(600, 480)
        self._build()

    def _build(self):
        root = QWidget(); root_lay = QHBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0); root_lay.setSpacing(0)
        self.setCentralWidget(root)

        self.sidebar = Sidebar(); self.sidebar.switched.connect(self._switch)
        root_lay.addWidget(self.sidebar)

        content = QWidget(); c_lay = QVBoxLayout(content)
        c_lay.setContentsMargins(0, 0, 0, 0); c_lay.setSpacing(0)
        self.header = Header(); c_lay.addWidget(self.header)

        self.stack         = QStackedWidget()
        self.editor_page   = EditorPage(self.header)
        self.sessions_page = SessionsPage()
        self.log_page      = LogPage()
        self.sessions_page.restore.connect(self._do_restore)
        self.stack.addWidget(self.editor_page)
        self.stack.addWidget(self.sessions_page)
        self.stack.addWidget(self.log_page)
        c_lay.addWidget(self.stack)
        root_lay.addWidget(content, stretch=1)

        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.editor_page.undo)

    PAGE_MAP = {"editor": 0, "sessions": 1, "log": 2}
    TITLES   = {"editor": "Text Editor", "sessions": "Sessions & Backups", "log": "Activity Log"}

    def _switch(self, key):
        self.stack.setCurrentIndex(self.PAGE_MAP[key])
        self.header.set_title(self.TITLES[key])
        if key == "sessions":
            self.sessions_page.refresh(); self.editor_page._refresh_sessions()
        elif key == "log":
            self.log_page.refresh()

    def _do_restore(self, text):
        self.editor_page.load_text(text)
        self.sidebar._activate("editor"); self._switch("editor")

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.sidebar.set_compact(event.size().width() < COMPACT_WIDTH)


# ═══════════════════════════════════════════════════════════════════════════════
#  BOOTSTRAP
# ═══════════════════════════════════════════════════════════════════════════════

def _load_qss(app):
    qss = os.path.join(os.path.dirname(__file__), "styles", "theme.qss")
    if os.path.exists(qss): 
        with open(qss) as f: app.setStyleSheet(f.read())

def run():
    db.init()
    app = QApplication(sys.argv)
    app.setApplicationName("DocuFlow Enterprise")
    _load_qss(app)
    win = MainWindow(); win.show()
    sys.exit(app.exec())