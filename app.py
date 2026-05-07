import os
import secrets
import smtplib
import ssl
import traceback
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash
import db

# =========================
# LOAD ENVIRONMENT VARIABLES
# =========================
load_dotenv()

# =========================
# ENV VARIABLES
# =========================
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


def is_admin_user(user):
    return bool(user and (user.get("role") == "admin" or user.get("is_admin")))


def admin_required():
    if not admin_logged_in():
        flash("Please log in to access the admin panel.", "error")
        return redirect("/admin/login")
    return None


def log_error(context, error):
    print(f"{context} ERROR: {error}")
    traceback.print_exc()
    app.logger.exception("%s ERROR", context)


def ensure_admin_database():
    try:
        db.ensure_app_schema()
        return True
    except Exception as e:
        log_error("ADMIN DATABASE SETUP", e)
        flash(f"Database setup error: {e}", "error")
        return False


def count_value(query, params=()):
    row = db.fetchone(query, params)
    if not row:
        return 0
    return row.get("c") or 0


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return error

    log_error("UNHANDLED SERVER", error)
    return "Internal Server Error. Check the Flask console for the real traceback.", 500


# =========================
# DEBUG ROUTES
# =========================
@app.route("/debug-db")
def debug_db():
    try:
        parsed = db.url_info()
        return jsonify({
            "database_url_exists": True,
            "host": parsed["host"],
            "port": parsed["port"],
            "username": parsed["username"],
            "direct_connection": parsed["direct_connection"],
            "sslmode": parsed["sslmode"],
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


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

            if is_admin_user(user):
                session["admin"] = email
                return redirect("/admin")

            session["user"] = email
            return redirect("/home")

        except Exception:
            traceback.print_exc()
            flash("Login failed. Try again.", "error")
            return render_template("login.html")

    return render_template("login.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
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
                return render_template("admin_login.html")

            if not is_admin_user(user):
                flash("This account is not an admin account.", "error")
                return render_template("admin_login.html")

            session.clear()
            session["admin"] = email
            return redirect("/admin")

        except Exception:
            traceback.print_exc()
            flash("Admin login failed. Try again.", "error")
            return render_template("admin_login.html")

    return render_template("admin_login.html")


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


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not valid_email(email) or not message:
            flash("Please enter your name, valid email, and message.", "error")
            return render_template("contact.html")

        try:
            db.ensure_app_schema()
            db.execute(
                """
                INSERT INTO contact_messages (name, email, subject, message)
                VALUES (%s, %s, %s, %s)
                """,
                (name, email, subject, message)
            )
            flash("Thanks for your message. We will get back to you soon.", "success")
        except Exception as e:
            log_error("CONTACT MESSAGE", e)
            flash(f"Could not send your message right now: {e}", "error")

    return render_template("contact.html")


@app.route("/profile")
def profile():
    if not logged_in():
        return redirect("/login")

    user_email = session["user"]
    booking_count = 0
    room_count = 0

    try:
        booking_row = db.fetchone(
            "SELECT COUNT(*) AS c FROM bookings WHERE user_email = %s",
            (user_email,)
        )
        room_row = db.fetchone("SELECT COUNT(*) AS c FROM rooms")
        booking_count = booking_row["c"] if booking_row else 0
        room_count = room_row["c"] if room_row else 0
    except Exception:
        traceback.print_exc()
        flash("Could not load all profile details right now.", "error")

    return render_template(
        "profile.html",
        user_email=user_email,
        booking_count=booking_count,
        room_count=room_count
    )


@app.route("/settings")
def settings():
    if not logged_in():
        return redirect("/login")
    return render_template("settings.html", user_email=session["user"])


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

    ensure_admin_database()

    total_users = 0
    total_bookings = 0
    total_revenue = 0
    total_rooms = 0
    pending_payments = 0
    recent_bookings = []

    try:
        total_users = count_value("SELECT COUNT(*) AS c FROM users")
        total_bookings = count_value("SELECT COUNT(*) AS c FROM bookings")
        total_rooms = count_value("SELECT COUNT(*) AS c FROM rooms")
        total_revenue = count_value(
            """
            SELECT COALESCE(SUM(amount), 0) AS c
            FROM payments
            WHERE payment_status = 'Paid'
            """
        )
        pending_payments = count_value(
            """
            SELECT COUNT(*) AS c
            FROM payments
            WHERE COALESCE(payment_status, 'Pending') = 'Pending'
            """
        )
        recent_bookings = db.fetchall(
            """
            SELECT
                b.id,
                b.user_email,
                COALESCE(r.name, 'Unknown room') AS room_name,
                b.checkin,
                b.checkout,
                COALESCE(p.payment_status, b.payment_status, 'Pending') AS payment_status
            FROM bookings b
            LEFT JOIN rooms r ON r.id = b.room_id
            LEFT JOIN LATERAL (
                SELECT payment_status
                FROM payments
                WHERE booking_id = b.id
                ORDER BY id DESC
                LIMIT 1
            ) p ON TRUE
            ORDER BY b.created_at DESC NULLS LAST, b.id DESC
            LIMIT 5
            """
        )
    except Exception as e:
        log_error("ADMIN DASHBOARD", e)
        flash(f"Could not load dashboard data: {e}", "error")

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_bookings=total_bookings,
        total_revenue=total_revenue,
        total_rooms=total_rooms,
        pending_payments=pending_payments,
        recent_bookings=recent_bookings
    )


@app.route("/admin/bookings")
def admin_bookings():
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    bookings = []

    try:
        bookings = db.fetchall(
            """
            SELECT
                b.id,
                b.user_email,
                COALESCE(r.name, 'Unknown room') AS room_name,
                b.checkin,
                b.checkout,
                b.payment_method,
                b.payment_status,
                COALESCE(p.payment_status, b.payment_status, 'Pending') AS pay_status,
                COALESCE(p.reference_number, b.reference_number, '') AS reference_number,
                COALESCE(p.amount, 0) AS amount
            FROM bookings b
            LEFT JOIN rooms r ON r.id = b.room_id
            LEFT JOIN LATERAL (
                SELECT payment_status, reference_number, amount
                FROM payments
                WHERE booking_id = b.id
                ORDER BY id DESC
                LIMIT 1
            ) p ON TRUE
            ORDER BY b.created_at DESC NULLS LAST, b.id DESC
            """
        )
    except Exception as e:
        log_error("ADMIN BOOKINGS", e)
        flash(f"Could not load bookings: {e}", "error")

    return render_template("admin_bookings.html", bookings=bookings)


@app.route("/admin/bookings/confirm/<int:booking_id>", methods=["POST"])
def admin_confirm_booking(booking_id):
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    try:
        db.execute("UPDATE bookings SET payment_status = 'Paid' WHERE id = %s", (booking_id,))
        db.execute(
            """
            UPDATE payments
            SET payment_status = 'Paid',
                paid_at = COALESCE(paid_at, NOW())
            WHERE booking_id = %s
            """,
            (booking_id,)
        )
        flash("Booking confirmed.", "success")
    except Exception as e:
        log_error("ADMIN CONFIRM BOOKING", e)
        flash(f"Could not confirm booking: {e}", "error")

    return redirect("/admin/bookings")


@app.route("/admin/bookings/reject/<int:booking_id>", methods=["POST"])
def admin_reject_booking(booking_id):
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    try:
        db.execute("UPDATE bookings SET payment_status = 'Cancelled' WHERE id = %s", (booking_id,))
        db.execute(
            "UPDATE payments SET payment_status = 'Cancelled' WHERE booking_id = %s",
            (booking_id,)
        )
        flash("Booking rejected.", "success")
    except Exception as e:
        log_error("ADMIN REJECT BOOKING", e)
        flash(f"Could not reject booking: {e}", "error")

    return redirect("/admin/bookings")


@app.route("/admin/bookings/delete/<int:booking_id>", methods=["POST"])
def admin_delete_booking(booking_id):
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    try:
        db.execute("DELETE FROM payments WHERE booking_id = %s", (booking_id,))
        db.execute("DELETE FROM bookings WHERE id = %s", (booking_id,))
        flash("Booking deleted.", "success")
    except Exception as e:
        log_error("ADMIN DELETE BOOKING", e)
        flash(f"Could not delete booking: {e}", "error")

    return redirect("/admin/bookings")


@app.route("/admin/payments")
def admin_payments():
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    payments = []

    try:
        payments = db.fetchall(
            """
            SELECT
                p.id,
                p.booking_id,
                p.user_email,
                COALESCE(r.name, 'Unknown room') AS room_name,
                COALESCE(p.amount, 0) AS amount,
                p.payment_method,
                p.payment_status,
                p.paid_at
            FROM payments p
            LEFT JOIN bookings b ON b.id = p.booking_id
            LEFT JOIN rooms r ON r.id = b.room_id
            ORDER BY p.id DESC
            """
        )
    except Exception as e:
        log_error("ADMIN PAYMENTS", e)
        flash(f"Could not load payments: {e}", "error")

    return render_template("admin_payments.html", payments=payments)


@app.route("/admin/payments/update/<int:payment_id>", methods=["POST"])
def admin_update_payment(payment_id):
    guard = admin_required()
    if guard:
        return guard

    status = request.form.get("status", "Pending")
    if status not in ("Pending", "Paid", "Cancelled"):
        status = "Pending"

    ensure_admin_database()
    try:
        payment = db.execute_returning(
            """
            UPDATE payments
            SET payment_status = %s,
                paid_at = CASE WHEN %s = 'Paid' THEN COALESCE(paid_at, NOW()) ELSE paid_at END
            WHERE id = %s
            RETURNING booking_id
            """,
            (status, status, payment_id)
        )

        if payment and payment.get("booking_id"):
            db.execute(
                "UPDATE bookings SET payment_status = %s WHERE id = %s",
                (status, payment["booking_id"])
            )

        flash("Payment updated.", "success")
    except Exception as e:
        log_error("ADMIN UPDATE PAYMENT", e)
        flash(f"Could not update payment: {e}", "error")

    return redirect("/admin/payments")


@app.route("/admin/rooms")
def admin_rooms():
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    rooms = []

    try:
        rooms = db.fetchall("SELECT * FROM rooms ORDER BY id ASC")
    except Exception as e:
        log_error("ADMIN ROOMS", e)
        flash(f"Could not load rooms: {e}", "error")

    return render_template("admin_rooms.html", rooms=rooms)


@app.route("/admin/rooms/add", methods=["POST"])
def admin_add_room():
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    try:
        db.execute(
            """
            INSERT INTO rooms (name, price, description, image, category)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                request.form.get("name", "").strip(),
                request.form.get("price") or 0,
                request.form.get("description", "").strip(),
                request.form.get("image", "").strip(),
                request.form.get("category", "Standard"),
            )
        )
        flash("Room added.", "success")
    except Exception as e:
        log_error("ADMIN ADD ROOM", e)
        flash(f"Could not add room: {e}", "error")

    return redirect("/admin/rooms")


@app.route("/admin/rooms/delete/<int:room_id>", methods=["POST"])
def admin_delete_room(room_id):
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    try:
        db.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
        flash("Room deleted.", "success")
    except Exception as e:
        log_error("ADMIN DELETE ROOM", e)
        flash(f"Could not delete room: {e}", "error")

    return redirect("/admin/rooms")


@app.route("/admin/users")
def admin_users():
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    users = []

    try:
        users = db.fetchall(
            """
            SELECT
                u.id,
                u.email,
                u.is_admin,
                u.role,
                COALESCE(COUNT(b.id), 0) AS booking_count
            FROM users u
            LEFT JOIN bookings b ON b.user_email = u.email
            GROUP BY u.id, u.email, u.is_admin, u.role
            ORDER BY u.created_at DESC NULLS LAST, u.email ASC
            """
        )
    except Exception as e:
        log_error("ADMIN USERS", e)
        flash(f"Could not load users: {e}", "error")

    return render_template("admin_users.html", users=users)


@app.route("/admin/users/delete/<user_id>", methods=["POST"])
def admin_delete_user(user_id):
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    try:
        db.execute(
            "DELETE FROM users WHERE id = %s AND COALESCE(is_admin, FALSE) = FALSE",
            (user_id,)
        )
        flash("User deleted.", "success")
    except Exception as e:
        log_error("ADMIN DELETE USER", e)
        flash(f"Could not delete user: {e}", "error")

    return redirect("/admin/users")


@app.route("/admin/messages")
def admin_messages():
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    messages = []

    try:
        messages = db.fetchall(
            """
            SELECT id, name, email, subject, message, is_read, created_at
            FROM contact_messages
            ORDER BY is_read ASC, created_at DESC NULLS LAST, id DESC
            """
        )
    except Exception as e:
        log_error("ADMIN MESSAGES", e)
        flash(f"Could not load messages: {e}", "error")

    return render_template("admin_messages.html", messages=messages)


@app.route("/admin/messages/read/<int:message_id>", methods=["POST"])
def admin_mark_message_read(message_id):
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    try:
        db.execute(
            "UPDATE contact_messages SET is_read = TRUE WHERE id = %s",
            (message_id,)
        )
        flash("Message marked as read.", "success")
    except Exception as e:
        log_error("ADMIN MARK MESSAGE READ", e)
        flash(f"Could not update message: {e}", "error")

    return redirect("/admin/messages")


@app.route("/admin/messages/delete/<int:message_id>", methods=["POST"])
def admin_delete_message(message_id):
    guard = admin_required()
    if guard:
        return guard

    ensure_admin_database()
    try:
        db.execute("DELETE FROM contact_messages WHERE id = %s", (message_id,))
        flash("Message deleted.", "success")
    except Exception as e:
        log_error("ADMIN DELETE MESSAGE", e)
        flash(f"Could not delete message: {e}", "error")

    return redirect("/admin/messages")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
