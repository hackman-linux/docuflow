"""
DocuFlow v4 — Free Edition
─────────────────────────────────────────────────
• Completely free — no licences, no payments, no limits
• Ribbon toolbar (tabs: Home / Format / Tools)
• Dark-mode toggle (persists per session)
• Word-count goal with live progress bar
• Auto-save every 60 s to the active session backup
• User profile dialog (change email / password)
• Clear Activity Log button
• All styles embedded → PyInstaller builds keep full theme
"""

import sys, os, datetime, threading, time

_ROOT = os.path.join(os.path.dirname(__file__), "..")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QSplitter, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QMessageBox, QCheckBox, QStackedWidget, QFrame,
    QSpinBox, QProgressBar,
)
from PyQt6.QtCore  import Qt, QTimer, pyqtSignal, QUrl, QThread, pyqtSlot
from PyQt6.QtGui   import (
    QFont, QTextBlockFormat, QTextCursor, QTextCharFormat,
    QKeySequence, QShortcut, QResizeEvent, QImage, QTextImageFormat,
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
    read_docx, write_docx, read_text_file,
    write_docx_optimised, optimise_existing_docx,
)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
COMPACT_WIDTH    = 920

FONT_FAMILIES = [
    "Calibri", "Times New Roman", "Arial", "Georgia",
    "Courier New", "Verdana", "Trebuchet MS",
]
DEFAULT_FONT_SIZE = 11


# ═══════════════════════════════════════════════════════════════════════════════
#  SMALL UI HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def ghost_btn(text, tooltip=""):
    b = QPushButton(text); b.setObjectName("ghost")
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

def ribbon_btn(icon, label, tooltip="", checkable=False, primary=False):
    b = QPushButton(f"{icon}\n{label}")
    b.setObjectName("RibbonBtnPrimary" if primary else "RibbonBtn")
    b.setToolTip(tooltip); b.setCursor(Qt.CursorShape.PointingHandCursor)
    if checkable: b.setCheckable(True)
    return b

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
#  AUTH PAGE  — split-screen login / register
# ═══════════════════════════════════════════════════════════════════════════════

class AuthPage(QWidget):
    logged_in = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setObjectName("AuthPage")
        root = QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ── Left brand panel ─────────────────────────────────────────────────
        brand = QWidget(); brand.setObjectName("AuthBrand"); brand.setFixedWidth(400)
        bl = QVBoxLayout(brand); bl.setContentsMargins(48,60,48,40); bl.setSpacing(0)
        bl.addStretch(2)
        bl.addWidget(make_label("DocuFlow",   "AuthLogo"))
        bl.addSpacing(4)
        bl.addWidget(make_label("FREE EDITION", "AuthLogoTag"))
        bl.addSpacing(32)
        bl.addWidget(make_label(
            "The word-processing automation\nplatform built for professionals.",
            "AuthTagline"
        ))
        bl.addSpacing(32)
        for feat in ["✦  Rich-text editing & formatting",
                     "✦  Sessions, backups & activity log",
                     "✦  Import/export .docx up to 500 MB",
                     "✦  Completely free — no limits, ever"]:
            lbl = make_label(feat, "AuthFeature"); bl.addWidget(lbl); bl.addSpacing(8)
        bl.addStretch(3)
        bl.addWidget(make_label("v4.0  ·  © 2025 DocuFlow Free Edition", "AuthFooter"))
        root.addWidget(brand)

        # ── Right form panel ─────────────────────────────────────────────────
        form_wrap = QWidget(); form_wrap.setObjectName("AuthFormWrap")
        fl = QVBoxLayout(form_wrap); fl.setContentsMargins(64,0,64,0)
        fl.setSpacing(0); fl.addStretch(2)

        self._title = make_label("Sign in", "AuthFormTitle"); fl.addWidget(self._title)
        fl.addSpacing(6)
        self._sub = make_label("Welcome back. Enter your credentials.", "AuthSub")
        fl.addWidget(self._sub); fl.addSpacing(30)

        fl.addWidget(make_label("USERNAME", "AuthFieldLabel")); fl.addSpacing(6)
        self._user = QLineEdit(); self._user.setObjectName("AuthInput")
        self._user.setPlaceholderText("your_username"); fl.addWidget(self._user); fl.addSpacing(16)

        fl.addWidget(make_label("PASSWORD", "AuthFieldLabel")); fl.addSpacing(6)
        self._pass = QLineEdit(); self._pass.setObjectName("AuthInput")
        self._pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass.setPlaceholderText("••••••••")
        self._pass.returnPressed.connect(self._do_action)
        fl.addWidget(self._pass); fl.addSpacing(8)

        # Email (hidden in login mode)
        self._email_lbl = make_label("EMAIL (optional)", "AuthFieldLabel")
        self._email_lbl.hide(); fl.addWidget(self._email_lbl); fl.addSpacing(6)
        self._email_in = QLineEdit(); self._email_in.setObjectName("AuthInput")
        self._email_in.setPlaceholderText("you@example.com"); self._email_in.hide()
        fl.addWidget(self._email_in); fl.addSpacing(16)

        self._action_btn = QPushButton("Sign In")
        self._action_btn.setObjectName("AuthBtn")
        self._action_btn.clicked.connect(self._do_action)
        fl.addWidget(self._action_btn); fl.addSpacing(16)

        self._toggle_btn = QPushButton("Don't have an account? Create one →")
        self._toggle_btn.setObjectName("AuthToggle"); self._toggle_btn.setFlat(True)
        self._toggle_btn.clicked.connect(self._toggle_mode)
        fl.addWidget(self._toggle_btn)

        self._error = make_label("", "AuthError"); self._error.setWordWrap(True)
        fl.addSpacing(10); fl.addWidget(self._error)
        fl.addStretch(3)
        root.addWidget(form_wrap, stretch=1)
        self._mode = "login"

    def _toggle_mode(self):
        if self._mode == "login":
            self._mode = "register"
            self._title.setText("Create account")
            self._sub.setText("Create your free account.")
            self._action_btn.setText("Create Account")
            self._toggle_btn.setText("Already have an account? Sign in →")
            self._email_lbl.show(); self._email_in.show()
        else:
            self._mode = "login"
            self._title.setText("Sign in")
            self._sub.setText("Welcome back. Enter your credentials.")
            self._action_btn.setText("Sign In")
            self._toggle_btn.setText("Don't have an account? Create one →")
            self._email_lbl.hide(); self._email_in.hide()
        self._error.setText(""); self._user.clear(); self._pass.clear()

    def _do_action(self):
        u = self._user.text().strip(); p = self._pass.text()
        self._error.setText("")
        if not u or not p:
            self._error.setText("Please enter both username and password."); return
        if self._mode == "login":
            user = db.authenticate(u, p)
            if user: self.logged_in.emit(user)
            else:    self._error.setText("Incorrect username or password.")
        else:
            if len(u) < 3:
                self._error.setText("Username must be at least 3 characters."); return
            if len(p) < 6:
                self._error.setText("Password must be at least 6 characters."); return
            email = self._email_in.text().strip()
            uid   = db.create_user(u, p, email)
            if uid is None:
                self._error.setText("That username is already taken.")
            else:
                self.logged_in.emit(db.get_user(uid))


# ═══════════════════════════════════════════════════════════════════════════════
#  PROFILE DIALOG  — change email / password
# ═══════════════════════════════════════════════════════════════════════════════

class ProfileDialog(QDialog):
    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DocuFlow — Profile Settings")
        self.setMinimumWidth(420)
        self._user = user

        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        hdr = QWidget(); hdr.setObjectName("PayHdr"); hdr.setFixedHeight(64)
        hl  = QHBoxLayout(hdr); hl.setContentsMargins(28,0,28,0)
        hl.addWidget(make_label("DocuFlow",       "PayLogo"))
        hl.addSpacing(8)
        hl.addWidget(make_label("Profile Settings", "PayLogoSub"))
        hl.addStretch()
        root.addWidget(hdr)

        body = QWidget(); body.setObjectName("PayBody")
        bl   = QVBoxLayout(body); bl.setContentsMargins(32,20,32,20); bl.setSpacing(12)

        bl.addWidget(make_label(f"Logged in as:  {user['username']}", "PayDesc"))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); bl.addWidget(sep)

        # Email
        bl.addWidget(make_label("EMAIL", "AuthFieldLabel"))
        self._email = QLineEdit(); self._email.setObjectName("AuthInput")
        self._email.setText(user.get("email", ""))
        self._email.setPlaceholderText("you@example.com")
        bl.addWidget(self._email)

        save_email = QPushButton("Update Email")
        save_email.setObjectName("PayConfirmBtn")
        save_email.clicked.connect(self._save_email)
        bl.addWidget(save_email)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine); bl.addWidget(sep2)

        # Password
        bl.addWidget(make_label("NEW PASSWORD", "AuthFieldLabel"))
        self._pw1 = QLineEdit(); self._pw1.setObjectName("AuthInput")
        self._pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw1.setPlaceholderText("New password (min 6 chars)")
        bl.addWidget(self._pw1)

        bl.addWidget(make_label("CONFIRM PASSWORD", "AuthFieldLabel"))
        self._pw2 = QLineEdit(); self._pw2.setObjectName("AuthInput")
        self._pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw2.setPlaceholderText("Repeat new password")
        bl.addWidget(self._pw2)

        save_pw = QPushButton("Change Password")
        save_pw.setObjectName("PayConfirmBtn")
        save_pw.clicked.connect(self._save_password)
        bl.addWidget(save_pw)

        self._msg = make_label("", "AuthError")
        self._msg.setWordWrap(True)
        bl.addWidget(self._msg)

        bl.addStretch()
        root.addWidget(body, stretch=1)

        ftr = QWidget(); ftr.setObjectName("PayFooter")
        fl  = QHBoxLayout(ftr); fl.setContentsMargins(28,10,28,10)
        fl.addStretch()
        close = ghost_btn("Close"); close.clicked.connect(self.accept)
        fl.addWidget(close)
        root.addWidget(ftr)

    def _save_email(self):
        email = self._email.text().strip()
        db.update_user_email(self._user["id"], email)
        self._user["email"] = email
        self._msg.setObjectName("AuthSuccess")
        self._msg.setText("✔  Email updated.")
        self._msg.style().unpolish(self._msg); self._msg.style().polish(self._msg)

    def _save_password(self):
        p1 = self._pw1.text(); p2 = self._pw2.text()
        if len(p1) < 6:
            self._msg.setObjectName("AuthError")
            self._msg.setText("✖  Password must be at least 6 characters.")
        elif p1 != p2:
            self._msg.setObjectName("AuthError")
            self._msg.setText("✖  Passwords do not match.")
        else:
            db.change_password(self._user["id"], p1)
            self._msg.setObjectName("AuthSuccess")
            self._msg.setText("✔  Password changed.")
            self._pw1.clear(); self._pw2.clear()
        self._msg.style().unpolish(self._msg); self._msg.style().polish(self._msg)


