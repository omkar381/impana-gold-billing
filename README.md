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

## 9. Production deployment (gunicorn + nginx + systemd + SSL)
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
