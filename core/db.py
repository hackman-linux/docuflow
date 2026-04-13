"""DocuFlow Enterprise — SQLite database layer (v2: multi-user + licence)."""
import sqlite3, datetime, os, hashlib, secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "docuflow.db")

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c

def init():
    db = _conn()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS licences (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            licence_key  TEXT    NOT NULL,
            valid_from   TEXT    NOT NULL,
            valid_until  TEXT    NOT NULL,
            activated_at TEXT,
            status       TEXT    NOT NULL DEFAULT 'pending'
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
    db.commit(); db.close()

def _now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _hash(pw: str) -> str: return hashlib.sha256(pw.encode()).hexdigest()


# ── Users ─────────────────────────────────────────────────────────────────────

def create_user(username: str, password: str):
    """Returns user id (int) on success, None if username taken."""
    try:
        db = _conn()
        cur = db.execute(
            "INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
            (username.strip(), _hash(password), _now())
        )
        db.commit(); uid = cur.lastrowid; db.close(); return uid
    except sqlite3.IntegrityError:
        return None

def authenticate(username: str, password: str):
    """Returns user dict on success, None on failure."""
    db = _conn()
    row = db.execute(
        "SELECT * FROM users WHERE username=? AND password_hash=?",
        (username.strip(), _hash(password))
    ).fetchone()
    db.close(); return dict(row) if row else None

def get_user(uid: int):
    db = _conn()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    db.close(); return dict(row) if row else None


# ── Licence ───────────────────────────────────────────────────────────────────

def generate_licence_key() -> str:
    raw = secrets.token_hex(8).upper()
    return "-".join(raw[i:i+4] for i in range(0, 16, 4))

def create_licence(user_id: int, key: str, months: int = 1) -> int:
    now   = datetime.datetime.now()
    until = now + datetime.timedelta(days=30 * months)
    db = _conn()
    cur = db.execute(
        "INSERT INTO licences(user_id,licence_key,valid_from,valid_until,status) VALUES(?,?,?,?,?)",
        (user_id, key, _now(), until.strftime("%Y-%m-%d %H:%M:%S"), "pending")
    )
    db.commit(); lid = cur.lastrowid; db.close(); return lid

def activate_licence(user_id: int, key: str) -> dict:
    db = _conn()
    row = db.execute(
        "SELECT * FROM licences WHERE user_id=? AND licence_key=? AND status='pending'",
        (user_id, key.strip().upper())
    ).fetchone()
    if not row:
        db.close(); return {"ok": False, "reason": "Key not found or already used."}
    until_dt = datetime.datetime.strptime(row["valid_until"], "%Y-%m-%d %H:%M:%S")
    if datetime.datetime.now() > until_dt:
        db.close(); return {"ok": False, "reason": "This key has expired."}
    db.execute(
        "UPDATE licences SET status='active', activated_at=? WHERE id=?",
        (_now(), row["id"])
    )
    db.commit(); db.close()
    return {"ok": True, "until": until_dt.strftime("%d %b %Y")}

def get_active_licence(user_id: int):
    db = _conn()
    row = db.execute(
        """SELECT * FROM licences WHERE user_id=? AND status IN ('active','pending')
           ORDER BY valid_until DESC LIMIT 1""",
        (user_id,)
    ).fetchone()
    db.close()
    if not row: return None
    r = dict(row)
    try:
        until = datetime.datetime.strptime(r["valid_until"], "%Y-%m-%d %H:%M:%S")
        if datetime.datetime.now() > until:
            db2 = _conn()
            db2.execute("UPDATE licences SET status='expired' WHERE id=?", (r["id"],))
            db2.commit(); db2.close(); return None
    except Exception: pass
    return r

def licence_days_remaining(user_id: int) -> int:
    lic = get_active_licence(user_id)
    if not lic: return 0
    try:
        until = datetime.datetime.strptime(lic["valid_until"], "%Y-%m-%d %H:%M:%S")
        return max(0, (until - datetime.datetime.now()).days)
    except Exception: return 0


# ── Sessions ──────────────────────────────────────────────────────────────────

def create_session(user_id: int, name: str) -> int:
    n = _now(); db = _conn()
    cur = db.execute(
        "INSERT INTO sessions(user_id,name,created_at,updated_at) VALUES(?,?,?,?)",
        (user_id, name, n, n)
    )
    db.commit(); sid = cur.lastrowid; db.close(); return sid

def get_sessions(user_id: int) -> list:
    db = _conn()
    rows = db.execute(
        "SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
    ).fetchall()
    db.close(); return [dict(r) for r in rows]

def delete_session(sid: int):
    db = _conn(); db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    db.commit(); db.close()

def _touch(sid: int):
    db = _conn()
    db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (_now(), sid))
    db.commit(); db.close()


# ── Backups ───────────────────────────────────────────────────────────────────

def save_backup(sid: int, content: str, label: str = "") -> int:
    n = _now(); db = _conn()
    cur = db.execute(
        "INSERT INTO backups(session_id,content,label,saved_at) VALUES(?,?,?,?)",
        (sid, content, label, n)
    )
    db.commit(); bid = cur.lastrowid; db.close(); _touch(sid); return bid

def get_backups(sid: int) -> list:
    db = _conn()
    rows = db.execute(
        "SELECT * FROM backups WHERE session_id=? ORDER BY saved_at DESC", (sid,)
    ).fetchall()
    db.close(); return [dict(r) for r in rows]

def get_backup(bid: int):
    db = _conn()
    row = db.execute("SELECT * FROM backups WHERE id=?", (bid,)).fetchone()
    db.close(); return dict(row) if row else None


# ── Logs ──────────────────────────────────────────────────────────────────────

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
    db.close(); return [dict(r) for r in rows]