# ═══════════════════════════════════════════════════════════════════════════════
#  WORD GOAL DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class WordGoalDialog(QDialog):
    goal_set = pyqtSignal(int)

    def __init__(self, current_goal: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Word-Count Goal")
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self); lay.setSpacing(12); lay.setContentsMargins(24,20,24,20)
        lay.addWidget(make_label("Target word count (0 = disable):", "PayDesc"))
        self._spin = QSpinBox()
        self._spin.setRange(0, 999999)
        self._spin.setValue(current_goal)
        self._spin.setSingleStep(100)
        lay.addWidget(self._spin)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ok(self):
        self.goal_set.emit(self._spin.value()); self.accept()


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
        lw = QVBoxLayout(self._logo_wrap); lw.setContentsMargins(20,26,20,22); lw.setSpacing(3)
        self._logo_name = make_label("DocuFlow",    "logo_name")
        self._logo_tag  = make_label("FREE EDITION", "logo_tag")
        lw.addWidget(self._logo_name); lw.addWidget(self._logo_tag)
        lay.addWidget(self._logo_wrap)

        self._user_lbl = make_label("", "SidebarUser"); lay.addWidget(self._user_lbl)
        self._section  = make_label("WORKSPACE", "nav_section_label"); lay.addWidget(self._section)

        for key, icon, name in self.PAGES:
            btn = QPushButton(f"  {icon}   {name}")
            btn.setObjectName("NavBtn"); btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._activate(k))
            self._btns[key] = btn; lay.addWidget(btn)

        lay.addStretch()
        self._logout_btn = ghost_btn("⎋  Sign Out"); self._logout_btn.setObjectName("SidebarLogout")
        lay.addWidget(self._logout_btn)
        self._footer = make_label("v4.0  ·  © 2025", "sidebar_footer"); lay.addWidget(self._footer)
        self._activate("editor")

    def _activate(self, key):
        for k, b in self._btns.items():
            b.setProperty("active", "true" if k == key else "false")
            b.style().unpolish(b); b.style().polish(b)
        self.switched.emit(key)

    def set_user(self, username): self._user_lbl.setText(f"  👤  {username}")

    def set_compact(self, compact: bool):
        if compact == self._compact: return
        self._compact = compact
        for w in [self._logo_name, self._logo_tag, self._section, self._footer,
                  self._user_lbl, self._logout_btn]:
            w.setVisible(not compact)
        for key, icon, name in self.PAGES:
            self._btns[key].setText(icon if compact else f"  {icon}   {name}")
        self.setFixedWidth(56 if compact else 220)


# ═══════════════════════════════════════════════════════════════════════════════
#  HEADER  (no licence banner — just title row)
# ═══════════════════════════════════════════════════════════════════════════════

