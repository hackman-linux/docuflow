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

import sys, os, datetime, smtplib, threading, webbrowser, secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Owner Gmail credentials (REPLACE with your real values) ──────────────────
# Use an App Password, not your normal Gmail password.
# Gmail → Manage Account → Security → 2-Step Verification → App Passwords
OWNER_EMAIL    = "your.email@gmail.com"          # ← your Gmail
OWNER_APP_PASS = "xxxx xxxx xxxx xxxx"           # ← 16-char App Password
NOTIFY_EMAIL   = "your.email@gmail.com"          # ← where to receive alerts

# Licence pricing
PRICE_USD   = 18          # $18 = 3-month licence  (≈ 11 000 FCFA)
LICENCE_MONTHS = 3        # key is valid for 3 months after activation

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
#  EMAIL HELPER  — sends a notification to your Gmail inbox
# ═══════════════════════════════════════════════════════════════════════════════

def _send_owner_email(subject: str, body: str):
    """Fire-and-forget email to the owner. Runs in a background thread."""
    def _send():
        try:
            msg = MIMEMultipart()
            msg["From"]    = OWNER_EMAIL
            msg["To"]      = NOTIFY_EMAIL
            msg["Subject"] = f"[DocuFlow] {subject}"
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
                s.login(OWNER_EMAIL, OWNER_APP_PASS)
                s.send_message(msg)
        except Exception:
            pass   # never crash the app over an email failure
    threading.Thread(target=_send, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
#  PAYMENT PAGE  — opened when user clicks "Don't have a key? Get one"
# ═══════════════════════════════════════════════════════════════════════════════

class PaymentPage(QDialog):
    """
    Guides the user through purchasing a 3-month licence.
    Shows payment options; when the user confirms payment was sent, emails
    the owner and shows a pending confirmation message.
    """

    # ── USD amount → FCFA (rough mid-rate; update periodically) ──────────────
    _USD_TO_XAF = 600    # 1 USD ≈ 600 FCFA

    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self._user = user
        self.setWindowTitle("DocuFlow Enterprise — Get a Licence")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── Dark header banner ────────────────────────────────────────────────
        hdr = QWidget(); hdr.setObjectName("PayHdr")
        hdr.setFixedHeight(80)
        hl  = QHBoxLayout(hdr); hl.setContentsMargins(32, 0, 32, 0)
        logo = make_label("DocuFlow", "PayLogo")
        sub  = make_label("Enterprise Licence", "PayLogoSub")
        hl.addWidget(logo); hl.addSpacing(10); hl.addWidget(sub); hl.addStretch()
        price_lbl = make_label(f"${PRICE_USD} / 3 months", "PayPrice")
        hl.addWidget(price_lbl)
        root.addWidget(hdr)

        # ── Body ─────────────────────────────────────────────────────────────
        body = QWidget(); body.setObjectName("PayBody")
        bl   = QVBoxLayout(body); bl.setContentsMargins(32, 24, 32, 24); bl.setSpacing(18)

        xaf = PRICE_USD * self._USD_TO_XAF
        desc = make_label(
            f"A DocuFlow Enterprise licence gives you 3 months of full access.\n"
            f"Price: ${PRICE_USD} USD  ≈  {xaf:,} FCFA  (converted at payment time).",
            "PayDesc"
        )
        desc.setWordWrap(True); bl.addWidget(desc)

        # ── Payment method buttons ────────────────────────────────────────────
        bl.addWidget(make_label("Choose how to pay:", "PaySectionLabel"))

        methods = QHBoxLayout(); methods.setSpacing(10)

        self._pay_btns = {}
        payment_options = [
            ("paypal",  "💳  PayPal",       "#003087", "#FFFFFF"),
            ("bank",    "🏦  Bank Transfer", "#1B6B3A", "#FFFFFF"),
            ("mtn",     "📱  MTN MoMo",     "#FFC000", "#000000"),
            ("orange",  "📱  Orange Money", "#FF6600", "#FFFFFF"),
        ]
        for key, label, bg, fg in payment_options:
            btn = QPushButton(label)
            btn.setObjectName("PayMethodBtn")
            btn.setStyleSheet(
                f"QPushButton#PayMethodBtn {{ background:{bg}; color:{fg}; "
                f"border:none; border-radius:8px; padding:12px 18px; "
                f"font-size:13px; font-weight:600; min-height:44px; }}"
                f"QPushButton#PayMethodBtn:hover {{ opacity: 0.85; }}"
            )
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self._select_method(k))
            self._pay_btns[key] = btn
            methods.addWidget(btn)

        bl.addLayout(methods)

        # ── Dynamic instructions ──────────────────────────────────────────────
        self._instructions = QLabel("")
        self._instructions.setObjectName("PayInstructions")
        self._instructions.setWordWrap(True)
        self._instructions.setMinimumHeight(100)
        bl.addWidget(self._instructions)

        # ── Reference / name entry ────────────────────────────────────────────
        bl.addWidget(make_label("Your name or username (for reference):", "PaySectionLabel"))
        self._ref_in = QLineEdit()
        self._ref_in.setPlaceholderText(user["username"])
        self._ref_in.setText(user["username"])
        bl.addWidget(self._ref_in)

        # ── "I have paid" confirmation button ─────────────────────────────────
        self._confirm_btn = QPushButton("✔  I have completed the payment — notify the owner")
        self._confirm_btn.setObjectName("PayConfirmBtn")
        self._confirm_btn.clicked.connect(self._on_confirm)
        self._confirm_btn.setEnabled(False)
        bl.addWidget(self._confirm_btn)

        self._status_lbl = make_label("", "PayStatus")
        self._status_lbl.setWordWrap(True)
        bl.addWidget(self._status_lbl)

        bl.addStretch()
        root.addWidget(body, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        ftr = QWidget(); ftr.setObjectName("PayFooter")
        fl  = QHBoxLayout(ftr); fl.setContentsMargins(32, 12, 32, 12)
        fl.addWidget(make_label(
            "After payment confirmation you will receive your licence key by email within 24 h.",
            "PayFooterNote"
        ))
        fl.addStretch()
        close = ghost_btn("Close"); close.clicked.connect(self.accept)
        fl.addWidget(close)
        root.addWidget(ftr)

        self._selected_method = None

    _INSTRUCTIONS = {
        "paypal": (
            "Send ${price} USD to:  <b>paypal.me/YourPayPalLink</b>\n\n"
            "• Log in to PayPal → Send Money → Friends & Family\n"
            "• Amount: ${price} USD\n"
            "• Note: DocuFlow licence — {user}\n\n"
            "Then click the button below."
        ),
        "bank": (
            "Bank Transfer details:\n\n"
            "  Bank:    Your Bank Name\n"
            "  Account: 00000-00000-00000000000-00\n"
            "  SWIFT:   XXXXXXXX\n"
            "  Amount:  ${price} USD (or {xaf} FCFA)\n"
            "  Ref:     DocuFlow-{user}\n\n"
            "Then click the button below."
        ),
        "mtn": (
            "MTN Mobile Money:\n\n"
            "  Dial *126# → Transfer → Enter number: +237 6XX XXX XXX\n"
            "  Amount: {xaf} FCFA\n"
            "  Reference: DocuFlow-{user}\n\n"
            "Then click the button below."
        ),
        "orange": (
            "Orange Money:\n\n"
            "  Dial #150*1# → Transfer → Enter number: +237 6XX XXX XXX\n"
            "  Amount: {xaf} FCFA\n"
            "  Reference: DocuFlow-{user}\n\n"
            "Then click the button below."
        ),
    }

    def _select_method(self, key: str):
        self._selected_method = key
        for k, b in self._pay_btns.items():
            if k != key:
                b.setChecked(False)
        xaf  = PRICE_USD * self._USD_TO_XAF
        tmpl = self._INSTRUCTIONS[key]
        self._instructions.setText(
            tmpl.format(price=PRICE_USD, xaf=f"{xaf:,}", user=self._user["username"])
        )
        self._confirm_btn.setEnabled(True)

    def _on_confirm(self):
        if not self._selected_method:
            return
        ref  = self._ref_in.text().strip() or self._user["username"]
        xaf  = PRICE_USD * self._USD_TO_XAF
        body = (
            f"DocuFlow licence payment notification\n"
            f"{'─'*48}\n"
            f"Username  : {self._user['username']}  (ID {self._user['id']})\n"
            f"Reference : {ref}\n"
            f"Method    : {self._selected_method.upper()}\n"
            f"Amount    : ${PRICE_USD} USD  ≈  {xaf:,} FCFA\n"
            f"Duration  : {LICENCE_MONTHS} months\n"
            f"Timestamp : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'─'*48}\n"
            f"Action required: verify payment and run db.create_licence({self._user['id']}, key, months={LICENCE_MONTHS})\n"
        )
        _send_owner_email(
            f"Payment notification — {self._user['username']} ({self._selected_method.upper()})",
            body
        )
        self._confirm_btn.setEnabled(False)
        self._status_lbl.setObjectName("LicenceActive")
        self._status_lbl.setText(
            "✔  Thank you! The owner has been notified.\n"
            "You will receive your licence key by email within 24 hours.\n"
            "Enter it in the Activate Licence screen to unlock the app."
        )
        self._status_lbl.style().unpolish(self._status_lbl)
        self._status_lbl.style().polish(self._status_lbl)


# ═══════════════════════════════════════════════════════════════════════════════
#  LICENCE DIALOG  — Microsoft-style activation (key first, buy link below)
# ═══════════════════════════════════════════════════════════════════════════════

class LicenceDialog(QDialog):
    """
    Looks and behaves like Microsoft's product activation dialog:
      • Key entry field front-and-centre
      • "Don't have a key?" link beneath it → opens PaymentPage
      • Current licence status shown at top
    """
    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DocuFlow Enterprise — Activate")
        self.setMinimumWidth(520)
        self._user      = user
        self._activated = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── Dark top banner ───────────────────────────────────────────────────
        hdr = QWidget(); hdr.setObjectName("PayHdr")
        hdr.setFixedHeight(72)
        hl  = QHBoxLayout(hdr); hl.setContentsMargins(28, 0, 28, 0)
        logo = make_label("DocuFlow", "PayLogo")
        sub  = make_label("Product Activation", "PayLogoSub")
        hl.addWidget(logo); hl.addSpacing(10); hl.addWidget(sub); hl.addStretch()
        root.addWidget(hdr)

        # ── Body ─────────────────────────────────────────────────────────────
        body = QWidget(); body.setObjectName("PayBody")
        bl   = QVBoxLayout(body); bl.setContentsMargins(32, 28, 32, 20); bl.setSpacing(16)

        # Current status
        days = db.licence_days_remaining(user["id"])
        lic  = db.get_active_licence(user["id"])
        if lic:
            until = datetime.datetime.strptime(lic["valid_until"], "%Y-%m-%d %H:%M:%S")
            st_text = f"✔  Licence active — expires {until.strftime('%d %b %Y')}  ({days} days remaining)"
            st_obj  = "LicenceActive"
        else:
            st_text = "✖  No active licence — the application is in read-only mode."
            st_obj  = "LicenceExpired"
        status_lbl = make_label(st_text, st_obj)
        status_lbl.setWordWrap(True); bl.addWidget(status_lbl)

        # Separator
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #DDE8E2;"); bl.addWidget(sep)

        # Instruction
        bl.addWidget(make_label(
            "Enter your 25-character product key below.\n"
            "The key looks like:  XXXX-XXXX-XXXX-XXXX",
            "PayDesc"
        ))

        # Key entry — large, Microsoft-style
        self._key_in = QLineEdit()
        self._key_in.setObjectName("LicKeyInput")
        self._key_in.setPlaceholderText("XXXX - XXXX - XXXX - XXXX")
        self._key_in.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._key_in.returnPressed.connect(self._activate)
        bl.addWidget(self._key_in)

        # Activate button
        act_btn = QPushButton("Activate  →")
        act_btn.setObjectName("PayConfirmBtn")
        act_btn.clicked.connect(self._activate)
        bl.addWidget(act_btn)

        # Message label
        self._msg = make_label("", "AuthError")
        self._msg.setWordWrap(True); self._msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self._msg)

        # "Get a key" link
        get_key_btn = QPushButton("Don't have a product key?  →  Purchase a licence")
        get_key_btn.setObjectName("AuthToggle")
        get_key_btn.setFlat(True)
        get_key_btn.clicked.connect(self._open_payment)
        bl.addWidget(get_key_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        bl.addStretch()
        root.addWidget(body, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        ftr = QWidget(); ftr.setObjectName("PayFooter")
        fl  = QHBoxLayout(ftr); fl.setContentsMargins(28, 10, 28, 10)
        fl.addWidget(make_label(
            f"3-month licence: ${PRICE_USD} USD  ·  Supports MTN, Orange Money, PayPal, Bank transfer",
            "PayFooterNote"
        ))
        fl.addStretch()
        close = ghost_btn("Close"); close.clicked.connect(self.accept)
        fl.addWidget(close)
        root.addWidget(ftr)

    def _activate(self):
        key = self._key_in.text().strip().upper()
        # Normalise: strip spaces and re-add dashes
        clean = key.replace("-", "").replace(" ", "")
        if len(clean) == 16:
            key = "-".join(clean[i:i+4] for i in range(0, 16, 4))
        if not key:
            self._msg.setText("Please enter a product key."); return
        result = db.activate_licence(self._user["id"], key)
        if result["ok"]:
            self._msg.setObjectName("LicenceActive")
            self._msg.setText(f"✔  Activated!  Licence valid until {result['until']}.")
            self._activated = True
        else:
            self._msg.setObjectName("AuthError")
            self._msg.setText(f"✖  {result['reason']}")
        self._msg.style().unpolish(self._msg); self._msg.style().polish(self._msg)

    def _open_payment(self):
        dlg = PaymentPage(self._user, self)
        dlg.exec()

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


def _get_qss() -> str:
    """
    Return the complete stylesheet.
    ALL CSS is embedded here as a Python string so that PyInstaller --onefile
    builds retain the full theme even when the styles/ folder is not present.
    The disk file (if found) is merged on top so dev-mode edits still work.
    """
    # ── Base theme (copy of ui/styles/theme.qss) ──────────────────────────────
    BASE_QSS = """
* { outline: none; }

QWidget {
    background-color: #F8FAF8;
    color: #0D1F14;
    font-family: "DM Sans", "Segoe UI Semibold", "SF Pro Display", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #F8FAF8; }

#Sidebar { background-color: #0E2318; min-width: 230px; max-width: 230px; }
#logo_wrap { background-color: #0A1C12; padding: 28px 22px 20px 22px; border-bottom: 1px solid #1A3D26; }
#logo_name { color: #FFFFFF; font-size: 20px; font-weight: 700; letter-spacing: 0.5px; }
#logo_tag  { color: #3D8A57; font-size: 9px; letter-spacing: 3px; font-weight: 600; margin-top: 2px; }
#nav_section_label { color: #2D6B43; font-size: 9px; letter-spacing: 2.5px; font-weight: 700; padding: 18px 22px 6px 22px; }

#NavBtn {
    background-color: transparent; color: #7AB891; border: none; border-radius: 0px;
    padding: 11px 22px; text-align: left; font-size: 13px; font-weight: 500;
    border-left: 3px solid transparent;
}
#NavBtn:hover { background-color: #132E1C; color: #C8E8D4; border-left: 3px solid #2D6B43; }
#NavBtn[active="true"] { background-color: #173D24; color: #FFFFFF; font-weight: 600; border-left: 3px solid #2ECC71; }
#sidebar_footer { color: #2D5C3C; font-size: 10px; padding: 16px 22px; border-top: 1px solid #1A3D26; }

#Header { background-color: #FFFFFF; border-bottom: 1px solid #E4EDE7; }
#page_title { font-size: 17px; font-weight: 700; color: #0D1F14; letter-spacing: -0.3px; }
#session_pill { background-color: #EAF5EE; color: #1B6B3A; border: 1px solid #C2DFC9; border-radius: 20px; padding: 4px 14px; font-size: 11px; font-weight: 600; }

#ActionBar { background-color: #FFFFFF; border-bottom: 1px solid #EEF3EF; padding: 8px 24px; min-height: 50px; }
#FormatBar { background-color: #F3F8F4; border-bottom: 1px solid #DFF0E4; padding: 8px 24px; min-height: 48px; max-height: 48px; }
#GroupLabel { color: #5A9A72; font-size: 9px; font-weight: 700; letter-spacing: 1.8px; margin-right: 4px; }

#FmtBtn { background-color: #FFFFFF; color: #1A4D2E; border: 1px solid #C8DDD0; border-radius: 6px; padding: 4px 11px; font-size: 12px; font-weight: 500; min-height: 28px; min-width: 52px; }
#FmtBtn:hover { background-color: #1B6B3A; color: #FFFFFF; border-color: #1B6B3A; }
#FmtBtn:pressed { background-color: #145A30; }

#VSep { background-color: #D8EAE0; max-width: 1px; min-width: 1px; min-height: 22px; max-height: 22px; margin: 0 8px; }

#FindBar { background-color: #FAFCFA; border-bottom: 1px solid #E4EEE7; padding: 7px 24px; min-height: 44px; max-height: 44px; }
#FindInput, #ReplaceInput { background-color: #FFFFFF; border: 1px solid #C8DDD0; border-radius: 6px; padding: 5px 10px; color: #0D1F14; font-size: 12px; min-width: 160px; max-width: 160px; }
#FindInput:focus, #ReplaceInput:focus { border: 1.5px solid #27AE60; }
#ReplaceBtn { background-color: #27AE60; color: #FFFFFF; border: none; border-radius: 6px; padding: 5px 16px; font-size: 12px; font-weight: 600; min-height: 28px; }
#ReplaceBtn:hover { background-color: #2ECC71; }
#ReplaceBtn:pressed { background-color: #1E9E54; }
#CaseCheck { color: #4A8060; font-size: 11px; spacing: 4px; }

#Editor { background-color: #FFFFFF; color: #0D1F14; border: none; padding: 24px 32px;
          font-family: "JetBrains Mono","Cascadia Code","Fira Code","Consolas",monospace;
          font-size: 13px; line-height: 1.7;
          selection-background-color: #B8E4C8; selection-color: #0D1F14; }

#StatusBar { background-color: #FFFFFF; border-top: 1px solid #E4EEE7; min-height: 30px; max-height: 30px; padding: 0 24px; }
#StatLabel { color: #6A9A7A; font-size: 11px; font-weight: 500; }
#FlashLabel { color: #1B6B3A; font-size: 11px; font-weight: 600; }

#PageArea { background-color: #F8FAF8; }
#CardTitle { font-size: 13px; font-weight: 700; color: #0D1F14; letter-spacing: -0.2px; }

#SessionList, #BackupList, #LogList { background-color: #FFFFFF; border: 1px solid #DFF0E4; border-radius: 10px; padding: 4px; outline: none; }
#SessionList::item, #BackupList::item, #LogList::item { padding: 10px 14px; border-radius: 7px; color: #1A3525; font-size: 12px; border: none; }
#SessionList::item:selected, #BackupList::item:selected, #LogList::item:selected { background-color: #D4EDDC; color: #0E2318; font-weight: 600; }
#SessionList::item:hover, #BackupList::item:hover, #LogList::item:hover { background-color: #EEF8F1; }

QPushButton { background-color: #1B6B3A; color: #FFFFFF; border: none; border-radius: 7px; padding: 7px 18px; font-size: 12px; font-weight: 600; min-height: 32px; }
QPushButton:hover { background-color: #22874A; }
QPushButton:pressed { background-color: #155C30; }
QPushButton#ghost { background-color: transparent; color: #1B6B3A; border: 1.5px solid #C2DFC9; }
QPushButton#ghost:hover { background-color: #EAF5EE; border-color: #27AE60; }
QPushButton#danger { background-color: transparent; color: #C0392B; border: 1.5px solid #F5C6C6; }
QPushButton#danger:hover { background-color: #C0392B; color: #FFFFFF; border-color: #C0392B; }

QLineEdit { background-color: #FFFFFF; border: 1.5px solid #C8DDD0; border-radius: 7px; padding: 7px 12px; color: #0D1F14; font-size: 13px; }
QLineEdit:focus { border-color: #27AE60; }
QComboBox { background-color: #FFFFFF; border: 1.5px solid #C8DDD0; border-radius: 7px; padding: 6px 12px; color: #0D1F14; font-size: 12px; min-height: 30px; min-width: 180px; }
QComboBox:hover { border-color: #27AE60; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #FFFFFF; border: 1px solid #C8DDD0; border-radius: 6px; selection-background-color: #D4EDDC; selection-color: #0D1F14; padding: 4px; }

QScrollBar:vertical { background: transparent; width: 7px; }
QScrollBar::handle:vertical { background: #C2DFC9; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #27AE60; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 0; }

QDialog { background-color: #F8FAF8; }
QLabel  { background: transparent; }
QCheckBox { color: #3A6B4E; font-size: 12px; spacing: 6px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1.5px solid #C2DFC9; border-radius: 4px; background: #FFFFFF; }
QCheckBox::indicator:checked { background-color: #27AE60; border-color: #27AE60; }
QToolTip { background-color: #0E2318; color: #C8E8D4; border: none; border-radius: 5px; padding: 5px 10px; font-size: 11px; }
QSplitter::handle { background-color: #E4EEE7; }
QSplitter::handle:horizontal { width: 1px; }
"""

    # ── Extra styles for v2 components ───────────────────────────────────────
    EXTRA_QSS = """
/* Auth page */
#AuthPage { background-color: #F8FAF8; }
#AuthBrand { background-color: #0E2318; }
#AuthLogo { color: #FFFFFF; font-size: 32px; font-weight: 800; letter-spacing: -0.5px; }
#AuthLogoTag { color: #3D8A57; font-size: 10px; letter-spacing: 4px; font-weight: 700; }
#AuthTagline { color: #7AB891; font-size: 14px; }
#AuthFooter { color: #2D5C3C; font-size: 11px; }
#AuthFormWrap { background-color: #FFFFFF; }
#AuthFormTitle { font-size: 22px; font-weight: 700; color: #0D1F14; }
#AuthSub { font-size: 13px; color: #6A9A7A; }
#AuthFieldLabel { font-size: 12px; font-weight: 600; color: #1A3525; }
#AuthInput { background-color: #F8FAF8; border: 1.5px solid #C8DDD0; border-radius: 8px; padding: 10px 14px; font-size: 14px; color: #0D1F14; min-height: 44px; }
#AuthInput:focus { border-color: #27AE60; background-color: #FFFFFF; }
#AuthBtn { background-color: #1B6B3A; color: #FFFFFF; border: none; border-radius: 8px; padding: 12px 0; font-size: 14px; font-weight: 700; min-height: 48px; }
#AuthBtn:hover { background-color: #22874A; }
#AuthBtn:pressed { background-color: #155C30; }
#AuthToggle { background: transparent; border: none; color: #27AE60; font-size: 12px; text-decoration: underline; min-height: 0; padding: 0; }
#AuthToggle:hover { color: #1B6B3A; }
#AuthError { color: #C0392B; font-size: 12px; }

/* Sidebar extras */
#SidebarUser { color: #7AB891; font-size: 11px; font-weight: 600; padding: 10px 22px 6px 22px; border-bottom: 1px solid #1A3D26; }
#SidebarLogout { margin: 0 14px 8px 14px; color: #9A6B7B; border-color: #4A2D35; }

/* Header banner */
#HeaderTitleRow { background-color: #FFFFFF; border-bottom: 1px solid #E4EDE7; }
#LicenceBannerOk      { background-color: #1B6B3A; }
#LicenceBannerWarn    { background-color: #B7770D; }
#LicenceBannerExpired { background-color: #8B1A1A; }
#BannerLabel { color: #FFFFFF; font-size: 11px; font-weight: 600; letter-spacing: 0.3px; }

/* Licence / payment dialogs */
#LicenceActive  { color: #1B6B3A; font-weight: 600; font-size: 13px; }
#LicenceExpired { color: #C0392B; font-weight: 600; font-size: 13px; }

#PayHdr { background-color: #0E2318; }
#PayLogo { color: #FFFFFF; font-size: 22px; font-weight: 800; }
#PayLogoSub { color: #7AB891; font-size: 13px; font-weight: 500; }
#PayPrice { color: #2ECC71; font-size: 18px; font-weight: 700; }
#PayBody { background-color: #FFFFFF; }
#PayFooter { background-color: #F3F8F4; border-top: 1px solid #DFF0E4; }
#PayDesc { color: #1A3525; font-size: 13px; line-height: 1.5; }
#PaySectionLabel { color: #5A9A72; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; }
#PayInstructions { background-color: #F3F8F4; border: 1px solid #C8DDD0; border-radius: 8px; padding: 14px 18px; color: #1A3525; font-size: 12px; min-height: 90px; }
#PayStatus { color: #1B6B3A; font-size: 12px; font-weight: 600; }
#PayFooterNote { color: #6A9A7A; font-size: 11px; }
#PayConfirmBtn { background-color: #1B6B3A; color: #FFFFFF; border: none; border-radius: 8px; padding: 12px 0; font-size: 13px; font-weight: 700; min-height: 46px; }
#PayConfirmBtn:hover { background-color: #22874A; }
#PayConfirmBtn:disabled { background-color: #A8C4B0; color: #FFFFFF; }

/* Key input — large Microsoft-style */
#LicKeyInput {
    background-color: #FFFFFF;
    border: 2px solid #C8DDD0;
    border-radius: 10px;
    padding: 14px 20px;
    font-size: 20px;
    font-weight: 700;
    color: #0D1F14;
    letter-spacing: 4px;
    min-height: 56px;
}
#LicKeyInput:focus { border-color: #27AE60; }

/* Rich-text bar */
#RichBar { background-color: #FFFFFF; border-bottom: 1px solid #EEF3EF; padding: 4px 24px; }
#RichBtnBold   { font-weight: 800; font-size: 14px; min-width: 32px; }
#RichBtnItalic { font-style: italic; font-size: 14px; min-width: 32px; }
#RichBtnUnder  { text-decoration: underline; font-size: 14px; min-width: 32px; }
#RichBtnBold:checked, #RichBtnItalic:checked, #RichBtnUnder:checked { background-color: #1B6B3A; color: #FFFFFF; border-color: #1B6B3A; }
#FontCombo { min-width: 160px; max-width: 200px; font-size: 12px; }
#FontSizeSpin { background-color: #FFFFFF; border: 1.5px solid #C8DDD0; border-radius: 6px; padding: 4px 6px; font-size: 12px; color: #0D1F14; }
"""

    # Try to load fresh disk copy (dev mode); fall back to full embedded string
    disk_extra = ""
    qss_path = os.path.join(os.path.dirname(__file__), "styles", "theme.qss")
    if os.path.exists(qss_path):
        try:
            with open(qss_path, encoding="utf-8") as f:
                disk_extra = f.read()
        except Exception:
            pass

    # If disk file found, use it as base (dev mode); otherwise use embedded BASE_QSS
    base = disk_extra if disk_extra else BASE_QSS
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