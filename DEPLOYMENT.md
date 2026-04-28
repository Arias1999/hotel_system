# Deployment Guide — Vercel + Supabase

This guide walks through deploying the hotel_system Flask app to Vercel with a Supabase PostgreSQL backend.

---

## Prerequisites

1. **Supabase project** — [supabase.com](https://supabase.com)
2. **Vercel account** — [vercel.com](https://vercel.com)
3. **GitHub repo** — code pushed to GitHub

---

## Step 1: Get Supabase Connection Strings

Go to your Supabase project → **Settings → Database**:

1. Under **Connection string**, copy the **Transaction pooler** URI (port 6543):
   ```
   postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
   ```
   This is your `DATABASE_URL_POOLER`.

2. Under **Connection string**, copy the **Direct connection** URI (port 5432):
   ```
   postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres
   ```
   This is your `DATABASE_URL_DIRECT` (optional for local dev).

---

## Step 2: Run Database Schema

In Supabase → **SQL Editor**, paste and run `schema.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email      TEXT UNIQUE NOT NULL,
    password   TEXT NOT NULL,
    is_admin   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rooms (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    price       NUMERIC(10, 2) NOT NULL,
    description TEXT,
    image       TEXT,
    category    TEXT NOT NULL DEFAULT 'Standard'
);

CREATE TABLE IF NOT EXISTS bookings (
    id             SERIAL PRIMARY KEY,
    user_email     TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    room_id        INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    checkin        DATE NOT NULL,
    checkout       DATE NOT NULL,
    payment_method TEXT NOT NULL DEFAULT 'Cash',
    payment_status TEXT NOT NULL DEFAULT 'Pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    id             SERIAL PRIMARY KEY,
    booking_id     INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    user_email     TEXT NOT NULL,
    amount         NUMERIC(10, 2) NOT NULL DEFAULT 0,
    payment_method TEXT NOT NULL DEFAULT 'Cash',
    payment_status TEXT NOT NULL DEFAULT 'Pending',
    paid_at        TIMESTAMPTZ
);
```

---

## Step 3: Deploy to Vercel

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import your GitHub repository
3. **Framework Preset**: Other
4. **Build Command**: (leave empty)
5. **Output Directory**: (leave empty)
6. Click **Deploy**

---

## Step 4: Set Environment Variables in Vercel

Go to your Vercel project → **Settings → Environment Variables** and add:

| Key                      | Value                                                                                      |
|--------------------------|--------------------------------------------------------------------------------------------|
| `ENV`                    | `production`                                                                               |
| `DATABASE_URL_POOLER`    | `postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres` |
| `SECRET_KEY`             | Generate a random string (e.g., `openssl rand -hex 32`)                                   |

**Important**: Use the **Transaction pooler** URL (port 6543) for production — Vercel's serverless functions can't hold persistent connections to port 5432.

---

## Step 5: Redeploy

After adding environment variables:
1. Go to **Deployments** tab
2. Click the three dots on the latest deployment → **Redeploy**

---

## Local Development

Create a `.env` file (not committed to Git):

```env
ENV=local
DATABASE_URL_DIRECT=postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres
DATABASE_URL_POOLER=postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
SECRET_KEY=your-local-secret-key
```

Run locally:
```bash
pip install -r requirements.txt
python app.py
```

---

## How ENV Switching Works

`db.py` reads the `ENV` variable:
- `ENV=local` → uses `DATABASE_URL_DIRECT` (port 5432, no pooler overhead)
- `ENV=production` → uses `DATABASE_URL_POOLER` (port 6543, required on Vercel)

Both connections enforce SSL (`sslmode=require`).

---

## Troubleshooting

### "Tenant or user not found" on pooler
- The pooler (port 6543) requires username format `postgres.PROJECT_REF`
- Verify your `DATABASE_URL_POOLER` matches the format from Supabase dashboard

### "Password authentication failed"
- Double-check the password in your connection string
- Reset the database password in Supabase → Settings → Database if needed

### Registration fails silently
- Check Vercel logs: **Deployments → [latest] → Functions → View Logs**
- Look for Python tracebacks printed by `traceback.print_exc()`

---

## Security Checklist

- ✅ `.env` is in `.gitignore` (never commit credentials)
- ✅ `SECRET_KEY` is set to a random value in production
- ✅ Passwords are hashed with `werkzeug.security.generate_password_hash`
- ✅ SSL is enforced on all database connections (`sslmode=require`)
- ✅ Session cookies use `HttpOnly` and `SameSite=Lax`

---

## Next Steps

- Add email verification (e.g., using SendGrid or AWS SES)
- Implement password reset flow
- Add rate limiting to prevent brute-force attacks
- Set up monitoring (e.g., Sentry for error tracking)
