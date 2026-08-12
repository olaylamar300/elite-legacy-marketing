import csv
import base64
import hashlib
import hmac
import io
import json
import os
import smtplib
import time
import stripe
from email.message import EmailMessage
from dotenv import load_dotenv
from openai import OpenAI
import random
import secrets
import sqlite3
from datetime import date, datetime, timezone
from functools import wraps

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID")
STRIPE_SERVICE_PRICE_IDS = {
    "ai-phone-receptionist": os.environ.get("STRIPE_PHONE_RECEPTIONIST_PRICE_ID"),
    "garage-ai-receptionist": os.environ.get("STRIPE_GARAGE_RECEPTIONIST_PRICE_ID"),
    "review-automation": os.environ.get("STRIPE_REVIEW_AUTOMATION_PRICE_ID"),
}
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "olaylamarbusiness@gmail.com").strip().lower()
ADMIN_CLAIM_TOKEN_HASH = "2b0a27d0095482b957763e0aecf6c6af5d5e88b6c4991ec3ab90857d6694283e"
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "").strip()
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://wwwelite-legacy-marketing.com").rstrip("/")
TELNYX_PUBLIC_KEY = os.environ.get("TELNYX_PUBLIC_KEY", "").strip()
TELNYX_ASSISTANT_ID = os.environ.get("TELNYX_ASSISTANT_ID", "").strip()
client = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
DATABASE = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "ideaforge.db"),
)

FREE_DAILY_LIMIT = 10

SERVICES = {
    "ai-phone-receptionist": {
        "name": "AI Phone Receptionist",
        "price": 80,
        "eyebrow": "NEVER MISS A BUSINESS CALL",
        "headline": "A professional first response, even when your team is busy.",
        "description": "An AI phone receptionist configured around your business, services and call-handling rules.",
        "features": [
            "24/7 call answering", "Natural AI conversation", "Business knowledge",
            "Caller identification", "Intent detection", "Appointment booking",
            "Rescheduling and cancellations", "SMS confirmations", "Appointment reminders",
            "Take a message", "Call summaries", "Business dashboard",
        ],
    },
    "garage-ai-receptionist": {
        "name": "Garage AI Receptionist",
        "price": 400,
        "eyebrow": "BUILT FOR BUSY GARAGES",
        "headline": "Keep the workshop moving while every caller gets answered.",
        "description": "A garage-focused AI receptionist that captures vehicle and booking information using your rules.",
        "features": [
            "Garage bookings", "AI customer service", "WhatsApp messaging",
            "Vehicle information collection", "Automatic reminders",
            "Repair status messages", "Missed-call recovery", "Garage dashboard",
        ],
    },
    "review-automation": {
        "name": "Review Automation",
        "price": 10,
        "eyebrow": "BUILD TRUST ON AUTOPILOT",
        "headline": "Turn completed jobs into a steady flow of customer reviews.",
        "description": "Automated, brand-friendly review requests with a simple follow-up journey for customers.",
        "features": [
            "Automatic review requests", "SMS requests", "Email requests",
            "WhatsApp integration", "Direct review links", "QR codes",
            "Custom messages", "Scheduled delays", "Automatic follow-ups",
            "Customer database", "Do-not-contact controls", "Review dashboard",
        ],
    },
}

HOOKS = [
    "Nobody tells you this about {topic}",
    "Three mistakes people make with {topic}",
    "What I wish I knew before starting {topic}",
    "Stop doing this if you want better results with {topic}",
    "The easiest way to improve your {topic}",
    "The truth about {topic}",
    "Five things beginners should know about {topic}",
    "I tested this {topic} strategy so you do not have to",
    "Before you spend money on {topic}, watch this",
    "This one change improved my {topic}",
    "A beginner's guide to {topic}",
    "Why most people struggle with {topic}",
    "An unpopular opinion about {topic}",
    "How to get results with {topic} without overcomplicating it",
    "The biggest lesson I learned from {topic}",
    "Do this before you start {topic}",
    "The simple {topic} checklist I wish I had",
    "What successful people understand about {topic}",
    "The fastest way to make {topic} easier",
    "One thing I would never do again with {topic}",
]

FORMATS = [
    "Step-by-step tutorial",
    "Day-in-the-life video",
    "Personal story",
    "Before-and-after comparison",
    "Frequently asked question",
    "Myth-versus-fact post",
    "Three practical tips",
    "Reaction to a common mistake",
    "Checklist",
    "Behind-the-scenes video",
    "Product or service review",
    "Beginner challenge",
    "Weekly lesson",
    "Mini case study",
    "Comparison post",
    "Voice-over montage",
    "Screen recording walkthrough",
    "Opinion-led talking video",
]

PLATFORM_TIPS = {
    "TikTok": "Use a strong opening in the first two seconds and keep the pacing fast.",
    "Instagram Reel": "Use on-screen captions and a clear visual hook.",
    "Instagram Carousel": "Make the first slide curiosity-driven and use one point per slide.",
    "YouTube": "Use a searchable title, strong thumbnail, and explain the value early.",
    "YouTube Short": "Focus on one idea and cut anything that slows the opening.",
    "LinkedIn": "Lead with a lesson, result, or strong professional opinion.",
    "X / Twitter": "Use a sharp first line and keep each point concise.",
}

CTAS = {
    "Grow followers": [
        "Follow for more content like this.",
        "Follow to see the next part.",
        "Save this and follow for more ideas.",
        "Share this with someone who needs it.",
    ],
    "Increase engagement": [
        "Which one do you agree with? Comment below.",
        "What would you add to this list?",
        "Comment your experience below.",
        "Send this to a friend and compare answers.",
    ],
    "Generate sales": [
        "Message us for more information.",
        "Use the link in the bio to get started.",
        "Comment 'INFO' for the details.",
        "Book while availability lasts.",
    ],
    "Build trust": [
        "Follow for honest advice and real experiences.",
        "Ask your questions in the comments.",
        "Save this for when you need it.",
        "Share this with someone who may find it useful.",
    ],
    "Educate people": [
        "Save this so you can come back to it.",
        "Comment which topic should be explained next.",
        "Share this with someone learning about this.",
        "Follow for the next lesson.",
    ],
    "Promote an event": [
        "Get tickets through the link in the bio.",
        "Tag the person you are coming with.",
        "Save the date and share this with your group.",
        "Message us for tickets and table bookings.",
    ],
    "Get clients": [
        "Message me if you want help with this.",
        "Book a consultation through the link in my bio.",
        "Comment 'HELP' for more information.",
        "Send me a message to discuss your project.",
    ],
    "Build a personal brand": [
        "Follow my journey for more behind-the-scenes content.",
        "Comment if you can relate.",
        "Follow for more lessons from my experience.",
        "Share this with someone building their own brand.",
    ],
}

NICHES = [
    "Lifestyle", "Business", "Marketing", "Fitness", "Fashion", "Food",
    "Travel", "Cars", "Technology", "Events", "Education",
    "Personal development", "Beauty", "Music", "Gaming", "Real estate"
]

