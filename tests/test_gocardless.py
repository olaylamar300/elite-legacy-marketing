import hashlib
import hmac
import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("SECRET_KEY", "test-secret")

import app as app_module


class GoCardlessLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.DATABASE = os.path.join(self.temp_dir.name, "gocardless.db")
        app_module.GOCARDLESS_ACCESS_TOKEN = "live_test_token"
        app_module.GOCARDLESS_WEBHOOK_SECRET = "webhook-secret"
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        app_module.init_db()
        db = app_module.get_db()
        cursor = db.execute(
            "INSERT INTO users (email, password_hash, plan, created_at) VALUES (?, ?, 'free', ?)",
            ("garage@example.com", "unused", datetime.utcnow().isoformat()),
        )
        self.user_id = cursor.lastrowid
        db.commit()
        db.close()
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def api_side_effect(method, path, payload=None, **kwargs):
        if path == "/billing_requests":
            return {"billing_requests": {"id": "BRQ123", "status": "pending"}}
        if path == "/billing_request_flows":
            return {
                "billing_request_flows": {
                    "id": "BRF123",
                    "authorisation_url": "https://pay.gocardless.com/test",
                }
            }
        if path == "/billing_requests/BRQ123":
            return {
                "billing_requests": {
                    "id": "BRQ123",
                    "status": "fulfilled",
                    "links": {"mandate_request_mandate": "MD123", "customer": "CU123"},
                }
            }
        if path == "/subscriptions":
            return {"subscriptions": {"id": "SB123"}}
        if path == "/payments/PM123":
            return {"payments": {"id": "PM123", "links": {"subscription": "SB123"}}}
        raise AssertionError((method, path, payload, kwargs))

    def test_checkout_creates_bacs_mandate_flow(self):
        with patch.object(app_module, "gocardless_request", side_effect=self.api_side_effect) as api:
            response = self.client.post("/gocardless/checkout")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "https://pay.gocardless.com/test")
        request_payload = api.call_args_list[0].args[2]["billing_requests"]
        self.assertEqual(request_payload["mandate_request"]["scheme"], "bacs")
        self.assertNotIn("subscription_request", request_payload)

    def test_success_creates_monthly_subscription_and_setup_workspace(self):
        with patch.object(app_module, "gocardless_request", side_effect=self.api_side_effect):
            self.client.post("/gocardless/checkout")
            db = app_module.get_db()
            token = db.execute("SELECT checkout_token FROM gocardless_checkouts").fetchone()[0]
            db.close()
            response = self.client.get(f"/gocardless/success?checkout={token}")
        self.assertEqual(response.status_code, 302)
        db = app_module.get_db()
        subscription = db.execute(
            "SELECT * FROM service_subscriptions WHERE user_id=? AND service_slug='garage-ai-receptionist'",
            (self.user_id,),
        ).fetchone()
        garage = db.execute("SELECT * FROM garage_accounts WHERE user_id=?", (self.user_id,)).fetchone()
        db.close()
        self.assertEqual(subscription["provider"], "gocardless")
        self.assertEqual(subscription["provider_subscription_id"], "SB123")
        self.assertEqual(subscription["status"], "pending_payment")
        self.assertEqual(garage["status"], "setup")

    def signed_webhook(self, event):
        payload = json.dumps({"events": [event]}, separators=(",", ":")).encode()
        signature = hmac.new(
            app_module.GOCARDLESS_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()
        return self.client.post(
            "/gocardless/webhook", data=payload,
            headers={"Webhook-Signature": signature, "Content-Type": "application/json"},
        )

    def test_confirmed_payment_activates_and_duplicate_is_idempotent(self):
        with patch.object(app_module, "gocardless_request", side_effect=self.api_side_effect):
            self.client.post("/gocardless/checkout")
            db = app_module.get_db()
            checkout = db.execute("SELECT * FROM gocardless_checkouts").fetchone()
            billing = self.api_side_effect("GET", "/billing_requests/BRQ123")["billing_requests"]
            app_module.create_gocardless_subscription(db, checkout, billing)
            db.commit()
            db.close()
            event = {
                "id": "EV123", "resource_type": "payments", "action": "confirmed",
                "links": {"payment": "PM123"},
            }
            self.assertEqual(self.signed_webhook(event).status_code, 204)
            self.assertEqual(self.signed_webhook(event).status_code, 204)
        db = app_module.get_db()
        status = db.execute(
            "SELECT status FROM service_subscriptions WHERE user_id=? AND service_slug='garage-ai-receptionist'",
            (self.user_id,),
        ).fetchone()[0]
        count = db.execute("SELECT COUNT(*) FROM gocardless_events WHERE event_id='EV123'").fetchone()[0]
        db.close()
        self.assertEqual(status, "active")
        self.assertEqual(count, 1)

    def test_invalid_signature_is_rejected(self):
        response = self.client.post(
            "/gocardless/webhook", data=b'{"events":[]}',
            headers={"Webhook-Signature": "wrong"},
        )
        self.assertEqual(response.status_code, 498)


if __name__ == "__main__":
    unittest.main()
