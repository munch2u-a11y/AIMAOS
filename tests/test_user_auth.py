"""Tests for AIMAOS Multi-User Accounts, Role Permissions, and Password Reset Engine."""
from __future__ import annotations

import os
import tempfile
import unittest

from core.db.office_sqlite import OfficeSQLite
from core.security import SecurityValidationError
from core.user_auth import UserManager, hash_password


class TestUserAuth(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_users.sqlite")
        self.db = OfficeSQLite(db_path=self.db_path)
        self.mgr = UserManager(db=self.db)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_hash_password_consistency_and_salt(self):
        pw = "SecretPass123"
        h1, salt1 = hash_password(pw)
        self.assertTrue(len(h1) > 0)
        self.assertTrue(len(salt1) > 0)

        # Re-hashing with the same salt produces exact match
        h2, _ = hash_password(pw, salt=salt1)
        self.assertEqual(h1, h2)

        # Re-hashing with different salt produces different hash
        h3, salt3 = hash_password(pw)
        self.assertNotEqual(h1, h3)

    def test_ensure_default_admin_creates_initial_account(self):
        admin = self.mgr.ensure_default_admin()
        self.assertEqual(admin["role"], "admin")
        self.assertEqual(admin["username"], "admin")
        self.assertEqual(admin["email"], "admin@localhost")

    def test_authenticate_user_success_and_session_token(self):
        user, token = self.mgr.authenticate_user("admin", "admin")
        self.assertIsNotNone(token)
        self.assertEqual(user["username"], "admin")
        self.assertEqual(user["role"], "admin")

        fetched = self.mgr.get_user_by_token(token)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["username"], "admin")

    def test_admin_create_staff_and_reviewer_users(self):
        admin = self.mgr.ensure_default_admin()
        staff_user = self.mgr.create_user(
            username="alex",
            email="alex@riverslaw.com",
            full_name="Attorney Alex Rivers",
            password="pass1234",
            role="staff",
            creator_user=admin,
        )
        self.assertEqual(staff_user["role"], "staff")
        self.assertEqual(staff_user["full_name"], "Attorney Alex Rivers")

        reviewer_user = self.mgr.create_user(
            username="sam",
            email="sam@riverslaw.com",
            full_name="Paralegal Sam",
            password="pass1234",
            role="reviewer",
            creator_user=admin,
        )
        self.assertEqual(reviewer_user["role"], "reviewer")

        # Non-admin cannot create users
        with self.assertRaises(SecurityValidationError):
            self.mgr.create_user(
                username="evil",
                email="evil@riverslaw.com",
                full_name="Evil Attacker",
                password="pass1234",
                role="admin",
                creator_user=staff_user,
            )

    def test_admin_reset_password(self):
        admin = self.mgr.ensure_default_admin()
        staff_user = self.mgr.create_user(
            username="chris",
            email="chris@riverslaw.com",
            full_name="Chris Manager",
            password="oldpassword",
            role="staff",
            creator_user=admin,
        )

        # Authenticate with old password
        _, token_old = self.mgr.authenticate_user("chris", "oldpassword")
        self.assertIsNotNone(token_old)

        # Admin resets password
        self.mgr.reset_password(admin, staff_user["user_id"], "newsecurepass")

        # Old password fails, new password succeeds
        with self.assertRaises(SecurityValidationError):
            self.mgr.authenticate_user("chris", "oldpassword")

        user_new, token_new = self.mgr.authenticate_user("chris", "newsecurepass")
        self.assertEqual(user_new["user_id"], staff_user["user_id"])


if __name__ == "__main__":
    unittest.main()
