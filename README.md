# Happy Kidz Public School — Production-Ready School System

A Flask + SQLite school management system and public website for **Happy Kidz Public School Bhimgarh**.

## What is ready

- Public school website: home, admissions, contact, gallery, notices, events, social links
- Admin / Teacher / Student role-based access
- Student and teacher management
- Attendance, exams, results and printable marksheets
- Question-paper builder
- Fees, receipts and timetable
- Admissions and contact inbox
- Reports
- No-code Website Manager for school staff
- Gallery uploads with file-extension and image-signature validation
- CSRF protection for authenticated state-changing requests
- Secure password hashing
- Admin password-change page
- Protection against deleting the last active administrator
- Safer session-cookie defaults and security response headers
- Production WSGI launcher for Waitress

## Important: your Admin account

The first administrator remains an **admin** account. If a database already contains your `admin` account, it is preserved.

For a new installation, you can configure the administrator before first startup:

```text
ADMIN_USERNAME=admin
ADMIN_PASSWORD=use-a-long-private-password
SECRET_KEY=generate-a-long-random-secret
```

If `ADMIN_PASSWORD` is omitted on a brand-new database, the application generates a temporary administrator password and prints it in the terminal. Change it immediately from **Admin → Account Security**.

Existing installations that still use the old `admin / admin123` password are forced to change it after login.

## Local development

1. Install Python 3.11+ (3.13 is also fine).
2. Open a terminal in this folder.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the local server:

```bash
python app.py
```

5. Open `http://127.0.0.1:5000`.

## Production deployment

Do **not** expose Flask's development server to the internet. Use Waitress (included in `requirements.txt`) or another production WSGI server, behind HTTPS.

### Linux/macOS example

Set strong environment variables first:

```bash
export HKPS_PRODUCTION=1
export SECRET_KEY="replace-with-a-long-random-secret"
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="replace-with-a-long-private-password"
export COOKIE_SECURE=1
```

Then install and run:

```bash
pip install -r requirements.txt
waitress-serve --listen=127.0.0.1:8000 production:app
```

Put Nginx, Caddy, a managed hosting proxy, or an equivalent HTTPS reverse proxy in front of Waitress. The included `production.py` applies `ProxyFix` for one trusted proxy hop.

### Windows server

For a temporary internal deployment, configure the same environment variables in the server's environment and run:

```powershell
waitress-serve --listen=127.0.0.1:8000 production:app
```

For an internet-facing deployment, use a proper HTTPS reverse proxy / managed platform rather than exposing the process directly.

## Database and backups

The application uses `school.db` in the project directory. Before moving from prototype to real school use:

1. Keep the database on persistent storage.
2. Back up `school.db` regularly.
3. Back up `static/uploads/` too, because student/teacher/gallery photos live there.
4. Store backups somewhere separate from the live server.
5. Test restoring a backup before relying on it.

Do not commit `school.db`, uploaded student photographs, passwords, or secret keys to Git.

## Security checklist before school handover

- [ ] Set a unique `SECRET_KEY` (32+ random characters).
- [ ] Set a strong administrator password.
- [ ] Use HTTPS in production and keep `COOKIE_SECURE=1`.
- [ ] Create individual teacher/student accounts rather than sharing the admin account.
- [ ] Confirm only trusted staff have admin access.
- [ ] Set up automated database + uploads backups.
- [ ] Test restore.
- [ ] Keep Python/Flask/Werkzeug/Waitress dependencies updated.
- [ ] Do not put sensitive student data in public website fields.

## Ownership recommendation

For handover, the school should own the production domain, hosting account, administrator credentials, database backups, and recovery email. You can retain your own administrator account for maintenance if the school explicitly authorizes it.

## Project structure

```text
app.py                  Flask application and routes
database.py             SQLite schema + first-run seeding
production.py           Waitress/production WSGI entry point
requirements.txt        Runtime dependencies
static/css/style.css    Design system
static/uploads/         Uploaded images
templates/              Public site and admin/teacher/student UI
```
