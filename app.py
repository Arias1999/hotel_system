import os
import secrets
import smtplib
import ssl
import traceback
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import db

# =========================
# LOAD ENVIRONMENT VARIABLES
# =========================
load_dotenv()

# =========================
# ENV VARIABLES
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")

OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", 10))

app = Flask(__name__)
app.secret_key = SECRET_KEY or "secret123"


# =========================
# BASIC HELPERS
# =========================
def valid_email(email):
    return email and "@" in email and "." in email and len(email) >= 5


def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def send_otp_email(to_email, otp_code):
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL]):
        print("EMAIL ERROR: Missing SMTP environment variables")
        return False

    server = None

    try:
        subject = "HotelBook OTP Verification"

        body = f"""
Hello,

Your HotelBook verification code is:

{otp_code}

This OTP will expire in {OTP_EXPIRY_MINUTES} minutes.

If you did not request this code, please ignore this email.

- HotelBook Team
"""

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM_EMAIL
        msg["To"] = to_email

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        server.starttls(context=ssl.create_default_context())
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        print("SMTP LOGIN SUCCESS")
        server.sendmail(
            SMTP_FROM_EMAIL,
            to_email,
            msg.as_string()
        )
        server.quit()
        server = None

        print("OTP EMAIL SENT SUCCESSFULLY")
        return True

    except Exception as e:
        print("EMAIL ERROR:", str(e))
        traceback.print_exc()
        return False
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


def save_pending_registration(full_name, phone, email, password_hash):
    otp = generate_otp()
    session["pending_registration"] = {
        "full_name": full_name,
        "phone": phone,
        "email": email,
        "password_hash": password_hash,
        "otp": otp,
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
        ).isoformat(),
    }
    if not send_otp_email(email, otp):
        session.pop("pending_registration", None)
        raise RuntimeError("OTP email failed to send.")


def email_error_message():
    return (
        "Could not send OTP. Please restart the Flask server and check your Gmail SMTP "
        "settings in .env."
    )


def logged_in():
    return "user" in session


def admin_logged_in():
    return "admin" in session


def admin_required():
    if not admin_logged_in():
        flash("Please log in to access the admin panel.", "error")
        return redirect("/login")
    return None


# =========================
# DEBUG ROUTES
# =========================
@app.route("/debug-db")
def debug_db():
    url = os.getenv("DATABASE_URL", "").strip()
    return jsonify({
        "database_url_exists": bool(url),
        "contains_project_user": "postgres.zyjqxnnvnpjbgmnmlxns" in url,
        "starts_with": url[:40] if url else "EMPTY",
    })


