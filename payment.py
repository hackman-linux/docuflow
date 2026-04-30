"""
DocuFlow Enterprise — Payment gateway integration
Uses Campay (free, Cameroon) for MTN MoMo + Orange Money.
Campay sandbox: https://demo.campay.net  — free to test
Campay live:    https://campay.net       — free API key after registration

Sign up at campay.net → get APP_USERNAME + APP_PASSWORD (free).
No monthly fee, no setup fee. Campay charges a small % per transaction
(typically 1-2 %) which is deducted from what they transfer to you.
"""

import threading, requests, time, datetime, os

# ─── Campay credentials — replace with your real values ──────────────────────
CAMPAY_USERNAME = "5YqizfRvH1HIj7m1Onk8X-CkKQ8NOT-yz5I8Lzbj_FcMist3u3u-Ff_51qMtIttj-12H5B4CSn7AwmYwCIUJjA"       # from campay.net dashboard
CAMPAY_PASSWORD = "x7Fq3KSwljEU70HMyiqfahGIOM89IExG9wAHHmJV53UYF_3g94oz26b2RxTNeEulTj3qNtSF4y1Z8BP3wxI_sg"       # from campay.net dashboard
CAMPAY_ENV      = "demo"   # "demo" for testing, "prod" for live

CAMPAY_BASE = {
    "demo": "https://demo.campay.net/api",
    "prod": "https://campay.net/api",
}[CAMPAY_ENV]

# Price in XAF (FCFA). $20 ≈ 12 500 FCFA at ~600 XAF/USD.
PRICE_XAF   = 12_500
PRICE_USD   = 20
LICENCE_MONTHS = 3


# ─── Owner Gmail for notifications ───────────────────────────────────────────
OWNER_EMAIL    = "ndjodongouhs@gmail.com"
OWNER_APP_PASS = "umja ibgf hsgy oejq"
NOTIFY_EMAIL   = "your.email@gmail.com"


def _get_campay_token() -> str | None:
    """Fetch a short-lived Campay access token."""
    try:
        r = requests.post(
            f"{CAMPAY_BASE}/token/",
            json={"username": CAMPAY_USERNAME, "password": CAMPAY_PASSWORD},
            timeout=15
        )
        r.raise_for_status()
        return r.json().get("token")
    except Exception:
        return None


def initiate_mtn_or_orange(phone: str, network: str, description: str) -> dict:
    """
    Initiate a collect (pull) payment request.
    phone   — user's phone number e.g. "237671234567"
    network — "MTN" or "ORANGE"
    Returns {"ok": True, "ref": str} or {"ok": False, "error": str}
    """
    token = _get_campay_token()
    if not token:
        return {"ok": False, "error": "Could not reach payment server. Check your connection."}

    payload = {
        "amount":      str(PRICE_XAF),
        "currency":    "XAF",
        "from":        phone,
        "description": description,
        "external_reference": f"docuflow-{description}",
    }
    try:
        r = requests.post(
            f"{CAMPAY_BASE}/collect/",
            json=payload,
            headers={"Authorization": f"Token {token}"},
            timeout=20
        )
        r.raise_for_status()
        data = r.json()
        ref = data.get("reference") or data.get("payment_ref") or ""
        if ref:
            return {"ok": True, "ref": ref}
        return {"ok": False, "error": data.get("message", "Unknown error from payment server.")}
    except requests.HTTPError as e:
        try:
            msg = e.response.json().get("message", str(e))
        except Exception:
            msg = str(e)
        return {"ok": False, "error": msg}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def poll_payment_status(ref: str, max_wait: int = 90) -> dict:
    """
    Poll Campay for payment status every 5 s for up to max_wait seconds.
    Returns {"status": "SUCCESSFUL"|"FAILED"|"PENDING", "ref": ref}
    """
    token = _get_campay_token()
    if not token:
        return {"status": "FAILED", "ref": ref}

    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(
                f"{CAMPAY_BASE}/transaction/{ref}/",
                headers={"Authorization": f"Token {token}"},
                timeout=10
            )
            r.raise_for_status()
            data   = r.json()
            status = data.get("status", "PENDING").upper()
            if status in ("SUCCESSFUL", "FAILED"):
                return {"status": status, "ref": ref}
        except Exception:
            pass
        time.sleep(5)
    return {"status": "PENDING", "ref": ref}   # timed out


def send_email(to: str, subject: str, body: str):
    """Non-blocking SMTP send via Gmail."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    def _send():
        try:
            msg = MIMEMultipart()
            msg["From"]    = OWNER_EMAIL
            msg["To"]      = to
            msg["Subject"] = f"[DocuFlow] {subject}"
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
                s.login(OWNER_EMAIL, OWNER_APP_PASS)
                s.send_message(msg)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


def notify_owner(username: str, uid: int, method: str, ref: str):
    """Tell the owner a payment succeeded."""
    body = (
        f"✔ Payment received\n"
        f"{'─'*40}\n"
        f"User      : {username} (ID {uid})\n"
        f"Method    : {method}\n"
        f"Reference : {ref}\n"
        f"Amount    : {PRICE_XAF:,} XAF  (~${PRICE_USD})\n"
        f"Duration  : {LICENCE_MONTHS} months\n"
        f"Timestamp : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'─'*40}\n"
        f"Licence key was auto-generated and emailed to the user."
    )
    send_email(NOTIFY_EMAIL, f"Payment – {username} ({method})", body)


def send_key_to_user(user_email: str, username: str, key: str, valid_until: str):
    """Email the licence key to the user."""
    body = (
        f"Hello {username},\n\n"
        f"Your payment was confirmed. Here is your DocuFlow Enterprise licence key:\n\n"
        f"    {key}\n\n"
        f"This key is valid until {valid_until[:10]}.\n\n"
        f"To activate:\n"
        f"  1. Open DocuFlow Enterprise\n"
        f"  2. Click the banner at the top\n"
        f"  3. Enter your key and click Activate\n\n"
        f"Thank you for choosing DocuFlow Enterprise!\n"
    )
    send_email(user_email, "Your DocuFlow licence key", body)


def send_expiry_warning(user_email: str, username: str, days: int, valid_until: str):
    """Warn the user their licence expires soon."""
    body = (
        f"Hello {username},\n\n"
        f"Your DocuFlow Enterprise licence expires in {days} day(s) "
        f"({valid_until[:10]}).\n\n"
        f"To continue without interruption, please renew your licence:\n"
        f"  Open DocuFlow → click the banner → Purchase a new licence\n\n"
        f"Thank you for using DocuFlow Enterprise!\n"
    )
    send_email(user_email, f"Licence expires in {days} day(s)", body)