"""
DocuFlow Enterprise v2  ·  Word Processing Automation Module
PyQt6 · Cross-platform · Green & White Enterprise Theme

New in v2
──────────
• Login / Registration — every user has their own account; sessions are private.
• Rich-text formatting — Bold (Ctrl+B), Italic (Ctrl+I), Underline (Ctrl+U).
• Font controls — family picker (Times New Roman, Calibri, Arial, Georgia,
  Courier New) + size spin-box + A+ / A- buttons.
• Licence system — 2 000 FCFA / month subscription. Users enter a licence key
  (obtained after payment) to activate their account each month. A banner in the
  header shows days remaining. Expired → read-only mode with a renewal prompt.
"""

import sys, os, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QSplitter, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QMessageBox, QCheckBox, QStackedWidget, QFrame,
    QSizePolicy, QSpinBox, QFormLayout, QGroupBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui  import (
    QFont, QTextBlockFormat, QTextCursor, QTextCharFormat,
    QKeySequence, QShortcut, QResizeEvent,
    QImage, QPixmap, QTextImageFormat, QFontDatabase,
    QColor,
)

from core import db
from core.processor import (
    align_left, align_center, align_right,
    remove_spaces, add_separator, add_separator_at, remove_separator,
    to_upper, to_lower, to_title, to_sentence,
    find_replace, stats, PAGE_BREAK_MARKER,
)
from core.docx_io import (
    available as docx_ok, pillow_available,
    read_docx, write_docx,
    read_text_file,
    write_docx_optimised, optimise_existing_docx,
)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024   # 500 MB
COMPACT_WIDTH    = 900                  # px — sidebar collapses below this
LICENCE_PRICE    = "2 000 FCFA"
GRACE_DAYS       = 3                    # days after expiry before read-only kicks in

# Payment instructions shown in the Licence dialog
PAYMENT_INFO = (
    "To renew your DocuFlow Enterprise licence (2 000 FCFA / month):\n\n"
    "  1.  Send 2 000 FCFA via Orange Money or MTN MoMo to:\n"
    "         +237 6XX XXX XXX\n"
    "      Reference: your username\n\n"
    "  2.  Send proof of payment by WhatsApp or email.\n"
    "      You will receive a licence key within 24 hours.\n\n"
    "  3.  Enter the key below and click Activate."
)


# ═══════════════════════════════════════════════════════════════════════════════
#  SMALL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def ghost_btn(text, tooltip=""):
    b = QPushButton(text); b.setObjectName("ghost")
    if tooltip: b.setToolTip(tooltip)
    return b

def danger_btn(text):
    b = QPushButton(text); b.setObjectName("danger"); return b

def fmt_btn(text, tooltip="", checkable=False):
    b = QPushButton(text); b.setObjectName("FmtBtn")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip: b.setToolTip(tooltip)
    if checkable: b.setCheckable(True)
    return b

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

def _save_state(editor):
    return editor.textCursor().position(), editor.verticalScrollBar().value()

def _restore_state(editor, state):
    pos, scroll = state
    c = editor.textCursor()
    c.setPosition(min(pos, len(editor.toPlainText())))
    editor.setTextCursor(c); editor.verticalScrollBar().setValue(scroll)

def _apply_block_alignment(editor, flag):
    fmt = QTextBlockFormat(); fmt.setAlignment(flag)
    c = editor.textCursor()
    c.select(QTextCursor.SelectionType.Document)
    c.mergeBlockFormat(fmt); c.clearSelection(); editor.setTextCursor(c)

def _cursor_line(editor) -> int:
    return editor.textCursor().blockNumber()


