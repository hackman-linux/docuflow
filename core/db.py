"""DocuFlow Enterprise — Database layer v3  (patched: safe schema migration)
Features:
  • Multi-user with per-user sessions/logs
  • 7-day free trial auto-assigned on registration
  • 3-month paid licences ($20 / ~12,000 FCFA)
  • Payment tracking table (pending → confirmed → key issued)
  • Expired licences auto-deleted (not just marked) to keep DB clean
  • Expiry warning at 7 days remaining
  • MIGRATION SAFE: works with old databases — adds missing columns automatically
"""
import sqlite3, datetime, os, hashlib, secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "docuflow.db")

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory   = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    return c

# ─────────────────────────────────────────────────────────────────────────────
#  INIT + MIGRATION
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_USERNAME = "admin"   # ← change to your admin username

def init():
    """Create tables if missing, then migrate any old schema to the current one."""
    db = _conn()

    # ── 1. Create all tables with the full, current schema ───────────────────
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            email         TEXT    DEFAULT '',
            created_at    TEXT    NOT NULL,
            is_admin      INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS licences (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            licence_key  TEXT    NOT NULL UNIQUE,
            valid_from   TEXT    NOT NULL,
            valid_until  TEXT    NOT NULL,
            activated_at TEXT,
            kind         TEXT    NOT NULL DEFAULT 'paid',
            status       TEXT    NOT NULL DEFAULT 'active',
            is_admin_key INTEGER NOT NULL DEFAULT 0,
            granted_to   INTEGER DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            method       TEXT    NOT NULL,
            account_ref  TEXT    NOT NULL,
            amount_usd   REAL    NOT NULL DEFAULT 20.0,
            currency     TEXT    NOT NULL DEFAULT 'USD',
            status       TEXT    NOT NULL DEFAULT 'pending',
            tx_ref       TEXT    DEFAULT '',
            initiated_at TEXT    NOT NULL,
            confirmed_at TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL DEFAULT 0,
            name        TEXT    NOT NULL,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS backups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            content     TEXT    NOT NULL,
            label       TEXT,
            saved_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            session_id  INTEGER,
            action      TEXT    NOT NULL,
            detail      TEXT,
            at          TEXT    NOT NULL
        );
    """)
    db.commit()

    # ── 2. Migrate old databases safely ─────────────────────────────────────
    _migrate(db)
    db.close()
    _cleanup_expired()


def _migrate(db):
    """
    Safe ALTER TABLE migrations.
    SQLite does not support DROP COLUMN before 3.35 or multi-column ALTER,
    so we only ADD columns that may be missing in older database files.
    Each migration is idempotent — safe to run multiple times.
    """
    existing = _table_columns(db)

    # licences table — columns added in v3
    _add_col_if_missing(db, "licences", "kind",         "TEXT NOT NULL DEFAULT 'paid'",   existing)
    _add_col_if_missing(db, "licences", "status",       "TEXT NOT NULL DEFAULT 'active'", existing)
    _add_col_if_missing(db, "licences", "activated_at", "TEXT",                           existing)
    # v4 admin columns
    _add_col_if_missing(db, "licences", "is_admin_key", "INTEGER NOT NULL DEFAULT 0",     existing)
    _add_col_if_missing(db, "licences", "granted_to",   "INTEGER DEFAULT NULL",           existing)

    # users table
    _add_col_if_missing(db, "users", "email",    "TEXT DEFAULT ''",           existing)
    _add_col_if_missing(db, "users", "is_admin", "INTEGER NOT NULL DEFAULT 0", existing)

    # logs table — session_id and user_id may be missing in very old schemas
    _add_col_if_missing(db, "logs", "user_id",    "INTEGER", existing)
    _add_col_if_missing(db, "logs", "session_id", "INTEGER", existing)

    db.commit()

    # Back-fill: any existing licences rows that lack a kind value
    db.execute("UPDATE licences SET kind='paid'   WHERE kind   IS NULL OR kind=''")
    db.execute("UPDATE licences SET status='active' WHERE status IS NULL OR status=''")
    db.commit()


def _table_columns(db) -> dict:
    """Return {table_name: set(column_names)} for all tables in the database."""
    result = {}
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    for row in tables:
        tbl  = row["name"]
        cols = db.execute(f"PRAGMA table_info({tbl})").fetchall()
        result[tbl] = {c["name"] for c in cols}
    return result


def _add_col_if_missing(db, table, column, col_def, existing):
    """ALTER TABLE … ADD COLUMN only when the column doesn't already exist."""
    if table in existing and column not in existing[table]:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            db.commit()
        except sqlite3.OperationalError:
            pass   # column already exists (race condition guard)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def generate_licence_key() -> str:
    raw = secrets.token_hex(8).upper()
    return "-".join(raw[i:i+4] for i in range(0, 16, 4))


