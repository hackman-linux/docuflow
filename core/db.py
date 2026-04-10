"""DocuFlow — SQLite database layer."""
import sqlite3, datetime, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "docuflow.db")

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    db = _conn()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
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
            session_id  INTEGER,
            action      TEXT    NOT NULL,
            detail      TEXT,
            at          TEXT    NOT NULL
        );
    """)
    db.commit(); db.close()

def _now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Sessions
def create_session(name):
    n = _now(); db = _conn()
    cur = db.execute("INSERT INTO sessions(name,created_at,updated_at) VALUES(?,?,?)", (name,n,n))
    db.commit(); sid = cur.lastrowid; db.close(); return sid

def get_sessions():
    db = _conn()
    rows = db.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
    db.close(); return [dict(r) for r in rows]

def delete_session(sid):
    db = _conn(); db.execute("DELETE FROM sessions WHERE id=?", (sid,)); db.commit(); db.close()

def _touch(sid):
    db = _conn(); db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (_now(), sid))
    db.commit(); db.close()

# Backups
def save_backup(sid, content, label=""):
    n = _now(); db = _conn()
    cur = db.execute("INSERT INTO backups(session_id,content,label,saved_at) VALUES(?,?,?,?)", (sid,content,label,n))
    db.commit(); bid = cur.lastrowid; db.close(); _touch(sid); return bid

def get_backups(sid):
    db = _conn()
    rows = db.execute("SELECT * FROM backups WHERE session_id=? ORDER BY saved_at DESC", (sid,)).fetchall()
    db.close(); return [dict(r) for r in rows]

def get_backup(bid):
    db = _conn()
    row = db.execute("SELECT * FROM backups WHERE id=?", (bid,)).fetchone()
    db.close(); return dict(row) if row else None

# Logs
def log(action, detail="", sid=None):
    db = _conn()
    db.execute("INSERT INTO logs(session_id,action,detail,at) VALUES(?,?,?,?)", (sid,action,detail,_now()))
    db.commit(); db.close()

def get_logs(limit=300):
    db = _conn()
    rows = db.execute("SELECT * FROM logs ORDER BY at DESC LIMIT ?", (limit,)).fetchall()
    db.close(); return [dict(r) for r in rows]
