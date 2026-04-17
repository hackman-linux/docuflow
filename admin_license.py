#!/usr/bin/env python3
"""
DocuFlow Enterprise — Admin Licence Tool
=========================================
Run this script on the machine where docuflow.db lives
to generate and assign licence keys after payment is confirmed.

Usage examples
──────────────
  # List all users
  python admin_licence.py users

  # Generate a new key for user "codex" (3 months)
  python admin_licence.py issue codex

  # Generate a key for user ID 5 with custom duration
  python admin_licence.py issue --id 5 --months 3

  # List all licences
  python admin_licence.py licences
"""

import sys, os, argparse, datetime, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Point to the docuflow package ───────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from core import db

# ── Owner email (same as in app.py) ─────────────────────────────────────────
OWNER_EMAIL    = "your.email@gmail.com"
OWNER_APP_PASS = "xxxx xxxx xxxx xxxx"
LICENCE_MONTHS = 3


def send_key_email(to_address: str, username: str, key: str, until: str):
    """Email the licence key to the user (optional — fill in their address)."""
    try:
        msg = MIMEMultipart()
        msg["From"]    = OWNER_EMAIL
        msg["To"]      = to_address
        msg["Subject"] = "Your DocuFlow Enterprise Licence Key"
        body = (
            f"Hello {username},\n\n"
            f"Thank you for your payment. Here is your 3-month licence key:\n\n"
            f"    {key}\n\n"
            f"This key is valid until {until}.\n\n"
            f"To activate:\n"
            f"  1. Open DocuFlow Enterprise\n"
            f"  2. Click the banner at the top of the screen\n"
            f"  3. Enter your key and click 'Activate'\n\n"
            f"Thank you for using DocuFlow Enterprise.\n"
        )
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
            s.login(OWNER_EMAIL, OWNER_APP_PASS)
            s.send_message(msg)
        print(f"  ✔ Key emailed to {to_address}")
    except Exception as e:
        print(f"  ⚠ Email failed: {e} — send the key manually.")


def cmd_users(_args):
    db.init()
    users = []
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH); conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    print(f"\n{'ID':>4}  {'USERNAME':<24}  {'CREATED'}")
    print("─" * 52)
    for r in rows:
        print(f"{r['id']:>4}  {r['username']:<24}  {r['created_at']}")
    print()


def cmd_licences(_args):
    db.init()
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH); conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT l.*, u.username FROM licences l JOIN users u ON l.user_id=u.id ORDER BY l.id"
    ).fetchall()
    conn.close()
    print(f"\n{'ID':>4}  {'USER':<18}  {'KEY':<19}  {'STATUS':<10}  {'VALID UNTIL'}")
    print("─" * 76)
    for r in rows:
        print(f"{r['id']:>4}  {r['username']:<18}  {r['licence_key']:<19}  "
              f"{r['status']:<10}  {r['valid_until']}")
    print()


def cmd_issue(args):
    db.init()

    # Resolve user
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH); conn.row_factory = sqlite3.Row

    if args.id:
        row = conn.execute("SELECT * FROM users WHERE id=?", (args.id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM users WHERE username=?", (args.username,)).fetchone()
    conn.close()

    if not row:
        print(f"\n✖  User not found: {args.username or args.id}\n"); return

    user_id  = row["id"]
    username = row["username"]
    months   = args.months or LICENCE_MONTHS

    key   = db.generate_licence_key()
    until = (datetime.datetime.now() + datetime.timedelta(days=30 * months))
    lid   = db.create_licence(user_id, key, months)

    print(f"\n✔  Licence created for '{username}'")
    print(f"   Key      : {key}")
    print(f"   Valid for: {months} months  (until {until.strftime('%d %b %Y')})")
    print(f"   DB id    : {lid}\n")

    # Optionally email the key
    if args.email:
        send_key_email(args.email, username, key, until.strftime("%d %b %Y"))
    else:
        print("   Tip: pass --email user@example.com to send the key automatically.\n")


def main():
    parser = argparse.ArgumentParser(
        description="DocuFlow Enterprise — Admin Licence Tool"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("users",    help="List all registered users")
    sub.add_parser("licences", help="List all licence records")

    pi = sub.add_parser("issue", help="Generate and assign a licence key")
    pi.add_argument("username", nargs="?", help="Username to issue key to")
    pi.add_argument("--id",     type=int,  help="User ID (alternative to username)")
    pi.add_argument("--months", type=int,  default=3, help="Licence duration in months (default 3)")
    pi.add_argument("--email",  type=str,  help="Email address to send the key to")

    args = parser.parse_args()
    {"users": cmd_users, "licences": cmd_licences, "issue": cmd_issue}[args.command](args)


if __name__ == "__main__":
    main()