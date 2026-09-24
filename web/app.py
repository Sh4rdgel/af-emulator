#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict, deque
import hmac
import os
from pathlib import Path
import secrets
import threading
import time

from flask import Flask, abort, g, redirect, render_template, request, session, url_for

ROOT = Path(__file__).resolve().parents[1]
from web.account_service import (
    _account_by_uin, _init_web_schema, _register, _verify_web_account, account_db,
)
from web.admin_service import (
    _bootstrap_admin, _create_invite, _issue_recovery_codes, _list_accounts,
    _recover, _set_banned, _web_stats,
)

def _env_bool(name: str, default=False) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


class RateLimiter:
    def __init__(self):
        self.events = defaultdict(deque); self.lock = threading.Lock()

    def allow(self, bucket, key, limit, window):
        now = time.monotonic(); cutoff = now - window
        with self.lock:
            q = self.events[(bucket, key)]
            while q and q[0] < cutoff: q.popleft()
            if len(q) >= limit: return False
            q.append(now); return True


limiter = RateLimiter()


def create_app(test_config=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        SECRET_KEY=os.environ.get("AF_WEB_SECRET") or secrets.token_hex(32),
        ACCOUNT_DB=os.environ.get("AF_ACCOUNT_DB", str(ROOT / "server" / "assaultfire_accounts.sqlite3")),
        REQUIRE_INVITE=_env_bool("AF_REQUIRE_INVITE", True),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_env_bool("AF_WEB_SECURE_COOKIE", False), MAX_CONTENT_LENGTH=65536,
    )
    if test_config: app.config.update(test_config)
    db_path = app.config["ACCOUNT_DB"]; _init_web_schema(db_path)
    au = os.environ.get("AF_ADMIN_USERNAME", "").strip(); ap = os.environ.get("AF_ADMIN_PASSWORD", "")
    if au and ap: _bootstrap_admin(db_path, au, ap)

    def ip(): return (request.remote_addr or "unknown")[:64]
    def csrf_token():
        if "csrf_token" not in session: session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def before():
        g.user = _account_by_uin(db_path, int(session["uin"])) if session.get("uin") else None
        if g.user and (g.user["status"] != "active" or g.user["is_banned"]): session.clear(); g.user = None
        if request.method == "POST":
            a, b = session.get("csrf_token", ""), request.form.get("csrf_token", "")
            if not a or not b or not hmac.compare_digest(a, b): abort(400)

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff"); resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'")
        if g.get("user"): resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    def admin_page(message=None, error=None, new_invite=None):
        if not g.user or not g.user["is_admin"]: abort(404)
        return render_template(
            "admin.html",
            accounts=_list_accounts(db_path),
            stats=_web_stats(db_path),
            message=message,
            error=error,
            new_invite=new_invite,
        )

    @app.get("/")
    def index(): return redirect(url_for("account" if g.user else "login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        error = None; registered = None; entered_username = ""
        if request.method == "POST":
            entered_username = request.form.get("username", "").strip(); p = request.form.get("password", "")
            if p != request.form.get("confirm_password", ""): error = "Passwords do not match."
            elif not limiter.allow("register", ip(), 8, 600): error = "Too many registration attempts. Try again later."
            else:
                try: registered = _register(db_path, entered_username, p, request.form.get("invite_code", ""), bool(app.config["REQUIRE_INVITE"]), ip())
                except account_db.AccountError as exc: error = str(exc)
                except Exception: app.logger.exception("registration failed"); error = "Registration failed."
        return render_template("register.html", error=error, registered=registered, entered_username=entered_username, require_invite=bool(app.config["REQUIRE_INVITE"]))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user: return redirect(url_for("account"))
        error = None; entered_username = ""
        if request.method == "POST":
            entered_username = request.form.get("username", "").strip()
            if not limiter.allow("login", ip(), 10, 600): error = "Too many login attempts. Try again later."
            else:
                user = _verify_web_account(db_path, entered_username, request.form.get("password", ""), ip())
                if not user: error = "Invalid username or password."
                else:
                    session.clear(); session["uin"] = int(user["uin"]); session["csrf_token"] = secrets.token_urlsafe(32)
                    return redirect(url_for("admin" if user["is_admin"] else "account"))
        return render_template("login.html", error=error, entered_username=entered_username)

    @app.post("/logout")
    def logout(): session.clear(); return redirect(url_for("login"))

    @app.get("/account")
    def account():
        if not g.user: return redirect(url_for("login"))
        return render_template("account.html", recovery_codes=None)

    @app.post("/account/recovery-codes")
    def recovery_codes():
        if not g.user: return redirect(url_for("login"))
        return render_template("account.html", recovery_codes=_issue_recovery_codes(db_path, int(g.user["uin"])))

    @app.route("/recover", methods=["GET", "POST"])
    def recover():
        error = None; success = False; entered_username = ""
        if request.method == "POST":
            entered_username = request.form.get("username", "").strip(); p = request.form.get("password", "")
            if p != request.form.get("confirm_password", ""): error = "Passwords do not match."
            elif not limiter.allow("recover", ip(), 6, 900): error = "Too many recovery attempts. Try again later."
            else:
                try: success = _recover(db_path, entered_username, request.form.get("recovery_code", ""), p, ip())
                except account_db.AccountError as exc: error = str(exc)
                if not success and not error: error = "Recovery failed. Check the account and one-time code."
        return render_template("recover.html", error=error, success=success, entered_username=entered_username)

    @app.get("/status")
    def status():
        return render_template("status.html", stats=_web_stats(db_path))

    @app.get("/admin")
    def admin(): return admin_page()

    @app.post("/admin/invites")
    def admin_invites():
        if not g.user or not g.user["is_admin"]: abort(404)
        try:
            code = _create_invite(db_path, int(g.user["uin"]), request.form.get("label", ""), int(request.form.get("uses", "1")), int(request.form["expires_hours"]) if request.form.get("expires_hours") else None)
            return admin_page("Invite created. Copy it now; only its hash is stored.", new_invite=code)
        except ValueError as exc: return admin_page(error=str(exc))

    @app.post("/admin/accounts/<int:uin>/ban")
    def admin_ban(uin):
        if not g.user or not g.user["is_admin"]: abort(404)
        if int(g.user["uin"]) == uin: return admin_page(error="You cannot ban the current admin account.")
        if not _set_banned(db_path, uin, True, request.form.get("reason", "")): abort(404)
        return admin_page(f"UIN {uin} banned.")

    @app.post("/admin/accounts/<int:uin>/unban")
    def admin_unban(uin):
        if not g.user or not g.user["is_admin"]: abort(404)
        if not _set_banned(db_path, uin, False): abort(404)
        return admin_page(f"UIN {uin} unbanned.")

    return app


app = create_app()
if __name__ == "__main__":
    app.run(host=os.environ.get("AF_WEB_HOST", "127.0.0.1"), port=int(os.environ.get("AF_WEB_PORT", "8080")), debug=False)