PLATFORMS = list(PLATFORM_TIPS.keys())
GOALS = list(CTAS.keys())
TONES = [
    "Entertaining", "Educational", "Professional", "Funny",
    "Inspirational", "Luxury", "Direct", "Storytelling"
]


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            niche TEXT NOT NULL,
            platform TEXT NOT NULL,
            topic TEXT NOT NULL,
            audience TEXT NOT NULL,
            goal TEXT NOT NULL,
            tone TEXT NOT NULL,
            format TEXT NOT NULL,
            platform_tip TEXT NOT NULL,
            cta TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            usage_date TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, usage_date),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS stripe_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            niche TEXT NOT NULL DEFAULT '',
            audience TEXT NOT NULL DEFAULT '',
            voice TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_name TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS service_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service_slug TEXT NOT NULL,
            business_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '',
            contact_line TEXT NOT NULL DEFAULT '',
            setup_notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS service_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service_slug TEXT NOT NULL,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, service_slug),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS telnyx_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            conversation_id TEXT,
            received_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS garage_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT UNIQUE,
            assistant_id TEXT NOT NULL DEFAULT '',
            caller_number TEXT NOT NULL DEFAULT '',
            called_number TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            customer_phone TEXT NOT NULL DEFAULT '',
            customer_email TEXT NOT NULL DEFAULT '',
            vehicle_registration TEXT NOT NULL DEFAULT '',
            vehicle_make_model TEXT NOT NULL DEFAULT '',
            vehicle_year TEXT NOT NULL DEFAULT '',
            request_type TEXT NOT NULL DEFAULT '',
            problem_description TEXT NOT NULL DEFAULT '',
            preferred_date TEXT NOT NULL DEFAULT '',
            preferred_time TEXT NOT NULL DEFAULT '',
            safe_to_drive TEXT NOT NULL DEFAULT '',
            additional_notes TEXT NOT NULL DEFAULT '',
            call_status TEXT NOT NULL DEFAULT 'details_collected',
            call_reason TEXT NOT NULL DEFAULT '',
            duration_seconds INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS garage_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service_request_id INTEGER,
            business_name TEXT NOT NULL,
            contact_name TEXT NOT NULL DEFAULT '',
            contact_email TEXT NOT NULL DEFAULT '',
            contact_phone TEXT NOT NULL DEFAULT '',
            business_line TEXT NOT NULL DEFAULT '',
            opening_hours TEXT NOT NULL DEFAULT '',
            services_offered TEXT NOT NULL DEFAULT '',
            booking_rules TEXT NOT NULL DEFAULT '',
            escalation_rules TEXT NOT NULL DEFAULT '',
            telnyx_assistant_id TEXT UNIQUE,
            webhook_key TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'setup',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(service_request_id) REFERENCES service_requests(id)
        );
        """
    )

    # Keep existing Railway databases compatible without deleting customer data.
    user_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()
    }
    migrations = {
        "stripe_customer_id": "TEXT",
        "stripe_subscription_id": "TEXT",
        "subscription_status": "TEXT NOT NULL DEFAULT 'none'",
        "subscription_period_end": "TEXT",
        "email_verified": "INTEGER NOT NULL DEFAULT 0",
        "display_name": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in migrations.items():
        if column not in user_columns:
            db.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")

    idea_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(ideas)").fetchall()
    }
    if "brand_id" not in idea_columns:
        db.execute("ALTER TABLE ideas ADD COLUMN brand_id INTEGER")

    service_request_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(service_requests)").fetchall()
    }
    if "contact_line" not in service_request_columns:
        db.execute("ALTER TABLE service_requests ADD COLUMN contact_line TEXT NOT NULL DEFAULT ''")

    garage_call_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(garage_calls)").fetchall()
    }
    if "garage_id" not in garage_call_columns:
        db.execute("ALTER TABLE garage_calls ADD COLUMN garage_id INTEGER")

    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_stripe_customer_idx "
        "ON users(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_stripe_subscription_idx "
        "ON users(stripe_subscription_id) "
        "WHERE stripe_subscription_id IS NOT NULL"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS garage_accounts_user_idx ON garage_accounts(user_id)"
    )
    admin = db.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)).fetchone()
    if admin:
        db.execute("UPDATE users SET plan='pro' WHERE id=?", (admin["id"],))
        for service_slug in SERVICES:
            db.execute(
                "INSERT INTO service_subscriptions "
                "(user_id, service_slug, status, created_at, updated_at) VALUES (?, ?, 'complimentary', ?, ?) "
                "ON CONFLICT(user_id, service_slug) DO UPDATE SET status='complimentary', updated_at=excluded.updated_at",
                (admin["id"], service_slug, utc_now(), utc_now()),
            )
        owner_garage = db.execute(
            "SELECT id FROM garage_accounts WHERE user_id=? ORDER BY id LIMIT 1",
            (admin["id"],),
        ).fetchone()
        if not owner_garage:
            now = utc_now()
            cursor = db.execute(
                "INSERT INTO garage_accounts "
                "(user_id, business_name, contact_name, contact_email, telnyx_assistant_id, webhook_key, status, created_at, updated_at) "
                "VALUES (?, 'Elite Garage', 'Owner', ?, ?, ?, 'active', ?, ?)",
                (admin["id"], ADMIN_EMAIL, TELNYX_ASSISTANT_ID or None, secrets.token_urlsafe(24), now, now),
            )
            owner_garage_id = cursor.lastrowid
        else:
            owner_garage_id = owner_garage["id"]
            if TELNYX_ASSISTANT_ID:
                db.execute(
                    "UPDATE garage_accounts SET telnyx_assistant_id=COALESCE(telnyx_assistant_id, ?) WHERE id=?",
                    (TELNYX_ASSISTANT_ID, owner_garage_id),
                )
        db.execute(
            "UPDATE garage_calls SET garage_id=? WHERE garage_id IS NULL",
            (owner_garage_id,),
        )
    db.commit()
    db.close()


@app.before_request
def ensure_database():
    init_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    user = db.execute(
        "SELECT id, email, plan, created_at, stripe_customer_id, "
        "stripe_subscription_id, subscription_status, "
        "subscription_period_end, email_verified, display_name "
        "FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    db.close()
    return user


def current_garage():
    user = current_user()
    if not user:
        return None
    db = get_db()
    garage = db.execute(
        "SELECT * FROM garage_accounts WHERE user_id=? ORDER BY id LIMIT 1",
        (user["id"],),
    ).fetchone()
    db.close()
    return garage


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def verify_telnyx_request(raw_body):
    """Verify Telnyx's Ed25519 signature and reject stale webhook replays."""
    if not TELNYX_PUBLIC_KEY:
        return False
    signature = request.headers.get("telnyx-signature-ed25519", "")
    timestamp = request.headers.get("telnyx-timestamp", "")
    try:
        timestamp_number = int(timestamp)
        if abs(int(time.time()) - timestamp_number) > 300:
            return False
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(TELNYX_PUBLIC_KEY))
        public_key.verify(
            base64.b64decode(signature),
            timestamp.encode("utf-8") + b"|" + raw_body,
        )
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False


def token_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="elite-legacy-account")


def account_token(email, purpose):
    return token_serializer().dumps({"email": email, "purpose": purpose})


def read_account_token(token, purpose, max_age=3600):
    data = token_serializer().loads(token, max_age=max_age)
    if data.get("purpose") != purpose:
        raise BadSignature("Incorrect token purpose")
    return data["email"]


def send_account_email(recipient, subject, body):
    host = os.environ.get("SMTP_HOST")
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM", SUPPORT_EMAIL)
    if not all([host, username, password, sender]):
        app.logger.warning("Email not sent because SMTP variables are incomplete")
        return False

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)
    return True


def email_configured():
    return all(
        os.environ.get(name)
        for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM")
    )


def log_event(event_name, user_id=None, metadata=""):
    db = get_db()
    db.execute(
        "INSERT INTO analytics_events (user_id, event_name, metadata, created_at) "
        "VALUES (?, ?, ?, ?)",
        (user_id or session.get("user_id"), event_name, str(metadata)[:500], utc_now()),
    )
    db.commit()
    db.close()