@app.route("/test-db")
def test_db():
    try:
        result = db.fetchone("SELECT 1 AS ok")
        return jsonify({"status": "connected", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# =========================
# AUTH
# =========================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name")
        phone = request.form.get("phone", "")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not all([full_name, email, password, confirm_password]):
            flash("All fields are required", "error")
            return render_template("register.html")

        if not valid_email(email):
            flash("Invalid email format", "error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template("register.html")

        try:
            db.ensure_users_table()
            existing = db.fetchone(
                "SELECT id FROM users WHERE email = %s",
                (email,)
            )
            print("EMAIL CHECK SUCCESS")
        except Exception as e:
            print("REGISTRATION EMAIL CHECK ERROR:", str(e))
            traceback.print_exc()
            flash(f"Database error while checking your email: {e}", "error")
            return render_template("register.html")

        if existing:
            flash("Email already exists", "error")
            return render_template("register.html")

        try:
            save_pending_registration(
                full_name,
                phone,
                email,
                generate_password_hash(password),
            )
            flash("We sent an OTP code to your Gmail. Please verify your account.", "success")
            return redirect("/verify-registration")

        except Exception:
            traceback.print_exc()
            flash(email_error_message(), "error")
            return render_template("register.html")

    return render_template("register.html")


@app.route("/verify-registration", methods=["GET", "POST"])
def verify_registration():
    pending = session.get("pending_registration")
    if not pending:
        flash("Please register first.", "error")
        return redirect("/register")

    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        expires_at = datetime.fromisoformat(pending["expires_at"])

        if datetime.now(timezone.utc) > expires_at:
            session.pop("pending_registration", None)
            flash("OTP expired. Please register again.", "error")
            return redirect("/register")

        if otp != pending["otp"]:
            flash("Invalid OTP code.", "error")
            return render_template("verify_otp.html", email=pending["email"])

        try:
            db.ensure_users_table()
            db.execute(
                """
                INSERT INTO users (full_name, phone, email, password, role)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    pending["full_name"],
                    pending["phone"],
                    pending["email"],
                    pending["password_hash"],
                    "customer",
                )
            )
            print("USER INSERTED")
            session.pop("pending_registration", None)
            flash("Account verified and created successfully!", "success")
            return redirect("/login")
        except Exception as e:
            print("USER INSERT ERROR:", str(e))
            traceback.print_exc()
            flash(f"Database error while creating your account: {e}", "error")

    return render_template("verify_otp.html", email=pending["email"])


@app.route("/resend-registration-otp", methods=["POST"])
def resend_registration_otp():
    pending = session.get("pending_registration")
    if not pending:
        flash("Please register first.", "error")
        return redirect("/register")

    try:
        save_pending_registration(
            pending["full_name"],
            pending["phone"],
            pending["email"],
            pending["password_hash"],
        )
        flash("A new OTP code was sent.", "success")
    except Exception:
        traceback.print_exc()
        flash(email_error_message(), "error")

    return redirect("/verify-registration")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        try:
            user = db.fetchone(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            if not user or not check_password_hash(user["password"], password):
                flash("Invalid email or password", "error")
                return render_template("login.html")

            session.clear()

            if user.get("role") == "admin":
                session["admin"] = email
                return redirect("/admin")

            session["user"] = email
            return redirect("/home")

        except Exception:
            traceback.print_exc()
            flash("Login failed. Try again.", "error")
            return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# =========================
# HOME
# =========================
@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/home")
def home():
    if not logged_in():
        return redirect("/login")
    return render_template("index.html")


# =========================
# MY BOOKINGS
# =========================
@app.route("/my-bookings")
def my_bookings():
    if not logged_in():
        return redirect("/login")

    try:
        user = db.fetchone(
            "SELECT * FROM users WHERE email = %s",
            (session["user"],)
        )

        if not user:
            flash("User not found. Please login again.", "error")
            session.clear()
            return redirect("/login")

        bookings = db.fetchall(
            """
            SELECT 
                b.id,
                r.name,
                r.price,
                b.checkin,
                b.checkout,
                COALESCE(b.payment_method, 'Cash') AS payment_method,
                COALESCE(b.payment_status, 'Pending') AS payment_status,
                p.id AS payment_id,
                COALESCE(p.amount, 0) AS amount,
                GREATEST((b.checkout::date - b.checkin::date), 0) AS nights,
                GREATEST((b.checkout::date - b.checkin::date), 0) * r.price AS total
            FROM bookings b
            JOIN rooms r ON b.room_id = r.id
            LEFT JOIN payments p ON p.booking_id = b.id
            WHERE b.user_email = %s
            ORDER BY b.id DESC
            """,
            (user["email"],)
        )

    except Exception:
        traceback.print_exc()
        flash("Could not load bookings.", "error")
        bookings = []

    return render_template("my_bookings.html", bookings=bookings)


# =========================
# CANCEL BOOKING
# =========================
@app.route("/cancel/<int:booking_id>", methods=["POST"])
def cancel_booking(booking_id):
    if not logged_in():
        return redirect("/login")

    try:
        user = db.fetchone(
            "SELECT * FROM users WHERE email = %s",
            (session["user"],)
        )

        db.execute(
            "DELETE FROM bookings WHERE id = %s AND user_email = %s",
            (booking_id, user["email"])
        )

        flash("Booking cancelled successfully.", "success")

    except Exception:
        traceback.print_exc()
        flash("Could not cancel booking.", "error")

    return redirect("/my-bookings")


# =========================
# ROOMS
# =========================
@app.route("/rooms")
def rooms():
    if not logged_in():
        return redirect("/login")

    try:
        rooms = db.fetchall("SELECT * FROM rooms ORDER BY id ASC")
    except Exception:
        traceback.print_exc()
        rooms = []

    return render_template("rooms.html", rooms=rooms)


# =========================
# ADMIN
# =========================
@app.route("/admin")
def admin_dashboard():
    guard = admin_required()
    if guard:
        return guard

    try:
        users = db.fetchone("SELECT COUNT(*) AS c FROM users")["c"]
        bookings = db.fetchone("SELECT COUNT(*) AS c FROM bookings")["c"]
    except Exception:
        traceback.print_exc()
        users = 0
        bookings = 0

    return render_template(
        "admin_dashboard.html",
        total_users=users,
        total_bookings=bookings
    )


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
