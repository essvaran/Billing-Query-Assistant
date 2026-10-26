"""Session tokens for tests. Auth refuses a token whose user row does not exist, so the row is created first
in whichever app database the test has pointed api.database at."""
from api import database
from api.auth import _make_jwt


def session_token(email: str, role: str = "user") -> str:
    with database.get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO users (email, role) VALUES (?, ?)", (email.lower(), role))
        conn.execute("UPDATE users SET role=? WHERE lower(email)=lower(?)", (role, email))
    return _make_jwt(email, role)