def current_brand():
    if "user_id" not in session:
        return None
    db = get_db()
    brand = None
    if session.get("brand_id"):
        brand = db.execute(
            "SELECT * FROM brands WHERE id=? AND user_id=?",
            (session["brand_id"], session["user_id"]),
        ).fetchone()
    if not brand:
        brand = db.execute(
            "SELECT * FROM brands WHERE user_id=? ORDER BY id LIMIT 1",
            (session["user_id"],),
        ).fetchone()
        if brand:
            session["brand_id"] = brand["id"]
    db.close()
    return brand


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or not ADMIN_EMAIL or user["email"] != ADMIN_EMAIL:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def stripe_value(value):
    """Return a plain value from Stripe objects or dictionaries."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def subscription_id_from_invoice(invoice):
    subscription = invoice.get("subscription")
    if isinstance(subscription, dict):
        return subscription.get("id")
    if subscription:
        return subscription

    parent = invoice.get("parent") or {}
    details = parent.get("subscription_details") or {}
    subscription = details.get("subscription")
    return subscription.get("id") if isinstance(subscription, dict) else subscription


def update_subscription_user(
    db,
    *,
    user_id=None,
    customer_id=None,
    subscription_id=None,
    status=None,
    period_end=None,
    plan=None,
):
    conditions = []
    values = []
    if user_id:
        conditions.append("id = ?")
        values.append(int(user_id))
    elif subscription_id:
        conditions.append("stripe_subscription_id = ?")
        values.append(subscription_id)
    elif customer_id:
        conditions.append("stripe_customer_id = ?")
        values.append(customer_id)
    if not conditions:
        return 0

    updates = []
    update_values = []
    for column, value in (
        ("stripe_customer_id", customer_id),
        ("stripe_subscription_id", subscription_id),
        ("subscription_status", status),
        ("subscription_period_end", period_end),
        ("plan", plan),
    ):
        if value is not None:
            updates.append(f"{column} = ?")
            update_values.append(value)

    if not updates:
        return 0

    result = db.execute(
        f"UPDATE users SET {', '.join(updates)} "
        f"WHERE {' OR '.join(conditions)}",
        (*update_values, *values),
    )
    return result.rowcount


def sync_subscription(db, subscription, user_id=None):
    subscription = stripe_value(subscription)
    status = subscription.get("status", "none")
    plan = "pro" if status in {"active", "trialing"} else "free"
    period_end = subscription.get("current_period_end")
    period_end = (
        datetime.utcfromtimestamp(period_end).isoformat()
        if period_end else None
    )
    metadata = subscription.get("metadata") or {}
    return update_subscription_user(
        db,
        user_id=user_id or metadata.get("user_id"),
        customer_id=subscription.get("customer"),
        subscription_id=subscription.get("id"),
        status=status,
        period_end=period_end,
        plan=plan,
    )


def sync_service_subscription(db, service_slug, *, user_id=None, customer_id=None,
                              subscription_id=None, status="active"):
    if service_slug not in SERVICES or not user_id:
        return 0
    db.execute(
        "INSERT INTO service_subscriptions "
        "(user_id, service_slug, stripe_customer_id, stripe_subscription_id, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, service_slug) DO UPDATE SET "
        "stripe_customer_id=excluded.stripe_customer_id, "
        "stripe_subscription_id=excluded.stripe_subscription_id, "
        "status=excluded.status, updated_at=excluded.updated_at",
        (int(user_id), service_slug, customer_id, subscription_id, status, utc_now(), utc_now()),
    )
    if service_slug == "garage-ai-receptionist":
        if status in {"active", "trialing", "complimentary"}:
            ensure_garage_workspace(db, int(user_id))
        elif status in {"canceled", "cancelled", "unpaid", "incomplete_expired"}:
            db.execute(
                "UPDATE garage_accounts SET status='paused', updated_at=? WHERE user_id=?",
                (utc_now(), int(user_id)),
            )
    return 1


def ensure_garage_workspace(db, user_id):
    """Provision a private garage workspace after verified subscription access."""
    existing = db.execute(
        "SELECT id FROM garage_accounts WHERE user_id=?", (user_id,)
    ).fetchone()
    if existing:
        return existing["id"]
    user = db.execute(
        "SELECT email, display_name FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not user:
        return None
    latest_request = db.execute(
        "SELECT * FROM service_requests WHERE user_id=? AND service_slug='garage-ai-receptionist' "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    business_name = latest_request["business_name"] if latest_request else (user["display_name"] or "My Garage")
    contact_name = latest_request["contact_name"] if latest_request else (user["display_name"] or "")
    contact_phone = latest_request["phone"] if latest_request else ""
    business_line = latest_request["contact_line"] if latest_request else ""
    request_id = latest_request["id"] if latest_request else None
    now = utc_now()
    cursor = db.execute(
        "INSERT INTO garage_accounts (user_id, service_request_id, business_name, contact_name, contact_email, "
        "contact_phone, business_line, webhook_key, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'setup', ?, ?)",
        (user_id, request_id, business_name, contact_name, user["email"], contact_phone,
         business_line, secrets.token_urlsafe(24), now, now),
    )
    if request_id:
        db.execute("UPDATE service_requests SET status='paid' WHERE id=?", (request_id,))
    return cursor.lastrowid


def get_today_usage(user_id):
    db = get_db()
    row = db.execute(
        "SELECT amount FROM usage WHERE user_id = ? AND usage_date = ?",
        (user_id, date.today().isoformat()),
    ).fetchone()
    db.close()
    return row["amount"] if row else 0


def increase_usage(user_id, amount):
    db = get_db()
    today = date.today().isoformat()
    db.execute(
        """
        INSERT INTO usage (user_id, usage_date, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, usage_date)
        DO UPDATE SET amount = amount + excluded.amount
        """,
        (user_id, today, amount),
    )
    db.commit()
    db.close()


def generate_unique_ideas(topic, number):
    ideas = []
    used = set()
    attempts = 0
    maximum_attempts = number * 30

    while len(ideas) < number and attempts < maximum_attempts:
        hook = random.choice(HOOKS).format(topic=topic)
        content_format = random.choice(FORMATS)
        combination = (hook, content_format)
        if combination not in used:
            used.add(combination)
            ideas.append({
                "title": hook,
                "hook": hook,
                "script": f"Create a {content_format.lower()} that clearly explains {topic}.",
                "caption": f"A practical look at {topic}.",
                "hashtags": "#contentmarketing #marketingtips #socialmedia",
                "cta": "Follow for more practical marketing ideas.",
            })
        attempts += 1

    return ideas
def generate_ai_ideas(
    niche,
    platform,
    topic,
    audience,
    goal,
    tone,
    number
):
    prompt = f"""
You are an elite marketing strategist and viral content expert.

Create {number} HIGH-QUALITY content ideas.

Business niche:
{niche}

Platform:
{platform}

Topic:
{topic}

Target audience:
{audience}

Goal:
{goal}

Tone:
{tone}

The ideas must be:
- Original
- Highly engaging
- Designed to go viral
- Suitable for the chosen platform
- Written by an expert marketer
- Not generic
- Different from each other

Return ONLY in this exact format:

TITLE ||| HOOK ||| SCRIPT ||| CAPTION ||| HASHTAGS ||| CTA

Example:

How I gained my first 10,000 followers ||| Stop scrolling if you want more followers... ||| Start the video by showing your profile and explain the strategy you used. ||| Here's exactly how I grew from 0 to 10k followers. ||| #marketing #business #contentcreator ||| Follow for more marketing tips.