class Header(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Header")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
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
#  RIBBON TOOLBAR  — tabs: Home · Format · Tools
# ═══════════════════════════════════════════════════════════════════════════════

class Ribbon(QWidget):
    format_acted = pyqtSignal(str)
    import_docx  = pyqtSignal()
    import_file  = pyqtSignal()
    export_docx  = pyqtSignal()
    export_opt   = pyqtSignal()
    new_session  = pyqtSignal()
    save_backup  = pyqtSignal()
    toggle_dark  = pyqtSignal()
    set_goal     = pyqtSignal()

    bold_toggled   = pyqtSignal(bool)
    italic_toggled = pyqtSignal(bool)
    under_toggled  = pyqtSignal(bool)
    font_changed   = pyqtSignal(str)
    size_changed   = pyqtSignal(int)

    TABS = ["Home", "Format", "Tools"]

    def __init__(self, editor: QTextEdit):
        super().__init__()
        self._editor   = editor
        self._updating = False
        self._tab_idx  = 0

        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        tab_bar = QWidget(); tab_bar.setObjectName("RibbonTabBar")
        tb = QHBoxLayout(tab_bar); tb.setContentsMargins(0,0,0,0); tb.setSpacing(0)
        self._tab_btns = []
        for i, name in enumerate(self.TABS):
            b = QPushButton(name); b.setObjectName("RibbonTab")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            self._tab_btns.append(b); tb.addWidget(b)
        tb.addStretch()
        root.addWidget(tab_bar)

        self._panel_stack = QStackedWidget()
        self._panel_stack.setFixedHeight(90)
        self._panel_stack.addWidget(self._build_home())
        self._panel_stack.addWidget(self._build_format())
        self._panel_stack.addWidget(self._build_tools())
        root.addWidget(self._panel_stack)

        self._switch_tab(0)
        editor.cursorPositionChanged.connect(self._sync_char_fmt)
        editor.currentCharFormatChanged.connect(self._on_char_fmt)

    def _switch_tab(self, idx):
        self._tab_idx = idx
        self._panel_stack.setCurrentIndex(idx)
        for i, b in enumerate(self._tab_btns):
            b.setProperty("active", "true" if i == idx else "false")
            b.style().unpolish(b); b.style().polish(b)

    def _panel(self) -> QWidget:
        w = QWidget(); w.setObjectName("RibbonPanel"); return w

    def _group(self, label: str, parent_lay: QHBoxLayout, last=False) -> QHBoxLayout:
        wrap = QWidget()
        wrap.setObjectName("RibbonGroupLast" if last else "RibbonGroup")
        inner = QVBoxLayout(wrap); inner.setContentsMargins(8,4,8,6); inner.setSpacing(2)
        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        inner.addLayout(btn_row, stretch=0)
        lbl = make_label(label, "RibbonGroupLabel")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(lbl)
        parent_lay.addWidget(wrap)
        if not last:
            sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
            sep.setFixedWidth(2); sep.setMinimumHeight(50)
            sep.setStyleSheet("background-color: #B0D8C0; margin: 4px 2px;")
            parent_lay.addWidget(sep)
        return btn_row

    # ── Home tab ─────────────────────────────────────────────────────────────
    def _build_home(self) -> QWidget:
        p = self._panel(); lay = QHBoxLayout(p); lay.setContentsMargins(16,0,16,0); lay.setSpacing(0)

        g = self._group("FILE", lay)
        b = ribbon_btn("⬆", "Import .docx", "Import a Word document", primary=False)
        b.clicked.connect(self.import_docx); g.addWidget(b)
        b = ribbon_btn("⬆", "Import File", "Import text/HTML/CSV… up to 500 MB")
        b.clicked.connect(self.import_file); g.addWidget(b)

        g = self._group("EXPORT", lay)
        b = ribbon_btn("⬇", "Export .docx", "Save as Word document", primary=True)
        b.clicked.connect(self.export_docx); g.addWidget(b)
        b = ribbon_btn("⬇", "Optimised", "Export compressed (images reduced)")
        b.clicked.connect(self.export_opt); g.addWidget(b)

        g = self._group("SESSION", lay)
        b = ribbon_btn("＋", "New Session", "Create a new workspace session")
        b.clicked.connect(self.new_session); g.addWidget(b)

        g = self._group("BACKUP", lay)
        b = ribbon_btn("🗄", "Save Backup", "Save a snapshot of the current text")
        b.clicked.connect(self.save_backup); g.addWidget(b)

        g = self._group("VIEW", lay, last=True)
        b = ribbon_btn("🌙", "Dark Mode", "Toggle dark / light theme")
        b.clicked.connect(self.toggle_dark); g.addWidget(b)
        b = ribbon_btn("🎯", "Word Goal", "Set a word-count writing goal")
        b.clicked.connect(self.set_goal); g.addWidget(b)

        lay.addStretch()
        return p

    # ── Format tab ───────────────────────────────────────────────────────────
    def _build_format(self) -> QWidget:
        p = self._panel(); lay = QHBoxLayout(p); lay.setContentsMargins(16,0,16,0); lay.setSpacing(0)

        g = self._group("TEXT STYLE", lay)
        self._bold_btn = QPushButton("B"); self._bold_btn.setObjectName("RichBtnBold")
        self._bold_btn.setCheckable(True); self._bold_btn.setFixedSize(34,34)
        self._bold_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bold_btn.clicked.connect(lambda c: self._apply_bold(c)); g.addWidget(self._bold_btn)

        self._ital_btn = QPushButton("I"); self._ital_btn.setObjectName("RichBtnItalic")
        self._ital_btn.setCheckable(True); self._ital_btn.setFixedSize(34,34)
        self._ital_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ital_btn.clicked.connect(lambda c: self._apply_italic(c)); g.addWidget(self._ital_btn)

        self._und_btn = QPushButton("U"); self._und_btn.setObjectName("RichBtnUnder")
        self._und_btn.setCheckable(True); self._und_btn.setFixedSize(34,34)
        self._und_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._und_btn.clicked.connect(lambda c: self._apply_underline(c)); g.addWidget(self._und_btn)

        g = self._group("FONT FAMILY", lay)
        self._font_cb = QComboBox(); self._font_cb.setObjectName("FontCombo")
        self._font_cb.setMinimumWidth(150)
        for f in FONT_FAMILIES: self._font_cb.addItem(f)
        self._font_cb.setCurrentText("Calibri")
        self._font_cb.currentTextChanged.connect(self._apply_font_family); g.addWidget(self._font_cb)

        g = self._group("SIZE", lay)
        self._size_dec = QPushButton("A−"); self._size_dec.setObjectName("RibbonBtn")
        self._size_dec.setFixedSize(36,34)
        self._size_dec.clicked.connect(lambda: self._change_size(-1)); g.addWidget(self._size_dec)
        self._size_spin = QSpinBox(); self._size_spin.setObjectName("FontSizeSpin")
        self._size_spin.setRange(6,96); self._size_spin.setValue(DEFAULT_FONT_SIZE)
        self._size_spin.setFixedWidth(52)
        self._size_spin.valueChanged.connect(self._apply_font_size); g.addWidget(self._size_spin)
        self._size_inc = QPushButton("A+"); self._size_inc.setObjectName("RibbonBtn")
        self._size_inc.setFixedSize(36,34)
        self._size_inc.clicked.connect(lambda: self._change_size(+1)); g.addWidget(self._size_inc)

        g = self._group("ALIGNMENT", lay)
        for icon, label, key in [("⬅","Left","align_left"),("⊟","Center","align_center"),("➡","Right","align_right")]:
            b = QPushButton(icon); b.setObjectName("RibbonBtn"); b.setFixedSize(36,34)
            b.setToolTip(f"{label} align"); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, k=key: self.format_acted.emit(k)); g.addWidget(b)

        g = self._group("CASE", lay, last=True)
        for icon, label, key in [("AA","UPPER","to_upper"),("aa","lower","to_lower"),("Aa","Title","to_title"),("A.","Sentence","to_sentence")]:
            b = QPushButton(icon); b.setObjectName("RibbonBtn"); b.setFixedSize(36,34)
            b.setToolTip(f"{label} case"); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, k=key: self.format_acted.emit(k)); g.addWidget(b)

        lay.addStretch(); return p

    # ── Tools tab ────────────────────────────────────────────────────────────
    def _build_tools(self) -> QWidget:
        p = self._panel(); lay = QHBoxLayout(p); lay.setContentsMargins(16,0,16,0); lay.setSpacing(0)

        g = self._group("CLEAN", lay)
        b = ribbon_btn("⌫", "Remove\nSpaces", "Collapse extra spaces and blank lines")
        b.clicked.connect(lambda: self.format_acted.emit("remove_spaces")); g.addWidget(b)

        g = self._group("SEPARATOR", lay)
        b = ribbon_btn("＋", "Add Sep", "Insert a horizontal separator at the cursor line")
        b.clicked.connect(lambda: self.format_acted.emit("add_separator")); g.addWidget(b)
        b = ribbon_btn("✕", "Remove\nSep", "Remove all separator lines")
        b.clicked.connect(lambda: self.format_acted.emit("remove_separator")); g.addWidget(b)

        g = self._group("TEXT STATS", lay, last=True)
        b = ribbon_btn("📊", "Word\nFreq", "Show most frequent words in the text")
        b.clicked.connect(lambda: self.format_acted.emit("word_freq")); g.addWidget(b)

        lay.addStretch(); return p

    # ── rich-text helpers ─────────────────────────────────────────────────────
    def _apply_fmt(self, fmt):
        c = self._editor.textCursor()
        if c.hasSelection(): c.mergeCharFormat(fmt)
        else: self._editor.mergeCurrentCharFormat(fmt)

    def _apply_bold(self, checked):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if checked else QFont.Weight.Normal)
        self._apply_fmt(fmt)

    def _apply_italic(self, checked):
        fmt = QTextCharFormat(); fmt.setFontItalic(checked); self._apply_fmt(fmt)

    def _apply_underline(self, checked):
        fmt = QTextCharFormat(); fmt.setFontUnderline(checked); self._apply_fmt(fmt)

    def _apply_font_family(self, family):
        if self._updating: return
        fmt = QTextCharFormat(); fmt.setFontFamilies([family]); self._apply_fmt(fmt)

    def _apply_font_size(self, size):
        if self._updating: return
        fmt = QTextCharFormat(); fmt.setFontPointSize(float(size)); self._apply_fmt(fmt)

    def _change_size(self, delta):
        self._size_spin.setValue(max(6, min(96, self._size_spin.value() + delta)))

    def _sync_char_fmt(self):
        self._on_char_fmt(self._editor.textCursor().charFormat())

    def _on_char_fmt(self, fmt):
        self._updating = True
        self._bold_btn.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
        self._ital_btn.setChecked(fmt.fontItalic())
        self._und_btn.setChecked(fmt.fontUnderline())
        fam = fmt.fontFamilies()
        if fam and fam[0] in FONT_FAMILIES:
            self._font_cb.setCurrentText(fam[0])
        sz = fmt.fontPointSize()
        if sz > 0: self._size_spin.setValue(int(sz))
        self._updating = False


# ═══════════════════════════════════════════════════════════════════════════════
#  FIND BAR
# ═══════════════════════════════════════════════════════════════════════════════