# ─────────────────────────────────────────────────────────────────────────────
#  CLEANUP
# ─────────────────────────────────────────────────────────────────────────────

def _cleanup_expired():
    """
    Delete paid/admin licences that have expired.
    Mark trials as expired (keep row to block second trial).
    Also expire admin keys granted to non-admin users after 30 minutes.
    """
    try:
        db = _conn()
        now = _now()
        # Normal paid licences — delete after expiry
        db.execute(
            "DELETE FROM licences WHERE valid_until < ? AND kind NOT IN ('trial','admin')",
            (now,)
        )
        # Admin keys granted to lambda users — delete after 30 min
        thirty_min_ago = (datetime.datetime.now() - datetime.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            "DELETE FROM licences "
            "WHERE is_admin_key=1 AND granted_to IS NOT NULL "
            "AND activated_at < ? AND kind='admin'",
            (thirty_min_ago,)
        )
        # Mark trials expired (don't delete — needed to block second trial)
        db.execute(
            "UPDATE licences SET status='expired' "
            "WHERE valid_until < ? AND kind='trial' AND status='active'",
            (now,)
        )
        db.commit(); db.close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  USERS
# ─────────────────────────────────────────────────────────────────────────────

def create_user(username: str, password: str, email: str = "", is_admin: bool = False):
    """Returns user id on success, None if username taken. Auto-assigns 7-day trial."""
    try:
        db = _conn()
        cur = db.execute(
            "INSERT INTO users(username,password_hash,email,created_at,is_admin) VALUES(?,?,?,?,?)",
            (username.strip(), _hash(password), email.strip(), _now(), 1 if is_admin else 0)
        )
        db.commit(); uid = cur.lastrowid; db.close()
        if is_admin:
            _ensure_admin_licence(uid, email)
        else:
            _assign_trial(uid)
        return uid
    except sqlite3.IntegrityError:
        return None

def _assign_trial(user_id: int):
    """Give a new user a 7-day free trial licence."""
    now   = datetime.datetime.now()
    until = now + datetime.timedelta(days=7)
    key   = "TRIAL-" + generate_licence_key()
    db = _conn()
    db.execute(
        "INSERT INTO licences(user_id,licence_key,valid_from,valid_until,kind,status) "
        "VALUES(?,?,?,?,?,?)",
        (user_id, key, _now(), until.strftime("%Y-%m-%d %H:%M:%S"), "trial", "active")
    )
    db.commit(); db.close()


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN LICENCE  (universal key, auto-renewed monthly, 30-min on lambda)
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_KEY_PREFIX = "ADMIN-"
ADMIN_KEY_DURATION_DAYS = 31          # auto-renewed every 31 days
ADMIN_GRANT_DURATION_MIN = 30         # lambda user gets 30 min when admin uses key