Return ONLY one line for each idea.
Separate every section using |||
Each idea must include TITLE, HOOK, SCRIPT, CAPTION, HASHTAGS and CTA.
Do not number anything.
Do not explain.
Return exactly {number} lines.
"""

    global client
    if client is None:
        client = OpenAI()

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    ideas = []

    for line in response.output_text.splitlines():
        line = line.strip()

        parts = [part.strip() for part in line.split("|||")]

        if len(parts) != 6:
            continue

        title, hook, script, caption, hashtags, cta = parts

        if all(parts):
            ideas.append({
                "title": title,
                "hook": hook,
                "script": script,
                "caption": caption,
                "hashtags": hashtags,
                "cta": cta,
            })

    if len(ideas) < number:
        raise ValueError("The AI did not return enough correctly formatted ideas.")

    return ideas[:number]

@app.context_processor
def inject_user():
    user = current_user()
    return {
        "current_user": user,
        "current_brand": current_brand(),
        "is_admin": bool(user and ADMIN_EMAIL and user["email"] == ADMIN_EMAIL),
        "support_email": SUPPORT_EMAIL,
        "support_contact": SUPPORT_EMAIL or "the contact form on this website",
        "email_enabled": email_configured(),
        "current_garage": current_garage(),
        "public_url": PUBLIC_URL,
    }


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or "@" not in email:
            flash("Enter a valid email address.", "danger")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return redirect(url_for("register"))

        db = get_db()
        try:
            cursor = db.execute(
                """
                INSERT INTO users (email, password_hash, plan, created_at)
                VALUES (?, ?, 'free', ?)
                """,
                (email, generate_password_hash(password), utc_now()),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.close()
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("register"))

        user_id = cursor.lastrowid
        db.execute(
            "INSERT INTO brands (user_id, name, created_at) VALUES (?, ?, ?)",
            (user_id, "My Brand", utc_now()),
        )
        db.commit()
        db.close()
        session.clear()
        session["user_id"] = user_id
        log_event("registration", user_id)

        verification_url = PUBLIC_URL + url_for(
            "verify_email", token=account_token(email, "verify")
        )
        send_account_email(
            email,
            "Verify your Elite Legacy Marketing account",
            f"Verify your email by opening this link:\n\n{verification_url}\n\n"
            "This link expires in 24 hours.",
        )
        flash("Your account has been created.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        db.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Incorrect email or password.", "danger")
            return redirect(url_for("login"))

        session.clear()
        session["user_id"] = user["id"]
        log_event("login", user["id"])
        flash("Welcome back.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    brand = current_brand()
    usage = get_today_usage(user["id"])
    remaining = None if user["plan"] == "pro" else max(FREE_DAILY_LIMIT - usage, 0)

    db = get_db()
    brand_filter = brand["id"] if brand else None
    recent_ideas = db.execute(
        """
        SELECT * FROM ideas
        WHERE user_id = ? AND (? IS NULL OR brand_id = ? OR brand_id IS NULL)
        ORDER BY id DESC
        LIMIT 8
        """,
        (user["id"], brand_filter, brand_filter),
    ).fetchall()
    total_ideas = db.execute(
        "SELECT COUNT(*) AS total FROM ideas WHERE user_id = ? "
        "AND (? IS NULL OR brand_id = ? OR brand_id IS NULL)",
        (user["id"], brand_filter, brand_filter),
    ).fetchone()["total"]
    db.close()

    return render_template(
        "dashboard.html",
        recent_ideas=recent_ideas,
        total_ideas=total_ideas,
        usage=usage,
        remaining=remaining,
        free_limit=FREE_DAILY_LIMIT,
    )


@app.route("/generate", methods=["GET", "POST"])
@login_required
def generate():
    generated = []
    user = current_user()

    if request.method == "POST":
        niche = request.form.get("niche", "").strip()
        platform = request.form.get("platform", "").strip()
        topic = request.form.get("topic", "").strip()
        audience = request.form.get("audience", "").strip()
        goal = request.form.get("goal", "").strip()
        tone = request.form.get("tone", "").strip()

        try:
            number = int(request.form.get("number", "5"))
        except ValueError:
            number = 5

        number = max(1, min(number, 20))

        if not all([niche, platform, topic, audience, goal, tone]):
            flash("Complete every field before generating ideas.", "danger")
            return redirect(url_for("generate"))

        usage = get_today_usage(user["id"])
        if user["plan"] != "pro" and usage + number > FREE_DAILY_LIMIT:
            allowed = max(FREE_DAILY_LIMIT - usage, 0)
            flash(
                f"Your free plan has {allowed} ideas remaining today. "
                "Upgrade the account to Pro for unlimited use.",
                "warning",
            )
            return redirect(url_for("pricing"))

        try:
            pairs = generate_ai_ideas(
                niche=niche,
                platform=platform,
                topic=topic,
                audience=audience,
                goal=goal,
                tone=tone,
                number=number
            )
        except Exception as error:
            print(f"AI generation failed: {error}")
            pairs = generate_unique_ideas(topic, number)
            flash(
                "AI generation was temporarily unavailable, so backup ideas were generated.",
                "warning"
            )

        db = get_db()

        for idea in pairs:
            title = idea["title"]
            hook_text = idea["hook"]
            script = idea["script"]
            caption = idea["caption"]
            hashtags = idea["hashtags"]
            cta = idea["cta"]

            content_format = f"{script}\n\nCaption: {caption}"
            platform_tip = f"Hook: {hook_text}\nHashtags: {hashtags}"

            cursor = db.execute(
                """
                INSERT INTO ideas (
                    user_id, title, niche, platform, topic, audience,
                    goal, tone, format, platform_tip, cta, created_at, brand_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"], title, niche, platform, topic, audience,
                    goal, tone, content_format, platform_tip, cta,
                    utc_now(), current_brand()["id"] if current_brand() else None,
                ),
            )

            generated.append({
                "id": cursor.lastrowid,
                "title": title,
                "format": content_format,
                "platform": platform,
                "audience": audience,
                "tone": tone,
                "goal": goal,
                "platform_tip": platform_tip,
                "cta": cta,
            })

        db.commit()
        db.close()
        increase_usage(user["id"], len(generated))
        log_event("ideas_generated", user["id"], len(generated))
        flash(f"{len(generated)} content ideas generated.", "success")

    return render_template(
        "generate.html",
        generated=generated,
        niches=NICHES,
        platforms=PLATFORMS,
        goals=GOALS,
        tones=TONES,
    )