class FindBar(QWidget):
    acted = pyqtSignal(str, str, bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("FindBar"); self.setFixedHeight(44)
        lay = QHBoxLayout(self); lay.setContentsMargins(24,0,24,0); lay.setSpacing(8)
        lay.addWidget(make_label("FIND & REPLACE", "GroupLabel"))
        self._find    = QLineEdit(); self._find.setObjectName("FindInput"); self._find.setPlaceholderText("Find…")
        self._replace = QLineEdit(); self._replace.setObjectName("ReplaceInput"); self._replace.setPlaceholderText("Replace with…")
        self._case    = QCheckBox("Match case"); self._case.setObjectName("CaseCheck")
        btn = QPushButton("Replace All"); btn.setObjectName("ReplaceBtn")
        btn.clicked.connect(self._go); self._find.returnPressed.connect(self._go)
        lay.addWidget(self._find); lay.addWidget(make_label("→"))
        lay.addWidget(self._replace); lay.addWidget(self._case); lay.addWidget(btn); lay.addStretch()

    def _go(self):
        self.acted.emit(self._find.text(), self._replace.text(), self._case.isChecked())


# ═══════════════════════════════════════════════════════════════════════════════
#  SESSION ROW
# ═══════════════════════════════════════════════════════════════════════════════

class SessionRow(QWidget):
    new_session      = pyqtSignal()
    session_selected = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("SessionRow")
        lay = QHBoxLayout(self); lay.setContentsMargins(24,0,24,0); lay.setSpacing(8)
        lay.addWidget(make_label("Session:", "GroupLabel"))
        self.combo = QComboBox(); self.combo.setPlaceholderText("Select a session…")
        self.combo.setMinimumWidth(200); lay.addWidget(self.combo)
        btn = ghost_btn("＋ New"); btn.clicked.connect(self.new_session); lay.addWidget(btn)
        lay.addStretch()
        self.combo.currentIndexChanged.connect(
            lambda i: self.session_selected.emit(self.combo.itemData(i) or 0)
        )

    def refresh(self, sessions, active_id=None):
        self.combo.blockSignals(True); self.combo.clear()
        for s in sessions:
            self.combo.addItem(s["name"], userData=s["id"])
        if active_id is not None:
            for i in range(self.combo.count()):
                if self.combo.itemData(i) == active_id:
                    self.combo.setCurrentIndex(i); break
        self.combo.blockSignals(False)

    def current_id(self):
        i = self.combo.currentIndex()
        return self.combo.itemData(i) if i >= 0 else None

    def current_name(self): return self.combo.currentText() or ""


# ═══════════════════════════════════════════════════════════════════════════════
#  STATUS BAR  — shows word/char/line stats + word-goal progress
# ═══════════════════════════════════════════════════════════════════════════════

class StatusBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("StatusBar"); self.setFixedHeight(28)
        lay = QHBoxLayout(self); lay.setContentsMargins(24,0,24,0); lay.setSpacing(22)
        self._w  = make_label("Words: 0",  "StatLabel")
        self._c  = make_label("Chars: 0",  "StatLabel")
        self._l  = make_label("Lines: 1",  "StatLabel")
        self._goal_lbl  = make_label("",   "StatLabel")
        self._goal_bar  = QProgressBar()
        self._goal_bar.setFixedWidth(120); self._goal_bar.setFixedHeight(14)
        self._goal_bar.setTextVisible(False); self._goal_bar.hide()
        self._fl = make_label("", "FlashLabel")
        for w in (self._w, self._c, self._l): lay.addWidget(w)
        lay.addWidget(self._goal_lbl)
        lay.addWidget(self._goal_bar)
        lay.addStretch(); lay.addWidget(self._fl)
        self._timer = QTimer(singleShot=True); self._timer.timeout.connect(lambda: self._fl.setText(""))
        self._goal = 0

    def set_goal(self, g: int):
        self._goal = g
        self._goal_bar.setVisible(g > 0)
        self._goal_lbl.setVisible(g > 0)
        if g > 0:
            self._goal_bar.setRange(0, g)

    def update(self, text):
        s = stats(text)
        self._w.setText(f"Words: {s['words']}")
        self._c.setText(f"Chars: {s['chars']}")
        self._l.setText(f"Lines: {s['lines']}")
        if self._goal > 0:
            pct = min(100, int(s["words"] / self._goal * 100))
            self._goal_bar.setValue(min(s["words"], self._goal))
            self._goal_lbl.setText(f"Goal: {s['words']}/{self._goal} ({pct}%)")
            self._goal_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: %s; border-radius: 3px; }"
                % ("#2ECC71" if pct < 100 else "#F1C40F")
            )

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
    _FN = {
        "remove_spaces": remove_spaces, "remove_separator": remove_separator,
        "to_upper": to_upper, "to_lower": to_lower,
        "to_title": to_title, "to_sentence": to_sentence,
    }

    def __init__(self, header: Header, user: dict):
        super().__init__()
        self.setObjectName("PageArea")
        self._header      = header
        self._user        = user
        self._undo        = []
        self._active_id   = None
        self._source_path = None
        self._word_goal   = 0
        self._dark_mode   = False

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        self.editor = QTextEdit(); self.editor.setObjectName("Editor")
        self.editor.setPlaceholderText(
            "Start typing, paste text, or import a file from the Home tab above.\n\n"
            "Use the Format tab for text styling and alignment.\n"
            "Use the Tools tab for cleaning, separators, and word frequency."
        )
        self.editor.textChanged.connect(self._text_changed)

        self.ribbon = Ribbon(self.editor)
        self.ribbon.format_acted.connect(self._format)
        self.ribbon.import_docx.connect(self._import_docx)
        self.ribbon.import_file.connect(self._import_text)
        self.ribbon.export_docx.connect(self._export_normal)
        self.ribbon.export_opt.connect(self._export_optimised)
        self.ribbon.new_session.connect(self._new_session)
        self.ribbon.save_backup.connect(self._backup)
        self.ribbon.toggle_dark.connect(self._toggle_dark)
        self.ribbon.set_goal.connect(self._open_goal_dialog)
        lay.addWidget(self.ribbon)
        lay.addSpacing(12)

        self.sess_row = SessionRow()
        self.sess_row.new_session.connect(self._new_session)
        self.sess_row.session_selected.connect(self._session_selected_by_id)
        lay.addWidget(self.sess_row)

        self.find_bar = FindBar(); self.find_bar.acted.connect(self._find_replace)
        lay.addWidget(self.find_bar)

        lay.addWidget(self.editor, stretch=1)
        self.status = StatusBar(); lay.addWidget(self.status)

        # Auto-save timer (every 60 s)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start(60_000)

        self._refresh_sessions()

    # ── sessions ──────────────────────────────────────────────────────────────

    def _refresh_sessions(self, keep_id=None):
        sessions = db.get_sessions(self._user["id"])
        self.sess_row.refresh(sessions, keep_id or self._active_id)
        if self._active_id is None and sessions:
            self._active_id = sessions[0]["id"]

    def _session_selected_by_id(self, sid):
        if sid:
            self._active_id = sid
            self._header.set_session(self.sess_row.current_name())
            db.log("SESSION_SWITCHED", self.sess_row.current_name(), sid=sid, uid=self._user["id"])

    def _new_session(self):
        dlg = NameDialog("New Session", "Session name:", self)
        if dlg.exec() and dlg.value().strip():
            name = dlg.value().strip()
            sid  = db.create_session(self._user["id"], name)
            db.log("SESSION_CREATED", name, sid=sid, uid=self._user["id"])
            self._active_id = sid
            self._refresh_sessions(sid)
            self._header.set_session(name)
            self.status.flash("✦ Session created")

    # ── auto-save ─────────────────────────────────────────────────────────────

    def _autosave(self):
        sid  = self._active_id
        text = self.editor.toPlainText()
        if not sid or not text.strip():
            return
        s = stats(text)
        db.save_backup(sid, text, f"[auto] {s['words']} words")
        db.log("BACKUP", "[auto-save]", sid=sid, uid=self._user["id"])
        self.status.flash("🗄 Auto-saved")

    # ── dark mode ─────────────────────────────────────────────────────────────

    def _toggle_dark(self):
        self._dark_mode = not self._dark_mode
        app = QApplication.instance()
        app.setStyleSheet(_get_qss(dark=self._dark_mode))
        self.status.flash("🌙 Dark mode ON" if self._dark_mode else "☀ Light mode ON")

    # ── word goal ─────────────────────────────────────────────────────────────

    def _open_goal_dialog(self):
        dlg = WordGoalDialog(self._word_goal, self)
        dlg.goal_set.connect(self._apply_goal)
        dlg.exec()

    def _apply_goal(self, g: int):
        self._word_goal = g
        self.status.set_goal(g)
        self.status.update(self.editor.toPlainText())
        self.status.flash(f"🎯 Goal set: {g} words" if g else "🎯 Goal cleared")

    # ── text ──────────────────────────────────────────────────────────────────

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

    def _set_text(self, t):
        st = _save_state(self.editor)
        self.editor.blockSignals(True)
        self.editor.setPlainText(t)
        self.editor.blockSignals(False)
        _restore_state(self.editor, st)

    def _text_changed(self): self.status.update(self.editor.toPlainText())

    # ── format ────────────────────────────────────────────────────────────────

    def _format(self, key):
        text = self.editor.toPlainText()
        if key == "word_freq":
            self._show_word_freq(text); return
        if not text.strip(): return
        self._push_undo()
        if key in self._ALIGN_MAP:
            _apply_block_alignment(self.editor, self._ALIGN_MAP[key])
        elif key == "add_separator":
            new = add_separator_at(text, _cursor_line(self.editor))
            self._set_text(new); self.status.update(new)
        else:
            new = self._FN[key](text)
            self._set_text(new); self.status.update(new)
        db.log("FORMAT", key, sid=self._active_id, uid=self._user["id"])
        self.status.flash("✔ Applied")

    def _show_word_freq(self, text):
        if not text.strip():
            QMessageBox.information(self, "Word Frequency", "The editor is empty."); return
        import re, collections
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        if not words:
            QMessageBox.information(self, "Word Frequency", "No words found."); return
        top = collections.Counter(words).most_common(20)
        lines = "\n".join(f"  {w:<20} {c}" for w, c in top)
        QMessageBox.information(self, "Top 20 Words", f"{'WORD':<20} COUNT\n{'─'*28}\n{lines}")

    def _find_replace(self, find, replace, case):
        if not find: return
        text = self.editor.toPlainText(); self._push_undo()
        new = find_replace(text, find, replace, case)
        self._set_text(new); self.status.update(new)
        db.log("REPLACE", f"'{find}'→'{replace}'", sid=self._active_id, uid=self._user["id"])
        self.status.flash("✔ Replace done")

    # ── import ────────────────────────────────────────────────────────────────

    def _import_docx(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Word Document", "", "Word Documents (*.docx);;All Files (*)")
        if not path: return
        if not docx_ok(): QMessageBox.critical(self, "Error", "pip install python-docx"); return
        try:
            self._push_undo(); text, images = read_docx(path)
            self._source_path = path; self._set_text(text)
            if images: self._insert_images(images)
            db.log("IMPORT", os.path.basename(path), sid=self._active_id, uid=self._user["id"])
            self.status.flash(f"⬆ {os.path.basename(path)}  ({os.path.getsize(path)/1024:.0f} KB)")
        except Exception as e: QMessageBox.critical(self, "Import failed", str(e))

    def _import_text(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import File", "",
            "Files (*.txt *.md *.csv *.html *.htm *.json *.xml *.log *.docx);;All Files (*)")
        if not path: return
        size = os.path.getsize(path)
        if size > MAX_UPLOAD_BYTES:
            QMessageBox.critical(self, "File too large", f"{size/1_048_576:.1f} MB — limit 500 MB"); return
        try:
            self._push_undo()
            ext = os.path.splitext(path)[1].lower()
            if ext == ".docx" and docx_ok():
                text, images = read_docx(path); self._source_path = path
                self._set_text(text)
                if images: self._insert_images(images)
            else:
                text, _ = read_text_file(path); self._source_path = None; self._set_text(text)
            db.log("IMPORT", os.path.basename(path), sid=self._active_id, uid=self._user["id"])
            self.status.flash(f"⬆ {os.path.basename(path)}  ({size/1024:.0f} KB)")
        except Exception as e: QMessageBox.critical(self, "Import failed", str(e))

    # ── export ────────────────────────────────────────────────────────────────

    def _export_normal(self):
        text = self.editor.toPlainText()
        if not text.strip(): QMessageBox.warning(self, "Empty", "The editor is empty."); return
        if not docx_ok(): QMessageBox.critical(self, "Error", "pip install python-docx"); return
        path, _ = QFileDialog.getSaveFileName(self, "Export Word Document", "document.docx", "Word Documents (*.docx)")
        if not path: return
        try:
            write_docx(text, path, self._collect_alignments())
            db.log("EXPORT", os.path.basename(path), sid=self._active_id, uid=self._user["id"])
            self.status.flash(f"⬇ {os.path.basename(path)}  ({os.path.getsize(path)/1024:.0f} KB)")
        except Exception as e: QMessageBox.critical(self, "Export failed", str(e))

    def _export_optimised(self):
        text = self.editor.toPlainText()
        if not text.strip(): QMessageBox.warning(self, "Empty", "The editor is empty."); return
        if not docx_ok(): QMessageBox.critical(self, "Error", "pip install python-docx"); return
        path, _ = QFileDialog.getSaveFileName(self, "Export Optimised .docx", "document_opt.docx", "Word Documents (*.docx)")
        if not path: return
        try:
            if self._source_path and os.path.exists(self._source_path):
                sd = optimise_existing_docx(self._source_path, path)
            else:
                sd = write_docx_optimised(text, path, self._collect_alignments())
            pct  = max(0, (1 - sd["final_kb"] / sd["original_kb"]) * 100) if sd["original_kb"] else 0
            imgs = f", {sd['images_processed']} image(s) resampled" if sd["images_processed"] else ""
            db.log("EXPORT_OPTIMISED", f"{os.path.basename(path)} | {sd['original_kb']:.0f}→{sd['final_kb']:.0f} KB{imgs}",
                   sid=self._active_id, uid=self._user["id"])
            self.status.flash(f"⬇ {os.path.basename(path)}  {sd['original_kb']:.0f}→{sd['final_kb']:.0f} KB  ({pct:.0f}% smaller{imgs})")
        except Exception as e: QMessageBox.critical(self, "Export failed", str(e))

    # ── backup ────────────────────────────────────────────────────────────────

    def _backup(self):
        sid = self._active_id
        if not sid: QMessageBox.information(self, "No session", "Create a session first."); return
        text = self.editor.toPlainText()
        if not text.strip(): QMessageBox.warning(self, "Empty", "The editor is empty."); return
        s = stats(text); label = f"{s['words']} words · {s['lines']} lines"
        db.save_backup(sid, text, label)
        db.log("BACKUP", label, sid=sid, uid=self._user["id"])
        self.status.flash("🗄 Backup saved")

    def load_text(self, text): self._push_undo(); self._set_text(text)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _insert_images(self, images):
        from PyQt6.QtCore import QByteArray
        c = self.editor.textCursor(); c.movePosition(QTextCursor.MoveOperation.End)
        c.insertBlock(); c.insertText("\n── Embedded Images ──")
        for i, img_bytes in enumerate(images):
            try:
                img = QImage.fromData(QByteArray(img_bytes))
                if img.isNull(): continue
                max_w = max(400, self.editor.viewport().width() - 80)
                if img.width() > max_w:
                    img = img.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
                name = f"df_img_{id(self)}_{i}"
                self.editor.document().addResource(3, QUrl(name), img)
                fmt = QTextImageFormat(); fmt.setName(name)
                fmt.setWidth(img.width()); fmt.setHeight(img.height())
                c.insertBlock(); c.insertImage(fmt)
            except Exception: pass

    def _collect_alignments(self):
        result = {}; block = self.editor.document().begin(); i = 0
        while block.isValid():
            a = block.blockFormat().alignment()
            if a in (Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignCenter): result[i] = "center"
            elif a == Qt.AlignmentFlag.AlignRight: result[i] = "right"
            block = block.next(); i += 1
        return result or None


# ═══════════════════════════════════════════════════════════════════════════════
#  SESSIONS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class SessionsPage(QWidget):
    restore = pyqtSignal(str)

    def __init__(self, user: dict):
        super().__init__(); self._user = user; self.setObjectName("PageArea")
        lay = QHBoxLayout(self); lay.setContentsMargins(24,24,24,24); lay.setSpacing(20)

        left = QVBoxLayout(); left.setSpacing(10)
        left.addWidget(make_label("SESSIONS", "CardTitle"))
        self.sess_list = QListWidget(); self.sess_list.setObjectName("SessionList")
        self.sess_list.currentRowChanged.connect(self._session_selected)
        left.addWidget(self.sess_list)
        row = QHBoxLayout(); row.setSpacing(8)
        del_btn = danger_btn("🗑  Delete"); del_btn.clicked.connect(self._delete_session)
        ref_btn = ghost_btn("↺  Refresh");  ref_btn.clicked.connect(self.refresh)
        row.addWidget(del_btn); row.addWidget(ref_btn); left.addLayout(row)

        right = QVBoxLayout(); right.setSpacing(10)
        right.addWidget(make_label("BACKUPS · SELECT TO PREVIEW & RESTORE", "CardTitle"))
        self.backup_list = QListWidget(); self.backup_list.setObjectName("BackupList")
        self.backup_list.currentRowChanged.connect(self._backup_selected)
        self.preview = QTextEdit(); self.preview.setObjectName("Editor")
        self.preview.setReadOnly(True); self.preview.setMaximumHeight(160)
        self.preview.setPlaceholderText("Select a backup to preview…")
        btn_row = QHBoxLayout()
        restore_btn = QPushButton("↩  Restore to Editor"); restore_btn.clicked.connect(self._restore)
        del_bk_btn  = danger_btn("🗑  Delete Backup");     del_bk_btn.clicked.connect(self._delete_backup)
        btn_row.addWidget(restore_btn); btn_row.addWidget(del_bk_btn)
        right.addWidget(self.backup_list)
        right.addWidget(make_label("PREVIEW", "CardTitle"))
        right.addWidget(self.preview)
        right.addLayout(btn_row)

        lw = QWidget(); lw.setLayout(left); rw = QWidget(); rw.setLayout(right)
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(lw); sp.addWidget(rw); sp.setSizes([260, 640])
        lay.addWidget(sp); self.refresh()

    def refresh(self):
        self.sess_list.clear()
        for s in db.get_sessions(self._user["id"]):
            bk_count = db.count_backups(s["id"])
            item = QListWidgetItem(f"  📁  {s['name']}   ·   {s['updated_at']}   ·   {bk_count} backup(s)")
            item.setData(Qt.ItemDataRole.UserRole, s["id"]); self.sess_list.addItem(item)

    def _session_selected(self, row):
        self.backup_list.clear(); self.preview.clear()
        item = self.sess_list.item(row)
        if not item: return
        for b in db.get_backups(item.data(Qt.ItemDataRole.UserRole)):
            bi = QListWidgetItem(f"  💾  {b['saved_at']}   ·   {b['label']}")
            bi.setData(Qt.ItemDataRole.UserRole, b["id"]); self.backup_list.addItem(bi)

    def _backup_selected(self, row):
        item = self.backup_list.item(row)
        if not item: return
        b = db.get_backup(item.data(Qt.ItemDataRole.UserRole))
        if b: self.preview.setPlainText(b["content"][:800] + ("…" if len(b["content"]) > 800 else ""))

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

    def _delete_backup(self):
        item = self.backup_list.currentItem()
        if not item: return
        bid = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Delete Backup", "Permanently delete this backup?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            db.delete_backup(bid)
            db.log("BACKUP_DELETED", f"id={bid}", uid=self._user["id"])
            self.refresh()

    def _delete_session(self):
        item = self.sess_list.currentItem()
        if not item: return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Delete Session", "Delete this session and all backups?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            db.delete_session(sid); db.log("SESSION_DELETED", f"id={sid}", uid=self._user["id"])
            self.refresh()


# ═══════════════════════════════════════════════════════════════════════════════
#  LOG PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class LogPage(QWidget):
    def __init__(self, user: dict):
        super().__init__(); self._user = user; self.setObjectName("PageArea")
        lay = QVBoxLayout(self); lay.setContentsMargins(24,24,24,24); lay.setSpacing(12)
        hdr = QHBoxLayout()
        hdr.addWidget(make_label("ACTIVITY LOG", "CardTitle"))
        hdr.addStretch()
        ref_btn = ghost_btn("↺  Refresh"); ref_btn.clicked.connect(self.refresh); hdr.addWidget(ref_btn)
        clr_btn = danger_btn("🗑  Clear Log"); clr_btn.clicked.connect(self._clear_log); hdr.addWidget(clr_btn)
        lay.addLayout(hdr)
        self.list = QListWidget(); self.list.setObjectName("LogList"); lay.addWidget(self.list)
        self.refresh()

    ICONS = {"FORMAT":"🔧","IMPORT":"⬆","EXPORT":"⬇","EXPORT_OPTIMISED":"⬇✦",
             "BACKUP":"🗄","RESTORE":"↩","REPLACE":"✏","BACKUP_DELETED":"🗑",
             "SESSION_CREATED":"✦","SESSION_DELETED":"🗑","SESSION_SWITCHED":"⊞"}

    def refresh(self):
        self.list.clear()
        for l in db.get_logs(self._user["id"]):
            icon   = self.ICONS.get(l["action"], "·")
            detail = f"   {l['detail']}" if l["detail"] else ""
            self.list.addItem(QListWidgetItem(f"  {icon}  {l['at']}    {l['action']}{detail}"))

    def _clear_log(self):
        if QMessageBox.question(self, "Clear Log", "Delete all activity log entries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            db.clear_logs(self._user["id"])
            self.refresh()


# ═══════════════════════════════════════════════════════════════════════════════
#  NAME DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class NameDialog(QDialog):
    def __init__(self, title, label, parent=None):
        super().__init__(parent); self.setWindowTitle(title); self.setMinimumWidth(340)
        lay = QVBoxLayout(self); lay.setSpacing(12)
        lay.addWidget(QLabel(label)); self._inp = QLineEdit(); lay.addWidget(self._inp)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); lay.addWidget(bb)

    def value(self): return self._inp.text()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DocuFlow — Free Edition")
        self.resize(1340, 880); self.setMinimumSize(680, 560)
        self._user = None

        self._root_stack = QStackedWidget(); self.setCentralWidget(self._root_stack)
        self._auth_page  = AuthPage(); self._auth_page.logged_in.connect(self._on_login)
        self._root_stack.addWidget(self._auth_page)
        self._app_shell = None

    def _on_login(self, user: dict):
        self._user = user
        if self._app_shell:
            self._root_stack.removeWidget(self._app_shell); self._app_shell.deleteLater()
        self._app_shell = self._build_shell(user)
        self._root_stack.addWidget(self._app_shell); self._root_stack.setCurrentIndex(1)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._editor_page.undo)

    def _build_shell(self, user: dict) -> QWidget:
        shell = QWidget(); lay = QHBoxLayout(shell); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        self.sidebar = Sidebar(); self.sidebar.set_user(user["username"])
        self.sidebar.switched.connect(self._switch)
        self.sidebar._logout_btn.clicked.connect(self._logout)
        lay.addWidget(self.sidebar)

        content = QWidget(); cl = QVBoxLayout(content); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)
        self.header = Header()
        cl.addWidget(self.header)

        # Profile button in header
        profile_btn = ghost_btn("👤 Profile")
        profile_btn.clicked.connect(self._open_profile)
        self.header.layout().itemAt(0).widget().layout().addWidget(profile_btn)

        self.stack          = QStackedWidget()
        self._editor_page   = EditorPage(self.header, user)
        self._sessions_page = SessionsPage(user)
        self._log_page      = LogPage(user)
        self._sessions_page.restore.connect(self._do_restore)
        self.stack.addWidget(self._editor_page)
        self.stack.addWidget(self._sessions_page)
        self.stack.addWidget(self._log_page)
        cl.addWidget(self.stack); lay.addWidget(content, stretch=1)
        return shell

    PAGE_MAP = {"editor": 0, "sessions": 1, "log": 2}
    TITLES   = {"editor": "Text Editor", "sessions": "Sessions & Backups", "log": "Activity Log"}

    def _switch(self, key):
        self.stack.setCurrentIndex(self.PAGE_MAP[key])
        self.header.set_title(self.TITLES[key])
        if key == "sessions": self._sessions_page.refresh(); self._editor_page._refresh_sessions()
        elif key == "log":    self._log_page.refresh()

    def _do_restore(self, text):
        self._editor_page.load_text(text)
        self.sidebar._activate("editor"); self._switch("editor")

    def _open_profile(self):
        dlg = ProfileDialog(self._user, self); dlg.exec()

    def _logout(self):
        self._user = None; self._root_stack.setCurrentIndex(0)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self.sidebar.set_compact(event.size().width() < COMPACT_WIDTH)


