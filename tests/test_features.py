import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("SECRET_KEY", "test-secret")

import app as app_module


class PlatformFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.DATABASE = os.path.join(self.temp_dir.name, "features.db")
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        app_module.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def register(self):
        with patch.object(app_module, "send_account_email", return_value=True):
            return self.client.post(
                "/register",
                data={"email": "owner@example.com", "password": "password123"},
                follow_redirects=True,
            )

    def test_registration_creates_first_brand_and_dashboard_renders(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Your content dashboard", response.data)
        db = app_module.get_db()
        brand = db.execute("SELECT * FROM brands").fetchone()
        db.close()
        self.assertEqual(brand["name"], "My Brand")

    def test_public_and_logged_in_pages_render(self):
        for path in [
            "/", "/pricing", "/terms", "/privacy", "/refund-policy", "/contact",
            "/services/ai-phone-receptionist",
            "/services/garage-ai-receptionist",
            "/services/review-automation",
        ]:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.register()
        for path in ["/dashboard", "/account", "/brands", "/tools", "/library", "/generate"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_free_account_cannot_create_second_workspace(self):
        self.register()
        response = self.client.post(
            "/brands", data={"name": "Second Client"}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/pricing", response.headers["Location"])

    def test_password_reset_changes_login_password(self):
        self.register()
        self.client.get("/logout")
        token = app_module.account_token("owner@example.com", "reset")
        response = self.client.post(
            f"/reset-password/{token}", data={"password": "newpassword123"}
        )
        self.assertEqual(response.status_code, 302)
        login = self.client.post(
            "/login",
            data={"email": "owner@example.com", "password": "newpassword123"},
        )
        self.assertEqual(login.status_code, 302)
        self.assertIn("/dashboard", login.headers["Location"])

    def test_non_admin_cannot_open_admin_dashboard(self):
        self.register()
        self.assertEqual(self.client.get("/admin").status_code, 403)

    def test_service_setup_request_is_saved(self):
        response = self.client.post(
            "/services/garage-ai-receptionist",
            data={
                "business_name": "Elite Garage",
                "contact_name": "Owner",
                "email": "garage@example.com",
                "phone": "07123456789",
                "setup_notes": "Capture registrations and service requests.",
            },
            follow_redirects=True,
        )
        self.assertIn(b"setup request has been received", response.data)
        db = app_module.get_db()
        saved = db.execute("SELECT * FROM service_requests").fetchone()
        db.close()
        self.assertEqual(saved["service_slug"], "garage-ai-receptionist")
        self.assertEqual(saved["business_name"], "Elite Garage")


if __name__ == "__main__":
    unittest.main()