# ═══════════════════════════════════════════════════════════════════════════════
#  LOGIN / REGISTER PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class AuthPage(QWidget):
    """Full-screen login / registration screen shown before the main app."""
    logged_in = pyqtSignal(dict)   # emits user dict on success

    def __init__(self):
        super().__init__()
        self.setObjectName("AuthPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left brand panel + right form panel ──────────────────────────────
        body = QHBoxLayout(); body.setSpacing(0); body.setContentsMargins(0,0,0,0)

        # Brand / left side
        brand = QWidget(); brand.setObjectName("AuthBrand")
        brand.setFixedWidth(380)
        bl = QVBoxLayout(brand); bl.setContentsMargins(48, 60, 48, 40)
        bl.setSpacing(16)
        bl.addStretch(2)
        logo = make_label("DocuFlow", "AuthLogo")
        tag  = make_label("ENTERPRISE", "AuthLogoTag")
        bl.addWidget(logo); bl.addWidget(tag)
        bl.addSpacing(28)
        bl.addWidget(make_label(
            "Professional word-processing\nautomation for your enterprise.",
            "AuthTagline"
        ))
        bl.addStretch(3)
        bl.addWidget(make_label("v2.0  ·  © 2025", "AuthFooter"))
        body.addWidget(brand)

        # Form / right side
        form_wrap = QWidget(); form_wrap.setObjectName("AuthFormWrap")
        fl = QVBoxLayout(form_wrap); fl.setContentsMargins(60, 0, 60, 0)
        fl.setSpacing(0); fl.addStretch(2)

        self._title = make_label("Sign in to DocuFlow", "AuthFormTitle")
        fl.addWidget(self._title)
        fl.addSpacing(8)
        self._sub = make_label("Enter your credentials to continue.", "AuthSub")
        fl.addWidget(self._sub)
        fl.addSpacing(32)

        # Username
        fl.addWidget(make_label("Username", "AuthFieldLabel"))
        fl.addSpacing(6)
        self._user = QLineEdit(); self._user.setObjectName("AuthInput")
        self._user.setPlaceholderText("your_username")
        fl.addWidget(self._user)
        fl.addSpacing(16)

        # Password
        fl.addWidget(make_label("Password", "AuthFieldLabel"))
        fl.addSpacing(6)
        self._pass = QLineEdit(); self._pass.setObjectName("AuthInput")
        self._pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass.setPlaceholderText("••••••••")
        self._pass.returnPressed.connect(self._do_action)
        fl.addWidget(self._pass)
        fl.addSpacing(28)

        # Action button
        self._action_btn = QPushButton("Sign In")
        self._action_btn.setObjectName("AuthBtn")
        self._action_btn.clicked.connect(self._do_action)
        fl.addWidget(self._action_btn)
        fl.addSpacing(18)

        # Toggle link
        self._toggle_btn = QPushButton("Don't have an account? Create one")
        self._toggle_btn.setObjectName("AuthToggle")
        self._toggle_btn.setFlat(True)
        self._toggle_btn.clicked.connect(self._toggle_mode)
        fl.addWidget(self._toggle_btn)

        self._error = make_label("", "AuthError")
        self._error.setWordWrap(True)
        fl.addSpacing(12); fl.addWidget(self._error)

        fl.addStretch(3)
        body.addWidget(form_wrap, stretch=1)
        root.addLayout(body, stretch=1)

        self._mode = "login"   # or "register"

    # ── mode toggle ──────────────────────────────────────────────────────────
    def _toggle_mode(self):
        if self._mode == "login":
            self._mode = "register"
            self._title.setText("Create your account")
            self._sub.setText("Choose a username and a strong password.")
            self._action_btn.setText("Create Account")
            self._toggle_btn.setText("Already have an account? Sign in")
        else:
            self._mode = "login"
            self._title.setText("Sign in to DocuFlow")
            self._sub.setText("Enter your credentials to continue.")
            self._action_btn.setText("Sign In")
            self._toggle_btn.setText("Don't have an account? Create one")
        self._error.setText("")
        self._user.clear(); self._pass.clear()

    # ── actions ──────────────────────────────────────────────────────────────
    def _do_action(self):
        u = self._user.text().strip()
        p = self._pass.text()
        self._error.setText("")
        if not u or not p:
            self._error.setText("Please enter both username and password."); return

        if self._mode == "login":
            user = db.authenticate(u, p)
            if user:
                self.logged_in.emit(user)
            else:
                self._error.setText("Incorrect username or password.")
        else:
            if len(u) < 3:
                self._error.setText("Username must be at least 3 characters."); return
            if len(p) < 6:
                self._error.setText("Password must be at least 6 characters."); return
            uid = db.create_user(u, p)
            if uid is None:
                self._error.setText("That username is already taken.")
            else:
                user = db.get_user(uid)
                self.logged_in.emit(user)


# ═══════════════════════════════════════════════════════════════════════════════
#  LICENCE DIALOG  (shown when user clicks on licence banner or key expired)
# ═══════════════════════════════════════════════════════════════════════════════

class LicenceDialog(QDialog):
    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DocuFlow Enterprise — Licence")
        self.setMinimumWidth(500)
        self._user = user
        self._activated = False

        lay = QVBoxLayout(self); lay.setSpacing(16); lay.setContentsMargins(28,28,28,28)

        # Status banner
        days = db.licence_days_remaining(user["id"])
        lic  = db.get_active_licence(user["id"])
        if lic:
            until = datetime.datetime.strptime(lic["valid_until"], "%Y-%m-%d %H:%M:%S")
            status_text = f"✔  Licence active — expires {until.strftime('%d %b %Y')}  ({days} days remaining)"
            status_obj  = "LicenceActive"
        else:
            status_text = "✖  No active licence — the application is in read-only mode."
            status_obj  = "LicenceExpired"

        status_lbl = make_label(status_text, status_obj)
        status_lbl.setWordWrap(True)
        lay.addWidget(status_lbl)

        # Payment info box
        info = QLabel(PAYMENT_INFO)
        info.setWordWrap(True); info.setObjectName("LicenceInfo")
        lay.addWidget(info)

        # Key entry
        key_row = QHBoxLayout()
        self._key_in = QLineEdit(); self._key_in.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self._key_in.setObjectName("AuthInput")
        activate_btn = QPushButton("Activate Key")
        activate_btn.clicked.connect(self._activate)
        key_row.addWidget(self._key_in, stretch=1)
        key_row.addWidget(activate_btn)
        lay.addLayout(key_row)

        self._msg = make_label("", "AuthError")
        lay.addWidget(self._msg)

        close_btn = ghost_btn("Close")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _activate(self):
        key = self._key_in.text().strip()
        if not key:
            self._msg.setText("Please enter a licence key."); return
        result = db.activate_licence(self._user["id"], key)
        if result["ok"]:
            self._msg.setObjectName("LicenceActive")
            self._msg.setText(f"✔  Activated! Valid until {result['until']}.")
            self._activated = True
        else:
            self._msg.setObjectName("AuthError")
            self._msg.setText(f"✖  {result['reason']}")
        self._msg.style().unpolish(self._msg); self._msg.style().polish(self._msg)

    def was_activated(self) -> bool:
        return self._activated


# ═══════════════════════════════════════════════════════════════════════════════
#  LICENCE BANNER  (thin strip in the header)
# ═══════════════════════════════════════════════════════════════════════════════

class LicenceBanner(QWidget):
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("LicenceBanner")
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self); lay.setContentsMargins(28, 0, 28, 0)
        self._lbl = make_label("", "BannerLabel")
        lay.addStretch(); lay.addWidget(self._lbl); lay.addStretch()

    def update_status(self, user_id: int):
        days = db.licence_days_remaining(user_id)
        lic  = db.get_active_licence(user_id)
        if lic and days > 7:
            self.setObjectName("LicenceBannerOk")
            self._lbl.setText(f"✔  Licence valid — {days} days remaining   (click to manage)")
        elif lic and days > 0:
            self.setObjectName("LicenceBannerWarn")
            self._lbl.setText(f"⚠  Licence expires in {days} day(s) — click to renew")
        else:
            self.setObjectName("LicenceBannerExpired")
            self._lbl.setText("✖  Licence expired — READ-ONLY MODE — click to activate")
        self.style().unpolish(self); self.style().polish(self)
        self._lbl.style().unpolish(self._lbl); self._lbl.style().polish(self._lbl)

    def mousePressEvent(self, _): self.clicked.emit()


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

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
        self._btns = {}; self._compact = False
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        self._logo_wrap = QWidget(); self._logo_wrap.setObjectName("logo_wrap")
        lw = QVBoxLayout(self._logo_wrap)
        lw.setContentsMargins(22,28,22,20); lw.setSpacing(3)
        self._logo_name = make_label("DocuFlow",   "logo_name")
        self._logo_tag  = make_label("ENTERPRISE", "logo_tag")
        lw.addWidget(self._logo_name); lw.addWidget(self._logo_tag)
        lay.addWidget(self._logo_wrap)

        self._user_lbl = make_label("", "SidebarUser")
        lay.addWidget(self._user_lbl)

        self._section = make_label("WORKSPACE", "nav_section_label")
        lay.addWidget(self._section)

        for key, icon, name in self.PAGES:
            btn = QPushButton(f"  {icon}   {name}")
            btn.setObjectName("NavBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._activate(k))
            self._btns[key] = btn; lay.addWidget(btn)

        lay.addStretch()

        self._logout_btn = ghost_btn("⎋  Sign Out")
        self._logout_btn.setObjectName("SidebarLogout")
        lay.addWidget(self._logout_btn)

        self._footer = make_label("v2.0  ·  © 2025 Enterprise", "sidebar_footer")
        lay.addWidget(self._footer)
        self._activate("editor")

    def _activate(self, key):
        for k, b in self._btns.items():
            b.setProperty("active", "true" if k == key else "false")
            b.style().unpolish(b); b.style().polish(b)
        self.switched.emit(key)

    def set_user(self, username: str):
        self._user_lbl.setText(f"  👤  {username}")

    def set_compact(self, compact: bool):
        if compact == self._compact: return
        self._compact = compact
        self._logo_name.setVisible(not compact)
        self._logo_tag.setVisible(not compact)
        self._section.setVisible(not compact)
        self._footer.setVisible(not compact)
        self._user_lbl.setVisible(not compact)
        self._logout_btn.setVisible(not compact)
        for key, icon, name in self.PAGES:
            self._btns[key].setText(icon if compact else f"  {icon}   {name}")
        self.setFixedWidth(56 if compact else 210)


# ═══════════════════════════════════════════════════════════════════════════════
#  HEADER BAR
# ═══════════════════════════════════════════════════════════════════════════════

class Header(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Header")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        self.banner = LicenceBanner()
        lay.addWidget(self.banner)

        title_row = QWidget(); title_row.setObjectName("HeaderTitleRow")
        title_row.setFixedHeight(52)
        tr = QHBoxLayout(title_row); tr.setContentsMargins(28,0,28,0)
        self.title = make_label("Text Editor", "page_title")
        self.pill  = make_label("No session",  "session_pill")
        tr.addWidget(self.title); tr.addStretch(); tr.addWidget(self.pill)
        lay.addWidget(title_row)

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
        lay = QHBoxLayout(self); lay.setContentsMargins(24,4,24,4); lay.setSpacing(6)

        lay.addWidget(make_label("Session:"))
        self.combo = QComboBox(); self.combo.setPlaceholderText("Select a session…")
        self.combo.setMinimumWidth(140); lay.addWidget(self.combo)

        btn_new = ghost_btn("＋ New"); btn_new.clicked.connect(self.new_session)
        lay.addWidget(btn_new); lay.addWidget(vline())

        btn_imp = ghost_btn("⬆ Import .docx", "Import a Word document")
        btn_imp.clicked.connect(self.import_docx_sig); lay.addWidget(btn_imp)

        btn_txt = ghost_btn("⬆ Import File", "Import text file or .docx — up to 500 MB")
        btn_txt.clicked.connect(self.import_text_sig); lay.addWidget(btn_txt)

        lay.addWidget(vline())

        btn_exp = QPushButton("⬇ Export .docx")
        btn_exp.setToolTip("Export as standard Word document")
        btn_exp.clicked.connect(self.export_normal); lay.addWidget(btn_exp)

        tip = ("Export Optimised .docx — images resampled, content recompressed.\n"
               + ("Pillow ✔ installed — images will be resampled."
                  if pillow_available() else "pip install Pillow for image optimisation"))
        btn_opt = ghost_btn("⬇ Optimised .docx", tip)
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
#  RICH-TEXT TOOLBAR  (Bold / Italic / Underline + Font family + Size)
# ═══════════════════════════════════════════════════════════════════════════════

FONT_FAMILIES = [
    "Calibri", "Times New Roman", "Arial", "Georgia",
    "Courier New", "Verdana", "Trebuchet MS",
]
DEFAULT_FONT_SIZE = 11

class RichBar(QWidget):
    """Toolbar for rich-text formatting: B/I/U, font family, size."""

    def __init__(self, editor: QTextEdit):
        super().__init__()
        self.setObjectName("RichBar")
        self.setFixedHeight(44)
        self._editor = editor
        self._updating = False   # guard against recursive signal loops

        lay = QHBoxLayout(self); lay.setContentsMargins(24,4,24,4); lay.setSpacing(6)

        # ── B / I / U ────────────────────────────────────────────────────────
        lay.addWidget(make_label("TEXT", "GroupLabel"))

        self._bold = fmt_btn("B", "Bold (Ctrl+B)", checkable=True)
        self._bold.setObjectName("RichBtnBold")
        self._bold.clicked.connect(self._apply_bold)
        lay.addWidget(self._bold)

        self._italic = fmt_btn("I", "Italic (Ctrl+I)", checkable=True)
        self._italic.setObjectName("RichBtnItalic")
        self._italic.clicked.connect(self._apply_italic)
        lay.addWidget(self._italic)

        self._under = fmt_btn("U", "Underline (Ctrl+U)", checkable=True)
        self._under.setObjectName("RichBtnUnder")
        self._under.clicked.connect(self._apply_underline)
        lay.addWidget(self._under)

        lay.addWidget(vline())

        # ── Font family ───────────────────────────────────────────────────────
        lay.addWidget(make_label("FONT", "GroupLabel"))
        self._font_cb = QComboBox()
        self._font_cb.setObjectName("FontCombo")
        self._font_cb.setMinimumWidth(160)
        for f in FONT_FAMILIES:
            self._font_cb.addItem(f)
        self._font_cb.setCurrentText("Calibri")
        self._font_cb.currentTextChanged.connect(self._apply_font_family)
        lay.addWidget(self._font_cb)

        lay.addWidget(vline())

        # ── Font size ─────────────────────────────────────────────────────────
        lay.addWidget(make_label("SIZE", "GroupLabel"))
        self._size_dec = fmt_btn("A−", "Decrease font size")
        self._size_dec.clicked.connect(lambda: self._change_size(-1))
        lay.addWidget(self._size_dec)

        self._size_spin = QSpinBox()
        self._size_spin.setObjectName("FontSizeSpin")
        self._size_spin.setRange(6, 96)
        self._size_spin.setValue(DEFAULT_FONT_SIZE)
        self._size_spin.setFixedWidth(52)
        self._size_spin.valueChanged.connect(self._apply_font_size)
        lay.addWidget(self._size_spin)

        self._size_inc = fmt_btn("A+", "Increase font size")
        self._size_inc.clicked.connect(lambda: self._change_size(+1))
        lay.addWidget(self._size_inc)

        lay.addStretch()

        # Reflect cursor changes in the toolbar
        editor.cursorPositionChanged.connect(self._sync_toolbar)
        editor.currentCharFormatChanged.connect(self._on_char_format_changed)

    # ── apply formatting ──────────────────────────────────────────────────────

    def _fmt(self) -> QTextCharFormat:
        return self._editor.textCursor().charFormat()

    def _apply_fmt(self, fmt: QTextCharFormat):
        c = self._editor.textCursor()
        if c.hasSelection():
            c.mergeCharFormat(fmt)
        else:
            self._editor.mergeCurrentCharFormat(fmt)

    def _apply_bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if self._bold.isChecked() else QFont.Weight.Normal)
        self._apply_fmt(fmt)

    def _apply_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(self._italic.isChecked())
        self._apply_fmt(fmt)

    def _apply_underline(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(self._under.isChecked())
        self._apply_fmt(fmt)

    def _apply_font_family(self, family: str):
        if self._updating: return
        fmt = QTextCharFormat()
        fmt.setFontFamilies([family])
        self._apply_fmt(fmt)

    def _apply_font_size(self, size: int):
        if self._updating: return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(size))
        self._apply_fmt(fmt)

    def _change_size(self, delta: int):
        new = max(6, min(96, self._size_spin.value() + delta))
        self._size_spin.setValue(new)   # triggers _apply_font_size

    # ── sync toolbar state with cursor ────────────────────────────────────────

    def _sync_toolbar(self):
        self._on_char_format_changed(self._fmt())

    def _on_char_format_changed(self, fmt: QTextCharFormat):
        self._updating = True
        self._bold.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
        self._italic.setChecked(fmt.fontItalic())
        self._under.setChecked(fmt.fontUnderline())
        fam = fmt.fontFamilies()
        if fam and fam[0] in FONT_FAMILIES:
            self._font_cb.setCurrentText(fam[0])
        sz = fmt.fontPointSize()
        if sz > 0:
            self._size_spin.setValue(int(sz))
        self._updating = False


# ═══════════════════════════════════════════════════════════════════════════════
#  FORMAT BAR  (Align / Clean / Case)
# ═══════════════════════════════════════════════════════════════════════════════

class FormatBar(QWidget):
    acted = pyqtSignal(str)
    GROUPS = [
        ("ALIGN", [
            ("⬅ Left",    "align_left",   "Align all paragraphs left"),
            ("⊟ Center",  "align_center", "Centre all paragraphs"),
            ("➡ Right",   "align_right",  "Align all paragraphs right"),
        ]),
        ("CLEAN", [
            ("⌫ Spaces",    "remove_spaces",   "Remove unnecessary spaces"),
            ("＋ Sep",       "add_separator",   "Insert separator at cursor line"),
            ("✕ Sep",       "remove_separator", "Remove all separator lines"),
        ]),
        ("CASE", [
            ("AA UPPER",    "to_upper",    "Convert to UPPERCASE"),
            ("aa lower",    "to_lower",    "Convert to lowercase"),
            ("Aa Title",    "to_title",    "Title Case"),
            ("A. Sentence", "to_sentence", "Sentence case"),
        ]),
    ]

    def __init__(self):
        super().__init__()
        self.setObjectName("FormatBar"); self.setMinimumHeight(46)
        lay = QHBoxLayout(self); lay.setContentsMargins(24,0,24,0); lay.setSpacing(4)
        for i, (label, btns) in enumerate(self.GROUPS):
            lay.addWidget(make_label(label, "GroupLabel"))
            for name, key, tip in btns:
                b = QPushButton(name); b.setObjectName("FmtBtn")
                b.setToolTip(tip); b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _, k=key: self.acted.emit(k))
                lay.addWidget(b)
            if i < len(self.GROUPS)-1: lay.addWidget(vline())
        lay.addStretch()


