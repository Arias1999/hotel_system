# Deployment Guide - Vercel + Supabase

This app uses Flask, Supabase PostgreSQL, and Gmail SMTP for OTP verification.

## Supabase Database URL

Use only the direct Supabase PostgreSQL connection:

```env
DATABASE_URL=postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres?sslmode=require
```

Do not use Supabase pooler URLs such as:

```env
postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
```

The app rejects pooler hosts and requires:

- host: `db.PROJECT_REF.supabase.co`
- port: `5432`
- user: `postgres`
- query: `sslmode=require`

## Vercel Environment Variables

In Vercel, open Project Settings > Environment Variables.

Delete old variables:

- `DATABASE_URL_POOLER`
- `DATABASE_URL_DIRECT`
- any `DATABASE_URL` that contains `pooler.supabase.com` or port `6543`

Keep only:

```env
DATABASE_URL=postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres?sslmode=require
SECRET_KEY=your-random-secret-key
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=yourgmail@gmail.com
SMTP_PASSWORD=your-gmail-app-password
SMTP_FROM_EMAIL=yourgmail@gmail.com
OTP_EXPIRY_MINUTES=10
```

After saving variables, force a fresh Vercel deploy:

1. Go to the Deployments tab.
2. Open the latest deployment menu.
3. Click Redeploy.
4. Do not reuse stale cached environment variables if Vercel asks.

## Local Development

Create `.env` locally:

```env
DATABASE_URL=postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres?sslmode=require
SECRET_KEY=your-local-secret-key
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=yourgmail@gmail.com
SMTP_PASSWORD=your-gmail-app-password
SMTP_FROM_EMAIL=yourgmail@gmail.com
OTP_EXPIRY_MINUTES=10
```

Run:

```bash
pip install -r requirements.txt
python app.py
```

## Debugging

Use these routes locally:

- `/debug-db` checks the parsed database URL without exposing the password.
- `/test-db` runs `SELECT 1`.

Expected terminal logs:

- `DATABASE_URL LOADED`
- `DATABASE CONNECTED SUCCESSFULLY`
- `USERS TABLE READY`
- `EMAIL CHECK SUCCESS`
- `SMTP LOGIN SUCCESS`
- `USER INSERTED`

If registration fails, read the terminal traceback. The app prints the exact database or SMTP error.
