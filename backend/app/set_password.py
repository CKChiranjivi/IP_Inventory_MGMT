import sys

from sqlalchemy import text

from app.db import engine
from app.security import hash_password

if len(sys.argv) != 3:
    sys.exit("Usage: python set_password.py USERNAME NEWPASSWORD")

username, password = sys.argv[1], sys.argv[2]
if len(password) < 8:
    sys.exit("Password must be at least 8 characters.")

with engine.connect() as conn:
    result = conn.execute(
        text("UPDATE users SET password_hash = :h WHERE username = :u"),
        {"h": hash_password(password), "u": username},
    )
    conn.commit()

print("Password updated." if result.rowcount else "User not found.")