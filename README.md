# Impana Gold Billing System

A production-ready POS and admin platform for Impana Gold, built with Flask and PostgreSQL.

## 1. Prerequisites
- Python 3.11+
- PostgreSQL 15+
- pip

## 2. Clone and virtual environment setup
```bash
python -m venv venv
```
Windows:
```bash
venv\Scripts\activate
```
macOS/Linux:
```bash
source venv/bin/activate
```

## 3. Install dependencies
```bash
pip install -r requirements.txt
```

## 4. Database setup
Create the database and configure your connection:
```bash
createdb impana_gold
```
Copy .env.example to .env and set DATABASE_URL.

## 5. Run migrations
```bash
flask db upgrade
```

## 6. Seed data
```bash
python seed.py
```
This creates default categories, products, and a superadmin user.

## 7. Run development server
```bash
flask run
```

## 8. Access the app
- POS: http://localhost:5000/
- Login: http://localhost:5000/login

## 9. Owner phone app (`/b`)
An installable web app (PWA) for billing from a phone. Open `https://<your-site>/b/` in Chrome on Android, sign in with
the admin account, and use Chrome's "Install app" (or the button on the Account tab).

- **Sign in once.** The phone stays signed in for 90 days (a signed cookie). Deactivating the admin or changing the
  password signs every phone out.
- **Fingerprint lock.** On first sign-in the phone registers its fingerprint (WebAuthn). After that the app asks for it
  every time it opens or returns after a minute in the background. If the fingerprint fails, Android offers the phone's
  own screen-lock PIN. The server enforces the lock: no bill or customer data is served while locked.
- **Billing.** Search a product, tap quantity, pick the buyer, save. Saving uses the same routine as the desktop screen
  (`utils/billing_service.py`), so GST, stock and bill numbers always match.
- **WhatsApp.** After saving, "Send on WhatsApp" opens the buyer's chat with the message typed; the owner taps Send.
  No paid API. The message holds a private link (`/r/<signed token>`) that opens the **original** bill without a login.

Deployment notes:
- It needs **HTTPS** (fingerprint lock and installing only work on secure sites) and a real **`SECRET_KEY`** in the
  environment: it signs the phone login and the buyer links. Changing it invalidates every link already sent.
- `pip install -r requirements.txt` (adds `webauthn`). The `owner_passkeys` table is created automatically on startup.
- Tests: `pytest tests` (they use a throwaway SQLite database, never the real one).

## 10. Production deployment (gunicorn + nginx + systemd + SSL)
Example gunicorn command:
```bash
gunicorn -c gunicorn.conf.py "app:create_app()"
```
Example nginx server block:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Systemd service example:
```ini
[Unit]
Description=Impana Gold Billing System
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/impana_gold
Environment="FLASK_ENV=production"
ExecStart=/path/to/venv/bin/gunicorn -c gunicorn.conf.py "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```
For SSL, use Certbot with your nginx configuration.

## 10. Default credentials
- Username: admin
- Password: ChangeMe@123
Change this immediately after first login.

## 11. Troubleshooting
- PostgreSQL connection errors: verify DATABASE_URL in .env and that the database exists.
- WeasyPrint dependencies (Linux): install system packages such as libpango-1.0-0, libpangocairo-1.0-0, libcairo2, and libffi-dev.
- Windows WeasyPrint: use WSL or install the required GTK libraries.

## Notes
- static/uploads is used for logo uploads and should be writable.
- schema.sql is a raw SQL alternative to migrations.
