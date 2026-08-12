# Elite Legacy Marketing — AI Marketing Platform

Elite Legacy Marketing is a Flask SaaS platform for creators, businesses, freelancers and marketing agencies.

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
- Email verification and secure password reset
- Account and subscription settings
- Multiple brand/client workspaces
- AI rewrite, hashtag and campaign strategy tools
- Terms, privacy, refund and contact pages
- Admin user, subscription and usage analytics
- Signed Telnyx call-event and garage-booking webhooks
- Garage call and booking-request dashboard
- Multi-garage workspaces with isolated calls and customer records
- Garage onboarding approval, configuration and connection management

## AI generation

The generator uses the OpenAI API and falls back to a local template library when AI generation is temporarily unavailable.

## Stripe and Railway configuration

Set these variables in the Railway service before accepting payments:

```text
SECRET_KEY=<a long random value>
OPENAI_API_KEY=<your OpenAI API key>
STRIPE_SECRET_KEY=<your Stripe test or live secret key>
STRIPE_PRICE_ID=<the recurring monthly Price ID>
STRIPE_PHONE_RECEPTIONIST_PRICE_ID=<£80 monthly recurring Price ID>
STRIPE_GARAGE_RECEPTIONIST_PRICE_ID=<£100 monthly recurring Price ID>
STRIPE_REVIEW_AUTOMATION_PRICE_ID=<£10 monthly recurring Price ID>
STRIPE_WEBHOOK_SECRET=<the signing secret for this endpoint>
DATABASE_PATH=/data/ideaforge.db
PUBLIC_URL=https://wwwelite-legacy-marketing.com
ADMIN_EMAIL=<the owner's registered account email>
SUPPORT_EMAIL=<public support email>
SMTP_HOST=<email provider SMTP host>
SMTP_PORT=587
SMTP_USERNAME=<email provider username>
SMTP_PASSWORD=<email provider password>
SMTP_FROM=<verified sender address>
TELNYX_PUBLIC_KEY=<base64 Ed25519 public key from Telnyx>
TELNYX_ASSISTANT_ID=<Elite Garage AI Receptionist assistant ID>
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

## Telnyx configuration

Add the two Telnyx variables above to Railway. Configure the assistant/call event destination as:

```text
https://wwwelite-legacy-marketing.com/telnyx/webhooks
```

Configure a synchronous webhook tool that sends the final structured booking details to:

```text
https://wwwelite-legacy-marketing.com/telnyx/tools/garage-booking
```

Both endpoints require Telnyx's Ed25519 signature headers. Webhook tools are correlated using Telnyx's automatic `x-telnyx-call-control-id` header, while the body contains the customer, vehicle, request, preferred-time and safety fields documented in the application tests.

Each approved garage receives a unique booking webhook URL from the admin dashboard. Use that URL only for the matching garage's Telnyx assistant. The Garage AI Receptionist is advertised at £400 per month; create a matching recurring price with the approved payment provider before enabling checkout.

Verified `active`, `trialing` or complimentary Garage AI Receptionist subscriptions automatically provision one private garage workspace. Repeated payment webhooks reuse the same workspace and webhook key. Cancelled or unpaid subscriptions pause the workspace. Telephone answering is activated separately after the garage profile, Telnyx assistant and number have been configured and tested.

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

## Before selling

1. Review the legal pages with a qualified UK adviser before relying on them commercially.
2. Configure a verified support email and SMTP delivery.
3. Test Stripe Checkout, renewals, failed payments and cancellations in test mode.
4. Add genuine customer testimonials only after receiving permission.
5. Use PostgreSQL once concurrency or customer volume outgrows SQLite.
6. Add error monitoring and automated database backups.
7. Test the platform on mobile and desktop before each release.

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

Host Elite Legacy Marketing online and charge customers monthly.

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