# ═══════════════════════════════════════════════════════════════════════════════
#  STYLESHEET  (light + dark variants)
# ═══════════════════════════════════════════════════════════════════════════════

_LIGHT_QSS = """
* { outline: none; }
QWidget { background-color: #F0F4F1; color: #0A1A0F; font-family: "Outfit","DM Sans","Segoe UI",sans-serif; font-size: 13px; }
QMainWindow { background-color: #0A1A0F; }
QDialog     { background-color: #FAFCFA; }
QLabel      { background: transparent; }
#Sidebar { background-color: #071610; min-width: 220px; max-width: 220px; border-right: 3px solid #2ECC71; }
#logo_wrap { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0D2419,stop:1 #071610); padding: 26px 20px 22px 20px; border-bottom: 3px solid #2ECC71; }
#logo_name { color: #FFFFFF; font-size: 22px; font-weight: 800; letter-spacing: -0.8px; }
#logo_tag  { color: #2ECC71; font-size: 8px; letter-spacing: 5px; font-weight: 700; margin-top: 3px; }
#SidebarUser { color: #FFFFFF; font-size: 12px; font-weight: 700; padding: 12px 20px 10px 20px; border-bottom: 2px solid #2ECC71; border-top: 1px solid #1E6040; background-color: #091D14; }
#nav_section_label { color: #2ECC71; font-size: 8px; letter-spacing: 3px; font-weight: 800; padding: 14px 20px 6px 20px; border-bottom: 2px solid #1A4A2E; }
#NavBtn { background-color: transparent; color: #8AC8A0; border: none; border-radius: 0; padding: 12px 20px; text-align: left; font-size: 13px; font-weight: 600; border-left: 4px solid transparent; border-bottom: 1px solid #1A3A28; }
#NavBtn:hover { background-color: #112E1A; color: #FFFFFF; border-left: 4px solid #2ECC71; }
#NavBtn[active="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1A4A28,stop:1 #112E1A); color: #FFFFFF; font-weight: 800; border-left: 4px solid #2ECC71; border-bottom: 1px solid #1A3A28; }
#SidebarLogout { background-color: transparent; color: #E08090; border: 1px solid #5A2030; border-radius: 6px; margin: 8px 14px; padding: 7px 16px; font-size: 11px; font-weight: 600; }
#SidebarLogout:hover { background-color: #5A2030; color: #FFFFFF; border-color: #FF4060; }
#sidebar_footer { color: #2ECC71; font-size: 9px; padding: 12px 20px; border-top: 2px solid #1A4A2E; }
#HeaderTitleRow { background-color: #FFFFFF; border-bottom: 1px solid #D8EAE0; min-height:52px; max-height:52px; }
#page_title { font-size: 16px; font-weight: 800; color: #071610; }
#session_pill { background-color: #E8F5EE; color: #0D5C2E; border: 1.5px solid #A8D8B8; border-radius: 20px; padding: 4px 14px; font-size: 11px; font-weight: 700; }
#RibbonTabBar { background-color: #FFFFFF; border-bottom: 2px solid #1B6B3A; padding: 0 24px; min-height:28px; max-height:28px; }
#RibbonTab { background-color: transparent; color: #5A8A6A; border: none; border-bottom: 3px solid transparent; border-radius: 0; padding: 4px 18px; font-size: 11px; font-weight: 600; min-height:28px; margin-bottom:-2px; }
#RibbonTab:hover { color: #0D5C2E; background-color: #F0F8F3; }
#RibbonTab[active="true"] { color: #071610; font-weight: 800; border-bottom: 3px solid #1B8040; }
#RibbonPanel { background-color: #FAFCFA; border-bottom: 2px solid #A8D8B8; padding: 4px 8px; min-height:90px; max-height:90px; }
#RibbonGroup { border-right: 2px solid #B0D8C0; padding-right: 10px; margin-right: 4px; }
#RibbonGroupLast { padding-right: 6px; }
#RibbonGroupLabel { color: #1B6B3A; font-size: 8px; font-weight: 800; letter-spacing: 2px; margin-top: 2px; background-color: transparent; }
#RibbonBtn { background-color: transparent; color: #1A4D2E; border: 1px solid transparent; border-radius: 5px; padding: 4px 8px; font-size: 11px; font-weight: 600; min-height:30px; min-width:46px; }
#RibbonBtn:hover { background-color: #E0F0E8; border-color: #A8D8B8; }
#RibbonBtn:pressed { background-color: #C8E8D0; }
#RibbonBtnPrimary { background-color: #1B6B3A; color: #FFFFFF; border: none; border-radius: 6px; padding: 6px 10px; font-size: 12px; font-weight: 700; min-height:34px; }
#RibbonBtnPrimary:hover { background-color: #22874A; }
#SessionRow { background-color: #D6F5E3; border-bottom: 1px solid #A8D8B8; padding: 6px 24px; min-height:44px; max-height:44px; }
#GroupLabel { color: #5A8A6A; font-size: 8px; font-weight: 800; letter-spacing: 2px; margin-right: 6px; }
#RichBtnBold,#RichBtnItalic,#RichBtnUnder { background-color:#F0F6F2; color:#1A4D2E; border:1px solid #C8DDD0; border-radius:5px; padding:5px; min-height:30px; }
#RichBtnBold { font-weight:900; font-size:14px; min-width:34px; }
#RichBtnItalic { font-style:italic; font-size:14px; min-width:34px; }
#RichBtnUnder { text-decoration:underline; font-size:14px; min-width:34px; }
#RichBtnBold:checked,#RichBtnItalic:checked,#RichBtnUnder:checked { background-color:#1B6B3A; color:#FFFFFF; border-color:#1B6B3A; }
#FontCombo { min-width:155px; max-width:180px; font-size:12px; }
#FontSizeSpin { min-width:50px; max-width:50px; font-size:12px; font-weight:700; }
#FindBar { background-color: #F8FAF8; border-bottom: 1px solid #D8EAE0; padding: 7px 24px; min-height:44px; max-height:44px; }
#FindInput,#ReplaceInput { background-color:#FFFFFF; border:1px solid #C0D8C8; border-radius:5px; padding:5px 10px; color:#0A1A0F; font-size:12px; min-width:160px; max-width:180px; }
#FindInput:focus,#ReplaceInput:focus { border:1.5px solid #1B8040; }
#ReplaceBtn { background-color:#1B8040; color:#FFFFFF; border:none; border-radius:5px; padding:5px 16px; font-size:12px; font-weight:700; min-height:30px; }
#ReplaceBtn:hover { background-color:#2ECC71; color:#071610; }
#CaseCheck { color:#4A8060; font-size:11px; spacing:4px; }
#Editor { background-color:#FFFFFF; color:#0A1A0F; border:none; padding:28px 40px; font-family:"JetBrains Mono","Cascadia Code","Fira Code","Consolas",monospace; font-size:13px; selection-background-color:#B0E8C8; selection-color:#071610; }
#StatusBar { background-color:#071610; border-top:1px solid #1A3528; min-height:28px; max-height:28px; padding:0 24px; }
#StatLabel  { color:#3A7055; font-size:11px; font-weight:600; }
#FlashLabel { color:#2ECC71; font-size:11px; font-weight:700; }
#PageArea   { background-color:#F0F4F1; }
#CardTitle  { font-size:12px; font-weight:800; color:#071610; }
#SessionList,#BackupList,#LogList { background-color:#FFFFFF; border:1.5px solid #C8DDD0; border-radius:8px; padding:4px; outline:none; }
#SessionList::item,#BackupList::item,#LogList::item { padding:10px 14px; border-radius:6px; color:#1A3528; font-size:12px; border-bottom:1px solid #EEF5F0; }
#SessionList::item:selected,#BackupList::item:selected,#LogList::item:selected { background-color:#C8EDD8; color:#071610; font-weight:700; }
#SessionList::item:hover,#BackupList::item:hover,#LogList::item:hover { background-color:#EAF5EE; }
QPushButton { background-color:#1B6B3A; color:#FFFFFF; border:none; border-radius:6px; padding:7px 18px; font-size:12px; font-weight:700; min-height:32px; }
QPushButton:hover   { background-color:#22874A; }
QPushButton:pressed { background-color:#145C30; }
QPushButton#ghost   { background-color:transparent; color:#1B6B3A; border:1.5px solid #A8D8B8; font-weight:600; }
QPushButton#ghost:hover { background-color:#EAF5EE; border-color:#1B8040; }
QPushButton#danger  { background-color:transparent; color:#C03030; border:1.5px solid #F0C0C0; font-weight:600; }
QPushButton#danger:hover { background-color:#C03030; color:#FFFFFF; }
#VSep { background-color:#B0D0BC; max-width:1px; min-width:1px; min-height:24px; max-height:24px; margin:0 6px; }
QLineEdit { background-color:#FFFFFF; border:1.5px solid #C0D8C8; border-radius:6px; padding:7px 12px; color:#0A1A0F; font-size:13px; }
QLineEdit:focus { border-color:#1B8040; }
QComboBox { background-color:#FFFFFF; border:1.5px solid #C0D8C8; border-radius:6px; padding:6px 12px; color:#0A1A0F; font-size:12px; min-height:30px; min-width:180px; }
QComboBox:hover { border-color:#1B8040; }
QComboBox::drop-down { border:none; width:22px; }
QComboBox QAbstractItemView { background:#FFFFFF; border:1px solid #C0D8C8; border-radius:6px; selection-background-color:#C8EDD8; selection-color:#071610; padding:4px; }
QSpinBox { background-color:#FFFFFF; border:1.5px solid #C0D8C8; border-radius:6px; padding:4px 8px; color:#0A1A0F; font-size:12px; }
QScrollBar:vertical { background:transparent; width:6px; }
QScrollBar::handle:vertical { background:#B8D8C4; border-radius:3px; min-height:28px; }
QScrollBar::handle:vertical:hover { background:#27AE60; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { height:0; }
QCheckBox { color:#3A7055; font-size:12px; spacing:6px; }
QCheckBox::indicator { width:15px; height:15px; border:1.5px solid #B8D8C4; border-radius:4px; background:#FFFFFF; }
QCheckBox::indicator:checked { background-color:#1B8040; border-color:#1B8040; }
QToolTip { background-color:#071610; color:#B0E8C8; border:1px solid #1E4030; border-radius:5px; padding:5px 10px; font-size:11px; }
QSplitter::handle { background-color:#C0D8C8; }
QSplitter::handle:horizontal { width:1px; }
QSplitter::handle:vertical   { height:1px; }
#AuthPage    { background-color:#F0F4F1; }
#AuthBrand   { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0A1A0F,stop:1 #0D2419); }
#AuthLogo    { color:#FFFFFF; font-size:34px; font-weight:900; letter-spacing:-1px; }
#AuthLogoTag { color:#2ECC71; font-size:9px; letter-spacing:5px; font-weight:800; }
#AuthTagline { color:#6AAE86; font-size:14px; }
#AuthFeature { color:#2ECC71; font-size:12px; font-weight:600; }
#AuthFooter  { color:#1A4030; font-size:10px; }
#AuthFormWrap  { background-color:#FFFFFF; }
#AuthFormTitle { font-size:24px; font-weight:800; color:#071610; }
#AuthSub       { font-size:13px; color:#5A8A6A; }
#AuthFieldLabel{ font-size:11px; font-weight:700; color:#1A3528; }
#AuthInput  { background-color:#F5F9F5; border:1.5px solid #C0D8C8; border-radius:8px; padding:12px 16px; font-size:14px; color:#071610; min-height:46px; }
#AuthInput:focus { border-color:#1B8040; background-color:#FFFFFF; }
#AuthBtn    { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #22874A,stop:1 #1B6B3A); color:#FFFFFF; border:none; border-radius:8px; padding:13px 0; font-size:14px; font-weight:800; min-height:50px; }
#AuthBtn:hover   { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2ECC71,stop:1 #22874A); }
#AuthBtn:pressed { background-color:#145C30; }
#AuthToggle { background:transparent; border:none; color:#1B8040; font-size:12px; font-weight:600; text-decoration:underline; min-height:0; padding:0; }
#AuthToggle:hover { color:#071610; }
#AuthError   { color:#C03030; font-size:12px; font-weight:600; }
#AuthSuccess { color:#1B8040; font-size:12px; font-weight:600; }
#PayHdr  { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #071610,stop:1 #0D2419); min-height:80px; }
#PayLogo { color:#FFFFFF; font-size:22px; font-weight:900; }
#PayLogoSub { color:#52A875; font-size:13px; }
#PayBody    { background-color:#FFFFFF; }
#PayFooter  { background-color:#F5F9F5; border-top:1px solid #D0E8D8; }
#PayDesc    { color:#1A3528; font-size:13px; }
#PayConfirmBtn { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #22874A,stop:1 #1B6B3A); color:#FFFFFF; border:none; border-radius:8px; padding:8px 0; font-size:14px; font-weight:800; min-height:36px; }
#PayConfirmBtn:hover    { background-color:#2ECC71; color:#071610; }
#PayFooterNote{ color:#5A8A6A; font-size:11px; }
"""

