# Backend (Flask + SQLite)

## Run

1. Create a virtual environment (optional).
2. Install deps:
   - `pip install -r requirements.txt`
3. Start server:
   - `python app.py`

The server serves the frontend from ../front and exposes the API at /api.
Database file is stored at back/data/inventory.db.

## Email verification (new users)

New accounts require email verification code (OTP) before login.

Set these environment variables to send real emails:

- `SMTP_HOST`
- `SMTP_PORT` (usually `587` for STARTTLS or `465` for SSL)
- `SMTP_USER`
- `SMTP_PASS`
- `SMTP_FROM`

You can define them in a `.env` file (supported automatically) either in:

- `back/.env`
- project root `.env`

Example `.env` for Gmail app password:

- `GMAIL_USER=tu_correo@gmail.com`
- `GMAIL_APP_PASSWORD=tu_app_password_16_chars`
- `SMTP_FROM=tu_correo@gmail.com`
- `SMTP_PORT=587`
- `ALLOW_DEV_EMAIL_FALLBACK=0`

Optional:

- `AUTH_CODE_SALT` (extra hash salt for OTP codes)
- `APP_TZ` (default: `America/Panama`)

### Gmail real (recommended for local MVP)

1. Enable 2-Step Verification on your Google account.
2. Create an App Password in Google Account Security.
3. Set in PowerShell before running backend:

   - `$env:GMAIL_USER="tu_correo@gmail.com"`
   - `$env:GMAIL_APP_PASSWORD="tu_app_password_16_chars"`
   - `$env:SMTP_FROM="tu_correo@gmail.com"`

4. Start backend:

   - `python back/app.py`

If `SMTP_HOST` is not provided and `GMAIL_USER` + `GMAIL_APP_PASSWORD` exist,
the app automatically uses `smtp.gmail.com:587` with STARTTLS.

### Local fallback (sin SMTP)

For local development, if SMTP fails or is not configured, registration can still continue
and the API returns `devCode` so you can verify manually.

- Default in local/dev: enabled
- Default in production: disabled

Override explicitly with:

- `ALLOW_DEV_EMAIL_FALLBACK=1` (enable)
- `ALLOW_DEV_EMAIL_FALLBACK=0` (disable)
