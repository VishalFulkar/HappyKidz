# Happy Kidz Public School — Production-Ready School System

A robust Flask-based school management system and public website for **Happy Kidz Public School Bhimgarh**.

## Features

- **Public Website:** Home, admissions, contact, gallery, notices, events, and social links.
- **Portals:** Dedicated dashboards for Admin, Teacher, and Student roles.
- **Academics:** Student & teacher management, classes, subjects, attendance, and timetable.
- **Examinations:** Question-paper builder, marks entry, and printable marksheets.
- **School Office:** Fee management, receipts, notices, events, and admission inquiries.
- **Website Manager:** No-code CMS for school staff to update public content.
- **Photo Gallery:** Cloudinary-powered image uploads with automatic compression and optimization.
- **Security:** CSRF protection, secure password hashing, session-cookie hardening, and security headers.

## Tech Stack

- **Backend:** Python (Flask, Werkzeug)
- **Database:** PostgreSQL (Neon Serverless DB) via `psycopg2-binary`
- **File Storage:** Cloudinary (CDN-delivered images)
- **Production Server:** Waitress (WSGI server)
- **Deployment:** Render (Free Tier)

---

## Local Development Setup

1. **Install Python 3.11+**
2. **Clone the repository and enter the directory**
3. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   ```
4. **Activate the virtual environment:**
   - Windows: `.venv\Scripts\activate`
   - Mac/Linux: `source .venv/bin/activate`
5. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
6. **Configure Environment Variables:**
   Copy the example config and add your API keys:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in:
   - `DATABASE_URL`: Your Neon PostgreSQL connection string.
   - `CLOUDINARY_URL`: Your Cloudinary API environment variable.
   - `SECRET_KEY`: A random 32-character string.

7. **Run the local server:**
   ```bash
   python app.py
   ```
   The database tables will automatically initialize on the first run. The app runs at `http://127.0.0.1:5000`.

---

## Initial Admin Account

On a brand-new database installation, the application will automatically create an `admin` account.

If you don't explicitly set `ADMIN_PASSWORD` in your `.env` file, the app will generate a highly secure temporary password and print it to your terminal:
```text
[HKPS] First admin account created.
[HKPS] Username: admin
[HKPS] Temporary password: <your-temporary-password>
```
Log in at `/login` and change your password immediately from **Admin → Account Security**.

---

## Deployment (Render.com + Neon)

This project is fully configured for 1-click deployment on [Render](https://render.com/).

1. Push your code to GitHub.
2. Sign up at Render and select **New → Web Service**.
3. Connect your GitHub repository.
4. Render will automatically detect the `render.yaml` configuration file.
5. In the Render dashboard, navigate to **Environment Variables** and add:
   - `DATABASE_URL`: Paste your Neon connection string.
   - `CLOUDINARY_URL`: Paste your Cloudinary connection string.
6. Click **Deploy**.

Render will automatically run `pip install -r requirements.txt` and launch the app using `waitress-serve`.

### Data Persistence Note
Because Render's free tier uses an ephemeral filesystem, we have migrated to **PostgreSQL (Neon)** for database persistence and **Cloudinary** for image persistence. This ensures that no student data or uploaded photos are lost when Render puts the app to sleep or redeploys.
