"""
database.py
Handles PostgreSQL connection and schema initialization for
Happy Kidz Public School - School Management System.

Requires DATABASE_URL environment variable pointing to a PostgreSQL instance
(e.g. Neon, Supabase, local Postgres). Render and some hosts give postgres://
URLs — this module automatically rewrites them to postgresql:// for psycopg2.
"""

import psycopg2
import psycopg2.extras
import os
import secrets
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# Connection URL
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Render (and some other hosts) issue postgres:// — psycopg2 needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ---------------------------------------------------------------------------
# PostgreSQL Schema
# ---------------------------------------------------------------------------

# Each item is one DDL statement (no semicolons inside).
# Changes from SQLite version:
#   - INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
#   - datetime('now') default         → NOW()::text
#   - date('now') default             → CURRENT_DATE::text
#   - PRAGMA foreign_keys             → removed (PG enforces FKs natively)
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id               SERIAL PRIMARY KEY,
        username         TEXT UNIQUE NOT NULL,
        password_hash    TEXT NOT NULL,
        role             TEXT NOT NULL CHECK(role IN ('admin','teacher','student')),
        linked_id        INTEGER,
        is_active        INTEGER DEFAULT 1,
        created_at       TEXT DEFAULT NOW()::text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS classes (
        id           SERIAL PRIMARY KEY,
        class_name   TEXT NOT NULL,
        section      TEXT NOT NULL,
        UNIQUE(class_name, section)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS students (
        id                   SERIAL PRIMARY KEY,
        student_uid          TEXT UNIQUE NOT NULL,
        admission_number     TEXT,
        roll_number          TEXT,
        full_name            TEXT NOT NULL,
        class_id             INTEGER,
        dob                  TEXT,
        gender               TEXT,
        photo                TEXT,
        blood_group          TEXT,
        father_name          TEXT,
        mother_name          TEXT,
        guardian_name        TEXT,
        parent_contact       TEXT,
        alternate_phone      TEXT,
        emergency_contact    TEXT,
        aadhaar_number       TEXT,
        sssm_id              TEXT,
        family_id            TEXT,
        category             TEXT,
        caste                TEXT,
        religion             TEXT,
        address              TEXT,
        city                 TEXT,
        state                TEXT,
        pincode              TEXT,
        family_annual_income TEXT,
        parent_occupation    TEXT,
        medical_issues       TEXT,
        bank_account_number  TEXT,
        bank_ifsc            TEXT,
        bank_name            TEXT,
        bank_account_holder  TEXT,
        previous_school      TEXT,
        previous_class       TEXT,
        admission_date       TEXT,
        other_info           TEXT,
        email                TEXT,
        phone                TEXT,
        status               TEXT DEFAULT 'active',
        created_at           TEXT DEFAULT NOW()::text,
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS teachers (
        id                SERIAL PRIMARY KEY,
        teacher_uid       TEXT UNIQUE NOT NULL,
        full_name         TEXT NOT NULL,
        subject           TEXT,
        designation       TEXT,
        qualification     TEXT,
        email             TEXT,
        phone             TEXT,
        joining_date      TEXT,
        address           TEXT,
        emergency_contact TEXT,
        photo             TEXT,
        status            TEXT DEFAULT 'active',
        created_at        TEXT DEFAULT NOW()::text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subjects (
        id           SERIAL PRIMARY KEY,
        subject_name TEXT UNIQUE NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exams (
        id               SERIAL PRIMARY KEY,
        exam_name        TEXT NOT NULL,
        academic_session TEXT,
        class_id         INTEGER,
        exam_date        TEXT,
        created_at       TEXT DEFAULT NOW()::text,
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exam_subjects (
        id         SERIAL PRIMARY KEY,
        exam_id    INTEGER NOT NULL,
        subject_id INTEGER NOT NULL,
        max_marks  REAL NOT NULL DEFAULT 100,
        FOREIGN KEY (exam_id)    REFERENCES exams(id)    ON DELETE CASCADE,
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
        UNIQUE(exam_id, subject_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS results (
        id             SERIAL PRIMARY KEY,
        student_id     INTEGER NOT NULL,
        exam_id        INTEGER NOT NULL,
        subject_id     INTEGER NOT NULL,
        marks_obtained REAL,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (exam_id)    REFERENCES exams(id)    ON DELETE CASCADE,
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
        UNIQUE(student_id, exam_id, subject_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attendance (
        id         SERIAL PRIMARY KEY,
        student_id INTEGER NOT NULL,
        class_id   INTEGER,
        date       TEXT NOT NULL,
        status     TEXT NOT NULL CHECK(status IN ('present','absent')),
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        UNIQUE(student_id, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fees (
        id             SERIAL PRIMARY KEY,
        student_id     INTEGER NOT NULL,
        amount         REAL NOT NULL,
        payment_status TEXT DEFAULT 'pending' CHECK(payment_status IN ('paid','pending','partial')),
        due_date       TEXT,
        payment_date   TEXT,
        receipt_number TEXT,
        remarks        TEXT,
        created_at     TEXT DEFAULT NOW()::text,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS timetable (
        id            SERIAL PRIMARY KEY,
        class_id      INTEGER NOT NULL,
        day_of_week   TEXT NOT NULL,
        period_number INTEGER NOT NULL,
        subject_id    INTEGER,
        teacher_id    INTEGER,
        FOREIGN KEY (class_id)   REFERENCES classes(id)  ON DELETE CASCADE,
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS social_links (
        id        INTEGER PRIMARY KEY CHECK(id=1),
        instagram TEXT,
        youtube   TEXT,
        facebook  TEXT,
        whatsapp  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS site_settings (
        id      INTEGER PRIMARY KEY CHECK(id=1),
        tagline TEXT,
        address TEXT,
        phone   TEXT,
        email   TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gallery_albums (
        id          SERIAL PRIMARY KEY,
        title       TEXT NOT NULL,
        event_date  TEXT,
        description TEXT,
        created_at  TEXT DEFAULT NOW()::text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gallery_photos (
        id         SERIAL PRIMARY KEY,
        album_id   INTEGER NOT NULL,
        photo_path TEXT NOT NULL,
        caption    TEXT,
        created_at TEXT DEFAULT NOW()::text,
        FOREIGN KEY (album_id) REFERENCES gallery_albums(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notices (
        id         SERIAL PRIMARY KEY,
        title      TEXT NOT NULL,
        content    TEXT,
        date       TEXT DEFAULT CURRENT_DATE::text,
        created_at TEXT DEFAULT NOW()::text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id          SERIAL PRIMARY KEY,
        title       TEXT NOT NULL,
        description TEXT,
        event_date  TEXT,
        created_at  TEXT DEFAULT NOW()::text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admissions (
        id            SERIAL PRIMARY KEY,
        student_name  TEXT NOT NULL,
        parent_name   TEXT,
        email         TEXT,
        phone         TEXT,
        class_applied TEXT,
        message       TEXT,
        status        TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
        created_at    TEXT DEFAULT NOW()::text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id         SERIAL PRIMARY KEY,
        name       TEXT NOT NULL,
        email      TEXT,
        message    TEXT,
        created_at TEXT DEFAULT NOW()::text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS question_papers (
        id               SERIAL PRIMARY KEY,
        title            TEXT NOT NULL,
        class_id         INTEGER,
        subject_id       INTEGER,
        exam_id          INTEGER,
        academic_session TEXT,
        total_marks      REAL,
        duration         TEXT,
        instructions     TEXT,
        created_at       TEXT DEFAULT NOW()::text,
        FOREIGN KEY (class_id)   REFERENCES classes(id)  ON DELETE SET NULL,
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
        FOREIGN KEY (exam_id)    REFERENCES exams(id)    ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS questions (
        id                SERIAL PRIMARY KEY,
        question_paper_id INTEGER NOT NULL,
        question_type     TEXT NOT NULL,
        question_text     TEXT NOT NULL,
        marks             REAL NOT NULL DEFAULT 1,
        order_index       INTEGER DEFAULT 0,
        FOREIGN KEY (question_paper_id) REFERENCES question_papers(id) ON DELETE CASCADE
    )
    """,
]

DEFAULT_SUBJECTS = [
    "English", "Mathematics", "Hindi", "Science", "Social Science",
    "Computer Science", "General Knowledge", "Drawing", "Physical Education"
]

# ---------------------------------------------------------------------------
# DB adapter — makes psycopg2 behave like sqlite3 for this app
# ---------------------------------------------------------------------------

class _CursorWrapper:
    """Wraps a psycopg2 RealDictCursor to match the sqlite3 cursor interface."""

    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        try:
            return self._cur.fetchone()
        except psycopg2.ProgrammingError:
            return None

    def fetchall(self):
        try:
            return self._cur.fetchall()
        except psycopg2.ProgrammingError:
            return []

    def __iter__(self):
        return iter(self.fetchall())


class DBWrapper:
    """
    Thin adapter that makes psycopg2 work like sqlite3 for this application.

    Key behaviours:
    - Automatically converts SQLite ? placeholders to psycopg2 %s placeholders.
    - Uses RealDictCursor so row["column"] access works (same as sqlite3.Row).
    - Manages a single connection per request (caller must call close()).
    """

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False

    def execute(self, sql: str, params=None) -> _CursorWrapper:
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Convert SQLite ? placeholders → psycopg2 %s placeholders
        sql = sql.replace("?", "%s")
        cur.execute(sql, params or ())
        return _CursorWrapper(cur)

    def commit(self):
        self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def get_db() -> DBWrapper:
    """Return a database connection wrapper for the current request."""
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Add it to your .env file or environment variables. "
            "Example: DATABASE_URL=postgresql://user:pass@host/dbname"
        )
    return DBWrapper(DATABASE_URL)


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db():
    """Create tables (if not exist) and seed initial data on first run."""
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Cannot initialise database."
        )

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Create all tables in a single transaction
    for stmt in SCHEMA_STATEMENTS:
        stmt = stmt.strip()
        if stmt:
            cur.execute(stmt)
    conn.commit()

    # Seed singleton rows
    cur.execute(
        "INSERT INTO social_links (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
    )
    cur.execute(
        """INSERT INTO site_settings (id, tagline, address, phone, email)
           VALUES (1, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
        ("Where every child learns to think, build and lead.", "Bhimgarh", "", "")
    )

    # Seed or preserve admin account
    cur.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    existing_admin = cur.fetchone()
    if not existing_admin:
        admin_username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
        admin_password = os.environ.get("ADMIN_PASSWORD", "")
        if not admin_password:
            admin_password = secrets.token_urlsafe(18)
            print("\n[HKPS] First admin account created.")
            print(f"[HKPS] Username: {admin_username}")
            print(f"[HKPS] Temporary password: {admin_password}")
            print("[HKPS] Change it immediately in Admin → Account Security.\n")
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
            (admin_username, generate_password_hash(admin_password), "admin")
        )

    # Seed default subjects
    for s in DEFAULT_SUBJECTS:
        cur.execute(
            "INSERT INTO subjects (subject_name) VALUES (%s) ON CONFLICT (subject_name) DO NOTHING",
            (s,)
        )

    # Seed default classes (Class 1–10, Section A)
    for cname in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
        cur.execute(
            "INSERT INTO classes (class_name, section) VALUES (%s, %s) "
            "ON CONFLICT (class_name, section) DO NOTHING",
            (cname, "A")
        )

    conn.commit()
    cur.close()
    conn.close()
