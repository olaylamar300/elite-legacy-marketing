import os
import hashlib
import base64
import json
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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
        self.assertIn(b"Marketing content workspace", response.data)
        db = app_module.get_db()
        brand = db.execute("SELECT * FROM brands").fetchone()
        db.close()
        self.assertEqual(brand["name"], "My Brand")

    def test_public_and_logged_in_pages_render(self):
        for path in [
            "/", "/pricing", "/terms", "/privacy", "/refund-policy", "/contact",
            "/services/garage-ai-receptionist",
        ]:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        for removed_path in [
            "/services/ai-phone-receptionist", "/services/review-automation"
        ]:
            self.assertEqual(self.client.get(removed_path).status_code, 404, removed_path)
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
        self.register()
        response = self.client.post(
            "/services/garage-ai-receptionist",
            data={
                "business_name": "Elite Garage",
                "contact_name": "Owner",
                "email": "garage@example.com",
                "phone": "07123456789",
                "contact_line": "020 7946 0123",
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
        self.assertEqual(saved["contact_line"], "020 7946 0123")

    def test_admin_claim_grants_all_services_and_expires(self):
        with patch.object(app_module, "send_account_email", return_value=True):
            self.client.post(
                "/register",
                data={"email": app_module.ADMIN_EMAIL, "password": "temporary123"},
            )
        token = "isolated-test-claim-token"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with patch.object(app_module, "ADMIN_CLAIM_TOKEN_HASH", token_hash):
            response = self.client.post(
                f"/claim-admin/{token}",
                data={"password": "chosenpassword123"},
                follow_redirects=True,
            )
        self.assertIn(b"administrator account is ready", response.data)
        db = app_module.get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email=?", (app_module.ADMIN_EMAIL,)
        ).fetchone()
        services = db.execute(
            "SELECT * FROM service_subscriptions WHERE user_id=?", (user["id"],)
        ).fetchall()
        db.close()
        self.assertEqual(user["plan"], "pro")
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]["service_slug"], "garage-ai-receptionist")
        self.assertTrue(all(row["status"] == "complimentary" for row in services))
        with patch.object(app_module, "ADMIN_CLAIM_TOKEN_HASH", token_hash):
            self.assertEqual(self.client.get(f"/claim-admin/{token}").status_code, 410)

    def telnyx_post(self, path, payload, private_key):
        raw = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = private_key.sign(timestamp.encode() + b"|" + raw)
        return self.client.post(
            path,
            data=raw,
            content_type="application/json",
            headers={
                "telnyx-timestamp": timestamp,
                "telnyx-signature-ed25519": base64.b64encode(signature).decode(),
            },
        )

    def create_test_garage(self, email="garage-owner@example.com", assistant_id="assistant-test"):
        db = app_module.get_db()
        cursor = db.execute(
            "INSERT INTO users (email, password_hash, plan, created_at) VALUES (?, 'unused', 'free', ?)",
            (email, app_module.utc_now()),
        )
        user_id = cursor.lastrowid
        garage = db.execute(
            "INSERT INTO garage_accounts (user_id, business_name, contact_email, telnyx_assistant_id, webhook_key, status, created_at, updated_at) "
            "VALUES (?, 'Test Garage', ?, ?, ?, 'active', ?, ?)",
            (user_id, email, assistant_id, "key-" + hashlib.sha256(email.encode()).hexdigest()[:16], app_module.utc_now(), app_module.utc_now()),
        )
        garage_id = garage.lastrowid
        db.commit()
        db.close()
        return user_id, garage_id

    def test_paid_complete_garage_gets_one_automatic_telnyx_assistant(self):
        user_id, garage_id = self.create_test_garage(assistant_id=None)
        db = app_module.get_db()
        db.execute(
            "UPDATE garage_accounts SET opening_hours='Mon-Fri 8-5', services_offered='MOT and repairs', "
            "booking_rules='Requests require confirmation' WHERE id=?", (garage_id,),
        )
        db.execute(
            "INSERT INTO service_subscriptions (user_id, service_slug, status, created_at, updated_at) "
            "VALUES (?, 'garage-ai-receptionist', 'active', ?, ?)",
            (user_id, app_module.utc_now(), app_module.utc_now()),
        )
        db.commit()
        db.close()
        telnyx_response = unittest.mock.Mock()
        telnyx_response.raise_for_status.return_value = None
        telnyx_response.json.return_value = {"data": {"id": "assistant-automatic", "telephony_settings": {"default_texml_app_id": "texml-app-1"}}}
        with patch.object(app_module, "TELNYX_API_KEY", "test-telnyx-key"), \
             patch.object(app_module.requests, "post", return_value=telnyx_response) as create:
            success, _ = app_module.provision_garage_assistant(garage_id)
            repeated_success, _ = app_module.provision_garage_assistant(garage_id)
        self.assertTrue(success)
        self.assertTrue(repeated_success)
        self.assertEqual(create.call_count, 1)
        payload = create.call_args.kwargs["json"]
        self.assertEqual(payload["tools"][0]["webhook"]["name"], "save_garage_booking")
        self.assertIn("Test Garage", payload["instructions"])
        db = app_module.get_db()
        garage = db.execute("SELECT * FROM garage_accounts WHERE id=?", (garage_id,)).fetchone()
        db.close()
        self.assertEqual(garage["telnyx_assistant_id"], "assistant-automatic")
        self.assertEqual(garage["telnyx_texml_app_id"], "texml-app-1")
        self.assertEqual(garage["provisioning_status"], "assistant_created")

    def test_unpaid_garage_is_not_provisioned(self):
        _, garage_id = self.create_test_garage(assistant_id=None)
        with patch.object(app_module.requests, "post") as create:
            success, message = app_module.provision_garage_assistant(garage_id)
        self.assertFalse(success)
        self.assertIn("subscription", message)
        create.assert_not_called()

    def telnyx_tool_post(self, payload, private_key, call_control_id):
        raw = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = private_key.sign(timestamp.encode() + b"|" + raw)
        return self.client.post(
            "/telnyx/tools/garage-booking",
            data=raw,
            content_type="application/json",
            headers={
                "telnyx-timestamp": timestamp,
                "telnyx-signature-ed25519": base64.b64encode(signature).decode(),
                "x-telnyx-call-control-id": call_control_id,
            },
        )

    def test_signed_telnyx_booking_and_call_event_reach_garage_dashboard(self):
        _, garage_id = self.create_test_garage()
        private_key = Ed25519PrivateKey.generate()
        public_key = base64.b64encode(private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )).decode()
        booking = {
            "conversation_id": "conversation-test-1",
            "customer_name": "Alex Driver",
            "customer_phone": "07123456789",
            "vehicle_registration": "AB12 CDE",
            "vehicle_make_model": "BMW 3 Series",
            "request_type": "Diagnostic booking",
            "problem_description": "Engine warning light",
            "preferred_date": "2026-08-14",
            "preferred_time": "morning",
            "safe_to_drive": "unknown",
        }
        ended = {"data": {
            "id": "event-test-1",
            "event_type": "call.conversation.ended",
            "payload": {
                "assistant_id": "assistant-test",
                "conversation_id": "conversation-test-1",
                "from": "+447123456789",
                "to": "+442079460123",
                "duration_sec": 95,
                "reason": "customer_disconnect",
            },
        }}
        with patch.object(app_module, "TELNYX_PUBLIC_KEY", public_key), \
             patch.object(app_module, "TELNYX_ASSISTANT_ID", "assistant-test"):
            self.assertEqual(self.telnyx_post(
                "/telnyx/tools/garage-booking", booking, private_key
            ).status_code, 200)
            self.assertEqual(self.telnyx_post(
                "/telnyx/webhooks", ended, private_key
            ).status_code, 200)
            duplicate = self.telnyx_post("/telnyx/webhooks", ended, private_key)
            self.assertTrue(duplicate.get_json()["duplicate"])

        db = app_module.get_db()
        saved = db.execute(
            "SELECT * FROM garage_calls WHERE conversation_id='conversation-test-1'"
        ).fetchone()
        db.close()
        self.assertEqual(saved["vehicle_registration"], "AB12 CDE")
        self.assertEqual(saved["duration_seconds"], 95)
        self.assertEqual(saved["garage_id"], garage_id)

    def test_telnyx_rejects_unsigned_requests(self):
        response = self.client.post(
            "/telnyx/tools/garage-booking", json={"conversation_id": "fake"}
        )
        self.assertEqual(response.status_code, 401)

    def test_telnyx_booking_uses_automatic_call_control_header(self):
        self.create_test_garage()
        private_key = Ed25519PrivateKey.generate()
        public_key = base64.b64encode(private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )).decode()
        with patch.object(app_module, "TELNYX_PUBLIC_KEY", public_key), \
             patch.object(app_module, "TELNYX_ASSISTANT_ID", "assistant-test"):
            response = self.telnyx_tool_post(
                {"customer_name": "Jordan", "vehicle_registration": "XY12 ZZZ"},
                private_key,
                "v3:test-call-control-id",
            )
        self.assertEqual(response.status_code, 200)
        db = app_module.get_db()
        saved = db.execute(
            "SELECT * FROM garage_calls WHERE conversation_id=?",
            ("v3:test-call-control-id",),
        ).fetchone()
        db.close()
        self.assertEqual(saved["customer_name"], "Jordan")

    def test_garage_users_only_see_their_own_calls(self):
        first_user, first_garage = self.create_test_garage("first@example.com", "assistant-first")
        second_user, second_garage = self.create_test_garage("second@example.com", "assistant-second")
        db = app_module.get_db()
        now = app_module.utc_now()
        db.execute(
            "INSERT INTO garage_calls (conversation_id, garage_id, customer_name, created_at, updated_at) VALUES ('first-call', ?, 'First Customer', ?, ?)",
            (first_garage, now, now),
        )
        db.execute(
            "INSERT INTO garage_calls (conversation_id, garage_id, customer_name, created_at, updated_at) VALUES ('second-call', ?, 'Second Customer', ?, ?)",
            (second_garage, now, now),
        )
        db.commit()
        db.close()
        with self.client.session_transaction() as session:
            session["user_id"] = first_user
        response = self.client.get("/garage-dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"First Customer", response.data)
        self.assertNotIn(b"Second Customer", response.data)

    def test_paid_garage_subscription_provisions_workspace_and_cancel_pauses_it(self):
        with patch.object(app_module, "send_account_email", return_value=True):
            self.client.post(
                "/register",
                data={"email": "paid-garage@example.com", "password": "password123"},
            )
        db = app_module.get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email='paid-garage@example.com'"
        ).fetchone()
        app_module.sync_service_subscription(
            db, "garage-ai-receptionist", user_id=user["id"],
            customer_id="cus_garage", subscription_id="sub_garage", status="active",
        )
        db.commit()
        garage = db.execute(
            "SELECT * FROM garage_accounts WHERE user_id=?", (user["id"],)
        ).fetchone()
        self.assertIsNotNone(garage)
        self.assertEqual(garage["status"], "setup")
        first_key = garage["webhook_key"]
        app_module.sync_service_subscription(
            db, "garage-ai-receptionist", user_id=user["id"],
            customer_id="cus_garage", subscription_id="sub_garage", status="active",
        )
        db.commit()
        self.assertEqual(
            db.execute("SELECT COUNT(*) FROM garage_accounts WHERE user_id=?", (user["id"],)).fetchone()[0], 1
        )
        self.assertEqual(
            db.execute("SELECT webhook_key FROM garage_accounts WHERE user_id=?", (user["id"],)).fetchone()[0], first_key
        )
        app_module.sync_service_subscription(
            db, "garage-ai-receptionist", user_id=user["id"], status="canceled"
        )
        db.commit()
        paused = db.execute(
            "SELECT status FROM garage_accounts WHERE user_id=?", (user["id"],)
        ).fetchone()[0]
        db.close()
        self.assertEqual(paused, "paused")

    def test_garage_price_is_four_hundred_pounds(self):
        response = self.client.get("/services/garage-ai-receptionist")
        self.assertIn(b"\xc2\xa3400", response.data)


if __name__ == "__main__":
    unittest.main()
