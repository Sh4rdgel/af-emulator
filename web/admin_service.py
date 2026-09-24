from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets

from web.account_service import (
    RECOVERY_FAIL_LIMIT, RECOVERY_LOCK_MINUTES, _flag_row, _hash_token, _now,
    _parse_time, account_db,
)

def _create_invite(db_path, admin_uin: int, label: str, uses: int, expires_hours: int | None):
    if uses < 1 or uses > 1000:
        raise ValueError("uses must be between 1 and 1000")
    code = "AF-" + secrets.token_urlsafe(24)
    expires = None
    if expires_hours is not None:
        expires = (datetime.now(timezone.utc) + timedelta(hours=max(1, min(expires_hours, 8760)))).isoformat()
    conn = account_db.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO web_invite_codes(code_hash,label,created_at,created_by_uin,expires_at,uses_remaining) VALUES(?,?,?,?,?,?)",
            (_hash_token(code), (label or "")[:120] or None, _now(), int(admin_uin), expires, uses),
        )
        conn.commit()
        return code
    finally:
        conn.close()


def _issue_recovery_codes(db_path, uin: int):
    codes = ["RC-" + secrets.token_urlsafe(16) for _ in range(3)]
    conn = account_db.connect(db_path)
    try:
        flags = _flag_row(conn, uin)
        if int(flags["is_banned"]):
            raise account_db.AccountError("Recovery is unavailable for this account.")
        conn.execute("DELETE FROM web_recovery_codes WHERE uin=? AND used_at IS NULL", (uin,))
        for code in codes:
            conn.execute("INSERT INTO web_recovery_codes(uin,code_hash,created_at) VALUES(?,?,?)", (uin, _hash_token(code), _now()))
        conn.execute("UPDATE web_account_flags SET recovery_failures=0,recovery_locked_until=NULL WHERE uin=?", (uin,))
        conn.commit()
        return codes
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _recover(db_path, username: str, code: str, new_password: str, ip: str):
    username_norm = account_db.normalize_username(username)
    digest, salt, iterations = account_db._hash_password(new_password)
    conn = account_db.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT a.id,a.uin,a.status,f.is_banned,f.recovery_failures,f.recovery_locked_until
               FROM accounts a LEFT JOIN web_account_flags f ON f.uin=a.uin WHERE a.username_norm=?""",
            (username_norm,),
        ).fetchone()
        if not row or row["status"] != "active" or int(row["is_banned"] or 0):
            conn.rollback(); return False
        conn.execute("INSERT OR IGNORE INTO web_account_flags(uin) VALUES(?)", (int(row["uin"]),))
        locked = _parse_time(row["recovery_locked_until"])
        now_dt = datetime.now(timezone.utc)
        if locked and locked > now_dt:
            conn.rollback(); return False
        hit = conn.execute(
            "SELECT id FROM web_recovery_codes WHERE uin=? AND code_hash=? AND used_at IS NULL",
            (int(row["uin"]), _hash_token((code or "").strip())),
        ).fetchone()
        if not hit:
            failures = int(row["recovery_failures"] or 0) + 1
            lock_until = None
            if failures >= RECOVERY_FAIL_LIMIT:
                failures = 0
                lock_until = (now_dt + timedelta(minutes=RECOVERY_LOCK_MINUTES)).isoformat()
            conn.execute("INSERT OR IGNORE INTO web_account_flags(uin) VALUES(?)", (int(row["uin"]),))
            conn.execute("UPDATE web_account_flags SET recovery_failures=?,recovery_locked_until=? WHERE uin=?", (failures, lock_until, int(row["uin"])))
            conn.commit(); return False
        conn.execute("UPDATE accounts SET password_hash=?,password_salt=?,password_iterations=? WHERE id=?", (digest, salt, iterations, int(row["id"])))
        conn.execute("UPDATE web_recovery_codes SET used_at=? WHERE id=?", (_now(), int(hit["id"])))
        conn.execute("UPDATE web_account_flags SET recovery_failures=0,recovery_locked_until=NULL,last_ip=? WHERE uin=?", (ip, int(row["uin"])))
        conn.execute("INSERT INTO web_access_log(uin,event,ip_address,created_at) VALUES(?,?,?,?)", (int(row["uin"]), "recovery", ip, _now()))
        conn.commit(); return True
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def _set_banned(db_path, uin: int, banned: bool, reason=""):
    conn = account_db.connect(db_path)
    try:
        if not conn.execute("SELECT 1 FROM accounts WHERE uin=?", (int(uin),)).fetchone():
            return False
        _flag_row(conn, uin)
        conn.execute(
            "UPDATE web_account_flags SET is_banned=?,banned_at=?,ban_reason=? WHERE uin=?",
            (1 if banned else 0, _now() if banned else None, ((reason or "")[:240] or None) if banned else None, int(uin)),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def _web_stats(db_path):
    conn = account_db.connect(db_path)
    try:
        row = conn.execute(
            """SELECT
                   (SELECT COUNT(*) FROM accounts) AS accounts,
                   (SELECT COUNT(*) FROM web_account_flags WHERE is_banned=1) AS banned,
                   (SELECT COUNT(*) FROM web_invite_codes
                      WHERE uses_remaining > 0
                        AND (expires_at IS NULL OR expires_at > ?)) AS active_invites""",
            (_now(),),
        ).fetchone()
        return {
            "accounts": int(row["accounts"] or 0),
            "banned": int(row["banned"] or 0),
            "active_invites": int(row["active_invites"] or 0),
        }
    finally:
        conn.close()


def _list_accounts(db_path):
    conn = account_db.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT a.uin,a.username,a.status,a.created_at,a.last_login_at,
                      COALESCE(f.is_admin,0) AS is_admin,COALESCE(f.is_banned,0) AS is_banned,
                      f.last_ip,f.ban_reason FROM accounts a LEFT JOIN web_account_flags f ON f.uin=a.uin
               ORDER BY a.uin LIMIT 500"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _bootstrap_admin(db_path, username: str, password: str):
    acct = account_db.get_account_by_username(username, db_path=db_path)
    if acct is None:
        acct = account_db.create_account(username, password, db_path=db_path)
    elif account_db.verify_account(username, password, db_path=db_path) is None:
        raise account_db.AccountError("Configured admin username exists but the password does not match.")
    conn = account_db.connect(db_path)
    try:
        conn.execute("INSERT OR IGNORE INTO web_account_flags(uin) VALUES(?)", (int(acct["uin"]),))
        conn.execute("UPDATE web_account_flags SET is_admin=1 WHERE uin=?", (int(acct["uin"]),))
        conn.commit()
    finally:
        conn.close()