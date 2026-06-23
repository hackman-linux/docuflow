"""DocuFlow — Database layer v4 (Free Edition)
─────────────────────────────────────────────────
• Multi-user with per-user sessions, backups, and activity logs
• No licences, no payments, no trials — all features always available
• MIGRATION SAFE: works with old databases — adds missing columns automatically
"""
import sqlite3, datetime, os, hashlib, secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "docuflow.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory  = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    return c


# ─────────────────────────────────────────────────────────────────────────────
#  INIT + MIGRATION
# ─────────────────────────────────────────────────────────────────────────────

def init():
    """Create tables if missing, then migrate any old schema to the current one."""
    db = _conn()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            email         TEXT    DEFAULT '',
            created_at    TEXT    NOT NULL
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
    _migrate(db)
    db.close()


def _migrate(db):
    """Add any columns that may be missing in older database files."""
    existing = _table_columns(db)
    _add_col_if_missing(db, "users", "email",    "TEXT DEFAULT ''", existing)
    _add_col_if_missing(db, "logs",  "user_id",  "INTEGER",         existing)
    _add_col_if_missing(db, "logs",  "session_id","INTEGER",        existing)
    db.commit()


def _table_columns(db) -> dict:
    result = {}
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for row in tables:
        tbl  = row["name"]
        cols = db.execute(f"PRAGMA table_info({tbl})").fetchall()
        result[tbl] = {c["name"] for c in cols}
    return result


def _add_col_if_missing(db, table, column, col_def, existing):
    if table in existing and column not in existing[table]:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            db.commit()
        except sqlite3.OperationalError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
#  USERS
# ─────────────────────────────────────────────────────────────────────────────

def create_user(username: str, password: str, email: str = "") -> int | None:
    """Returns user id on success, None if username is already taken."""
    try:
        db = _conn()
        cur = db.execute(
            "INSERT INTO users(username,password_hash,email,created_at) VALUES(?,?,?,?)",
            (username.strip(), _hash(password), email.strip(), _now())
        )
        db.commit()
        uid = cur.lastrowid
        db.close()
        return uid
    except sqlite3.IntegrityError:
        return None


def authenticate(username: str, password: str):
    """Return the user dict on success, None on failure."""
    db = _conn()
    row = db.execute(
        "SELECT * FROM users WHERE username=? AND password_hash=?",
        (username.strip(), _hash(password))
    ).fetchone()
    db.close()
    return dict(row) if row else None


def get_user(uid: int):
    db = _conn()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    db.close()
    return dict(row) if row else None


def update_user_email(uid: int, email: str):
    db = _conn()
    db.execute("UPDATE users SET email=? WHERE id=?", (email.strip(), uid))
    db.commit()
    db.close()


def change_password(uid: int, new_password: str):
    db = _conn()
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash(new_password), uid))
    db.commit()
    db.close()


def delete_user(uid: int):
    db = _conn()
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    db.close()


def list_users() -> list:
    db = _conn()
    rows = db.execute("SELECT id, username, email, created_at FROM users ORDER BY id").fetchall()
    db.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
#  SESSIONS
# ─────────────────────────────────────────────────────────────────────────────

def create_session(user_id: int, name: str) -> int:
    n = _now()
    db = _conn()
    cur = db.execute(
        "INSERT INTO sessions(user_id,name,created_at,updated_at) VALUES(?,?,?,?)",
        (user_id, name, n, n)
    )
    db.commit()
    sid = cur.lastrowid
    db.close()
    return sid


def get_sessions(user_id: int) -> list:
    db = _conn()
    rows = db.execute(
        "SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def rename_session(sid: int, new_name: str):
    db = _conn()
    db.execute("UPDATE sessions SET name=?, updated_at=? WHERE id=?", (new_name, _now(), sid))
    db.commit()
    db.close()


def delete_session(sid: int):
    db = _conn()
    db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    db.commit()
    db.close()


def _touch(sid: int):
    db = _conn()
    db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (_now(), sid))
    db.commit()
    db.close()


# ─────────────────────────────────────────────────────────────────────────────
#  BACKUPS
# ─────────────────────────────────────────────────────────────────────────────

def save_backup(sid: int, content: str, label: str = "") -> int:
    n = _now()
    db = _conn()
    cur = db.execute(
        "INSERT INTO backups(session_id,content,label,saved_at) VALUES(?,?,?,?)",
        (sid, content, label, n)
    )
    db.commit()
    bid = cur.lastrowid
    db.close()
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


def delete_backup(bid: int):
    db = _conn()
    db.execute("DELETE FROM backups WHERE id=?", (bid,))
    db.commit()
    db.close()


def count_backups(sid: int) -> int:
    db = _conn()
    row = db.execute("SELECT COUNT(*) as n FROM backups WHERE session_id=?", (sid,)).fetchone()
    db.close()
    return row["n"] if row else 0


# ─────────────────────────────────────────────────────────────────────────────
#  LOGS
# ─────────────────────────────────────────────────────────────────────────────

def log(action: str, detail: str = "", sid=None, uid=None):
    db = _conn()
    db.execute(
        "INSERT INTO logs(user_id,session_id,action,detail,at) VALUES(?,?,?,?,?)",
        (uid, sid, action, detail, _now())
    )
    db.commit()
    db.close()


def get_logs(user_id: int, limit: int = 300) -> list:
    db = _conn()
    rows = db.execute(
        "SELECT * FROM logs WHERE user_id=? ORDER BY at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def clear_logs(user_id: int):
    db = _conn()
    db.execute("DELETE FROM logs WHERE user_id=?", (user_id,))
    db.commit()
    db.close()
