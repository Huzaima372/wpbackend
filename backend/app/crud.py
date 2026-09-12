from typing import Any
from .database import get_conn

def create_user(name: str, email: str, phone: str|None=None, address: str|None=None, extra_data: str|None=None) -> int:
    conn=get_conn()
    try:
        cur=conn.execute("INSERT INTO users(name,email,phone,address,extra_data) VALUES (?,?,?,?,?)",
                         (name,email.lower(),phone,address,extra_data))
        conn.commit()
        return int(cur.lastrowid)
    finally: conn.close()

def find_user_by_email(email: str) -> dict[str,Any]|None:
    conn=get_conn()
    try:
        row=conn.execute("SELECT id,name,email,phone,address,extra_data FROM users WHERE email=? COLLATE NOCASE LIMIT 1",
                         (email.strip(),)).fetchone()
        return dict(row) if row else None
    finally: conn.close()

def update_user_by_email(email: str, updates: dict[str,Any]) -> dict[str,Any]|None:
    allowed={"name","phone","address","extra_data"}
    safe={k:v for k,v in updates.items() if k in allowed}
    if not safe: raise ValueError("No supported fields were supplied for update.")
    conn=get_conn()
    try:
        row=conn.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE LIMIT 1",(email.strip(),)).fetchone()
        if not row: return None
        assignments=", ".join(f"{k}=?" for k in safe)
        conn.execute(f"UPDATE users SET {assignments} WHERE id=?", [*safe.values(),row["id"]])
        conn.commit()
    finally: conn.close()
    return find_user_by_email(email)

def delete_user_by_email(email: str) -> dict[str,Any]|None:
    user=find_user_by_email(email)
    if not user: return None
    conn=get_conn()
    try:
        conn.execute("DELETE FROM users WHERE id=?",(user["id"],)); conn.commit()
    finally: conn.close()
    return user

def list_users() -> list[dict[str,Any]]:
    conn=get_conn()
    try:
        rows=conn.execute("SELECT id,name,email,phone,address,extra_data FROM users ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally: conn.close()