# ═══════════════════════════════════════════════════════════════════════════════
#  FIND & REPLACE BAR
# ═══════════════════════════════════════════════════════════════════════════════

class FindBar(QWidget):
    acted = pyqtSignal(str, str, bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("FindBar"); self.setFixedHeight(44)
        lay = QHBoxLayout(self); lay.setContentsMargins(24,0,24,0); lay.setSpacing(8)
        lay.addWidget(make_label("FIND & REPLACE", "GroupLabel"))
        self._find    = QLineEdit(); self._find.setObjectName("FindInput")
        self._find.setPlaceholderText("Find text…")
        self._replace = QLineEdit(); self._replace.setObjectName("ReplaceInput")
        self._replace.setPlaceholderText("Replace with…")
        self._case = QCheckBox("Match case"); self._case.setObjectName("CaseCheck")
        btn = QPushButton("Replace All"); btn.setObjectName("ReplaceBtn")
        btn.clicked.connect(self._go); self._find.returnPressed.connect(self._go)
        lay.addWidget(self._find); lay.addWidget(make_label("→"))
        lay.addWidget(self._replace); lay.addWidget(self._case)
        lay.addWidget(btn); lay.addStretch()

    def _go(self):
        self.acted.emit(self._find.text(), self._replace.text(), self._case.isChecked())


# ═══════════════════════════════════════════════════════════════════════════════
#  STATUS BAR
# ═══════════════════════════════════════════════════════════════════════════════

class StatusBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("StatusBar"); self.setFixedHeight(30)
        lay = QHBoxLayout(self); lay.setContentsMargins(24,0,24,0); lay.setSpacing(22)
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
    _ALIGN_MAP = {
        "align_left":   Qt.AlignmentFlag.AlignLeft,
        "align_center": Qt.AlignmentFlag.AlignCenter,
        "align_right":  Qt.AlignmentFlag.AlignRight,
    }

    def __init__(self, header: Header, user: dict):
        super().__init__()
        self.setObjectName("PageArea")
        self._header      = header
        self._user        = user
        self._undo        = []
        self._active_id   = None
        self._source_path = None
        self._read_only   = False

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        self.action_bar = ActionBar()
        self.action_bar.new_session.connect(self._new_session)
        self.action_bar.import_docx_sig.connect(self._import_docx)
        self.action_bar.import_text_sig.connect(self._import_text)
        self.action_bar.export_normal.connect(self._export_normal)
        self.action_bar.export_optimised.connect(self._export_optimised)
        self.action_bar.save_backup.connect(self._backup)
        self.action_bar.combo.currentIndexChanged.connect(self._session_selected)
        lay.addWidget(self.action_bar)

        # Editor widget (created before RichBar so we can pass it)
        self.editor = QTextEdit()
        self.editor.setObjectName("Editor")
        self.editor.setPlaceholderText(
            "Paste or type your text here — or import a file above.\n\n"
            "Use the toolbars to format, align, clean, or transform your text."
        )
        self.editor.textChanged.connect(self._text_changed)

        self.rich_bar = RichBar(self.editor)
        lay.addWidget(self.rich_bar)

        self.fmt_bar = FormatBar()
        self.fmt_bar.acted.connect(self._format)
        lay.addWidget(self.fmt_bar)

        self.find_bar = FindBar()
        self.find_bar.acted.connect(self._find_replace)
        lay.addWidget(self.find_bar)

        lay.addWidget(self.editor, stretch=1)

        self.status = StatusBar()
        lay.addWidget(self.status)

        self._refresh_sessions()

    # ── read-only mode (expired licence) ─────────────────────────────────────

    def set_read_only(self, ro: bool):
        self._read_only = ro
        self.editor.setReadOnly(ro)
        self.rich_bar.setEnabled(not ro)
        self.fmt_bar.setEnabled(not ro)
        self.find_bar.setEnabled(not ro)
        # disable import/export buttons
        self.action_bar.setEnabled(not ro)
        if ro:
            self.status.flash("⚠  Read-only mode — activate your licence to edit")

    def refresh_licence(self):
        uid  = self._user["id"]
        days = db.licence_days_remaining(uid)
        self.set_read_only(days == 0)
        self._header.banner.update_status(uid)

    # ── session ───────────────────────────────────────────────────────────────

    def _refresh_sessions(self, keep_id=None):
        sessions = db.get_sessions(self._user["id"])
        self.action_bar.refresh_sessions(sessions, keep_id or self._active_id)
        if self._active_id is None and sessions:
            self._active_id = sessions[0]["id"]

    def _session_selected(self, idx):
        sid = self.action_bar.current_session_id()
        if sid:
            self._active_id = sid
            name = self.action_bar.current_session_name()
            self._header.set_session(name)
            db.log("SESSION_SWITCHED", name, sid=sid, uid=self._user["id"])

    def _new_session(self):
        if self._read_only: return
        dlg = NameDialog("New Session", "Session name:", self)
        if dlg.exec() and dlg.value().strip():
            name = dlg.value().strip()
            sid  = db.create_session(self._user["id"], name)
            db.log("SESSION_CREATED", name, sid=sid, uid=self._user["id"])
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
        st = _save_state(self.editor)
        self.editor.blockSignals(True)
        self.editor.setPlainText(new_text)
        self.editor.blockSignals(False)
        _restore_state(self.editor, st)

    # ── format ────────────────────────────────────────────────────────────────

    FN = {
        "remove_spaces":    remove_spaces,
        "remove_separator": remove_separator,
        "to_upper":         to_upper,
        "to_lower":         to_lower,
        "to_title":         to_title,
        "to_sentence":      to_sentence,
    }

    def _format(self, key: str):
        if self._read_only: return
        text = self.editor.toPlainText()
        if not text.strip(): return
        self._push_undo()
        if key in self._ALIGN_MAP:
            _apply_block_alignment(self.editor, self._ALIGN_MAP[key])
        elif key == "add_separator":
            new = add_separator_at(text, _cursor_line(self.editor))
            self._set_text(new); self.status.update(new)
        else:
            new = self.FN[key](text)
            self._set_text(new); self.status.update(new)
        db.log("FORMAT", key, sid=self._active_id, uid=self._user["id"])
        self.status.flash("✔ Applied")

    def _find_replace(self, find, replace, case):
        if self._read_only or not find: return
        text = self.editor.toPlainText()
        self._push_undo()
        new = find_replace(text, find, replace, case)
        self._set_text(new); self.status.update(new)
        db.log("REPLACE", f"'{find}' → '{replace}'", sid=self._active_id, uid=self._user["id"])
        self.status.flash("✔ Replace done")

    def _text_changed(self):
        self.status.update(self.editor.toPlainText())

    # ── import ────────────────────────────────────────────────────────────────

    def _import_docx(self):
        if self._read_only: return
        path, _ = QFileDialog.getOpenFileName(self, "Import Word Document", "",
            "Word Documents (*.docx);;All Files (*)")
        if not path: return
        if not docx_ok():
            QMessageBox.critical(self, "Error", "python-docx not installed.\npip install python-docx"); return
        try:
            self._push_undo()
            text, images = read_docx(path)
            self._source_path = path
            self._set_text(text)
            if images: self._insert_images(images)
            db.log("IMPORT", os.path.basename(path), sid=self._active_id, uid=self._user["id"])
            sz = os.path.getsize(path) / 1024
            self.status.flash(f"⬆ {os.path.basename(path)}  ({sz:.0f} KB{'  · ' + str(len(images)) + ' image(s)' if images else ''})")
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))

    def _import_text(self):
        if self._read_only: return
        path, _ = QFileDialog.getOpenFileName(self, "Import File", "",
            "Files (*.txt *.md *.csv *.html *.htm *.json *.xml *.log *.docx);;All Files (*)")
        if not path: return
        size = os.path.getsize(path)
        if size > MAX_UPLOAD_BYTES:
            QMessageBox.critical(self, "File too large",
                f"{size/1_048_576:.1f} MB — limit is 500 MB"); return
        ext = os.path.splitext(path)[1].lower()
        try:
            self._push_undo()
            if ext == ".docx" and docx_ok():
                text, images = read_docx(path)
                self._source_path = path
                self._set_text(text)
                if images: self._insert_images(images)
            else:
                text, _ = read_text_file(path)
                self._source_path = None
                self._set_text(text)
            db.log("IMPORT", os.path.basename(path), sid=self._active_id, uid=self._user["id"])
            self.status.flash(f"⬆ {os.path.basename(path)}  ({size/1024:.0f} KB)")
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))

    # ── export ────────────────────────────────────────────────────────────────

    def _export_normal(self):
        text = self.editor.toPlainText()
        if not text.strip(): QMessageBox.warning(self, "Empty", "The editor is empty."); return
        if not docx_ok(): QMessageBox.critical(self, "Error", "pip install python-docx"); return
        path, _ = QFileDialog.getSaveFileName(self, "Export Word Document", "document.docx",
            "Word Documents (*.docx)")
        if not path: return
        try:
            write_docx(text, path, self._collect_alignments())
            db.log("EXPORT", os.path.basename(path), sid=self._active_id, uid=self._user["id"])
            self.status.flash(f"⬇ {os.path.basename(path)}  ({os.path.getsize(path)/1024:.0f} KB)")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _export_optimised(self):
        text = self.editor.toPlainText()
        if not text.strip(): QMessageBox.warning(self, "Empty", "The editor is empty."); return
        if not docx_ok(): QMessageBox.critical(self, "Error", "pip install python-docx"); return
        path, _ = QFileDialog.getSaveFileName(self, "Export Optimised .docx",
            "document_optimised.docx", "Word Documents (*.docx)")
        if not path: return
        try:
            if self._source_path and os.path.exists(self._source_path):
                sd = optimise_existing_docx(self._source_path, path)
            else:
                sd = write_docx_optimised(text, path, self._collect_alignments())
            pct = max(0, (1 - sd["final_kb"] / sd["original_kb"]) * 100) if sd["original_kb"] else 0
            imgs = f", {sd['images_processed']} image(s) resampled" if sd["images_processed"] else ""
            db.log("EXPORT_OPTIMISED",
                   f"{os.path.basename(path)} | {sd['original_kb']:.0f}→{sd['final_kb']:.0f} KB{imgs}",
                   sid=self._active_id, uid=self._user["id"])
            self.status.flash(
                f"⬇ {os.path.basename(path)}  {sd['original_kb']:.0f}→{sd['final_kb']:.0f} KB  ({pct:.0f}% smaller{imgs})"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    # ── backup ────────────────────────────────────────────────────────────────

    def _backup(self):
        if self._read_only: return
        sid = self._active_id
        if not sid: QMessageBox.information(self, "No session", "Create a session first."); return
        text = self.editor.toPlainText()
        if not text.strip(): QMessageBox.warning(self, "Empty", "The editor is empty."); return
        s = stats(text)
        label = f"{s['words']} words  ·  {s['lines']} lines"
        db.save_backup(sid, text, label)
        db.log("BACKUP", label, sid=sid, uid=self._user["id"])
        self.status.flash("🗄 Backup saved")

    def load_text(self, text):
        self._push_undo(); self._set_text(text)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _insert_images(self, images: list):
        from PyQt6.QtCore import QByteArray
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock(); cursor.insertText("\n── Embedded Images ──")
        for i, img_bytes in enumerate(images):
            try:
                ba = QByteArray(img_bytes); img = QImage.fromData(ba)
                if img.isNull(): continue
                max_w = max(400, self.editor.viewport().width() - 80)
                if img.width() > max_w:
                    img = img.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
                name = f"df_img_{id(self)}_{i}"
                self.editor.document().addResource(3, QUrl(name), img)
                fmt = QTextImageFormat(); fmt.setName(name)
                fmt.setWidth(img.width()); fmt.setHeight(img.height())
                cursor.insertBlock(); cursor.insertImage(fmt)
            except Exception: pass

    def _collect_alignments(self):
        result = {}; block = self.editor.document().begin(); i = 0
        while block.isValid():
            a = block.blockFormat().alignment()
            if a in (Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignCenter):
                result[i] = "center"
            elif a == Qt.AlignmentFlag.AlignRight:
                result[i] = "right"
            block = block.next(); i += 1
        return result or None


# ═══════════════════════════════════════════════════════════════════════════════
#  SESSIONS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class SessionsPage(QWidget):
    restore = pyqtSignal(str)

    def __init__(self, user: dict):
        super().__init__()
        self._user = user
        self.setObjectName("PageArea")
        lay = QHBoxLayout(self); lay.setContentsMargins(24,24,24,24); lay.setSpacing(20)

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
        self.preview.setPlaceholderText("Select a backup to preview…")
        self.preview.setMaximumHeight(180)
        self.backup_list = QListWidget(); self.backup_list.setObjectName("BackupList")
        self.backup_list.currentRowChanged.connect(self._backup_selected)
        restore_btn = QPushButton("↩  Restore Selected Backup to Editor")
        restore_btn.clicked.connect(self._restore)
        right.addWidget(self.backup_list)
        right.addWidget(make_label("PREVIEW", "CardTitle"))
        right.addWidget(self.preview); right.addWidget(restore_btn)

        lw = QWidget(); lw.setLayout(left)
        rw = QWidget(); rw.setLayout(right)
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(lw); sp.addWidget(rw); sp.setSizes([280, 620])
        lay.addWidget(sp); self.refresh()

    def refresh(self):
        self.sess_list.clear()
        for s in db.get_sessions(self._user["id"]):
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
        if b: self.preview.setPlainText(b["content"][:800] + ("…" if len(b["content"])>800 else ""))

    def _restore(self):
        item = self.backup_list.currentItem()
        if not item: return
        b = db.get_backup(item.data(Qt.ItemDataRole.UserRole))
        if not b: return
        if QMessageBox.question(self, "Restore", "Load this backup into the editor?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.restore.emit(b["content"])
            db.log("RESTORE", f"Backup {b['id']}", uid=self._user["id"])

    def _delete_session(self):
        item = self.sess_list.currentItem()
        if not item: return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Delete Session",
            "Delete this session and all its backups?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            db.delete_session(sid)
            db.log("SESSION_DELETED", f"id={sid}", uid=self._user["id"])
            self.refresh()


# ═══════════════════════════════════════════════════════════════════════════════
#  LOG PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class LogPage(QWidget):
    def __init__(self, user: dict):
        super().__init__()
        self._user = user; self.setObjectName("PageArea")
        lay = QVBoxLayout(self); lay.setContentsMargins(24,24,24,24); lay.setSpacing(12)
        hdr = QHBoxLayout(); hdr.addWidget(make_label("ACTIVITY LOG", "CardTitle"))
        hdr.addStretch()
        ref = ghost_btn("↺  Refresh"); ref.clicked.connect(self.refresh); hdr.addWidget(ref)
        lay.addLayout(hdr)
        self.list = QListWidget(); self.list.setObjectName("LogList"); lay.addWidget(self.list)
        self.refresh()

    ICONS = {
        "FORMAT":"🔧","IMPORT":"⬆","EXPORT":"⬇","EXPORT_OPTIMISED":"⬇✦",
        "BACKUP":"🗄","RESTORE":"↩","REPLACE":"✏",
        "SESSION_CREATED":"✦","SESSION_DELETED":"🗑","SESSION_SWITCHED":"⊞",
    }

    def refresh(self):
        self.list.clear()
        for l in db.get_logs(self._user["id"]):
            icon   = self.ICONS.get(l["action"], "·")
            detail = f"   {l['detail']}" if l["detail"] else ""
            self.list.addItem(QListWidgetItem(f"  {icon}  {l['at']}    {l['action']}{detail}"))


# ═══════════════════════════════════════════════════════════════════════════════
#  NAME DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class NameDialog(QDialog):
    def __init__(self, title, label, parent=None):
        super().__init__(parent); self.setWindowTitle(title); self.setMinimumWidth(340)
        lay = QVBoxLayout(self); lay.setSpacing(12)
        lay.addWidget(QLabel(label))
        self._inp = QLineEdit(); lay.addWidget(self._inp)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
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
        self.resize(1300, 860); self.setMinimumSize(640, 520)
        self._user = None

        # Root stack: 0 = auth, 1 = app
        self._root_stack = QStackedWidget()
        self.setCentralWidget(self._root_stack)

        self._auth_page = AuthPage()
        self._auth_page.logged_in.connect(self._on_login)
        self._root_stack.addWidget(self._auth_page)   # index 0

        # App shell (built after login)
        self._app_shell = None

    def _on_login(self, user: dict):
        self._user = user
        if self._app_shell:
            self._root_stack.removeWidget(self._app_shell)
            self._app_shell.deleteLater()
        self._app_shell = self._build_app_shell(user)
        self._root_stack.addWidget(self._app_shell)   # index 1
        self._root_stack.setCurrentIndex(1)

        # Keyboard shortcuts (re-register after rebuild)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._editor_page.undo)
        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(
            lambda: self._editor_page.rich_bar._apply_bold()
        )
        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(
            lambda: self._editor_page.rich_bar._apply_italic()
        )
        QShortcut(QKeySequence("Ctrl+U"), self).activated.connect(
            lambda: self._editor_page.rich_bar._apply_underline()
        )

        # Refresh licence status
        self._editor_page.refresh_licence()

        # Periodic licence check every 60 s
        self._lic_timer = QTimer(self)
        self._lic_timer.timeout.connect(self._editor_page.refresh_licence)
        self._lic_timer.start(60_000)

    def _build_app_shell(self, user: dict) -> QWidget:
        shell = QWidget()
        lay   = QHBoxLayout(shell); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.set_user(user["username"])
        self.sidebar.switched.connect(self._switch)
        self.sidebar._logout_btn.clicked.connect(self._logout)
        lay.addWidget(self.sidebar)

        content = QWidget(); cl = QVBoxLayout(content)
        cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)

        self.header = Header()
        self.header.banner.clicked.connect(self._open_licence)
        cl.addWidget(self.header)

        self.stack          = QStackedWidget()
        self._editor_page   = EditorPage(self.header, user)
        self._sessions_page = SessionsPage(user)
        self._log_page      = LogPage(user)

        self._sessions_page.restore.connect(self._do_restore)
        self.stack.addWidget(self._editor_page)    # 0
        self.stack.addWidget(self._sessions_page)  # 1
        self.stack.addWidget(self._log_page)       # 2
        cl.addWidget(self.stack)
        lay.addWidget(content, stretch=1)
        return shell

    PAGE_MAP = {"editor": 0, "sessions": 1, "log": 2}
    TITLES   = {"editor": "Text Editor", "sessions": "Sessions & Backups", "log": "Activity Log"}

    def _switch(self, key):
        self.stack.setCurrentIndex(self.PAGE_MAP[key])
        self.header.set_title(self.TITLES[key])
        if key == "sessions":
            self._sessions_page.refresh()
            self._editor_page._refresh_sessions()
        elif key == "log":
            self._log_page.refresh()

    def _do_restore(self, text):
        self._editor_page.load_text(text)
        self.sidebar._activate("editor"); self._switch("editor")

    def _open_licence(self):
        dlg = LicenceDialog(self._user, self)
        dlg.exec()
        if dlg.was_activated():
            self._editor_page.refresh_licence()

    def _logout(self):
        if hasattr(self, "_lic_timer"): self._lic_timer.stop()
        self._user = None
        self._root_stack.setCurrentIndex(0)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self.sidebar.set_compact(event.size().width() < COMPACT_WIDTH)


# ═══════════════════════════════════════════════════════════════════════════════
#  STYLESHEET  (embedded fallback + disk loader)
# ═══════════════════════════════════════════════════════════════════════════════

EXTRA_QSS = """
/* ── Auth page ─────────────────────────────────────────── */
#AuthPage { background-color: #F8FAF8; }

#AuthBrand {
    background-color: #0E2318;
}
#AuthLogo {
    color: #FFFFFF; font-size: 32px; font-weight: 800; letter-spacing: -0.5px;
}
#AuthLogoTag {
    color: #3D8A57; font-size: 10px; letter-spacing: 4px; font-weight: 700;
}
#AuthTagline {
    color: #7AB891; font-size: 14px; line-height: 1.5;
}
#AuthFooter { color: #2D5C3C; font-size: 11px; }

#AuthFormWrap { background-color: #FFFFFF; }
#AuthFormTitle { font-size: 22px; font-weight: 700; color: #0D1F14; }
#AuthSub       { font-size: 13px; color: #6A9A7A; }
#AuthFieldLabel{ font-size: 12px; font-weight: 600; color: #1A3525; }

#AuthInput {
    background-color: #F8FAF8;
    border: 1.5px solid #C8DDD0;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    color: #0D1F14;
    min-height: 44px;
}
#AuthInput:focus { border-color: #27AE60; background-color: #FFFFFF; }

#AuthBtn {
    background-color: #1B6B3A;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 12px 0;
    font-size: 14px;
    font-weight: 700;
    min-height: 48px;
}
#AuthBtn:hover  { background-color: #22874A; }
#AuthBtn:pressed{ background-color: #155C30; }

#AuthToggle {
    background: transparent; border: none;
    color: #27AE60; font-size: 12px; text-decoration: underline;
    min-height: 0; padding: 0;
}
#AuthToggle:hover { color: #1B6B3A; }

#AuthError { color: #C0392B; font-size: 12px; }

/* ── Sidebar user label & logout ────────────────────────── */
#SidebarUser {
    color: #7AB891; font-size: 11px; font-weight: 600;
    padding: 10px 22px 6px 22px;
    border-bottom: 1px solid #1A3D26;
}
#SidebarLogout {
    margin: 0 14px 8px 14px;
    color: #9A6B7B; border-color: #4A2D35;
}

/* ── Header banner ──────────────────────────────────────── */
#HeaderTitleRow { background-color: #FFFFFF; border-bottom: 1px solid #E4EDE7; }

#LicenceBannerOk      { background-color: #1B6B3A; }
#LicenceBannerWarn    { background-color: #B7770D; }
#LicenceBannerExpired { background-color: #8B1A1A; }

#BannerLabel { color: #FFFFFF; font-size: 11px; font-weight: 600; letter-spacing: 0.3px; }

/* ── Licence dialog ─────────────────────────────────────── */
#LicenceActive  { color: #1B6B3A; font-weight: 600; font-size: 13px; }
#LicenceExpired { color: #C0392B; font-weight: 600; font-size: 13px; }
#LicenceInfo    { color: #1A3525; font-size: 12px; line-height: 1.6;
                  background-color: #F3F8F4; border-radius: 8px;
                  padding: 14px 18px; border: 1px solid #C8DDD0; }

/* ── Rich-text bar ──────────────────────────────────────── */
#RichBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #EEF3EF;
    padding: 4px 24px;
}

#RichBtnBold   { font-weight: 800; font-size: 14px; min-width: 32px; }
#RichBtnItalic { font-style: italic; font-size: 14px; min-width: 32px; }
#RichBtnUnder  { text-decoration: underline; font-size: 14px; min-width: 32px; }

#RichBtnBold:checked, #RichBtnItalic:checked, #RichBtnUnder:checked {
    background-color: #1B6B3A;
    color: #FFFFFF;
    border-color: #1B6B3A;
}

#FontCombo { min-width: 160px; max-width: 200px; font-size: 12px; }

#FontSizeSpin {
    background-color: #FFFFFF;
    border: 1.5px solid #C8DDD0;
    border-radius: 6px;
    padding: 4px 6px;
    font-size: 12px;
    color: #0D1F14;
}
"""

def _get_qss() -> str:
    qss_path = os.path.join(os.path.dirname(__file__), "styles", "theme.qss")
    base = ""
    if os.path.exists(qss_path):
        try:
            with open(qss_path, encoding="utf-8") as f:
                base = f.read()
        except Exception: pass
    return base + "\n" + EXTRA_QSS

def _load_qss(app):
    app.setStyleSheet(_get_qss())

def run():
    db.init()
    app = QApplication(sys.argv)
    app.setApplicationName("DocuFlow Enterprise")
    _load_qss(app)
    win = MainWindow(); win.show()
    sys.exit(app.exec())