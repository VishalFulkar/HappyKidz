"""
Happy Kidz Public School - School Management System
"""

import os
from dotenv import load_dotenv
load_dotenv()  # Load variables from .env into os.environ

import uuid
from functools import wraps
from datetime import datetime, date
import secrets
import re

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from database import get_db, init_db

# ---------------------------------------------------------------------------
# Cloudinary (optional — falls back to local storage if not configured)
# ---------------------------------------------------------------------------
try:
    import cloudinary
    import cloudinary.uploader
    _cld_url = os.environ.get("CLOUDINARY_URL", "").strip()
    if _cld_url:
        cloudinary.config(cloudinary_url=_cld_url)
        CLOUDINARY_CONFIGURED = True
    else:
        CLOUDINARY_CONFIGURED = False
except ImportError:
    CLOUDINARY_CONFIGURED = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_GALLERY_PHOTOS = 30

app = Flask(__name__)
HKPS_PRODUCTION = os.environ.get("HKPS_PRODUCTION", "0") == "1" or os.environ.get("FLASK_ENV") == "production"
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
if HKPS_PRODUCTION and len(SECRET_KEY) < 32:
    raise RuntimeError("Production requires SECRET_KEY (at least 32 characters). Set it in the server environment.")
app.secret_key = SECRET_KEY or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB uploads
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "1" if HKPS_PRODUCTION else "0") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 8

