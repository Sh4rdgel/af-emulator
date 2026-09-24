from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from server import account_db  # noqa: E402

RECOVERY_FAIL_LIMIT = 5
RECOVERY_LOCK_MINUTES = 15

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_time(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _init_web_schema(db_path):
    account_db.init_db(db_path)
    conn = account_db.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS web_account_flags (
                uin INTEGER PRIMARY KEY,
                is_admin INTEGER NOT NULL DEFAULT 0 CHECK(is_admin IN (0,1)),
                is_banned INTEGER NOT NULL DEFAULT 0 CHECK(is_banned IN (0,1)),
                banned_at TEXT,
                ban_reason TEXT,
                last_ip TEXT,
                recovery_failures INTEGER NOT NULL DEFAULT 0,
                recovery_locked_until TEXT,
                FOREIGN KEY(uin) REFERENCES accounts(uin) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS web_invite_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_hash TEXT NOT NULL UNIQUE,
                label TEXT,
                created_at TEXT NOT NULL,
                created_by_uin INTEGER,
                expires_at TEXT,
                uses_remaining INTEGER NOT NULL DEFAULT 1 CHECK(uses_remaining >= 0),
                disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)),
                FOREIGN KEY(created_by_uin) REFERENCES accounts(uin) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS web_recovery_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uin INTEGER NOT NULL,
                code_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                used_at TEXT,
                UNIQUE(uin, code_hash),
                FOREIGN KEY(uin) REFERENCES accounts(uin) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS web_access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uin INTEGER,
                event TEXT NOT NULL,
                ip_address TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(uin) REFERENCES accounts(uin) ON DELETE SET NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _flag_row(conn, uin: int):
    conn.execute("INSERT OR IGNORE INTO web_account_flags(uin) VALUES(?)", (int(uin),))
    return conn.execute("SELECT * FROM web_account_flags WHERE uin=?", (int(uin),)).fetchone()


def _account_by_uin(db_path, uin: int):
    _init_web_schema(db_path)
    conn = account_db.connect(db_path)
    try:
        row = conn.execute(
            """SELECT a.uin,a.username,a.status,a.created_at,a.last_login_at,
                      f.is_admin,f.is_banned,f.banned_at,f.ban_reason,f.last_ip
               FROM accounts a LEFT JOIN web_account_flags f ON f.uin=a.uin
               WHERE a.uin=?""",
            (int(uin),),
        ).fetchone()
        if not row:
            return None
        return dict(row) | {"is_admin": bool(row["is_admin"] or 0), "is_banned": bool(row["is_banned"] or 0)}
    finally:
        conn.close()


def _verify_web_account(db_path, username: str, password: str, ip: str):
    acct = account_db.get_account_by_username(username, db_path=db_path)
    if not acct:
        return None
    conn = account_db.connect(db_path)
    try:
        flags = _flag_row(conn, int(acct["uin"]))
        if int(flags["is_banned"]):
            conn.commit()
            return None
        conn.commit()
    finally:
        conn.close()
    verified = account_db.verify_account(username, password, db_path=db_path, update_last_login=True)
    if verified is None:
        return None
    conn = account_db.connect(db_path)
    try:
        conn.execute("UPDATE web_account_flags SET last_ip=? WHERE uin=?", (ip, int(verified["uin"])))
        conn.execute("INSERT INTO web_access_log(uin,event,ip_address,created_at) VALUES(?,?,?,?)", (int(verified["uin"]), "login", ip, _now()))
        conn.commit()
    finally:
        conn.close()
    return _account_by_uin(db_path, int(verified["uin"]))


def _register(db_path, username: str, password: str, invite_code: str, require_invite: bool, ip: str):
    username = (username or "").strip()
    username_norm = account_db.normalize_username(username)
    digest, salt, iterations = account_db._hash_password(password)
    _init_web_schema(db_path)
    conn = account_db.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        invite = None
        if require_invite:
            invite = conn.execute(
                "SELECT id,expires_at,uses_remaining,disabled FROM web_invite_codes WHERE code_hash=?",
                (_hash_token((invite_code or "").strip()),),
            ).fetchone()
            expires = _parse_time(invite["expires_at"]) if invite else None
            if (not invite or int(invite["disabled"]) or int(invite["uses_remaining"]) <= 0 or
                    (expires and expires <= datetime.now(timezone.utc))):
                raise account_db.AccountError("That invite code is invalid, expired, or already used.")
        if conn.execute("SELECT 1 FROM accounts WHERE username_norm=?", (username_norm,)).fetchone():
            raise account_db.DuplicateUsername("That username is already registered.")
        row = conn.execute("SELECT MAX(uin) AS max_uin FROM accounts").fetchone()
        uin = max(account_db.FIRST_UIN, int(row["max_uin"] or account_db.FIRST_UIN - 1) + 1)
        created = _now()
        conn.execute(
            """INSERT INTO accounts(uin,username,username_norm,password_hash,password_salt,
               password_iterations,status,created_at) VALUES(?,?,?,?,?,?,'active',?)""",
            (uin, username, username_norm, digest, salt, iterations, created),
        )
        conn.execute("INSERT INTO profiles(uin,nickname,created_at) VALUES(?,NULL,?)", (uin, created))
        conn.execute("INSERT INTO web_account_flags(uin,last_ip) VALUES(?,?)", (uin, ip))
        conn.execute("INSERT INTO web_access_log(uin,event,ip_address,created_at) VALUES(?,?,?,?)", (uin, "register", ip, created))
        if invite:
            conn.execute("UPDATE web_invite_codes SET uses_remaining=uses_remaining-1 WHERE id=?", (int(invite["id"]),))
        conn.commit()
        return {"uin": uin, "username": username}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()