_DARK_QSS = """
* { outline: none; }
QWidget { background-color: #12171A; color: #D0D8DC; font-family: "Outfit","DM Sans","Segoe UI",sans-serif; font-size: 13px; }
QMainWindow { background-color: #0A0E10; }
QDialog     { background-color: #1C2228; }
QLabel      { background: transparent; }
#Sidebar { background-color: #0A0E10; min-width: 220px; max-width: 220px; border-right: 3px solid #27AE60; }
#logo_wrap { background: #0D1418; padding: 26px 20px 22px 20px; border-bottom: 3px solid #27AE60; }
#logo_name { color: #FFFFFF; font-size: 22px; font-weight: 800; }
#logo_tag  { color: #27AE60; font-size: 8px; letter-spacing: 5px; font-weight: 700; margin-top: 3px; }
#SidebarUser { color: #A0B8B0; font-size: 12px; font-weight: 700; padding: 12px 20px 10px 20px; border-bottom: 1px solid #253030; background-color: #0D1418; }
#nav_section_label { color: #27AE60; font-size: 8px; letter-spacing: 3px; font-weight: 800; padding: 14px 20px 6px 20px; }
#NavBtn { background-color: transparent; color: #608878; border: none; padding: 12px 20px; text-align: left; font-size: 13px; font-weight: 600; border-left: 4px solid transparent; border-bottom: 1px solid #1C2828; }
#NavBtn:hover { background-color: #1A2828; color: #FFFFFF; border-left: 4px solid #27AE60; }
#NavBtn[active="true"] { background-color: #1A2828; color: #FFFFFF; font-weight: 800; border-left: 4px solid #27AE60; }
#SidebarLogout { background-color: transparent; color: #C07080; border: 1px solid #4A2030; border-radius: 6px; margin: 8px 14px; padding: 7px 16px; font-size: 11px; font-weight: 600; }
#sidebar_footer { color: #2A5040; font-size: 9px; padding: 12px 20px; }
#HeaderTitleRow { background-color: #1C2228; border-bottom: 1px solid #253030; min-height:52px; max-height:52px; }
#page_title { font-size: 16px; font-weight: 800; color: #D0D8DC; }
#session_pill { background-color: #1A2828; color: #7FC89A; border: 1.5px solid #2A5040; border-radius: 20px; padding: 4px 14px; font-size: 11px; }
#RibbonTabBar { background-color: #1C2228; border-bottom: 2px solid #27AE60; min-height:28px; max-height:28px; }
#RibbonTab { background-color: transparent; color: #608878; border: none; border-bottom: 3px solid transparent; border-radius: 0; padding: 4px 18px; font-size: 11px; font-weight: 600; min-height:28px; margin-bottom:-2px; }
#RibbonTab:hover { color: #D0D8DC; background-color: #253030; }
#RibbonTab[active="true"] { color: #D0D8DC; font-weight: 800; border-bottom: 3px solid #27AE60; }
#RibbonPanel { background-color: #1C2228; border-bottom: 2px solid #253030; padding: 4px 8px; min-height:90px; max-height:90px; }
#RibbonGroup { border-right: 2px solid #253030; padding-right: 10px; margin-right: 4px; }
#RibbonGroupLast { padding-right: 6px; }
#RibbonGroupLabel { color: #27AE60; font-size: 8px; font-weight: 800; letter-spacing: 2px; margin-top: 2px; background-color: transparent; }
#RibbonBtn { background-color: transparent; color: #90B8A8; border: 1px solid transparent; border-radius: 5px; padding: 4px 8px; font-size: 11px; font-weight: 600; min-height:30px; min-width:46px; }
#RibbonBtn:hover { background-color: #253030; border-color: #2A5040; }
#RibbonBtnPrimary { background-color: #1B6B3A; color: #FFFFFF; border: none; border-radius: 6px; padding: 6px 10px; font-size: 12px; font-weight: 700; min-height:34px; }
#RibbonBtnPrimary:hover { background-color: #22874A; }
#SessionRow { background-color: #1C2228; border-bottom: 1px solid #253030; padding: 6px 24px; min-height:44px; max-height:44px; }
#GroupLabel { color: #608878; font-size: 8px; font-weight: 800; letter-spacing: 2px; margin-right: 6px; }
#RichBtnBold,#RichBtnItalic,#RichBtnUnder { background-color:#253030; color:#90B8A8; border:1px solid #2A5040; border-radius:5px; padding:5px; min-height:30px; }
#RichBtnBold { font-weight:900; font-size:14px; min-width:34px; }
#RichBtnItalic { font-style:italic; font-size:14px; min-width:34px; }
#RichBtnUnder { text-decoration:underline; font-size:14px; min-width:34px; }
#RichBtnBold:checked,#RichBtnItalic:checked,#RichBtnUnder:checked { background-color:#27AE60; color:#FFFFFF; }
#FontCombo { min-width:155px; max-width:180px; font-size:12px; }
#FontSizeSpin { min-width:50px; max-width:50px; font-size:12px; font-weight:700; }
#FindBar { background-color: #1C2228; border-bottom: 1px solid #253030; padding: 7px 24px; min-height:44px; max-height:44px; }
#FindInput,#ReplaceInput { background-color:#253030; border:1px solid #2A5040; border-radius:5px; padding:5px 10px; color:#D0D8DC; font-size:12px; min-width:160px; max-width:180px; }
#ReplaceBtn { background-color:#1B6B3A; color:#FFFFFF; border:none; border-radius:5px; padding:5px 16px; font-size:12px; font-weight:700; min-height:30px; }
#CaseCheck { color:#608878; font-size:11px; }
#Editor { background-color:#1A1E22; color:#C8D8D0; border:none; padding:28px 40px; font-family:"JetBrains Mono","Cascadia Code","Fira Code","Consolas",monospace; font-size:13px; selection-background-color:#27AE60; selection-color:#FFFFFF; }
#StatusBar { background-color:#0A0E10; border-top:1px solid #1C2828; min-height:28px; max-height:28px; padding:0 24px; }
#StatLabel  { color:#608878; font-size:11px; font-weight:600; }
#FlashLabel { color:#27AE60; font-size:11px; font-weight:700; }
#PageArea   { background-color:#12171A; }
#CardTitle  { font-size:12px; font-weight:800; color:#D0D8DC; }
#SessionList,#BackupList,#LogList { background-color:#1C2228; border:1.5px solid #253030; border-radius:8px; padding:4px; }
#SessionList::item,#BackupList::item,#LogList::item { padding:10px 14px; border-radius:6px; color:#90B8A8; font-size:12px; border-bottom:1px solid #1C2828; }
#SessionList::item:selected,#BackupList::item:selected,#LogList::item:selected { background-color:#253030; color:#FFFFFF; font-weight:700; }
QPushButton { background-color:#1B6B3A; color:#FFFFFF; border:none; border-radius:6px; padding:7px 18px; font-size:12px; font-weight:700; min-height:32px; }
QPushButton:hover   { background-color:#22874A; }
QPushButton#ghost   { background-color:transparent; color:#27AE60; border:1.5px solid #2A5040; font-weight:600; }
QPushButton#ghost:hover { background-color:#253030; }
QPushButton#danger  { background-color:transparent; color:#C05050; border:1.5px solid #5A2030; font-weight:600; }
QPushButton#danger:hover { background-color:#C05050; color:#FFFFFF; }
QLineEdit { background-color:#253030; border:1.5px solid #2A5040; border-radius:6px; padding:7px 12px; color:#D0D8DC; font-size:13px; }
QLineEdit:focus { border-color:#27AE60; }
QComboBox { background-color:#253030; border:1.5px solid #2A5040; border-radius:6px; padding:6px 12px; color:#D0D8DC; font-size:12px; min-height:30px; }
QComboBox::drop-down { border:none; width:22px; }
QComboBox QAbstractItemView { background:#253030; border:1px solid #2A5040; selection-background-color:#1B6B3A; selection-color:#FFFFFF; padding:4px; }
QSpinBox { background-color:#253030; border:1.5px solid #2A5040; border-radius:6px; padding:4px 8px; color:#D0D8DC; font-size:12px; }
QScrollBar:vertical { background:transparent; width:6px; }
QScrollBar::handle:vertical { background:#2A5040; border-radius:3px; min-height:28px; }
QScrollBar::handle:vertical:hover { background:#27AE60; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { height:0; }
QCheckBox { color:#608878; font-size:12px; }
QCheckBox::indicator { width:15px; height:15px; border:1.5px solid #2A5040; border-radius:4px; background:#253030; }
QCheckBox::indicator:checked { background-color:#27AE60; border-color:#27AE60; }
QToolTip { background-color:#0A0E10; color:#90B8A8; border:1px solid #2A5040; border-radius:5px; padding:5px 10px; font-size:11px; }
QSplitter::handle { background-color:#253030; }
#AuthPage    { background-color:#12171A; }
#AuthBrand   { background:#0A0E10; }
#AuthLogo    { color:#FFFFFF; font-size:34px; font-weight:900; }
#AuthLogoTag { color:#27AE60; font-size:9px; letter-spacing:5px; font-weight:800; }
#AuthTagline { color:#608878; font-size:14px; }
#AuthFeature { color:#27AE60; font-size:12px; font-weight:600; }
#AuthFooter  { color:#2A5040; font-size:10px; }
#AuthFormWrap  { background-color:#1C2228; }
#AuthFormTitle { font-size:24px; font-weight:800; color:#D0D8DC; }
#AuthSub       { font-size:13px; color:#608878; }
#AuthFieldLabel{ font-size:11px; font-weight:700; color:#90B8A8; }
#AuthInput  { background-color:#253030; border:1.5px solid #2A5040; border-radius:8px; padding:12px 16px; font-size:14px; color:#D0D8DC; min-height:46px; }
#AuthInput:focus { border-color:#27AE60; }
#AuthBtn    { background-color:#1B6B3A; color:#FFFFFF; border:none; border-radius:8px; padding:13px 0; font-size:14px; font-weight:800; min-height:50px; }
#AuthBtn:hover   { background-color:#22874A; }
#AuthToggle { background:transparent; border:none; color:#27AE60; font-size:12px; font-weight:600; min-height:0; padding:0; }
#AuthError   { color:#E07070; font-size:12px; font-weight:600; }
#AuthSuccess { color:#27AE60; font-size:12px; font-weight:600; }
#PayHdr  { background:#0A0E10; min-height:80px; }
#PayLogo { color:#FFFFFF; font-size:22px; font-weight:900; }
#PayLogoSub { color:#27AE60; font-size:13px; }
#PayBody    { background-color:#1C2228; }
#PayFooter  { background-color:#12171A; border-top:1px solid #253030; }
#PayDesc    { color:#90B8A8; font-size:13px; }
#PayConfirmBtn { background-color:#1B6B3A; color:#FFFFFF; border:none; border-radius:8px; padding:8px 0; font-size:14px; font-weight:800; min-height:36px; }
#PayConfirmBtn:hover    { background-color:#22874A; }
#PayFooterNote{ color:#608878; font-size:11px; }
"""


def _get_qss(dark: bool = False) -> str:
    qss_path = os.path.join(os.path.dirname(__file__), "styles", "theme_dark.qss" if dark else "theme.qss")
    if os.path.exists(qss_path):
        try:
            with open(qss_path, encoding="utf-8") as f: return f.read()
        except Exception:
            pass
    return _DARK_QSS if dark else _LIGHT_QSS


def _load_qss(app, dark=False): app.setStyleSheet(_get_qss(dark))


def run():
    db.init()
    app = QApplication(sys.argv)
    app.setApplicationName("DocuFlow")
    _load_qss(app)
    win = MainWindow(); win.show()
    sys.exit(app.exec())