def _ensure_admin_licence(admin_uid: int, email: str = ""):
    """
    Create (or renew) the admin's universal licence key.
    Called at registration and on every login if < 7 days remain.
    The admin key never expires for the admin's own account.
    Returns the key string.
    """
    db = _conn()
    # Check for existing admin key that hasn't expired for admin's own account
    row = db.execute(
        "SELECT * FROM licences WHERE user_id=? AND kind='admin' AND granted_to IS NULL",
        (admin_uid,)
    ).fetchone()

    now   = datetime.datetime.now()
    until = (now + datetime.timedelta(days=ADMIN_KEY_DURATION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    if row:
        exp = datetime.datetime.strptime(row["valid_until"], "%Y-%m-%d %H:%M:%S")
        days_left = (exp - now).days
        if days_left <= 7:
            # Renew — extend expiry
            db.execute(
                "UPDATE licences SET valid_until=?, status='active' WHERE id=?",
                (until, row["id"])
            )
            db.commit(); db.close()
            key = row["licence_key"]
            # Email the renewed key to admin
            if email:
                _queue_admin_key_email(email, key, until[:10], renewed=True)
            return key
        db.close()
        return row["licence_key"]

    # No admin key yet — create one
    key = ADMIN_KEY_PREFIX + generate_licence_key()
    db.execute(
        "INSERT INTO licences"
        "(user_id,licence_key,valid_from,valid_until,kind,status,is_admin_key,activated_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (admin_uid, key, _now(), until, "admin", "active", 1, _now())
    )
    db.commit(); db.close()
    if email:
        _queue_admin_key_email(email, key, until[:10], renewed=False)
    return key


def _queue_admin_key_email(email: str, key: str, until: str, renewed: bool):
    """Fire-and-forget email of admin key (does not block the UI)."""
    import threading
    def _go():
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            # Import owner config from app level if available
            try:
                from ui.app import OWNER_EMAIL, OWNER_APP_PASS
            except Exception:
                return   # email not configured — skip silently
            action = "renewed" if renewed else "created"
            msg = MIMEMultipart()
            msg["From"]    = OWNER_EMAIL
            msg["To"]      = email
            msg["Subject"] = f"[DocuFlow Admin] Your universal licence key has been {action}"
            body = (
                f"Hello Admin,\n\n"
                f"Your DocuFlow Enterprise admin licence key has been {action}:\n\n"
                f"    {key}\n\n"
                f"This key is valid until {until}.\n"
                f"It grants you full access and can be used on any account for 30 minutes.\n\n"
                f"Keep this key confidential.\n"
            )
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
                s.login(OWNER_EMAIL, OWNER_APP_PASS)
                s.send_message(msg)
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


def get_admin_key(admin_uid: int) -> str | None:
    """Return the admin's current universal key, or None."""
    db = _conn()
    row = db.execute(
        "SELECT licence_key FROM licences WHERE user_id=? AND kind='admin' AND granted_to IS NULL",
        (admin_uid,)
    ).fetchone()
    db.close()
    return row["licence_key"] if row else None


def use_admin_key_on_user(admin_uid: int, target_uid: int) -> dict:
    """
    Admin activates their key on a lambda user.
    The lambda user gets 30 minutes of access.
    The admin's own key is NOT consumed — it remains valid indefinitely.
    Returns {"ok": bool, "until": str, "reason": str}
    """
    admin_key = get_admin_key(admin_uid)
    if not admin_key:
        return {"ok": False, "reason": "No admin key found. Please re-login."}

    # Grant a temporary 30-min licence to the target user
    now   = datetime.datetime.now()
    until = (now + datetime.timedelta(minutes=ADMIN_GRANT_DURATION_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    # Create a new unique copy of the admin key record for this user
    temp_key = ADMIN_KEY_PREFIX + generate_licence_key() + "-T"
    db = _conn()
    db.execute(
        "INSERT INTO licences"
        "(user_id,licence_key,valid_from,valid_until,kind,status,is_admin_key,activated_at,granted_to) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (target_uid, temp_key, _now(), until, "admin", "active", 1, _now(), admin_uid)
    )
    db.commit(); db.close()
    return {"ok": True, "until": until, "key": temp_key}


def renew_admin_licence_if_needed(admin_uid: int, email: str = ""):
    """Call on every admin login — renews key if expiry is within 7 days."""
    _ensure_admin_licence(admin_uid, email)


def is_admin(user_id: int) -> bool:
    db = _conn()
    row = db.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    db.close()
    return bool(row["is_admin"]) if row else False


def authenticate(username: str, password: str):
    db = _conn()
    row = db.execute(
        "SELECT * FROM users WHERE username=? AND password_hash=?",
        (username.strip(), _hash(password))
    ).fetchone()
    db.close()
    if row:
        _cleanup_expired()
        user = dict(row)
        # Auto-renew admin key on every login if needed
        if user.get("is_admin"):
            renew_admin_licence_if_needed(user["id"], user.get("email", ""))
        return user
    return None

def get_user(uid: int):
    db = _conn()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    db.close()
    return dict(row) if row else None

def update_user_email(uid: int, email: str):
    db = _conn()
    db.execute("UPDATE users SET email=? WHERE id=?", (email.strip(), uid))
    db.commit(); db.close()


# ─────────────────────────────────────────────────────────────────────────────
#  LICENCE QUERIES
# ─────────────────────────────────────────────────────────────────────────────

def get_active_licence(user_id: int):
    """Return the current valid licence (admin > paid > trial), or None."""
    _cleanup_expired()
    db = _conn()
    row = db.execute(
        """SELECT * FROM licences
           WHERE user_id=? AND status='active'
           ORDER BY CASE kind
               WHEN 'admin' THEN 0
               WHEN 'paid'  THEN 1
               ELSE 2 END,
           valid_until DESC
           LIMIT 1""",
        (user_id,)
    ).fetchone()
    db.close()
    return dict(row) if row else None

def licence_days_remaining(user_id: int) -> int:
    lic = get_active_licence(user_id)
    if not lic:
        return 0
    try:
        until = datetime.datetime.strptime(lic["valid_until"], "%Y-%m-%d %H:%M:%S")
        return max(0, (until - datetime.datetime.now()).days)
    except Exception:
        return 0

def has_had_trial(user_id: int) -> bool:
    db = _conn()
    row = db.execute(
        "SELECT id FROM licences WHERE user_id=? AND kind='trial' LIMIT 1", (user_id,)
    ).fetchone()
    db.close()
    return row is not None

def activate_licence(user_id: int, key: str) -> dict:
    """
    Activate a licence key for a user.
    If it's an admin key used on a non-admin account, grants 30-minute access
    without consuming the admin key.
    """
    clean_key = key.strip().upper()

    # Check if this is an admin key
    db = _conn()
    admin_row = db.execute(
        "SELECT l.id, l.user_id as admin_uid, u.email FROM licences l "
        "JOIN users u ON l.user_id=u.id "
        "WHERE l.licence_key=? AND l.kind='admin' AND l.granted_to IS NULL AND l.status='active'",
        (clean_key,)
    ).fetchone()
    db.close()

    if admin_row:
        admin_uid = admin_row["admin_uid"]
        if admin_uid == user_id:
            # Admin activating on their own account — already has licence
            return {"ok": True, "until": "Permanent (admin)"}
        # Admin key used on a lambda user — grant 30-min temporary access
        result = use_admin_key_on_user(admin_uid, user_id)
        if result["ok"]:
            return {"ok": True, "until": result["until"][:16] + " (30-min admin debug access)"}
        return {"ok": False, "reason": result.get("reason", "Failed to grant access.")}

    # Normal paid key
    db = _conn()
    row = db.execute(
        "SELECT * FROM licences "
        "WHERE user_id=? AND licence_key=? AND status='active' AND kind='paid'",
        (user_id, clean_key)
    ).fetchone()
    if not row:
        db.close()
        return {"ok": False, "reason": "Key not found, already used, or not assigned to this account."}
    until_dt = datetime.datetime.strptime(row["valid_until"], "%Y-%m-%d %H:%M:%S")
    if datetime.datetime.now() > until_dt:
        db.execute("DELETE FROM licences WHERE id=?", (row["id"],))
        db.commit(); db.close()
        return {"ok": False, "reason": "This key has expired."}
    db.execute("UPDATE licences SET activated_at=? WHERE id=?", (_now(), row["id"]))
    db.commit(); db.close()
    return {"ok": True, "until": until_dt.strftime("%d %b %Y")}

def create_paid_licence(user_id: int, months: int = 3) -> str:
    """Generate and store a new paid licence key. Returns the key string."""
    now   = datetime.datetime.now()
    until = now + datetime.timedelta(days=30 * months)
    key   = generate_licence_key()
    db = _conn()
    db.execute(
        "INSERT INTO licences(user_id,licence_key,valid_from,valid_until,kind,status) "
        "VALUES(?,?,?,?,?,?)",
        (user_id, key, _now(), until.strftime("%Y-%m-%d %H:%M:%S"), "paid", "active")
    )
    db.commit(); db.close()
    return key


# ─────────────────────────────────────────────────────────────────────────────
#  PAYMENTS
# ─────────────────────────────────────────────────────────────────────────────

def create_payment(user_id: int, method: str, account_ref: str,
                   amount_usd: float = 20.0, currency: str = "USD") -> int:
    db = _conn()
    cur = db.execute(
        "INSERT INTO payments(user_id,method,account_ref,amount_usd,currency,status,initiated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (user_id, method, account_ref, amount_usd, currency, "pending", _now())
    )
    db.commit(); pid = cur.lastrowid; db.close()
    return pid

def update_payment_txref(payment_id: int, tx_ref: str):
    db = _conn()
    db.execute("UPDATE payments SET tx_ref=? WHERE id=?", (tx_ref, payment_id))
    db.commit(); db.close()

def confirm_payment(payment_id: int) -> dict:
    """Mark payment confirmed and generate a licence key."""
    db = _conn()
    row = db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
    if not row:
        db.close()
        return {"ok": False}
    db.execute(
        "UPDATE payments SET status='confirmed', confirmed_at=? WHERE id=?",
        (_now(), payment_id)
    )
    db.commit(); db.close()
    key   = create_paid_licence(row["user_id"], months=3)
    until = (datetime.datetime.now() + datetime.timedelta(days=90)).strftime("%d %b %Y")
    return {"ok": True, "key": key, "until": until, "user_id": row["user_id"]}

def get_pending_payments():
    db = _conn()
    rows = db.execute(
        "SELECT p.*, u.username, u.email FROM payments p "
        "JOIN users u ON p.user_id=u.id "
        "WHERE p.status='pending' ORDER BY p.initiated_at DESC"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_payment(payment_id: int):
    db = _conn()
    row = db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
    db.close()
    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────────────────────
#  SESSIONS
# ─────────────────────────────────────────────────────────────────────────────

def create_session(user_id: int, name: str) -> int:
    n = _now(); db = _conn()
    cur = db.execute(
        "INSERT INTO sessions(user_id,name,created_at,updated_at) VALUES(?,?,?,?)",
        (user_id, name, n, n)
    )
    db.commit(); sid = cur.lastrowid; db.close()
    return sid

def get_sessions(user_id: int) -> list:
    db = _conn()
    rows = db.execute(
        "SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

def delete_session(sid: int):
    db = _conn()
    db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    db.commit(); db.close()

def _touch(sid: int):
    db = _conn()
    db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (_now(), sid))
    db.commit(); db.close()


# ─────────────────────────────────────────────────────────────────────────────
#  BACKUPS
# ─────────────────────────────────────────────────────────────────────────────

def save_backup(sid: int, content: str, label: str = "") -> int:
    n = _now(); db = _conn()
    cur = db.execute(
        "INSERT INTO backups(session_id,content,label,saved_at) VALUES(?,?,?,?)",
        (sid, content, label, n)
    )
    db.commit(); bid = cur.lastrowid; db.close()
    _touch(sid)
    return bid

def get_backups(sid: int) -> list:
    db = _conn()
    rows = db.execute(
        "SELECT * FROM backups WHERE session_id=? ORDER BY saved_at DESC", (sid,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_backup(bid: int):
    db = _conn()
    row = db.execute("SELECT * FROM backups WHERE id=?", (bid,)).fetchone()
    db.close()
    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────────────────────
#  LOGS
# ─────────────────────────────────────────────────────────────────────────────

def log(action: str, detail: str = "", sid=None, uid=None):
    db = _conn()
    db.execute(
        "INSERT INTO logs(user_id,session_id,action,detail,at) VALUES(?,?,?,?,?)",
        (uid, sid, action, detail, _now())
    )
    db.commit(); db.close()

def get_logs(user_id: int, limit: int = 300) -> list:
    db = _conn()
    rows = db.execute(
        "SELECT * FROM logs WHERE user_id=? ORDER BY at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]