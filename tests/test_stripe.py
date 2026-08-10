import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("SECRET_KEY", "test-secret")

import app as app_module


class StripeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.DATABASE = os.path.join(self.temp_dir.name, "test.db")
        app_module.STRIPE_WEBHOOK_SECRET = "whsec_test"
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        app_module.init_db()

        db = app_module.get_db()
        cursor = db.execute(
            "INSERT INTO users (email, password_hash, plan, created_at) "
            "VALUES (?, ?, 'free', ?)",
            ("customer@example.com", "unused", datetime.utcnow().isoformat()),
        )
        self.user_id = cursor.lastrowid
        db.commit()
        db.close()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def send_event(self, event):
        with patch.object(
            app_module.stripe.Webhook, "construct_event", return_value=event
        ):
            return self.client.post(
                "/stripe-webhook",
                data=b"{}",
                headers={"Stripe-Signature": "test-signature"},
            )

    def get_user(self):
        db = app_module.get_db()
        user = db.execute(
            "SELECT * FROM users WHERE id = ?", (self.user_id,)
        ).fetchone()
        db.close()
        return user

    def test_database_migration_adds_stripe_fields(self):
        user = self.get_user()
        self.assertEqual(user["subscription_status"], "none")
        self.assertIsNone(user["stripe_customer_id"])
        self.assertIsNone(user["stripe_subscription_id"])

    def test_checkout_session_carries_user_identity_into_subscription(self):
        app_module.stripe.api_key = "sk_test_example"
        app_module.STRIPE_PRICE_ID = "price_123"
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

        checkout = type("Checkout", (), {"url": "https://checkout.example/test"})()
        with patch.object(
            app_module.stripe.checkout.Session,
            "create",
            return_value=checkout,
        ) as create:
            response = self.client.post("/create-checkout-session")

        self.assertEqual(response.status_code, 303)
        options = create.call_args.kwargs
        self.assertEqual(options["metadata"]["user_id"], str(self.user_id))
        self.assertEqual(
            options["subscription_data"]["metadata"]["user_id"],
            str(self.user_id),
        )
        self.assertEqual(options["line_items"][0]["price"], "price_123")

    def test_checkout_success_rejects_another_users_session(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

        foreign_checkout = {
            "id": "cs_foreign",
            "payment_status": "paid",
            "subscription": "sub_foreign",
            "metadata": {"user_id": "999"},
        }
        with patch.object(
            app_module.stripe.checkout.Session,
            "retrieve",
            return_value=foreign_checkout,
        ):
            response = self.client.get("/checkout-success?session_id=cs_foreign")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.get_user()["plan"], "free")

    def test_checkout_webhook_upgrades_once_and_cancellation_removes_access(self):
        checkout_event = {
            "id": "evt_checkout",
            "type": "checkout.session.completed",
            "data": {"object": {
                "payment_status": "paid",
                "customer": "cus_123",
                "subscription": "sub_123",
                "metadata": {"user_id": str(self.user_id)},
            }},
        }
        self.assertEqual(self.send_event(checkout_event).status_code, 200)
        self.assertEqual(self.send_event(checkout_event).status_code, 200)

        user = self.get_user()
        self.assertEqual(user["plan"], "pro")
        self.assertEqual(user["stripe_customer_id"], "cus_123")
        self.assertEqual(user["stripe_subscription_id"], "sub_123")

        deleted_event = {
            "id": "evt_deleted",
            "type": "customer.subscription.deleted",
            "data": {"object": {
                "id": "sub_123",
                "customer": "cus_123",
                "status": "canceled",
                "metadata": {"user_id": str(self.user_id)},
            }},
        }
        self.assertEqual(self.send_event(deleted_event).status_code, 200)
        user = self.get_user()
        self.assertEqual(user["plan"], "free")
        self.assertEqual(user["subscription_status"], "canceled")

    def test_failed_renewal_records_past_due_without_immediate_lockout(self):
        db = app_module.get_db()
        db.execute(
            "UPDATE users SET plan='pro', stripe_customer_id='cus_123', "
            "stripe_subscription_id='sub_123', subscription_status='active' "
            "WHERE id=?",
            (self.user_id,),
        )
        db.commit()
        db.close()

        failed_event = {
            "id": "evt_failed",
            "type": "invoice.payment_failed",
            "data": {"object": {
                "customer": "cus_123",
                "subscription": "sub_123",
            }},
        }
        self.assertEqual(self.send_event(failed_event).status_code, 200)
        user = self.get_user()
        self.assertEqual(user["plan"], "pro")
        self.assertEqual(user["subscription_status"], "past_due")


if __name__ == "__main__":
    unittest.main()
