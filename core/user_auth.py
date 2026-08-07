"""Multi-User Authentication, Role Permissions, and Password Reset Engine for AIMAOS."""
from __future__ import annotations

import base64
import hashlib
import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from core.db.office_sqlite import OfficeSQLite
from core.security import SecurityValidationError

# In-memory session store mapping active token -> user record dict
_ACTIVE_SESSIONS: Dict[str, dict] = {}


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Cryptographic PBKDF2-SHA256 password hashing with 100,000 iterations and per-user salt."""
    if not salt:
        salt = base64.b64encode(os.urandom(16)).decode("utf-8")
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    pw_hash = base64.b64encode(key).decode("utf-8")
    return pw_hash, salt


class UserManager:
    """Manages multi-user accounts, authentication, admin controls, and session validation."""

    def __init__(self, db: Optional[OfficeSQLite] = None):
        self.db = db or OfficeSQLite()
        self.ensure_default_admin()

    def ensure_default_admin(self) -> dict:
        """Ensure at least one admin account exists on initial boot."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM users")
            count = cursor.fetchone()["count"]
            if count == 0:
                # Create initial admin account
                return self.create_user(
                    username="admin",
                    email="admin@localhost",
                    full_name="Office Administrator",
                    password="admin",
                    role="admin",
                )
            # Return primary admin user
            cursor.execute("SELECT * FROM users WHERE role = 'admin' LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else {}

    def create_user(
        self,
        username: str,
        email: str,
        full_name: str,
        password: str,
        role: str = "staff",
        creator_user: Optional[dict] = None,
    ) -> dict:
        """Create a new user account with hashed password and role assignment."""
        username = username.strip().lower()
        email = email.strip().lower()
        full_name = full_name.strip()
        role = role.strip().lower()

        if creator_user and creator_user.get("role") != "admin":
            raise SecurityValidationError("Only Admin users can create new team members.")

        if not re.fullmatch(r"[a-z0-9_.-]{2,32}", username):
            raise SecurityValidationError("Username must be 2-32 alphanumeric characters, dots, or underscores.")
        if "@" not in email or len(email) < 5 or len(email) > 120:
            raise SecurityValidationError("A valid email address is required.")
        if not full_name or len(full_name) > 100:
            raise SecurityValidationError("Full name must be between 1 and 100 characters.")
        if len(password) < 4:
            raise SecurityValidationError("Password must be at least 4 characters.")
        if role not in {"admin", "staff", "reviewer"}:
            raise SecurityValidationError("Role must be 'admin', 'staff', or 'reviewer'.")

        pw_hash, salt = hash_password(password)
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO users (user_id, username, email, full_name, role, password_hash, salt, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (user_id, username, email, full_name, role, pw_hash, salt, now),
                )
                conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    raise SecurityValidationError("Username or Email already exists in the office directory.") from exc
                raise

        return {
            "user_id": user_id,
            "username": username,
            "email": email,
            "full_name": full_name,
            "role": role,
            "created_at": now,
        }

    def authenticate_user(self, username_or_email: str, password: str) -> tuple[dict, str]:
        """Authenticate user by username or email and return (user_dict, session_token)."""
        identifier = username_or_email.strip().lower()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE (username = ? OR email = ?) AND is_active = 1",
                (identifier, identifier),
            )
            row = cursor.fetchone()
            if not row:
                raise SecurityValidationError("Invalid username/email or password.")

            user = dict(row)
            pw_hash, _ = hash_password(password, salt=user["salt"])
            if pw_hash != user["password_hash"]:
                raise SecurityValidationError("Invalid username/email or password.")

            # Update last_login_at
            now = datetime.now().isoformat()
            cursor.execute("UPDATE users SET last_login_at = ? WHERE user_id = ?", (now, user["user_id"]))
            conn.commit()

            user_record = {
                "user_id": user["user_id"],
                "username": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
                "role": user["role"],
                "last_login_at": now,
            }

            token = f"sess_{uuid.uuid4().hex}"
            _ACTIVE_SESSIONS[token] = user_record
            return user_record, token

    def get_user_by_token(self, token: str) -> Optional[dict]:
        """Retrieve user record associated with an active session token."""
        return _ACTIVE_SESSIONS.get(token)

    def logout_token(self, token: str) -> None:
        """Revoke a session token."""
        _ACTIVE_SESSIONS.pop(token, None)

    def reset_password(self, admin_user: dict, target_user_id: str, new_password: str) -> dict:
        """Allow Admin user to reset a team member's password."""
        if admin_user.get("role") != "admin":
            raise SecurityValidationError("Only Admin users can reset team passwords.")
        if len(new_password) < 4:
            raise SecurityValidationError("Password must be at least 4 characters.")

        pw_hash, salt = hash_password(new_password)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (target_user_id,))
            target = cursor.fetchone()
            if not target:
                raise SecurityValidationError("User not found.")

            cursor.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE user_id = ?",
                (pw_hash, salt, target_user_id),
            )
            conn.commit()
            return {"user_id": target_user_id, "username": target["username"], "full_name": target["full_name"]}

    def list_users(self, requesting_user: Optional[dict] = None) -> List[dict]:
        """Return list of all registered office users."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, username, email, full_name, role, is_active, created_at, last_login_at FROM users ORDER BY full_name ASC")
            return [dict(row) for row in cursor.fetchall()]
