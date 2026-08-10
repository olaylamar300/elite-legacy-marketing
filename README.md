# IdeaForge — Sellable Content Idea Generator MVP

IdeaForge is a working Flask web application that can be sold as a subscription service or customised for clients.

## Included features

- Customer registration and login
- Secure password hashing
- Free and Pro plans
- Free-plan daily usage limit
- Content idea generation
- Saved private content library
- Delete ideas
- TXT exports
- CSV exports
- Mobile-friendly dark interface
- SQLite database
- Stripe Checkout subscriptions
- Automatic Pro activation and renewal handling
- Stripe Customer Portal for billing and cancellations

## AI generation

The generator uses the OpenAI API and falls back to a local template library when AI generation is temporarily unavailable.

## Stripe and Railway configuration

Set these variables in the Railway service before accepting payments:

```text
SECRET_KEY=<a long random value>
OPENAI_API_KEY=<your OpenAI API key>
STRIPE_SECRET_KEY=<your Stripe test or live secret key>
STRIPE_PRICE_ID=<the recurring monthly Price ID>
STRIPE_WEBHOOK_SECRET=<the signing secret for this endpoint>
DATABASE_PATH=/data/ideaforge.db
```

Create the Stripe webhook endpoint using the deployed site URL:

```text
https://<your-domain>/stripe-webhook
```

Subscribe that endpoint to:

- `checkout.session.completed`
- `invoice.paid`
- `invoice.payment_failed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`

Use keys, products, prices and webhook secrets from the same Stripe mode. Test-mode and live-mode values cannot be mixed. Configure Stripe's Customer Portal so Pro customers can update their payment method, view invoices and cancel their subscription.

## Run on a MacBook

### 1. Open Terminal

Press Command + Space, search for Terminal, and open it.

### 2. Open the project folder

Example if the folder is on your Desktop:

```bash
cd ~/Desktop/ideaforge_sellable_mvp
```

### 3. Create a virtual environment

```bash
python3 -m venv venv
```

### 4. Activate it

```bash
source venv/bin/activate
```

### 5. Install Flask

```bash
pip install -r requirements.txt
```

### 6. Set a secure secret key

For a quick local test, the built-in development value will work.

Before launch, run:

```bash
export SECRET_KEY="replace-this-with-a-long-random-secret"
```

### 7. Start the app

```bash
python3 app.py
```

Open this address in Safari or Chrome:

```text
http://127.0.0.1:5000
```

## Run from IDLE

IDLE can open `app.py`, but Flask projects are easier to run from Terminal.

1. Open IDLE.
2. Select File → Open.
3. Choose `app.py`.
4. Select Run → Run Module.

You may still need to install Flask first using Terminal.

## Upgrade a customer manually

Activate the virtual environment and run:

```bash
flask --app app make-pro
```

Enter the customer's registered email.

To return a customer to the free plan:

```bash
flask --app app make-free
```

## Suggested first pricing

- Free: 10 ideas per day
- Pro: £11.99 per month
- Agency: £24.99 per month after adding multiple brands and team access

## What to change before selling

1. Replace the name IdeaForge with your final brand.
2. Add your logo, terms, privacy policy, support email, and refund policy.
3. Test Stripe Checkout, renewals, failed payments and cancellations in test mode.
4. Deploy the app to a hosting platform.
5. Turn off Flask debug mode in production.
6. Use PostgreSQL instead of SQLite once you have active customers.
7. Add email verification and password reset.
8. Add analytics and error monitoring.
9. Add an AI API later for more original, contextual ideas.
10. Test the app on mobile and desktop.

## Product positioning

A simple offer:

> Generate a full week of social-media content ideas in under two minutes.

Potential customers:

- Small businesses
- Event promoters
- Social-media managers
- Freelancers
- Personal brands
- Gym owners
- Car rental companies
- Restaurants
- University societies

## Suggested sales model

### Option 1: Subscription website

Host IdeaForge online and charge customers monthly.

### Option 2: White-label client tool

Customise the name, logo, colours, and content categories for a business, then charge a setup fee.

Suggested starting range:

- £150–£350 for a basic customised version
- £500–£1,000 after adding payments, analytics, email features, and deployment
- Monthly support or hosting from £20–£75

### Option 3: Lead-generation tool

Allow free idea generation and collect customer emails, then sell content creation or social-media management services.

## Project structure

```text
ideaforge_sellable_mvp/
├── app.py
├── requirements.txt
├── .env.example
├── README.md
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── register.html
│   ├── login.html
│   ├── dashboard.html
│   ├── generate.html
│   ├── library.html
│   └── pricing.html
└── static/
    └── style.css
```

## Licence note

This code is provided for you to use and customise. Before selling it at scale, add your own legal terms and have the product reviewed for security, privacy, and consumer-law compliance.