SCHOOL_NAME = "Happy Kidz Public School"
SCHOOL_PLACE = "Bhimgarh"
FULL_SCHOOL_NAME = f"{SCHOOL_NAME} {SCHOOL_PLACE}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def valid_image_bytes(data, ext):
    """Lightweight file-signature check to reject renamed non-image uploads."""
    if ext in {"jpg", "jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if ext == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == "gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if ext == "webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def is_safe_external_url(value):
    return bool(re.match(r"^https?://", value or "", re.IGNORECASE))


def media_url(path):
    """Return a usable URL for a stored media path.
    Handles both Cloudinary full URLs (https://...) and local relative paths.
    Safe to call with None — returns None.
    """
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path  # Already a full Cloudinary / external URL
    return url_for("static", filename=path)  # Local static file


def save_photo(file_storage, subfolder):
    """Validate and save an uploaded image.

    Uploads to Cloudinary when CLOUDINARY_URL is configured;
    falls back to local disk otherwise.
    Returns a URL string (Cloudinary) or relative path (local), or None on failure.
    """
    if not file_storage or not file_storage.filename:
        return None
    original = secure_filename(file_storage.filename)
    if not original or not allowed_file(original):
        return None
    ext = original.rsplit(".", 1)[1].lower()
    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if not valid_image_bytes(header, ext):
        return None

    # --- Cloudinary upload ---
    if CLOUDINARY_CONFIGURED:
        try:
            result = cloudinary.uploader.upload(
                file_storage.stream,
                folder=f"hkps/{subfolder}",
                resource_type="image",
                transformation=[
                    {"width": 800, "crop": "limit",
                     "quality": "auto", "fetch_format": "auto"}
                ],
            )
            return result["secure_url"]
        except Exception as exc:
            app.logger.warning("Cloudinary upload failed (%s). Using local storage.", exc)
            file_storage.stream.seek(0)

    # --- Local disk fallback ---
    fname = f"{uuid.uuid4().hex}.{ext}"
    folder = os.path.join(UPLOAD_DIR, subfolder)
    os.makedirs(folder, exist_ok=True)
    file_storage.save(os.path.join(folder, fname))
    return f"uploads/{subfolder}/{fname}"


def login_required(roles=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            if roles and session.get("role") not in roles:
                flash("You do not have permission to view that page.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def calc_grade(pct):
    if pct is None:
        return "-"
    if pct >= 90:
        return "A+"
    if pct >= 80:
        return "A"
    if pct >= 70:
        return "B+"
    if pct >= 60:
        return "B"
    if pct >= 50:
        return "C"
    if pct >= 33:
        return "D"
    return "F"


def gen_student_uid():
    return "HKPS" + datetime.now().strftime("%y") + uuid.uuid4().hex[:5].upper()


def gen_teacher_uid():
    return "HKPST" + uuid.uuid4().hex[:5].upper()


def gen_receipt_number():
    return "RCT" + datetime.now().strftime("%y%m%d") + uuid.uuid4().hex[:4].upper()


@app.context_processor
def inject_globals():
    settings = {
        "tagline": "Where every child learns to think, build and lead.",
        "address": "Bhimgarh",
        "phone": "",
        "email": "",
    }
    try:
        db = get_db()
        row = db.execute("SELECT * FROM site_settings WHERE id=1").fetchone()
        db.close()
        if row:
            settings.update(dict(row))
    except Exception:
        pass
    return dict(
        school_name=SCHOOL_NAME,
        school_place=SCHOOL_PLACE,
        site_settings=settings,
        current_year=datetime.now().year,
        session=session,
        csrf_token=csrf_token(),
        full_school_name=FULL_SCHOOL_NAME,
        media_url=media_url,       # available in every template
    )


# ---------------------------------------------------------------------------
# Security middleware
# ---------------------------------------------------------------------------

@app.before_request
def enforce_admin_password_change():
    if session.get("must_change_password") and session.get("role") == "admin":
        if request.endpoint not in {"admin_security", "logout", "static"}:
            return redirect(url_for("admin_security"))
    return None


@app.before_request
def protect_mutating_requests():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    # Public forms and login do not have an authenticated session yet.
    if request.endpoint in {"login", "admission", "contact"}:
        return None
    if "user_id" not in session:
        return None
    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        return ("Invalid or missing security token. Please refresh the page and try again.", 400)
    return None


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if HKPS_PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ---------------------------------------------------------------------------
# Public site
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    db = get_db()
    notices = db.execute(
        "SELECT * FROM notices ORDER BY date DESC, id DESC LIMIT 5"
    ).fetchall()
    events = db.execute(
        "SELECT * FROM events WHERE event_date >= ? ORDER BY event_date ASC LIMIT 5",
        (date.today().isoformat(),)
    ).fetchall()
    albums = db.execute(
        "SELECT a.*, (SELECT photo_path FROM gallery_photos p WHERE p.album_id=a.id ORDER BY p.id ASC LIMIT 1) cover_path, "
        "(SELECT COUNT(*) FROM gallery_photos p2 WHERE p2.album_id=a.id) photo_count "
        "FROM gallery_albums a ORDER BY a.event_date DESC, a.id DESC LIMIT 6"
    ).fetchall()
    social = db.execute("SELECT * FROM social_links WHERE id=1").fetchone()
    stats = {
        "students": db.execute("SELECT COUNT(*) c FROM students WHERE status='active'").fetchone()["c"],
        "teachers": db.execute("SELECT COUNT(*) c FROM teachers WHERE status='active'").fetchone()["c"],
        "classes": db.execute("SELECT COUNT(*) c FROM classes").fetchone()["c"],
    }
    db.close()
    return render_template("public/home.html", notices=notices, events=events, stats=stats, albums=albums, social=social)


@app.route("/gallery")
def public_gallery():
    db = get_db()
    albums = db.execute(
        "SELECT a.*, (SELECT photo_path FROM gallery_photos p WHERE p.album_id=a.id ORDER BY p.id ASC LIMIT 1) cover_path, "
        "(SELECT COUNT(*) FROM gallery_photos p2 WHERE p2.album_id=a.id) photo_count "
        "FROM gallery_albums a ORDER BY a.event_date DESC, a.id DESC"
    ).fetchall()
    selected = request.args.get("album", type=int)
    if selected:
        selected_album = db.execute("SELECT * FROM gallery_albums WHERE id=?", (selected,)).fetchone()
    else:
        selected_album = albums[0] if albums else None
        selected = selected_album["id"] if selected_album else None
    photos = db.execute("SELECT * FROM gallery_photos WHERE album_id=? ORDER BY id DESC", (selected,)).fetchall() if selected else []
    db.close()
    return render_template("public/gallery.html", albums=albums, photos=photos, selected_album=selected_album)


@app.route("/admission", methods=["GET", "POST"])
def admission():
    if request.method == "POST":
        db = get_db()
        db.execute(
            """INSERT INTO admissions (student_name, parent_name, email, phone, class_applied, message)
               VALUES (?,?,?,?,?,?)""",
            (request.form.get("student_name"), request.form.get("parent_name"),
             request.form.get("email"), request.form.get("phone"),
             request.form.get("class_applied"), request.form.get("message"))
        )
        db.commit()
        db.close()
        flash("Your admission application has been submitted. We will contact you soon.", "success")
        return redirect(url_for("admission"))
    return render_template("public/admission.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        db = get_db()
        db.execute(
            "INSERT INTO messages (name, email, message) VALUES (?,?,?)",
            (request.form.get("name"), request.form.get("email"), request.form.get("message"))
        )
        db.commit()
        db.close()
        flash("Your message has been sent. Thank you for reaching out.", "success")
        return redirect(url_for("contact"))
    return render_template("public/contact.html")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        db.close()
        if user and check_password_hash(user["password_hash"], password) and user["is_active"]:
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            session["username"] = user["username"]
            session["linked_id"] = user["linked_id"]
            if user["role"] == "admin" and check_password_hash(user["password_hash"], "admin123"):
                session["must_change_password"] = True
            flash(f"Welcome back, {username}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("auth/login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required()
def dashboard():
    role = session.get("role")
    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    if role == "teacher":
        return redirect(url_for("teacher_dashboard"))
    return redirect(url_for("student_dashboard"))


# ---------------------------------------------------------------------------
# ADMIN DASHBOARD
# ---------------------------------------------------------------------------

@app.route("/admin/dashboard")
@login_required(["admin"])
def admin_dashboard():
    db = get_db()
    stats = {
        "students": db.execute("SELECT COUNT(*) c FROM students WHERE status='active'").fetchone()["c"],
        "teachers": db.execute("SELECT COUNT(*) c FROM teachers WHERE status='active'").fetchone()["c"],
        "classes": db.execute("SELECT COUNT(*) c FROM classes").fetchone()["c"],
        "subjects": db.execute("SELECT COUNT(*) c FROM subjects").fetchone()["c"],
        "exams": db.execute("SELECT COUNT(*) c FROM exams").fetchone()["c"],
        "pending_admissions": db.execute("SELECT COUNT(*) c FROM admissions WHERE status='pending'").fetchone()["c"],
        "fees_collected": db.execute("SELECT COALESCE(SUM(amount),0) s FROM fees WHERE payment_status='paid'").fetchone()["s"],
        "fees_pending": db.execute("SELECT COALESCE(SUM(amount),0) s FROM fees WHERE payment_status IN ('pending','partial')").fetchone()["s"],
    }
    today = date.today().isoformat()
    att_today = db.execute("SELECT COUNT(*) c FROM attendance WHERE date=? AND status='present'", (today,)).fetchone()["c"]
    att_total = db.execute("SELECT COUNT(*) c FROM attendance WHERE date=?", (today,)).fetchone()["c"]
    stats["attendance_today_pct"] = round((att_today / att_total) * 100, 1) if att_total else None

    recent_admissions = db.execute(
        "SELECT * FROM admissions ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    upcoming_events = db.execute(
        "SELECT * FROM events WHERE event_date >= ? ORDER BY event_date ASC LIMIT 5",
        (date.today().isoformat(),)
    ).fetchall()
    recent_notices = db.execute(
        "SELECT * FROM notices ORDER BY date DESC LIMIT 5"
    ).fetchall()
    db.close()
    return render_template("admin/dashboard.html", stats=stats,
                            recent_admissions=recent_admissions,
                            upcoming_events=upcoming_events,
                            recent_notices=recent_notices)


# ---------------------------------------------------------------------------
# Global search (used by admin & teacher header search bar)
# ---------------------------------------------------------------------------

@app.route("/api/search")
@login_required(["admin", "teacher"])
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    db = get_db()
    rows = db.execute(
        """SELECT s.id, s.full_name, s.roll_number, s.student_uid,
                  c.class_name, c.section
           FROM students s LEFT JOIN classes c ON s.class_id = c.id
           WHERE s.full_name LIKE ? OR s.student_uid LIKE ? OR s.roll_number LIKE ?
                 OR s.father_name LIKE ? OR s.phone LIKE ?
           LIMIT 10""",
        tuple(f"%{q}%" for _ in range(5))
    ).fetchall()
    db.close()
    results = [
        {
            "id": r["id"], "name": r["full_name"], "roll": r["roll_number"],
            "uid": r["student_uid"],
            "class_label": f"{r['class_name']}-{r['section']}" if r["class_name"] else ""
        } for r in rows
    ]
    return jsonify(results)


# ---------------------------------------------------------------------------
# STUDENT MANAGEMENT (admin + teacher access; teacher read-mostly)
# ---------------------------------------------------------------------------

@app.route("/students")
@login_required(["admin", "teacher"])
def student_list():
    q = request.args.get("q", "").strip()
    class_id = request.args.get("class_id", "")
    db = get_db()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    sql = """SELECT s.*, c.class_name, c.section FROM students s
              LEFT JOIN classes c ON s.class_id = c.id WHERE s.status='active'"""
    params = []
    if q:
        sql += """ AND (s.full_name LIKE ? OR s.student_uid LIKE ? OR s.roll_number LIKE ?
                    OR s.father_name LIKE ? OR s.phone LIKE ?)"""
        params += [f"%{q}%"] * 5
    if class_id:
        sql += " AND s.class_id = ?"
        params.append(class_id)
    sql += " ORDER BY c.class_name, s.roll_number"
    students = db.execute(sql, params).fetchall()
    db.close()
    return render_template("students/list.html", students=students, classes=classes, q=q, class_id=class_id)


@app.route("/students/add", methods=["GET", "POST"])
@login_required(["admin"])
def student_add():
    db = get_db()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    if request.method == "POST":
        f = request.form
        photo_path = save_photo(request.files.get("photo"), "students")
        db.execute(
            """INSERT INTO students (
                student_uid, admission_number, roll_number, full_name, class_id, dob, gender,
                photo, blood_group, father_name, mother_name, guardian_name, parent_contact,
                alternate_phone, emergency_contact, aadhaar_number, sssm_id, family_id,
                category, caste, religion, address, city, state, pincode,
                family_annual_income, parent_occupation, medical_issues,
                bank_account_number, bank_ifsc, bank_name, bank_account_holder,
                previous_school, previous_class, admission_date, other_info, email, phone
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                gen_student_uid(), f.get("admission_number"), f.get("roll_number"), f.get("full_name"),
                f.get("class_id") or None, f.get("dob"), f.get("gender"), photo_path, f.get("blood_group"),
                f.get("father_name"), f.get("mother_name"), f.get("guardian_name"), f.get("parent_contact"),
                f.get("alternate_phone"), f.get("emergency_contact"), f.get("aadhaar_number"), f.get("sssm_id"),
                f.get("family_id"), f.get("category"), f.get("caste"), f.get("religion"), f.get("address"),
                f.get("city"), f.get("state"), f.get("pincode"), f.get("family_annual_income"),
                f.get("parent_occupation"), f.get("medical_issues"), f.get("bank_account_number"),
                f.get("bank_ifsc"), f.get("bank_name"), f.get("bank_account_holder"), f.get("previous_school"),
                f.get("previous_class"), f.get("admission_date") or date.today().isoformat(),
                f.get("other_info"), f.get("email"), f.get("phone")
            )
        )
        db.commit()
        db.close()
        flash("Student added successfully.", "success")
        return redirect(url_for("student_list"))
    db.close()
    return render_template("students/form.html", student=None, classes=classes)


@app.route("/students/<int:sid>")
@login_required(["admin", "teacher", "student"])
def student_profile(sid):
    if session.get("role") == "student" and session.get("linked_id") != sid:
        flash("You can only view your own profile.", "error")
        return redirect(url_for("dashboard"))
    db = get_db()
    student = db.execute(
        """SELECT s.*, c.class_name, c.section FROM students s
           LEFT JOIN classes c ON s.class_id = c.id WHERE s.id=?""", (sid,)
    ).fetchone()
    if not student:
        db.close()
        flash("Student not found.", "error")
        return redirect(url_for("student_list"))

    att_total = db.execute("SELECT COUNT(*) c FROM attendance WHERE student_id=?", (sid,)).fetchone()["c"]
    att_present = db.execute("SELECT COUNT(*) c FROM attendance WHERE student_id=? AND status='present'", (sid,)).fetchone()["c"]
    att_pct = round((att_present / att_total) * 100, 1) if att_total else None

    exams = db.execute(
        """SELECT DISTINCT e.id, e.exam_name, e.academic_session, e.exam_date
           FROM results r JOIN exams e ON r.exam_id = e.id
           WHERE r.student_id=? ORDER BY e.exam_date DESC""", (sid,)
    ).fetchall()

    fees = db.execute("SELECT * FROM fees WHERE student_id=? ORDER BY due_date DESC", (sid,)).fetchall()
    timetable = []
    if student["class_id"]:
        timetable = db.execute(
            """SELECT t.*, sub.subject_name, te.full_name as teacher_name
               FROM timetable t
               LEFT JOIN subjects sub ON t.subject_id = sub.id
               LEFT JOIN teachers te ON t.teacher_id = te.id
               WHERE t.class_id=? ORDER BY t.day_of_week, t.period_number""",
            (student["class_id"],)
        ).fetchall()
    db.close()
    return render_template(
        "students/profile.html", student=student, att_pct=att_pct,
        att_total=att_total, att_present=att_present, exams=exams, fees=fees,
        timetable=timetable
    )


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@login_required(["admin"])
def student_edit(sid):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    if not student:
        db.close()
        flash("Student not found.", "error")
        return redirect(url_for("student_list"))
    if request.method == "POST":
        f = request.form
        photo_path = save_photo(request.files.get("photo"), "students")
        if not photo_path:
            photo_path = student["photo"]
        db.execute(
            """UPDATE students SET admission_number=?, roll_number=?, full_name=?, class_id=?, dob=?,
               gender=?, photo=?, blood_group=?, father_name=?, mother_name=?, guardian_name=?,
               parent_contact=?, alternate_phone=?, emergency_contact=?, aadhaar_number=?, sssm_id=?,
               family_id=?, category=?, caste=?, religion=?, address=?, city=?, state=?, pincode=?,
               family_annual_income=?, parent_occupation=?, medical_issues=?, bank_account_number=?,
               bank_ifsc=?, bank_name=?, bank_account_holder=?, previous_school=?, previous_class=?,
               admission_date=?, other_info=?, email=?, phone=? WHERE id=?""",
            (
                f.get("admission_number"), f.get("roll_number"), f.get("full_name"), f.get("class_id") or None,
                f.get("dob"), f.get("gender"), photo_path, f.get("blood_group"), f.get("father_name"),
                f.get("mother_name"), f.get("guardian_name"), f.get("parent_contact"), f.get("alternate_phone"),
                f.get("emergency_contact"), f.get("aadhaar_number"), f.get("sssm_id"), f.get("family_id"),
                f.get("category"), f.get("caste"), f.get("religion"), f.get("address"), f.get("city"),
                f.get("state"), f.get("pincode"), f.get("family_annual_income"), f.get("parent_occupation"),
                f.get("medical_issues"), f.get("bank_account_number"), f.get("bank_ifsc"), f.get("bank_name"),
                f.get("bank_account_holder"), f.get("previous_school"), f.get("previous_class"),
                f.get("admission_date"), f.get("other_info"), f.get("email"), f.get("phone"), sid
            )
        )
        db.commit()
        db.close()
        flash("Student profile updated.", "success")
        return redirect(url_for("student_profile", sid=sid))
    db.close()
    return render_template("students/form.html", student=student, classes=classes)


@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required(["admin"])
def student_delete(sid):
    db = get_db()
    db.execute("UPDATE students SET status='inactive' WHERE id=?", (sid,))
    db.commit()
    db.close()
    flash("Student record deactivated.", "success")
    return redirect(url_for("student_list"))


# ---------------------------------------------------------------------------
# TEACHER MANAGEMENT (admin only manages)
# ---------------------------------------------------------------------------

@app.route("/teachers")
@login_required(["admin"])
def teacher_list():
    db = get_db()
    teachers = db.execute("SELECT * FROM teachers WHERE status='active' ORDER BY full_name").fetchall()
    db.close()
    return render_template("teachers/list.html", teachers=teachers)


@app.route("/teachers/add", methods=["GET", "POST"])
@login_required(["admin"])
def teacher_add():
    if request.method == "POST":
        f = request.form
        photo_path = save_photo(request.files.get("photo"), "teachers")
        db = get_db()
        db.execute(
            """INSERT INTO teachers (teacher_uid, full_name, subject, designation, qualification,
               email, phone, joining_date, address, emergency_contact, photo)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (gen_teacher_uid(), f.get("full_name"), f.get("subject"), f.get("designation"),
             f.get("qualification"), f.get("email"), f.get("phone"),
             f.get("joining_date") or date.today().isoformat(), f.get("address"),
             f.get("emergency_contact"), photo_path)
        )
        db.commit()
        db.close()
        flash("Teacher added successfully.", "success")
        return redirect(url_for("teacher_list"))
    return render_template("teachers/form.html", teacher=None)


@app.route("/teachers/<int:tid>")
@login_required(["admin", "teacher"])
def teacher_profile(tid):
    db = get_db()
    teacher = db.execute("SELECT * FROM teachers WHERE id=?", (tid,)).fetchone()
    db.close()
    if not teacher:
        flash("Teacher not found.", "error")
        return redirect(url_for("teacher_list"))
    return render_template("teachers/profile.html", teacher=teacher)


@app.route("/teachers/<int:tid>/edit", methods=["GET", "POST"])
@login_required(["admin"])
def teacher_edit(tid):
    db = get_db()
    teacher = db.execute("SELECT * FROM teachers WHERE id=?", (tid,)).fetchone()
    if not teacher:
        db.close()
        flash("Teacher not found.", "error")
        return redirect(url_for("teacher_list"))
    if request.method == "POST":
        f = request.form
        photo_path = save_photo(request.files.get("photo"), "teachers")
        if not photo_path:
            photo_path = teacher["photo"]
        db.execute(
            """UPDATE teachers SET full_name=?, subject=?, designation=?, qualification=?, email=?,
               phone=?, joining_date=?, address=?, emergency_contact=?, photo=? WHERE id=?""",
            (f.get("full_name"), f.get("subject"), f.get("designation"), f.get("qualification"),
             f.get("email"), f.get("phone"), f.get("joining_date"), f.get("address"),
             f.get("emergency_contact"), photo_path, tid)
        )
        db.commit()
        db.close()
        flash("Teacher profile updated.", "success")
        return redirect(url_for("teacher_profile", tid=tid))
    db.close()
    return render_template("teachers/form.html", teacher=teacher)


@app.route("/teachers/<int:tid>/delete", methods=["POST"])
@login_required(["admin"])
def teacher_delete(tid):
    db = get_db()
    db.execute("UPDATE teachers SET status='inactive' WHERE id=?", (tid,))
    db.commit()
    db.close()
    flash("Teacher deactivated.", "success")
    return redirect(url_for("teacher_list"))


# ---------------------------------------------------------------------------
# CLASSES
# ---------------------------------------------------------------------------

@app.route("/classes", methods=["GET", "POST"])
@login_required(["admin"])
def class_list():
    db = get_db()
    if request.method == "POST":
        cname = request.form.get("class_name", "").strip()
        sec = request.form.get("section", "").strip().upper()
        if cname and sec:
            try:
                db.execute("INSERT INTO classes (class_name, section) VALUES (?,?)", (cname, sec))
                db.commit()
                flash("Class added.", "success")
            except Exception:
                flash("That class/section already exists.", "error")
        return redirect(url_for("class_list"))
    classes = db.execute(
        """SELECT c.*, (SELECT COUNT(*) FROM students s WHERE s.class_id=c.id AND s.status='active') as student_count
           FROM classes c ORDER BY c.class_name, c.section"""
    ).fetchall()
    db.close()
    return render_template("classes/list.html", classes=classes)


@app.route("/classes/<int:cid>/delete", methods=["POST"])
@login_required(["admin"])
def class_delete(cid):
    db = get_db()
    db.execute("DELETE FROM classes WHERE id=?", (cid,))
    db.commit()
    db.close()
    flash("Class removed.", "success")
    return redirect(url_for("class_list"))


# ---------------------------------------------------------------------------
# SUBJECTS
# ---------------------------------------------------------------------------

@app.route("/subjects", methods=["GET", "POST"])
@login_required(["admin"])
def subject_list():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("subject_name", "").strip()
        if name:
            try:
                db.execute("INSERT INTO subjects (subject_name) VALUES (?)", (name,))
                db.commit()
                flash("Subject added.", "success")
            except Exception:
                flash("That subject already exists.", "error")
        return redirect(url_for("subject_list"))
    subjects = db.execute("SELECT * FROM subjects ORDER BY subject_name").fetchall()
    db.close()
    return render_template("subjects/list.html", subjects=subjects)


@app.route("/subjects/<int:sub_id>/delete", methods=["POST"])
@login_required(["admin"])
def subject_delete(sub_id):
    db = get_db()
    db.execute("DELETE FROM subjects WHERE id=?", (sub_id,))
    db.commit()
    db.close()
    flash("Subject removed.", "success")
    return redirect(url_for("subject_list"))


# ---------------------------------------------------------------------------
# EXAMS
# ---------------------------------------------------------------------------

@app.route("/exams")
@login_required(["admin", "teacher"])
def exam_list():
    db = get_db()
    exams = db.execute(
        """SELECT e.*, c.class_name, c.section FROM exams e
           LEFT JOIN classes c ON e.class_id = c.id ORDER BY e.exam_date DESC"""
    ).fetchall()
    db.close()
    return render_template("exams/list.html", exams=exams)


@app.route("/exams/add", methods=["GET", "POST"])
@login_required(["admin"])
def exam_add():
    db = get_db()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    subjects = db.execute("SELECT * FROM subjects ORDER BY subject_name").fetchall()
    if request.method == "POST":
        f = request.form
        cur = db.execute(
            "INSERT INTO exams (exam_name, academic_session, class_id, exam_date) VALUES (?,?,?,?) RETURNING id",
            (f.get("exam_name"), f.get("academic_session"), f.get("class_id") or None, f.get("exam_date"))
        )
        exam_id = cur.fetchone()["id"]
        subject_ids = request.form.getlist("subject_ids")
        for subid in subject_ids:
            max_marks = request.form.get(f"max_marks_{subid}", "100")
            db.execute(
                "INSERT INTO exam_subjects (exam_id, subject_id, max_marks) VALUES (?,?,?) "
                "ON CONFLICT (exam_id, subject_id) DO NOTHING",
                (exam_id, int(subid), max_marks or 100)
            )
        db.commit()
        db.close()
        flash("Exam created successfully.", "success")
        return redirect(url_for("exam_list"))
    db.close()
    return render_template("exams/form.html", classes=classes, subjects=subjects)


@app.route("/exams/<int:eid>/delete", methods=["POST"])
@login_required(["admin"])
def exam_delete(eid):
    db = get_db()
    db.execute("DELETE FROM exams WHERE id=?", (eid,))
    db.commit()
    db.close()
    flash("Exam and its results removed.", "success")
    return redirect(url_for("exam_list"))


# ---------------------------------------------------------------------------
# ATTENDANCE
# ---------------------------------------------------------------------------

@app.route("/attendance", methods=["GET", "POST"])
@login_required(["admin", "teacher"])
def attendance():
    db = get_db()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    class_id = request.args.get("class_id") or request.form.get("class_id")
    att_date = request.args.get("date") or request.form.get("date") or date.today().isoformat()

    if request.method == "POST" and class_id:
        students_in_class = db.execute(
            "SELECT id FROM students WHERE class_id=? AND status='active'", (class_id,)
        ).fetchall()
        for s in students_in_class:
            status = request.form.get(f"status_{s['id']}", "absent")
            db.execute(
                """INSERT INTO attendance (student_id, class_id, date, status) VALUES (?,?,?,?)
                   ON CONFLICT(student_id, date) DO UPDATE SET status=excluded.status, class_id=excluded.class_id""",
                (s["id"], class_id, att_date, status)
            )
        db.commit()
        flash("Attendance saved for the class.", "success")
        db.close()
        return redirect(url_for("attendance", class_id=class_id, date=att_date))

    students = []
    existing = {}
    if class_id:
        students = db.execute(
            "SELECT * FROM students WHERE class_id=? AND status='active' ORDER BY roll_number", (class_id,)
        ).fetchall()
        rows = db.execute(
            "SELECT student_id, status FROM attendance WHERE class_id=? AND date=?", (class_id, att_date)
        ).fetchall()
        existing = {r["student_id"]: r["status"] for r in rows}
    db.close()
    return render_template(
        "attendance/mark.html", classes=classes, students=students,
        class_id=class_id, att_date=att_date, existing=existing
    )


@app.route("/attendance/reports")
@login_required(["admin", "teacher"])
def attendance_reports():
    db = get_db()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    class_id = request.args.get("class_id", "")
    report = []
    if class_id:
        students = db.execute(
            "SELECT * FROM students WHERE class_id=? AND status='active' ORDER BY roll_number", (class_id,)
        ).fetchall()
        for s in students:
            total = db.execute("SELECT COUNT(*) c FROM attendance WHERE student_id=?", (s["id"],)).fetchone()["c"]
            present = db.execute(
                "SELECT COUNT(*) c FROM attendance WHERE student_id=? AND status='present'", (s["id"],)
            ).fetchone()["c"]
            pct = round((present / total) * 100, 1) if total else 0
            report.append({"student": s, "total": total, "present": present,
                            "absent": total - present, "pct": pct})
    db.close()
    return render_template("attendance/reports.html", classes=classes, class_id=class_id, report=report)


# ---------------------------------------------------------------------------
# MARKS ENTRY
# ---------------------------------------------------------------------------

@app.route("/marks", methods=["GET", "POST"])
@login_required(["admin", "teacher"])
def marks_entry():
    db = get_db()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    class_id = request.args.get("class_id") or request.form.get("class_id")
    student_id = request.args.get("student_id") or request.form.get("student_id")
    exam_id = request.args.get("exam_id") or request.form.get("exam_id")

    students = []
    if class_id:
        students = db.execute(
            "SELECT * FROM students WHERE class_id=? AND status='active' ORDER BY roll_number", (class_id,)
        ).fetchall()

    exams = []
    if class_id:
        exams = db.execute("SELECT * FROM exams WHERE class_id=? ORDER BY exam_date DESC", (class_id,)).fetchall()

    exam_subjects = []
    student = None
    existing_marks = {}
    if student_id and exam_id:
        student = db.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
        exam_subjects = db.execute(
            """SELECT es.*, sub.subject_name FROM exam_subjects es
               JOIN subjects sub ON es.subject_id = sub.id
               WHERE es.exam_id=? ORDER BY sub.subject_name""", (exam_id,)
        ).fetchall()
        rows = db.execute(
            "SELECT subject_id, marks_obtained FROM results WHERE student_id=? AND exam_id=?",
            (student_id, exam_id)
        ).fetchall()
        existing_marks = {r["subject_id"]: r["marks_obtained"] for r in rows}

    if request.method == "POST" and student_id and exam_id:
        subj_rows = db.execute("SELECT * FROM exam_subjects WHERE exam_id=?", (exam_id,)).fetchall()
        for row in subj_rows:
            raw = request.form.get(f"marks_{row['subject_id']}", "").strip()
            if raw == "":
                continue
            try:
                val = float(raw)
            except ValueError:
                continue
            val = max(0, min(val, row["max_marks"]))
            db.execute(
                """INSERT INTO results (student_id, exam_id, subject_id, marks_obtained) VALUES (?,?,?,?)
                   ON CONFLICT(student_id, exam_id, subject_id) DO UPDATE SET marks_obtained=excluded.marks_obtained""",
                (student_id, exam_id, row["subject_id"], val)
            )
        db.commit()
        flash("Result saved successfully.", "success")
        db.close()
        return redirect(url_for("marks_entry", class_id=class_id, student_id=student_id, exam_id=exam_id))

    db.close()
    return render_template(
        "marks/entry.html", classes=classes, students=students, exams=exams,
        class_id=class_id, student_id=student_id, exam_id=exam_id,
        exam_subjects=exam_subjects, student=student, existing_marks=existing_marks
    )


# ---------------------------------------------------------------------------
# MARKSHEET GENERATOR
# ---------------------------------------------------------------------------

@app.route("/marksheet", methods=["GET"])
@login_required(["admin", "teacher", "student"])
def marksheet_select():
    db = get_db()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    if session.get("role") == "student":
        sid = session.get("linked_id")
        exams = db.execute(
            """SELECT DISTINCT e.* FROM exams e JOIN results r ON r.exam_id = e.id
               WHERE r.student_id=? ORDER BY e.exam_date DESC""", (sid,)
        ).fetchall()
        db.close()
        return render_template("marks/marksheet_select.html", classes=classes, student_only=True,
                                sid=sid, exams=exams)
    db.close()
    return render_template("marks/marksheet_select.html", classes=classes, student_only=False)


@app.route("/marksheet/options")
@login_required(["admin", "teacher", "student"])
def marksheet_options():
    class_id = request.args.get("class_id")
    db = get_db()
    students = db.execute(
        "SELECT id, full_name, roll_number FROM students WHERE class_id=? AND status='active' ORDER BY roll_number",
        (class_id,)
    ).fetchall()
    exams = db.execute(
        "SELECT id, exam_name FROM exams WHERE class_id=? ORDER BY exam_date DESC", (class_id,)
    ).fetchall()
    db.close()
    return jsonify({
        "students": [dict(s) for s in students],
        "exams": [dict(e) for e in exams]
    })


@app.route("/marksheet/view")
@login_required(["admin", "teacher", "student"])
def marksheet_view():
    student_id = request.args.get("student_id", type=int)
    exam_id = request.args.get("exam_id", type=int)
    if session.get("role") == "student" and session.get("linked_id") != student_id:
        flash("You can only view your own marksheet.", "error")
        return redirect(url_for("dashboard"))
    if not student_id or not exam_id:
        flash("Please select a student and an exam.", "error")
        return redirect(url_for("marksheet_select"))

    db = get_db()
    student = db.execute(
        """SELECT s.*, c.class_name, c.section FROM students s
           LEFT JOIN classes c ON s.class_id = c.id WHERE s.id=?""", (student_id,)
    ).fetchone()
    exam = db.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
    rows = db.execute(
        """SELECT sub.subject_name, es.max_marks, r.marks_obtained
           FROM exam_subjects es
           JOIN subjects sub ON es.subject_id = sub.id
           LEFT JOIN results r ON r.subject_id = es.subject_id AND r.exam_id = es.exam_id AND r.student_id=?
           WHERE es.exam_id=? ORDER BY sub.subject_name""",
        (student_id, exam_id)
    ).fetchall()

    total_obtained = sum((r["marks_obtained"] or 0) for r in rows)
    total_max = sum(r["max_marks"] for r in rows)
    overall_pct = round((total_obtained / total_max) * 100, 1) if total_max else 0
    subject_rows = []
    fail = False
    for r in rows:
        obt = r["marks_obtained"]
        pct = round((obt / r["max_marks"]) * 100, 1) if (obt is not None and r["max_marks"]) else None
        grade = calc_grade(pct)
        if pct is not None and pct < 33:
            fail = True
        subject_rows.append({"name": r["subject_name"], "max": r["max_marks"],
                              "obtained": obt, "pct": pct, "grade": grade})

    att_total = db.execute("SELECT COUNT(*) c FROM attendance WHERE student_id=?", (student_id,)).fetchone()["c"]
    att_present = db.execute(
        "SELECT COUNT(*) c FROM attendance WHERE student_id=? AND status='present'", (student_id,)
    ).fetchone()["c"]
    att_pct = round((att_present / att_total) * 100, 1) if att_total else None
    db.close()

    return render_template(
        "marks/marksheet_print.html", student=student, exam=exam, subject_rows=subject_rows,
        total_obtained=total_obtained, total_max=total_max, overall_pct=overall_pct,
        overall_grade=calc_grade(overall_pct), result_status=("FAIL" if fail else "PASS"),
        att_pct=att_pct, today=date.today().strftime("%d-%m-%Y")
    )


# ---------------------------------------------------------------------------
# QUESTION PAPER GENERATOR
# ---------------------------------------------------------------------------

@app.route("/question-papers")
@login_required(["admin", "teacher"])
def qp_list():
    db = get_db()
    papers = db.execute(
        """SELECT qp.*, c.class_name, c.section, sub.subject_name FROM question_papers qp
           LEFT JOIN classes c ON qp.class_id = c.id
           LEFT JOIN subjects sub ON qp.subject_id = sub.id
           ORDER BY qp.created_at DESC"""
    ).fetchall()
    db.close()
    return render_template("qp/list.html", papers=papers)


@app.route("/question-papers/add", methods=["GET", "POST"])
@login_required(["admin", "teacher"])
def qp_add():
    db = get_db()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    subjects = db.execute("SELECT * FROM subjects ORDER BY subject_name").fetchall()
    exams = db.execute("SELECT * FROM exams ORDER BY exam_date DESC").fetchall()
    if request.method == "POST":
        f = request.form
        cur = db.execute(
            """INSERT INTO question_papers (title, class_id, subject_id, exam_id, academic_session,
               total_marks, duration, instructions) VALUES (?,?,?,?,?,?,?,?) RETURNING id""",
            (f.get("title"), f.get("class_id") or None, f.get("subject_id") or None,
             f.get("exam_id") or None, f.get("academic_session"), f.get("total_marks") or 0,
             f.get("duration"), f.get("instructions"))
        )
        db.commit()
        qp_id = cur.fetchone()["id"]
        db.close()
        flash("Question paper created. Now add questions.", "success")
        return redirect(url_for("qp_builder", qp_id=qp_id))
    db.close()
    return render_template("qp/form.html", classes=classes, subjects=subjects, exams=exams)


@app.route("/question-papers/<int:qp_id>", methods=["GET", "POST"])
@login_required(["admin", "teacher"])
def qp_builder(qp_id):
    db = get_db()
    paper = db.execute("SELECT * FROM question_papers WHERE id=?", (qp_id,)).fetchone()
    if not paper:
        db.close()
        flash("Question paper not found.", "error")
        return redirect(url_for("qp_list"))
    if request.method == "POST":
        qtype = request.form.get("question_type")
        qtext = request.form.get("question_text")
        marks = request.form.get("marks") or 1
        if qtext:
            max_order = db.execute(
                "SELECT COALESCE(MAX(order_index),0) m FROM questions WHERE question_paper_id=?", (qp_id,)
            ).fetchone()["m"]
            db.execute(
                """INSERT INTO questions (question_paper_id, question_type, question_text, marks, order_index)
                   VALUES (?,?,?,?,?)""",
                (qp_id, qtype, qtext, marks, max_order + 1)
            )
            db.commit()
            flash("Question added.", "success")
        db.close()
        return redirect(url_for("qp_builder", qp_id=qp_id))
    questions = db.execute(
        "SELECT * FROM questions WHERE question_paper_id=? ORDER BY order_index", (qp_id,)
    ).fetchall()
    total_q_marks = sum(q["marks"] for q in questions)
    db.close()
    return render_template("qp/builder.html", paper=paper, questions=questions, total_q_marks=total_q_marks)


@app.route("/question-papers/<int:qp_id>/questions/<int:q_id>/delete", methods=["POST"])
@login_required(["admin", "teacher"])
def qp_question_delete(qp_id, q_id):
    db = get_db()
    db.execute("DELETE FROM questions WHERE id=? AND question_paper_id=?", (q_id, qp_id))
    db.commit()
    db.close()
    flash("Question removed.", "success")
    return redirect(url_for("qp_builder", qp_id=qp_id))


@app.route("/question-papers/<int:qp_id>/print")
@login_required(["admin", "teacher"])
def qp_print(qp_id):
    db = get_db()
    paper = db.execute(
        """SELECT qp.*, c.class_name, c.section, sub.subject_name FROM question_papers qp
           LEFT JOIN classes c ON qp.class_id = c.id
           LEFT JOIN subjects sub ON qp.subject_id = sub.id
           WHERE qp.id=?""", (qp_id,)
    ).fetchone()
    questions = db.execute(
        "SELECT * FROM questions WHERE question_paper_id=? ORDER BY order_index", (qp_id,)
    ).fetchall()
    db.close()
    if not paper:
        flash("Question paper not found.", "error")
        return redirect(url_for("qp_list"))
    return render_template("qp/print.html", paper=paper, questions=questions,
                            today=date.today().strftime("%d-%m-%Y"))


@app.route("/question-papers/<int:qp_id>/delete", methods=["POST"])
@login_required(["admin", "teacher"])
def qp_delete(qp_id):
    db = get_db()
    db.execute("DELETE FROM question_papers WHERE id=?", (qp_id,))
    db.commit()
    db.close()
    flash("Question paper deleted.", "success")
    return redirect(url_for("qp_list"))


# ---------------------------------------------------------------------------
# FEES
# ---------------------------------------------------------------------------

@app.route("/fees", methods=["GET", "POST"])
@login_required(["admin"])
def fees_list():
    db = get_db()
    if request.method == "POST":
        f = request.form
        status = f.get("payment_status", "pending")
        receipt = gen_receipt_number() if status == "paid" else None
        db.execute(
            """INSERT INTO fees (student_id, amount, payment_status, due_date, payment_date, receipt_number, remarks)
               VALUES (?,?,?,?,?,?,?)""",
            (f.get("student_id"), f.get("amount"), status, f.get("due_date"),
             f.get("payment_date") if status == "paid" else None, receipt, f.get("remarks"))
        )
        db.commit()
        db.close()
        flash("Fee record added.", "success")
        return redirect(url_for("fees_list"))
    students = db.execute("SELECT * FROM students WHERE status='active' ORDER BY full_name").fetchall()
    fees = db.execute(
        """SELECT f.*, s.full_name, s.student_uid FROM fees f
           JOIN students s ON f.student_id = s.id ORDER BY f.due_date DESC"""
    ).fetchall()
    totals = {
        "collected": db.execute("SELECT COALESCE(SUM(amount),0) s FROM fees WHERE payment_status='paid'").fetchone()["s"],
        "pending": db.execute("SELECT COALESCE(SUM(amount),0) s FROM fees WHERE payment_status IN ('pending','partial')").fetchone()["s"],
    }
    db.close()
    return render_template("fees/list.html", students=students, fees=fees, totals=totals)


@app.route("/fees/<int:fee_id>/mark-paid", methods=["POST"])
@login_required(["admin"])
def fees_mark_paid(fee_id):
    db = get_db()
    db.execute(
        "UPDATE fees SET payment_status='paid', payment_date=?, receipt_number=? WHERE id=?",
        (date.today().isoformat(), gen_receipt_number(), fee_id)
    )
    db.commit()
    db.close()
    flash("Fee marked as paid.", "success")
    return redirect(url_for("fees_list"))


@app.route("/fees/<int:fee_id>/receipt")
@login_required(["admin", "student"])
def fees_receipt(fee_id):
    db = get_db()
    fee = db.execute(
        """SELECT f.*, s.full_name, s.student_uid, s.roll_number, c.class_name, c.section
           FROM fees f JOIN students s ON f.student_id = s.id
           LEFT JOIN classes c ON s.class_id = c.id WHERE f.id=?""", (fee_id,)
    ).fetchone()
    db.close()
    if not fee:
        flash("Receipt not found.", "error")
        return redirect(url_for("dashboard"))
    if session.get("role") == "student" and session.get("linked_id") != fee["student_id"]:
        flash("You can only view your own receipts.", "error")
        return redirect(url_for("dashboard"))
    return render_template("fees/receipt.html", fee=fee, today=date.today().strftime("%d-%m-%Y"))


# ---------------------------------------------------------------------------
# TIMETABLE
# ---------------------------------------------------------------------------

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


@app.route("/timetable", methods=["GET", "POST"])
@login_required(["admin", "teacher", "student"])
def timetable_view():
    db = get_db()
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    subjects = db.execute("SELECT * FROM subjects ORDER BY subject_name").fetchall()
    teachers = db.execute("SELECT * FROM teachers WHERE status='active' ORDER BY full_name").fetchall()

    if session.get("role") == "student":
        student = db.execute("SELECT * FROM students WHERE id=?", (session.get("linked_id"),)).fetchone()
        class_id = student["class_id"] if student else None
    else:
        class_id = request.args.get("class_id") or request.form.get("class_id")

    if request.method == "POST" and session.get("role") == "admin" and class_id:
        day = request.form.get("day_of_week")
        period = request.form.get("period_number")
        subject_id = request.form.get("subject_id") or None
        teacher_id = request.form.get("teacher_id") or None
        db.execute("DELETE FROM timetable WHERE class_id=? AND day_of_week=? AND period_number=?",
                   (class_id, day, period))
        if subject_id:
            db.execute(
                "INSERT INTO timetable (class_id, day_of_week, period_number, subject_id, teacher_id) VALUES (?,?,?,?,?)",
                (class_id, day, period, subject_id, teacher_id)
            )
        db.commit()
        flash("Timetable updated.", "success")
        db.close()
        return redirect(url_for("timetable_view", class_id=class_id))

    grid = {}
    if class_id:
        rows = db.execute(
            """SELECT t.*, sub.subject_name, te.full_name as teacher_name FROM timetable t
               LEFT JOIN subjects sub ON t.subject_id = sub.id
               LEFT JOIN teachers te ON t.teacher_id = te.id
               WHERE t.class_id=?""", (class_id,)
        ).fetchall()
        for r in rows:
            grid[(r["day_of_week"], r["period_number"])] = r
    db.close()
    return render_template(
        "timetable/view.html", classes=classes, subjects=subjects, teachers=teachers,
        class_id=class_id, days=DAYS, periods=range(1, 9), grid=grid
    )


# ---------------------------------------------------------------------------
# NOTICES
# ---------------------------------------------------------------------------

@app.route("/notices", methods=["GET", "POST"])
@login_required(["admin", "teacher", "student"])
def notice_list():
    db = get_db()
    if request.method == "POST" and session.get("role") == "admin":
        db.execute(
            "INSERT INTO notices (title, content, date) VALUES (?,?,?)",
            (request.form.get("title"), request.form.get("content"),
             request.form.get("date") or date.today().isoformat())
        )
        db.commit()
        db.close()
        flash("Notice published.", "success")
        return redirect(url_for("notice_list"))
    notices = db.execute("SELECT * FROM notices ORDER BY date DESC, id DESC").fetchall()
    db.close()
    return render_template("notices/list.html", notices=notices)


@app.route("/notices/<int:nid>/delete", methods=["POST"])
@login_required(["admin"])
def notice_delete(nid):
    db = get_db()
    db.execute("DELETE FROM notices WHERE id=?", (nid,))
    db.commit()
    db.close()
    flash("Notice deleted.", "success")
    return redirect(url_for("notice_list"))


# ---------------------------------------------------------------------------
# EVENTS
# ---------------------------------------------------------------------------

@app.route("/events", methods=["GET", "POST"])
@login_required(["admin", "teacher", "student"])
def event_list():
    db = get_db()
    if request.method == "POST" and session.get("role") == "admin":
        db.execute(
            "INSERT INTO events (title, description, event_date) VALUES (?,?,?)",
            (request.form.get("title"), request.form.get("description"), request.form.get("event_date"))
        )
        db.commit()
        db.close()
        flash("Event added.", "success")
        return redirect(url_for("event_list"))
    events = db.execute("SELECT * FROM events ORDER BY event_date ASC").fetchall()
    db.close()
    return render_template("events/list.html", events=events)


@app.route("/events/<int:eid>/delete", methods=["POST"])
@login_required(["admin"])
def event_delete(eid):
    db = get_db()
    db.execute("DELETE FROM events WHERE id=?", (eid,))
    db.commit()
    db.close()
    flash("Event deleted.", "success")
    return redirect(url_for("event_list"))


# ---------------------------------------------------------------------------
# ADMISSIONS (applications received via public form)
# ---------------------------------------------------------------------------

@app.route("/admissions")
@login_required(["admin"])
def admission_list():
    db = get_db()
    status = request.args.get("status", "")
    sql = "SELECT * FROM admissions"
    params = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    apps = db.execute(sql, params).fetchall()
    db.close()
    return render_template("admissions/list.html", apps=apps, status=status)


@app.route("/admissions/<int:aid>/<action>", methods=["POST"])
@login_required(["admin"])
def admission_update(aid, action):
    if action not in ("approve", "reject"):
        return redirect(url_for("admission_list"))
    status = "approved" if action == "approve" else "rejected"
    db = get_db()
    db.execute("UPDATE admissions SET status=? WHERE id=?", (status, aid))
    db.commit()
    db.close()
    flash(f"Application {status}.", "success")
    return redirect(url_for("admission_list"))


# ---------------------------------------------------------------------------
# CONTACT MESSAGES
# ---------------------------------------------------------------------------

@app.route("/messages")
@login_required(["admin"])
def message_list():
    db = get_db()
    msgs = db.execute("SELECT * FROM messages ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template("messages/list.html", msgs=msgs)


# ---------------------------------------------------------------------------
# REPORTS
# ---------------------------------------------------------------------------

@app.route("/reports")
@login_required(["admin"])
def reports_home():
    return render_template("reports/home.html")


@app.route("/reports/students")
@login_required(["admin"])
def report_students():
    db = get_db()
    class_id = request.args.get("class_id", "")
    classes = db.execute("SELECT * FROM classes ORDER BY class_name, section").fetchall()
    sql = """SELECT s.*, c.class_name, c.section FROM students s
             LEFT JOIN classes c ON s.class_id = c.id WHERE s.status='active'"""
    params = []
    if class_id:
        sql += " AND s.class_id=?"
        params.append(class_id)
    sql += " ORDER BY c.class_name, s.roll_number"
    students = db.execute(sql, params).fetchall()
    db.close()
    return render_template("reports/students.html", students=students, classes=classes, class_id=class_id)


@app.route("/reports/teachers")
@login_required(["admin"])
def report_teachers():
    db = get_db()
    teachers = db.execute("SELECT * FROM teachers WHERE status='active' ORDER BY full_name").fetchall()
    db.close()
    return render_template("reports/teachers.html", teachers=teachers)


@app.route("/reports/results")
@login_required(["admin"])
def report_results():
    db = get_db()
    exams = db.execute("SELECT * FROM exams ORDER BY exam_date DESC").fetchall()
    exam_id = request.args.get("exam_id", "")
    summary = []
    if exam_id:
        students = db.execute(
            """SELECT DISTINCT s.* FROM students s JOIN results r ON r.student_id = s.id
               WHERE r.exam_id=?""", (exam_id,)
        ).fetchall()
        for s in students:
            rows = db.execute(
                """SELECT es.max_marks, r.marks_obtained FROM exam_subjects es
                   LEFT JOIN results r ON r.subject_id=es.subject_id AND r.exam_id=es.exam_id AND r.student_id=?
                   WHERE es.exam_id=?""", (s["id"], exam_id)
            ).fetchall()
            total_obt = sum((r["marks_obtained"] or 0) for r in rows)
            total_max = sum(r["max_marks"] for r in rows)
            pct = round((total_obt / total_max) * 100, 1) if total_max else 0
            summary.append({"student": s, "total_obt": total_obt, "total_max": total_max,
                             "pct": pct, "grade": calc_grade(pct)})
        summary.sort(key=lambda x: -x["pct"])
    db.close()
    return render_template("reports/results.html", exams=exams, exam_id=exam_id, summary=summary)


@app.route("/reports/fees")
@login_required(["admin"])
def report_fees():
    db = get_db()
    fees = db.execute(
        """SELECT f.*, s.full_name, s.student_uid FROM fees f
           JOIN students s ON f.student_id = s.id ORDER BY f.due_date DESC"""
    ).fetchall()
    db.close()
    return render_template("reports/fees.html", fees=fees)


@app.route("/reports/admissions")
@login_required(["admin"])
def report_admissions():
    db = get_db()
    apps = db.execute("SELECT * FROM admissions ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template("reports/admissions.html", apps=apps)


# ---------------------------------------------------------------------------
# WEBSITE CONTENT MANAGEMENT (admin only)
# ---------------------------------------------------------------------------

@app.route("/website/settings", methods=["GET", "POST"])
@login_required(["admin"])
def website_settings():
    db = get_db()
    if request.method == "POST":
        values = {k: request.form.get(k, "").strip() for k in ["tagline", "address", "phone", "email"]}
        db.execute("""INSERT INTO site_settings (id, tagline, address, phone, email)
                       VALUES (1,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET tagline=excluded.tagline, address=excluded.address,
                       phone=excluded.phone, email=excluded.email""",
                   (values["tagline"], values["address"], values["phone"], values["email"]))
        db.commit(); db.close()
        flash("Website details updated.", "success")
        return redirect(url_for("website_settings"))
    row = db.execute("SELECT * FROM site_settings WHERE id=1").fetchone()
    db.close()
    return render_template("website/settings.html", site_settings=row)


@app.route("/website")
@login_required(["admin"])
def website_manager():
    db = get_db()
    album_count = db.execute("SELECT COUNT(*) c FROM gallery_albums").fetchone()["c"]
    photo_count = db.execute("SELECT COUNT(*) c FROM gallery_photos").fetchone()["c"]
    notice_count = db.execute("SELECT COUNT(*) c FROM notices").fetchone()["c"]
    event_count = db.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
    social = db.execute("SELECT * FROM social_links WHERE id=1").fetchone()
    db.close()
    return render_template("website/manager.html", album_count=album_count, photo_count=photo_count,
                           notice_count=notice_count, event_count=event_count, social=social)


@app.route("/website/social", methods=["GET", "POST"])
@login_required(["admin"])
def social_settings():
    db = get_db()
    if request.method == "POST":
        values = {k: request.form.get(k, "").strip() for k in ["instagram", "youtube", "facebook", "whatsapp"]}
        invalid = [k for k, v in values.items() if v and not is_safe_external_url(v)]
        if invalid:
            db.close()
            flash("Social links must use http:// or https:// URLs.", "error")
            return redirect(url_for("social_settings"))
        db.execute("""INSERT INTO social_links (id, instagram, youtube, facebook, whatsapp)
                       VALUES (1,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET instagram=excluded.instagram, youtube=excluded.youtube,
                       facebook=excluded.facebook, whatsapp=excluded.whatsapp""",
                   (values["instagram"], values["youtube"], values["facebook"], values["whatsapp"]))
        db.commit(); db.close()
        flash("Social media links updated.", "success")
        return redirect(url_for("social_settings"))
    social = db.execute("SELECT * FROM social_links WHERE id=1").fetchone()
    db.close()
    return render_template("website/social.html", social=social)


@app.route("/website/gallery", methods=["GET", "POST"])
@login_required(["admin"])
def gallery_manage():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        event_date = request.form.get("event_date", "").strip() or date.today().isoformat()
        description = request.form.get("description", "").strip()
        files = request.files.getlist("photos")
        if not title:
            flash("Please enter an album name.", "error")
        elif not files or not any(f.filename for f in files):
            flash("Please choose at least one photo.", "error")
        elif len([f for f in files if f.filename]) > MAX_GALLERY_PHOTOS:
            flash(f"Please upload no more than {MAX_GALLERY_PHOTOS} photos at once.", "error")
        else:
            cur = db.execute(
                "INSERT INTO gallery_albums (title, event_date, description) VALUES (?,?,?) RETURNING id",
                (title, event_date, description)
            )
            album_id = cur.fetchone()["id"]
            saved = 0
            for f in files:
                path = save_photo(f, "gallery")
                if path:
                    db.execute("INSERT INTO gallery_photos (album_id, photo_path, caption) VALUES (?,?,?)",
                               (album_id, path, ""))
                    saved += 1
            if saved:
                db.commit(); flash(f"Album published with {saved} photo(s).", "success")
            else:
                db.execute("DELETE FROM gallery_albums WHERE id=?", (album_id,)); db.commit()
                flash("No valid image files were uploaded.", "error")
        db.close()
        return redirect(url_for("gallery_manage"))
    albums = db.execute("""SELECT a.*, (SELECT COUNT(*) FROM gallery_photos p WHERE p.album_id=a.id) photo_count
                           FROM gallery_albums a ORDER BY a.event_date DESC, a.id DESC""").fetchall()
    db.close()
    return render_template("website/gallery.html", albums=albums)


@app.route("/website/gallery/<int:album_id>/delete", methods=["POST"])
@login_required(["admin"])
def gallery_delete(album_id):
    db = get_db()
    photos = db.execute("SELECT photo_path FROM gallery_photos WHERE album_id=?", (album_id,)).fetchall()
    for row in photos:
        path = row["photo_path"]
        if path and path.startswith(("http://", "https://")):
            # Cloudinary — delete by public_id
            if CLOUDINARY_CONFIGURED:
                try:
                    parts = path.split("/upload/", 1)
                    if len(parts) == 2:
                        public_id = parts[1].rsplit(".", 1)[0]
                        # Strip version prefix (v123456/)
                        if "/" in public_id and public_id.split("/")[0].startswith("v"):
                            public_id = public_id.split("/", 1)[1]
                        cloudinary.uploader.destroy(public_id)
                except Exception as exc:
                    app.logger.warning("Cloudinary delete failed: %s", exc)
        else:
            # Local disk
            try:
                os.remove(os.path.join(BASE_DIR, "static", path))
            except OSError:
                pass
    db.execute("DELETE FROM gallery_albums WHERE id=?", (album_id,))
    db.commit()
    db.close()
    flash("Gallery album deleted.", "success")
    return redirect(url_for("gallery_manage"))


# ---------------------------------------------------------------------------
# ROLE DASHBOARDS: teacher & student
# ---------------------------------------------------------------------------

@app.route("/teacher/dashboard")
@login_required(["teacher"])
def teacher_dashboard():
    db = get_db()
    teacher = db.execute("SELECT * FROM teachers WHERE id=?", (session.get("linked_id"),)).fetchone()
    total_students = db.execute("SELECT COUNT(*) c FROM students WHERE status='active'").fetchone()["c"]
    upcoming_exams = db.execute(
        "SELECT * FROM exams WHERE exam_date >= ? ORDER BY exam_date LIMIT 5",
        (date.today().isoformat(),)
    ).fetchall()
    notices = db.execute("SELECT * FROM notices ORDER BY date DESC LIMIT 5").fetchall()
    db.close()
    return render_template("teacher/dashboard.html", teacher=teacher, total_students=total_students,
                            upcoming_exams=upcoming_exams, notices=notices)


@app.route("/student/dashboard")
@login_required(["student"])
def student_dashboard():
    db = get_db()
    student = db.execute(
        """SELECT s.*, c.class_name, c.section FROM students s
           LEFT JOIN classes c ON s.class_id = c.id WHERE s.id=?""",
        (session.get("linked_id"),)
    ).fetchone()
    att_total = db.execute("SELECT COUNT(*) c FROM attendance WHERE student_id=?", (student["id"],)).fetchone()["c"]
    att_present = db.execute(
        "SELECT COUNT(*) c FROM attendance WHERE student_id=? AND status='present'", (student["id"],)
    ).fetchone()["c"]
    att_pct = round((att_present / att_total) * 100, 1) if att_total else None
    notices = db.execute("SELECT * FROM notices ORDER BY date DESC LIMIT 5").fetchall()
    events = db.execute(
        "SELECT * FROM events WHERE event_date >= ? ORDER BY event_date LIMIT 5",
        (date.today().isoformat(),)
    ).fetchall()
    fees = db.execute("SELECT * FROM fees WHERE student_id=? ORDER BY due_date DESC", (student["id"],)).fetchall()
    db.close()
    return render_template("student/dashboard.html", student=student, att_pct=att_pct,
                            notices=notices, events=events, fees=fees)


# ---------------------------------------------------------------------------
# ADMIN: account security
# ---------------------------------------------------------------------------

@app.route("/admin/security", methods=["GET", "POST"])
@login_required(["admin"])
def admin_security():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id=?", (session.get("user_id"),)).fetchone()
        if not user or not check_password_hash(user["password_hash"], current):
            db.close(); flash("Current password is incorrect.", "error"); return redirect(url_for("admin_security"))
        if len(new_password) < 10:
            db.close(); flash("Use a new password with at least 10 characters.", "error"); return redirect(url_for("admin_security"))
        if new_password != confirm:
            db.close(); flash("The new passwords do not match.", "error"); return redirect(url_for("admin_security"))
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_password), user["id"]))
        db.commit(); db.close()
        session.pop("must_change_password", None)
        session["csrf_token"] = secrets.token_urlsafe(32)
        flash("Your admin password has been changed successfully.", "success")
        return redirect(url_for("admin_security"))
    return render_template("accounts/security.html")


# ---------------------------------------------------------------------------
# ADMIN: create login accounts for teachers / students
# ---------------------------------------------------------------------------

@app.route("/accounts", methods=["GET", "POST"])
@login_required(["admin"])
def accounts():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role")
        linked_id = request.form.get("linked_id") or None
        if username and password and role:
            if len(password) < 8:
                flash("Passwords must be at least 8 characters long.", "error")
                db.close()
                return redirect(url_for("accounts"))
            if role not in {"admin", "teacher", "student"}:
                flash("Invalid account role.", "error")
                db.close()
                return redirect(url_for("accounts"))
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash, role, linked_id) VALUES (?,?,?,?)",
                    (username, generate_password_hash(password), role, linked_id)
                )
                db.commit()
                flash("Login account created.", "success")
            except Exception:
                flash("That username already exists.", "error")
        return redirect(url_for("accounts"))
    users = db.execute("SELECT * FROM users ORDER BY role, username").fetchall()
    teachers = db.execute("SELECT * FROM teachers WHERE status='active' ORDER BY full_name").fetchall()
    students = db.execute("SELECT * FROM students WHERE status='active' ORDER BY full_name").fetchall()
    db.close()
    return render_template("accounts/list.html", users=users, teachers=teachers, students=students)


@app.route("/accounts/<int:uid>/delete", methods=["POST"])
@login_required(["admin"])
def account_delete(uid):
    if uid == session.get("user_id"):
        flash("You cannot delete your own account while logged in.", "error")
        return redirect(url_for("accounts"))
    db = get_db()
    target = db.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
    if not target:
        db.close(); flash("Account not found.", "error"); return redirect(url_for("accounts"))
    if target["role"] == "admin":
        admin_count = db.execute("SELECT COUNT(*) c FROM users WHERE role='admin' AND is_active=1").fetchone()["c"]
        if admin_count <= 1:
            db.close(); flash("Keep at least one active admin account.", "error"); return redirect(url_for("accounts"))
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    db.close()
    flash("Account removed.", "success")
    return redirect(url_for("accounts"))


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    if HKPS_PRODUCTION:
        raise RuntimeError("Do not use Flask's development server in production. Run: waitress-serve --listen=127.0.0.1:8000 production:app")
    app.run(debug=False, host="127.0.0.1", port=5000)
else:
    init_db()
