import csv
import io
import os
import stripe
from dotenv import load_dotenv
from openai import OpenAI
import random
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask, flash, redirect, render_template, request,
    send_file, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
client = OpenAI()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
DATABASE = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "ideaforge.db"),
)

FREE_DAILY_LIMIT = 10

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
        """
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
        "SELECT id, email, plan, created_at FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    db.close()
    return user


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
            ideas.append((hook, content_format))
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
    return {"current_user": current_user()}


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
                (email, generate_password_hash(password), datetime.utcnow().isoformat()),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.close()
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("register"))

        user_id = cursor.lastrowid
        db.close()
        session.clear()
        session["user_id"] = user_id
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
    usage = get_today_usage(user["id"])
    remaining = None if user["plan"] == "pro" else max(FREE_DAILY_LIMIT - usage, 0)

    db = get_db()
    recent_ideas = db.execute(
        """
        SELECT * FROM ideas
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 8
        """,
        (user["id"],),
    ).fetchall()
    total_ideas = db.execute(
        "SELECT COUNT(*) AS total FROM ideas WHERE user_id = ?",
        (user["id"],),
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
                    goal, tone, format, platform_tip, cta, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"], title, niche, platform, topic, audience,
                    goal, tone, content_format, platform_tip, cta,
                    datetime.utcnow().isoformat(),
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
                    goal, tone, format, platform_tip, cta, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    datetime.utcnow().isoformat(),
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

    try:
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price": STRIPE_PRICE_ID,
                    "quantity": 1,
                }
            ],
            customer_email=user["email"],
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
            },
        )

        return redirect(checkout_session.url, code=303)

    except Exception as error:
        print(f"Stripe Checkout error: {error}")
        flash(
            "Stripe Checkout could not be opened. Please try again.",
            "danger",
        )
        return redirect(url_for("pricing"))


@app.route("/checkout-success")
@login_required
def checkout_success():
    session_id = request.args.get("session_id")

    if not session_id:
        flash("Stripe session could not be found.", "danger")
        return redirect(url_for("pricing"))

    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)

        if checkout_session.payment_status == "paid":
            db = get_db()

            db.execute(
                "UPDATE users SET plan='pro' WHERE id=?",
                (session["user_id"],)
            )

            db.commit()
            db.close()

            

            flash(
                "Payment completed. Your Pro account is now active!",
                "success",
            )

    except Exception as e:
        print(e)
        flash("Unable to activate Pro.", "danger")

    return redirect(url_for("dashboard"))

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    signature = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        checkout_session = event["data"]["object"].to_dict()

        user_id = checkout_session.get("metadata", {}).get("user_id")

        if user_id:
            db = get_db()
            db.execute(
                "UPDATE users SET plan = ? WHERE id = ?",
                ("pro", int(user_id)),
            )
            db.commit()
            db.close()

            print(f"User {user_id} upgraded to Pro")

    return "", 200


@app.route("/library")
@login_required
def library():
    db = get_db()
    ideas = db.execute(
        """
        SELECT * FROM ideas
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],),
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
    db = get_db()
    ideas = db.execute(
        "SELECT * FROM ideas WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],),
    ).fetchall()
    db.close()

    output = io.StringIO()
    output.write("IDEAFORGE CONTENT LIBRARY\n")
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
        download_name="ideaforge_content_ideas.txt",
        mimetype="text/plain",
    )


@app.route("/export/csv")
@login_required
def export_csv():
    db = get_db()
    ideas = db.execute(
        "SELECT * FROM ideas WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],),
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
        download_name="ideaforge_content_ideas.csv",
        mimetype="text/csv",
    )


@app.route("/pricing")
def pricing():
    return render_template("pricing.html")


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