@app.route("/calendar", methods=["GET", "POST"])
@login_required
def content_calendar():
    user = current_user()
    calendar_ideas = []

    if request.method == "POST":
        niche = request.form.get("niche", "").strip()
        platform = request.form.get("platform", "").strip()
        topic = request.form.get("topic", "").strip()
        audience = request.form.get("audience", "").strip()
        goal = request.form.get("goal", "").strip()
        tone = request.form.get("tone", "").strip()

        if not all([niche, platform, topic, audience, goal, tone]):
            flash("Please complete every calendar field.", "danger")
            return redirect(url_for("content_calendar"))

        # Keep the 30-day generator as a paid feature.
        if user["plan"] != "pro":
            flash(
                "The 30-day content calendar is available on the Pro plan.",
                "warning"
            )
            return redirect(url_for("pricing"))

        try:
            calendar_ideas = generate_ai_ideas(
                niche=niche,
                platform=platform,
                topic=topic,
                audience=audience,
                goal=goal,
                tone=tone,
                number=30
            )
        except Exception as error:
            print(f"Calendar generation failed: {error}")
            flash(
                "The AI could not generate your calendar. Please try again.",
                "danger"
            )
            return redirect(url_for("content_calendar"))

        db = get_db()
        saved_ideas = []

        for day_number, idea in enumerate(calendar_ideas, start=1):
            title = idea["title"]
            hook_text = idea["hook"]
            script = idea["script"]
            caption = idea["caption"]
            hashtags = idea["hashtags"]
            cta = idea["cta"]

            content_format = f"{script}\n\nCaption: {caption}"
            platform_tip = (
                f"Day: {day_number}\n"
                f"Hook: {hook_text}\n"
                f"Hashtags: {hashtags}"
            )

            cursor = db.execute(
                """
                INSERT INTO ideas (
                    user_id, title, niche, platform, topic, audience,
                    goal, tone, format, platform_tip, cta, created_at, brand_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    title,
                    niche,
                    platform,
                    topic,
                    audience,
                    goal,
                    tone,
                    content_format,
                    platform_tip,
                    cta,
                    utc_now(),
                    current_brand()["id"] if current_brand() else None,
                ),
            )

            saved_ideas.append({
                "id": cursor.lastrowid,
                "day": day_number,
                "title": title,
                "platform": platform,
                "audience": audience,
                "goal": goal,
                "cta": cta,
            })

        db.commit()
        db.close()

        flash("Your 30-day AI content calendar is ready.", "success")

        return render_template(
            "content_calendar.html",
            ideas=saved_ideas
        )

    return render_template(
        "content_calendar.html",
        ideas=[]
    )
@app.route("/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    user = current_user()
    service_slug = request.form.get("service", "marketing-pro")
    if service_slug == "marketing-pro":
        price_id = STRIPE_PRICE_ID
        service_name = "Pro Creator"
    elif service_slug in SERVICES:
        price_id = STRIPE_SERVICE_PRICE_IDS.get(service_slug)
        service_name = SERVICES[service_slug]["name"]
    else:
        abort(400)

    if not stripe.api_key or not price_id:
        app.logger.error("Stripe secret key or price ID is missing")
        flash(
            f"Online checkout for {service_name} is being prepared. Send your setup request and we will contact you.",
            "warning",
        )
        if service_slug in SERVICES:
            return redirect(url_for("service_page", service_slug=service_slug) + "#get-started")
        return redirect(url_for("pricing"))

    if service_slug == "marketing-pro" and user["plan"] == "pro" and user["stripe_customer_id"]:
        return redirect(url_for("create_billing_portal"))

    try:
        checkout_options = dict(
            mode="subscription",
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            success_url=url_for(
                "checkout_success",
                _external=True,
            ) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for(
                "pricing",
                _external=True,
            ),
            metadata={
                "user_id": str(user["id"]),
                "service": service_slug,
            },
            subscription_data={
                "metadata": {"user_id": str(user["id"]), "service": service_slug},
            },
            allow_promotion_codes=True,
        )

        if user["stripe_customer_id"]:
            checkout_options["customer"] = user["stripe_customer_id"]
        else:
            checkout_options["customer_email"] = user["email"]

        checkout_session = stripe.checkout.Session.create(**checkout_options)

        return redirect(checkout_session.url, code=303)

    except Exception as error:
        app.logger.exception("Stripe Checkout failed: %s", error)
        flash(
            "Stripe Checkout could not be opened. Please try again.",
            "danger",
        )
        return redirect(url_for("pricing"))


@app.route("/checkout-success")
@login_required
def checkout_success():
    session_id = request.args.get("session_id")
    redirect_endpoint = "dashboard"

    if not session_id:
        flash("Stripe session could not be found.", "danger")
        return redirect(url_for("pricing"))

    try:
        checkout_session = stripe_value(
            stripe.checkout.Session.retrieve(session_id)
        )
        checkout_user_id = (checkout_session.get("metadata") or {}).get("user_id")

        if checkout_user_id != str(session["user_id"]):
            app.logger.warning("Checkout session did not belong to logged-in user")
            flash("That payment session could not be verified.", "danger")
            return redirect(url_for("pricing"))

        if checkout_session.get("payment_status") == "paid":
            db = get_db()
            service_slug = (checkout_session.get("metadata") or {}).get("service", "marketing-pro")
            subscription_id = checkout_session.get("subscription")
            if isinstance(subscription_id, dict):
                subscription_id = subscription_id.get("id")
            if service_slug in SERVICES:
                sync_service_subscription(
                    db,
                    service_slug,
                    user_id=session["user_id"],
                    customer_id=checkout_session.get("customer"),
                    subscription_id=subscription_id,
                )
                if service_slug == "garage-ai-receptionist":
                    success_message = "Payment completed. Your private garage workspace is ready for onboarding."
                    redirect_endpoint = "garage_settings"
                else:
                    success_message = f"Payment completed. We will contact you to configure {SERVICES[service_slug]['name']}."
            else:
                subscription = stripe.Subscription.retrieve(subscription_id)
                sync_subscription(db, subscription, user_id=session["user_id"])
                success_message = "Payment completed. Your Pro account is now active!"
            db.commit()
            db.close()
            flash(success_message, "success")
        else:
            flash("Your payment is still processing.", "warning")

    except Exception as error:
        app.logger.exception("Unable to verify Checkout session: %s", error)
        flash(
            "Payment received. Your account will update automatically shortly.",
            "warning",
        )

    return redirect(url_for(redirect_endpoint))

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    signature = request.headers.get("Stripe-Signature")

    if not STRIPE_WEBHOOK_SECRET:
        app.logger.error("STRIPE_WEBHOOK_SECRET is missing")
        return "Webhook is not configured", 503

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        return "Invalid payload", 400
    except stripe.SignatureVerificationError:
        return "Invalid signature", 400

    event = stripe_value(event)
    event_id = event.get("id")
    event_type = event.get("type")
    stripe_object = stripe_value(event["data"]["object"])
    db = get_db()

    if db.execute(
        "SELECT 1 FROM stripe_events WHERE event_id = ?", (event_id,)
    ).fetchone():
        db.close()
        return "", 200

    try:
        if event_type == "checkout.session.completed":
            metadata = stripe_object.get("metadata") or {}
            user_id = metadata.get("user_id")
            service_slug = metadata.get("service", "marketing-pro")
            if stripe_object.get("payment_status") == "paid" and user_id:
                if service_slug in SERVICES:
                    sync_service_subscription(
                        db, service_slug, user_id=user_id,
                        customer_id=stripe_object.get("customer"),
                        subscription_id=stripe_object.get("subscription"),
                    )
                else:
                    update_subscription_user(
                        db,
                        user_id=user_id,
                        customer_id=stripe_object.get("customer"),
                        subscription_id=stripe_object.get("subscription"),
                        status="active",
                        plan="pro",
                    )

        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            metadata = stripe_object.get("metadata") or {}
            service_slug = metadata.get("service", "marketing-pro")
            if service_slug in SERVICES:
                sync_service_subscription(
                    db, service_slug, user_id=metadata.get("user_id"),
                    customer_id=stripe_object.get("customer"),
                    subscription_id=stripe_object.get("id"),
                    status=stripe_object.get("status", "none"),
                )
            else:
                sync_subscription(db, stripe_object)

        elif event_type == "invoice.paid":
            subscription_id = subscription_id_from_invoice(stripe_object)
            if subscription_id:
                update_subscription_user(
                    db,
                    customer_id=stripe_object.get("customer"),
                    subscription_id=subscription_id,
                    status="active",
                    plan="pro",
                )

        elif event_type == "invoice.payment_failed":
            # Stripe may retry a failed renewal, so record the state while
            # subscription.updated decides when access should be removed.
            update_subscription_user(
                db,
                customer_id=stripe_object.get("customer"),
                subscription_id=subscription_id_from_invoice(stripe_object),
                status="past_due",
            )

        db.execute(
            "INSERT INTO stripe_events (event_id, event_type, processed_at) "
            "VALUES (?, ?, ?)",
            (event_id, event_type, utc_now()),
        )
        db.commit()
    except Exception:
        db.rollback()
        app.logger.exception("Failed to process Stripe event %s", event_id)
        return "Webhook processing failed", 500
    finally:
        db.close()

    return "", 200


@app.route("/billing-portal", methods=["POST", "GET"])
@login_required
def create_billing_portal():
    user = current_user()
    if not user["stripe_customer_id"]:
        flash("No Stripe subscription was found for this account.", "warning")
        return redirect(url_for("pricing"))

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=user["stripe_customer_id"],
            return_url=url_for("dashboard", _external=True),
        )
        return redirect(portal_session.url, code=303)
    except Exception as error:
        app.logger.exception("Stripe billing portal failed: %s", error)
        flash("Billing management is temporarily unavailable.", "danger")
        return redirect(url_for("dashboard"))


@app.route("/library")
@login_required
def library():
    brand = current_brand()
    brand_id = brand["id"] if brand else None
    db = get_db()
    ideas = db.execute(
        """
        SELECT * FROM ideas
        WHERE user_id = ? AND (? IS NULL OR brand_id = ? OR brand_id IS NULL)
        ORDER BY id DESC
        """,
        (session["user_id"], brand_id, brand_id),
    ).fetchall()
    db.close()
    return render_template("library.html", ideas=ideas)


@app.route("/idea/<int:idea_id>/delete", methods=["POST"])
@login_required
def delete_idea(idea_id):
    db = get_db()
    db.execute(
        "DELETE FROM ideas WHERE id = ? AND user_id = ?",
        (idea_id, session["user_id"]),
    )
    db.commit()
    db.close()
    flash("Idea deleted.", "success")
    return redirect(request.referrer or url_for("library"))


@app.route("/export/txt")
@login_required
def export_txt():
    if current_user()["plan"] != "pro":
        flash("Exports are available on the Pro plan.", "warning")
        return redirect(url_for("pricing"))
    brand = current_brand()
    brand_id = brand["id"] if brand else None
    db = get_db()
    ideas = db.execute(
        "SELECT * FROM ideas WHERE user_id = ? "
        "AND (? IS NULL OR brand_id = ? OR brand_id IS NULL) ORDER BY id DESC",
        (session["user_id"], brand_id, brand_id),
    ).fetchall()
    db.close()

    output = io.StringIO()
    output.write("ELITE LEGACY MARKETING CONTENT LIBRARY\n")
    output.write("=" * 50 + "\n\n")

    for index, idea in enumerate(ideas, start=1):
        output.write(f"{index}. {idea['title']}\n")
        output.write(f"Platform: {idea['platform']}\n")
        output.write(f"Format: {idea['format']}\n")
        output.write(f"Audience: {idea['audience']}\n")
        output.write(f"Tone: {idea['tone']}\n")
        output.write(f"Goal: {idea['goal']}\n")
        output.write(f"Platform tip: {idea['platform_tip']}\n")
        output.write(f"Call to action: {idea['cta']}\n\n")

    buffer = io.BytesIO(output.getvalue().encode("utf-8"))
    return send_file(
        buffer,
        as_attachment=True,
        download_name="elite_legacy_content_ideas.txt",
        mimetype="text/plain",
    )


@app.route("/export/csv")
@login_required
def export_csv():
    if current_user()["plan"] != "pro":
        flash("Exports are available on the Pro plan.", "warning")
        return redirect(url_for("pricing"))
    brand = current_brand()
    brand_id = brand["id"] if brand else None
    db = get_db()
    ideas = db.execute(
        "SELECT * FROM ideas WHERE user_id = ? "
        "AND (? IS NULL OR brand_id = ? OR brand_id IS NULL) ORDER BY id DESC",
        (session["user_id"], brand_id, brand_id),
    ).fetchall()
    db.close()

    text_buffer = io.StringIO()
    writer = csv.writer(text_buffer)
    writer.writerow([
        "Title", "Niche", "Platform", "Topic", "Audience",
        "Goal", "Tone", "Format", "Platform Tip", "CTA", "Created"
    ])

    for idea in ideas:
        writer.writerow([
            idea["title"], idea["niche"], idea["platform"], idea["topic"],
            idea["audience"], idea["goal"], idea["tone"], idea["format"],
            idea["platform_tip"], idea["cta"], idea["created_at"]
        ])

    buffer = io.BytesIO(text_buffer.getvalue().encode("utf-8-sig"))
    return send_file(
        buffer,
        as_attachment=True,
        download_name="elite_legacy_content_ideas.csv",
        mimetype="text/csv",
    )


@app.route("/pricing")
def pricing():
    return render_template("pricing.html", services=SERVICES)


@app.route("/services/<service_slug>", methods=["GET", "POST"])
def service_page(service_slug):
    service = SERVICES.get(service_slug)
    if not service:
        abort(404)

    if request.method == "POST":
        if service_slug == "garage-ai-receptionist" and not session.get("user_id"):
            flash("Create or sign in to your account before requesting a garage workspace.", "warning")
            return redirect(url_for("register"))
        business_name = request.form.get("business_name", "").strip()[:120]
        contact_name = request.form.get("contact_name", "").strip()[:120]
        email = request.form.get("email", "").strip().lower()[:200]
        phone = request.form.get("phone", "").strip()[:50]
        contact_line = request.form.get("contact_line", "").strip()[:80]
        setup_notes = request.form.get("setup_notes", "").strip()[:2000]
        if not business_name or not contact_name or "@" not in email:
            flash("Enter your business name, contact name and a valid email.", "danger")
            return redirect(url_for("service_page", service_slug=service_slug) + "#get-started")
        db = get_db()
        db.execute(
            "INSERT INTO service_requests "
            "(user_id, service_slug, business_name, contact_name, email, phone, contact_line, setup_notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session.get("user_id"), service_slug, business_name, contact_name,
             email, phone, contact_line, setup_notes, utc_now()),
        )
        db.commit()
        db.close()
        log_event("service_request", session.get("user_id"), service_slug)
        flash(f"Your {service['name']} setup request has been received.", "success")
        return redirect(url_for("service_page", service_slug=service_slug))

    return render_template("service.html", service=service, service_slug=service_slug)


@app.route("/telnyx/tools/garage-booking", methods=["POST"])
@app.route("/telnyx/tools/garage-booking/<webhook_key>", methods=["POST"])
def telnyx_garage_booking_tool(webhook_key=None):
    """Receive structured booking details collected by the Telnyx assistant."""
    raw_body = request.get_data(cache=True)
    if not verify_telnyx_request(raw_body):
        return jsonify({"error": "Invalid Telnyx signature"}), 401

    data = request.get_json(silent=True) or {}
    db = get_db()
    if webhook_key:
        garage = db.execute(
            "SELECT * FROM garage_accounts WHERE webhook_key=? AND status IN ('setup', 'active')",
            (webhook_key,),
        ).fetchone()
    else:
        garage = db.execute(
            "SELECT * FROM garage_accounts WHERE telnyx_assistant_id=? ORDER BY id LIMIT 1",
            (TELNYX_ASSISTANT_ID,),
        ).fetchone()
    if not garage:
        db.close()
        return jsonify({"error": "Garage workspace not found"}), 404
    conversation_id = str(
        data.get("conversation_id")
        or data.get("telnyx_conversation_id")
        or request.headers.get("x-telnyx-call-control-id", "")
        or request.headers.get("x-telnyx-conversation-id", "")
    ).strip()[:160]
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400

    fields = {
        "customer_name": 120,
        "customer_phone": 50,
        "customer_email": 200,
        "vehicle_registration": 30,
        "vehicle_make_model": 120,
        "vehicle_year": 10,
        "request_type": 80,
        "problem_description": 1000,
        "preferred_date": 40,
        "preferred_time": 40,
        "safe_to_drive": 30,
        "additional_notes": 1500,
    }
    values = {
        name: str(data.get(name, "") or "").strip()[:limit]
        for name, limit in fields.items()
    }
    now = utc_now()
    db.execute(
        """
        INSERT INTO garage_calls (
            conversation_id, garage_id, assistant_id, customer_name, customer_phone,
            customer_email, vehicle_registration, vehicle_make_model, vehicle_year,
            request_type, problem_description, preferred_date, preferred_time,
            safe_to_drive, additional_notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(conversation_id) DO UPDATE SET
            garage_id=excluded.garage_id,
            customer_name=excluded.customer_name,
            customer_phone=excluded.customer_phone,
            customer_email=excluded.customer_email,
            vehicle_registration=excluded.vehicle_registration,
            vehicle_make_model=excluded.vehicle_make_model,
            vehicle_year=excluded.vehicle_year,
            request_type=excluded.request_type,
            problem_description=excluded.problem_description,
            preferred_date=excluded.preferred_date,
            preferred_time=excluded.preferred_time,
            safe_to_drive=excluded.safe_to_drive,
            additional_notes=excluded.additional_notes,
            updated_at=excluded.updated_at
        """,
        (
            conversation_id, garage["id"], garage["telnyx_assistant_id"] or TELNYX_ASSISTANT_ID, values["customer_name"],
            values["customer_phone"], values["customer_email"],
            values["vehicle_registration"], values["vehicle_make_model"],
            values["vehicle_year"], values["request_type"],
            values["problem_description"], values["preferred_date"],
            values["preferred_time"], values["safe_to_drive"],
            values["additional_notes"], now, now,
        ),
    )
    db.commit()
    db.close()
    return jsonify({
        "success": True,
        "message": "The booking request has been saved for the garage team to review."
    })


@app.route("/telnyx/webhooks", methods=["POST"])
def telnyx_webhooks():
    """Record signed, idempotent Telnyx call lifecycle events."""
    raw_body = request.get_data(cache=True)
    if not verify_telnyx_request(raw_body):
        return jsonify({"error": "Invalid Telnyx signature"}), 401
    body = request.get_json(silent=True) or {}
    event = body.get("data") or {}
    payload = event.get("payload") or {}
    event_id = str(event.get("id", "")).strip()
    event_type = str(event.get("event_type", "")).strip()
    if not event_id or not event_type:
        return jsonify({"error": "Invalid event envelope"}), 400

    assistant_id = str(payload.get("assistant_id", ""))
    db = get_db()
    garage = db.execute(
        "SELECT * FROM garage_accounts WHERE telnyx_assistant_id=?",
        (assistant_id,),
    ).fetchone() if assistant_id else None
    if not garage:
        db.close()
        return jsonify({"received": True, "ignored": True})

    conversation_id = str(payload.get("conversation_id", "")).strip()[:160]
    inserted = db.execute(
        "INSERT OR IGNORE INTO telnyx_events (event_id, event_type, conversation_id, received_at) "
        "VALUES (?, ?, ?, ?)",
        (event_id, event_type, conversation_id, utc_now()),
    ).rowcount
    if inserted and event_type == "call.conversation.ended" and conversation_id:
        now = utc_now()
        db.execute(
            """
            INSERT INTO garage_calls (
                conversation_id, garage_id, assistant_id, caller_number, called_number,
                call_status, call_reason, duration_seconds, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                garage_id=excluded.garage_id,
                assistant_id=excluded.assistant_id,
                caller_number=excluded.caller_number,
                called_number=excluded.called_number,
                call_status='completed',
                call_reason=excluded.call_reason,
                duration_seconds=excluded.duration_seconds,
                updated_at=excluded.updated_at
            """,
            (
                conversation_id, garage["id"], assistant_id, str(payload.get("from", ""))[:50],
                str(payload.get("to", ""))[:120], str(payload.get("reason", ""))[:80],
                payload.get("duration_sec"), now, now,
            ),
        )
    db.commit()
    db.close()
    return jsonify({"received": True, "duplicate": not bool(inserted)})


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user = current_user()
    if request.method == "POST":
        action = request.form.get("action")
        db = get_db()
        if action == "profile":
            display_name = request.form.get("display_name", "").strip()[:80]
            db.execute(
                "UPDATE users SET display_name=? WHERE id=?",
                (display_name, user["id"]),
            )
            db.commit()
            flash("Profile updated.", "success")
        elif action == "password":
            old_password = request.form.get("old_password", "")
            new_password = request.form.get("new_password", "")
            stored = db.execute(
                "SELECT password_hash FROM users WHERE id=?", (user["id"],)
            ).fetchone()
            if not check_password_hash(stored["password_hash"], old_password):
                flash("Current password is incorrect.", "danger")
            elif len(new_password) < 8:
                flash("New password must contain at least 8 characters.", "danger")
            else:
                db.execute(
                    "UPDATE users SET password_hash=? WHERE id=?",
                    (generate_password_hash(new_password), user["id"]),
                )
                db.commit()
                flash("Password changed.", "success")
        db.close()
        return redirect(url_for("account"))
    return render_template("account.html", user=user)


@app.route("/claim-admin/<token>", methods=["GET", "POST"])
def claim_admin(token):
    supplied_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(supplied_hash, ADMIN_CLAIM_TOKEN_HASH):
        abort(404)
    db = get_db()
    user = db.execute(
        "SELECT id, email_verified FROM users WHERE email=?", (ADMIN_EMAIL,)
    ).fetchone()
    if not user:
        db.close()
        abort(404)
    if user["email_verified"]:
        db.close()
        return "This one-time account claim link has already been used.", 410
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < 8:
            db.close()
            flash("Password must contain at least 8 characters.", "danger")
            return redirect(url_for("claim_admin", token=token))
        db.execute(
            "UPDATE users SET password_hash=?, email_verified=1, plan='pro' WHERE id=?",
            (generate_password_hash(password), user["id"]),
        )
        db.commit()
        db.close()
        session.clear()
        session["user_id"] = user["id"]
        flash("Your administrator account is ready.", "success")
        return redirect(url_for("dashboard"))
    db.close()
    return render_template("claim_admin.html")


@app.route("/verify-email/<token>")
def verify_email(token):
    try:
        email = read_account_token(token, "verify", 86400)
    except (BadSignature, SignatureExpired):
        flash("That verification link is invalid or expired.", "danger")
        return redirect(url_for("login"))
    db = get_db()
    db.execute("UPDATE users SET email_verified=1 WHERE email=?", (email,))
    db.commit()
    db.close()
    flash("Email verified successfully.", "success")
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))


@app.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    user = current_user()
    link = PUBLIC_URL + url_for(
        "verify_email", token=account_token(user["email"], "verify")
    )
    sent = send_account_email(
        user["email"],
        "Verify your Elite Legacy Marketing account",
        f"Verify your email:\n\n{link}\n\nThis link expires in 24 hours.",
    )
    flash(
        "Verification email sent." if sent else
        "Email delivery is not configured yet. Please contact support.",
        "success" if sent else "warning",
    )
    return redirect(url_for("account"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        db = get_db()
        exists = db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
        db.close()
        if exists:
            link = PUBLIC_URL + url_for(
                "reset_password", token=account_token(email, "reset")
            )
            send_account_email(
                email,
                "Reset your Elite Legacy Marketing password",
                f"Reset your password:\n\n{link}\n\nThis link expires in one hour.",
            )
        flash("If that account exists, a reset email has been sent.", "success")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = read_account_token(token, "reset", 3600)
    except (BadSignature, SignatureExpired):
        flash("That reset link is invalid or expired.", "danger")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
        else:
            db = get_db()
            db.execute(
                "UPDATE users SET password_hash=? WHERE email=?",
                (generate_password_hash(password), email),
            )
            db.commit()
            db.close()
            flash("Password reset. You can now log in.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.route("/brands", methods=["GET", "POST"])
@login_required
def brands():
    user = current_user()
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        brand_count = db.execute(
            "SELECT COUNT(*) AS total FROM brands WHERE user_id=?", (user["id"],)
        ).fetchone()["total"]
        if user["plan"] != "pro" and brand_count >= 1:
            db.close()
            flash("Multiple client workspaces require Pro.", "warning")
            return redirect(url_for("pricing"))
        if not name:
            flash("Enter a brand name.", "danger")
        else:
            cursor = db.execute(
                "INSERT INTO brands (user_id, name, niche, audience, voice, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"], name, request.form.get("niche", "")[:120],
                 request.form.get("audience", "")[:200],
                 request.form.get("voice", "")[:200], utc_now()),
            )
            db.commit()
            session["brand_id"] = cursor.lastrowid
            flash("Brand workspace created.", "success")
        db.close()
        return redirect(url_for("brands"))
    all_brands = db.execute(
        "SELECT * FROM brands WHERE user_id=? ORDER BY id", (user["id"],)
    ).fetchall()
    db.close()
    return render_template("brands.html", brands=all_brands)


@app.route("/brands/<int:brand_id>/select", methods=["POST"])
@login_required
def select_brand(brand_id):
    db = get_db()
    brand = db.execute(
        "SELECT id FROM brands WHERE id=? AND user_id=?",
        (brand_id, session["user_id"]),
    ).fetchone()
    db.close()
    if not brand:
        abort(404)
    session["brand_id"] = brand_id
    flash("Workspace switched.", "success")
    return redirect(request.referrer or url_for("dashboard"))


def run_marketing_tool(tool_name, content, brand):
    global client
    if client is None:
        client = OpenAI()
    context = ""
    if brand:
        context = (
            f"Brand: {brand['name']}\nNiche: {brand['niche']}\n"
            f"Audience: {brand['audience']}\nVoice: {brand['voice']}\n"
        )
    instructions = {
        "rewrite": "Rewrite the supplied content into three stronger versions. Label each version and preserve the facts.",
        "hashtags": "Create 20 relevant hashtags grouped into broad, niche, and local/discovery groups. Avoid spammy tags.",
        "campaign": "Create a practical marketing campaign with objective, audience, message, channels, seven-day action plan, KPIs, and CTA.",
    }
    response = client.responses.create(
        model="gpt-5-mini",
        input=f"You are an expert UK marketing strategist.\n{context}\nTask: {instructions[tool_name]}\n\nInput:\n{content}",
    )
    return response.output_text.strip()


@app.route("/tools", methods=["GET", "POST"])
@login_required
def marketing_tools():
    user = current_user()
    result = ""
    selected_tool = request.form.get("tool", "rewrite")
    if request.method == "POST":
        if user["plan"] != "pro":
            flash("Advanced AI tools require Pro.", "warning")
            return redirect(url_for("pricing"))
        content = request.form.get("content", "").strip()
        if selected_tool not in {"rewrite", "hashtags", "campaign"} or not content:
            flash("Choose a tool and enter some content.", "danger")
        else:
            try:
                result = run_marketing_tool(selected_tool, content, current_brand())
                log_event(f"tool_{selected_tool}", user["id"])
            except Exception as error:
                app.logger.exception("Marketing tool failed: %s", error)
                flash("The AI tool is temporarily unavailable.", "danger")
    return render_template("tools.html", result=result, selected_tool=selected_tool)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:100]
        email = request.form.get("email", "").strip().lower()[:200]
        message = request.form.get("message", "").strip()[:3000]
        if not name or "@" not in email or not message:
            flash("Complete every contact field.", "danger")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO contact_messages (name, email, message, created_at) "
                "VALUES (?, ?, ?, ?)", (name, email, message, utc_now())
            )
            db.commit()
            db.close()
            flash("Message received. We will respond as soon as possible.", "success")
            return redirect(url_for("contact"))
    return render_template("contact.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/refund-policy")
def refund_policy():
    return render_template("refund_policy.html")


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        "users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "pro_users": db.execute("SELECT COUNT(*) FROM users WHERE plan='pro'").fetchone()[0],
        "ideas": db.execute("SELECT COUNT(*) FROM ideas").fetchone()[0],
        "brands": db.execute("SELECT COUNT(*) FROM brands").fetchone()[0],
        "messages": db.execute("SELECT COUNT(*) FROM contact_messages").fetchone()[0],
        "service_requests": db.execute("SELECT COUNT(*) FROM service_requests").fetchone()[0],
        "garages": db.execute("SELECT COUNT(*) FROM garage_accounts").fetchone()[0],
    }
    users = db.execute(
        "SELECT id, email, display_name, plan, subscription_status, email_verified, created_at "
        "FROM users ORDER BY id DESC LIMIT 100"
    ).fetchall()
    events = db.execute(
        "SELECT event_name, COUNT(*) AS total FROM analytics_events "
        "GROUP BY event_name ORDER BY total DESC"
    ).fetchall()
    messages = db.execute(
        "SELECT * FROM contact_messages ORDER BY id DESC LIMIT 20"
    ).fetchall()
    service_requests = db.execute(
        "SELECT * FROM service_requests ORDER BY id DESC LIMIT 50"
    ).fetchall()
    garages = db.execute(
        "SELECT g.*, u.email AS user_email FROM garage_accounts g JOIN users u ON u.id=g.user_id ORDER BY g.id DESC"
    ).fetchall()
    db.close()
    return render_template(
        "admin.html", stats=stats, users=users, events=events, messages=messages,
        service_requests=service_requests, garages=garages,
    )


@app.route("/admin/garages/<int:garage_id>/connection", methods=["POST"])
@login_required
@admin_required
def update_garage_connection(garage_id):
    assistant_id = request.form.get("telnyx_assistant_id", "").strip()[:160] or None
    status = request.form.get("status", "setup")
    if status not in {"setup", "active", "paused", "cancelled"}:
        abort(400)
    db = get_db()
    try:
        result = db.execute(
            "UPDATE garage_accounts SET telnyx_assistant_id=?, status=?, updated_at=? WHERE id=?",
            (assistant_id, status, utc_now(), garage_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        flash("That Telnyx assistant is already assigned to another garage.", "danger")
        return redirect(url_for("admin_dashboard"))
    db.close()
    if not result.rowcount:
        abort(404)
    flash("Garage connection updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/garage-dashboard")
@login_required
def garage_dashboard():
    user = current_user()
    is_admin_user = bool(ADMIN_EMAIL and user["email"] == ADMIN_EMAIL)
    db = get_db()
    garage = db.execute(
        "SELECT * FROM garage_accounts WHERE user_id=? ORDER BY id LIMIT 1",
        (user["id"],),
    ).fetchone()
    if not garage and not is_admin_user:
        db.close()
        abort(403)
    garage_id = garage["id"] if garage else None
    calls = db.execute(
        "SELECT * FROM garage_calls WHERE (? IS NULL OR garage_id=?) ORDER BY updated_at DESC LIMIT 100",
        (garage_id, garage_id),
    ).fetchall()
    stats = {
        "total_calls": db.execute(
            "SELECT COUNT(*) FROM garage_calls WHERE (? IS NULL OR garage_id=?)",
            (garage_id, garage_id),
        ).fetchone()[0],
        "booking_requests": db.execute(
            "SELECT COUNT(*) FROM garage_calls WHERE request_type != '' AND (? IS NULL OR garage_id=?)",
            (garage_id, garage_id),
        ).fetchone()[0],
        "needs_follow_up": db.execute(
            "SELECT COUNT(*) FROM garage_calls WHERE customer_phone != '' "
            "AND call_status != 'resolved' AND (? IS NULL OR garage_id=?)",
            (garage_id, garage_id),
        ).fetchone()[0],
    }
    db.close()
    return render_template("garage_dashboard.html", calls=calls, stats=stats, garage=garage)


@app.route("/garage-settings", methods=["GET", "POST"])
@login_required
def garage_settings():
    garage = current_garage()
    if not garage:
        abort(403)
    if request.method == "POST":
        fields = {
            "business_name": 120, "contact_name": 120, "contact_phone": 50,
            "business_line": 80, "opening_hours": 1000, "services_offered": 2000,
            "booking_rules": 2000, "escalation_rules": 2000,
        }
        values = {name: request.form.get(name, "").strip()[:limit] for name, limit in fields.items()}
        db = get_db()
        db.execute(
            "UPDATE garage_accounts SET business_name=?, contact_name=?, contact_phone=?, business_line=?, "
            "opening_hours=?, services_offered=?, booking_rules=?, escalation_rules=?, updated_at=? WHERE id=? AND user_id=?",
            (*values.values(), utc_now(), garage["id"], session["user_id"]),
        )
        db.commit()
        db.close()
        flash("Garage settings updated.", "success")
        return redirect(url_for("garage_settings"))
    db = get_db()
    subscription = db.execute(
        "SELECT status FROM service_subscriptions WHERE user_id=? AND service_slug='garage-ai-receptionist'",
        (session["user_id"],),
    ).fetchone()
    db.close()
    readiness = {
        "subscription": bool(subscription and subscription["status"] in {"active", "trialing", "complimentary"}),
        "business_profile": bool(garage["business_name"] and garage["opening_hours"] and garage["services_offered"]),
        "booking_rules": bool(garage["booking_rules"]),
        "phone_connection": bool(garage["telnyx_assistant_id"]),
        "activated": garage["status"] == "active",
    }
    return render_template("garage_settings.html", garage=garage, readiness=readiness)


@app.route("/garage-calls/<int:call_id>/status", methods=["POST"])
@login_required
def update_garage_call_status(call_id):
    status = request.form.get("status", "")
    if status not in {"details_collected", "contacted", "booked", "resolved"}:
        abort(400)
    user = current_user()
    garage = current_garage()
    is_admin_user = bool(ADMIN_EMAIL and user["email"] == ADMIN_EMAIL)
    if not garage and not is_admin_user:
        abort(403)
    db = get_db()
    if is_admin_user and not garage:
        result = db.execute("UPDATE garage_calls SET call_status=?, updated_at=? WHERE id=?", (status, utc_now(), call_id))
    else:
        result = db.execute(
            "UPDATE garage_calls SET call_status=?, updated_at=? WHERE id=? AND garage_id=?",
            (status, utc_now(), call_id, garage["id"]),
        )
    db.commit()
    db.close()
    if not result.rowcount:
        abort(404)
    flash("Call status updated.", "success")
    return redirect(url_for("garage_dashboard"))


@app.route("/admin/service-requests/<int:request_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_service_request(request_id):
    db = get_db()
    setup_request = db.execute(
        "SELECT * FROM service_requests WHERE id=? AND service_slug='garage-ai-receptionist'",
        (request_id,),
    ).fetchone()
    if not setup_request:
        db.close()
        abort(404)
    if not setup_request["user_id"]:
        db.close()
        flash("This customer must create an account using the same email before approval.", "warning")
        return redirect(url_for("admin_dashboard"))
    assistant_id = request.form.get("telnyx_assistant_id", "").strip()[:160] or None
    now = utc_now()
    db.execute(
        "INSERT INTO garage_accounts (user_id, service_request_id, business_name, contact_name, contact_email, "
        "contact_phone, business_line, telnyx_assistant_id, webhook_key, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'setup', ?, ?) "
        "ON CONFLICT(user_id) DO NOTHING",
        (setup_request["user_id"], request_id, setup_request["business_name"], setup_request["contact_name"],
         setup_request["email"], setup_request["phone"], setup_request["contact_line"], assistant_id,
         secrets.token_urlsafe(24), now, now),
    )
    db.execute("UPDATE service_requests SET status='approved' WHERE id=?", (request_id,))
    db.commit()
    db.close()
    flash("Garage workspace approved and created.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/upgrade-demo", methods=["POST"])
@login_required
def upgrade_demo():
    flash(
        "Payment processing is not connected yet. "
        "The owner can activate Pro accounts from the command line.",
        "warning",
    )
    return redirect(url_for("pricing"))


@app.cli.command("make-pro")
def make_pro():
    email = input("Customer email: ").strip().lower()
    db = get_db()
    result = db.execute(
        "UPDATE users SET plan = 'pro' WHERE email = ?",
        (email,),
    )
    db.commit()
    db.close()

    if result.rowcount:
        print(f"{email} is now on the Pro plan.")
    else:
        print("No account was found with that email.")


@app.cli.command("make-free")
def make_free():
    email = input("Customer email: ").strip().lower()
    db = get_db()
    result = db.execute(
        "UPDATE users SET plan = 'free' WHERE email = ?",
        (email,),
    )
    db.commit()
    db.close()

    if result.rowcount:
        print(f"{email} is now on the Free plan.")
    else:
        print("No account was found with that email.")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
