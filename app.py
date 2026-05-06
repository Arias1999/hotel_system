import os
import secrets
import smtplib
import traceback
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

import db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", 10))


def valid_email(email):
    return email and "@" in email and "." in email


def generate_otp():
    return f"{secrets.randbelow(1000000):06d}"


def send_otp_email(to_email, otp_code):
    try:
        if not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_FROM_EMAIL:
            print("SMTP ERROR: Missing SMTP credentials")
            return False

        body = f"""Hello,

Your HotelBook verification code is:

{otp_code}

This OTP will expire in {OTP_EXPIRY_MINUTES} minutes.

- HotelBook Team
"""

        msg = MIMEText(body)
        msg["Subject"] = "HotelBook OTP Verification"
        msg["From"] = SMTP_FROM_EMAIL
        msg["To"] = to_email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, to_email, msg.as_string())

        print("OTP EMAIL SENT SUCCESSFULLY")
        return True

    except Exception as e:
        print("SMTP ERROR:", repr(e))
        return False


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
        raise RuntimeError("OTP email failed to send")


def logged_in():
    return "user" in session


def admin_logged_in():
    return "admin" in session


def admin_required():
    if not admin_logged_in():
        flash("Please log in to access the admin panel.", "error")
        return redirect("/login")
    return None


@app.route("/debug-db")
def debug_db():
    url = os.getenv("DATABASE_URL", "").strip()
    return jsonify({
        "database_url_exists": bool(url),
        "starts_with": url[:50] if url else "EMPTY",
        "has_placeholder": "PROJECT_REF" in url or "YOUR_DB_PASSWORD" in url or "REGION" in url,
    })


@app.route("/test-db")
def test_db():
    try:
        result = db.fetchone("SELECT 1 AS ok")
        return jsonify({"status": "connected", "result": result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    email = ""

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or not email or not password or not confirm_password:
            flash("All required fields must be filled in.", "error")
            return render_template("register.html", email=email)

        if not valid_email(email):
            flash("Invalid email format.", "error")
            return render_template("register.html", email=email)

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html", email=email)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html", email=email)

        try:
            existing = db.fetchone(
                "SELECT id FROM users WHERE email = %s",
                (email,)
            )
        except Exception as e:
            print("DATABASE EMAIL CHECK ERROR:", repr(e))
            traceback.print_exc()
            flash("Database error while checking your email. Please try again.", "error")
            return render_template("register.html", email=email)

        if existing:
            flash("Email already exists. Please login.", "error")
            return render_template("register.html", email=email)

        try:
            save_pending_registration(
                full_name,
                phone,
                email,
                generate_password_hash(password)
            )

            flash("We sent an OTP code to your Gmail. Please verify your account.", "success")
            return redirect("/verify-registration")

        except Exception as e:
            print("REGISTRATION OTP ERROR:", repr(e))
            traceback.print_exc()
            flash("Could not send OTP. Please check your Gmail app password settings.", "error")
            return render_template("register.html", email=email)

    return render_template("register.html", email=email)


@app.route("/verify-registration", methods=["GET", "POST"])
def verify_registration():
    pending = session.get("pending_registration")

    if not pending:
        flash("Please register first.", "error")
        return redirect("/register")

    if request.method == "POST":
        otp = request.form.get("otp", "").strip()

        try:
            expires_at = datetime.fromisoformat(pending["expires_at"])
        except Exception:
            session.pop("pending_registration", None)
            flash("OTP session error. Please register again.", "error")
            return redirect("/register")

        if datetime.now(timezone.utc) > expires_at:
            session.pop("pending_registration", None)
            flash("OTP expired. Please register again.", "error")
            return redirect("/register")

        if otp != pending["otp"]:
            flash("Invalid OTP code.", "error")
            return render_template("verify_otp.html", email=pending["email"])

        try:
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

            session.pop("pending_registration", None)
            flash("Account verified and created successfully!", "success")
            return redirect("/login")

        except Exception as e:
            print("VERIFY INSERT DATABASE ERROR:", repr(e))
            traceback.print_exc()
            flash("Database error while creating your account. Please try again.", "error")

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

    except Exception as e:
        print("RESEND OTP ERROR:", repr(e))
        traceback.print_exc()
        flash("Could not send OTP. Please check your Gmail app password settings.", "error")

    return redirect("/verify-registration")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        try:
            user = db.fetchone(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            if not user or not check_password_hash(user["password"], password):
                flash("Invalid email or password.", "error")
                return render_template("login.html")

            session.clear()

            if user.get("role") == "admin":
                session["admin"] = email
                return redirect("/admin")

            session["user"] = email
            return redirect("/home")

        except Exception as e:
            print("LOGIN ERROR:", repr(e))
            traceback.print_exc()
            flash("Login failed. Please try again.", "error")
            return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/home")
def home():
    if not logged_in():
        return redirect("/login")
    return render_template("index.html")


@app.route("/rooms")
def rooms():
    if not logged_in():
        return redirect("/login")

    try:
        rooms_data = db.fetchall("SELECT * FROM rooms ORDER BY id ASC")
    except Exception as e:
        print("ROOMS ERROR:", repr(e))
        traceback.print_exc()
        rooms_data = []
        flash("Could not load rooms.", "error")

    return render_template("rooms.html", rooms=rooms_data)


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
                b.payment_id,
                COALESCE(b.amount, 0) AS amount,
                GREATEST((b.checkout::date - b.checkin::date), 0) AS nights,
                GREATEST((b.checkout::date - b.checkin::date), 0) * r.price AS total
            FROM bookings b
            JOIN rooms r ON b.room_id = r.id
            WHERE b.user_id = %s
            ORDER BY b.id DESC
            """,
            (user["id"],)
        )

    except Exception as e:
        print("MY BOOKINGS ERROR:", repr(e))
        traceback.print_exc()
        flash("Could not load bookings.", "error")
        bookings = []

    return render_template("my_bookings.html", bookings=bookings)


@app.route("/cancel/<int:booking_id>", methods=["POST"])
def cancel_booking(booking_id):
    if not logged_in():
        return redirect("/login")

    try:
        user = db.fetchone(
            "SELECT * FROM users WHERE email = %s",
            (session["user"],)
        )

        if user:
            db.execute(
                "DELETE FROM bookings WHERE id = %s AND user_id = %s",
                (booking_id, user["id"])
            )
            flash("Booking cancelled successfully.", "success")
        else:
            flash("User not found.", "error")

    except Exception as e:
        print("CANCEL BOOKING ERROR:", repr(e))
        traceback.print_exc()
        flash("Could not cancel booking.", "error")

    return redirect("/my-bookings")


@app.route("/admin")
def admin_dashboard():
    guard = admin_required()
    if guard:
        return guard

    try:
        total_users = db.fetchone("SELECT COUNT(*) AS c FROM users")["c"]
        total_bookings = db.fetchone("SELECT COUNT(*) AS c FROM bookings")["c"]
    except Exception as e:
        print("ADMIN DASHBOARD ERROR:", repr(e))
        traceback.print_exc()
        total_users = 0
        total_bookings = 0

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_bookings=total_bookings
    )


if __name__ == "__main__":
    app.run(debug=True)