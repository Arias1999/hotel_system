import os
import traceback
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "secret123")


# =========================
# BASIC HELPERS
# =========================
def valid_email(email):
    return "@" in email and "." in email and len(email) >= 5


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
# 🔥 DEBUG ROUTES
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
        phone = request.form.get("phone")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not all([full_name, phone, email, password, confirm_password]):
            flash("All fields are required", "error")
            return render_template("register.html")

        if not valid_email(email):
            flash("Invalid email format", "error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template("register.html")

        try:
            existing = db.fetchone(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            if existing:
                flash("Email already exists", "error")
                return render_template("register.html")

            db.execute(
                """
                INSERT INTO users (full_name, phone, email, password, role)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (full_name, phone, email, generate_password_hash(password), "customer")
            )

            flash("Account created successfully!", "success")
            return redirect("/login")

        except Exception:
            traceback.print_exc()
            flash("Database error. Please try again.", "error")
            return render_template("register.html")

    return render_template("register.html")


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

            if user.get("role") == "admin":
                session.clear()
                session["admin"] = email
                return redirect("/admin")

            session.clear()
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
        return redirect("/")
    return render_template("index.html")


# =========================
# ROOMS
# =========================
@app.route("/rooms")
def rooms():
    if not logged_in():
        return redirect("/")

    category = request.args.get("category")

    try:
        if category:
            room_list = db.fetchall(
                "SELECT * FROM rooms WHERE category = %s",
                (category,)
            )
        else:
            room_list = db.fetchall("SELECT * FROM rooms ORDER BY available DESC")
    except Exception:
        traceback.print_exc()
        room_list = []

    return render_template("rooms.html", rooms=room_list, category=category)


# =========================
# MESSAGES
# =========================
@app.route("/messages", methods=["GET", "POST"])
def messages():
    if not logged_in():
        return redirect("/")

    email = session["user"]

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        if not body:
            flash("Message cannot be empty.", "error")
        else:
            try:
                db.execute(
                    "INSERT INTO messages (user_email, subject, body) VALUES (%s, %s, %s)",
                    (email, subject, body)
                )
                flash("Message sent!", "success")
            except Exception:
                traceback.print_exc()
                flash("Failed to send message.", "error")
        return redirect("/messages")

    try:
        inbox = db.fetchall(
            "SELECT * FROM messages WHERE user_email = %s ORDER BY created_at DESC",
            (email,)
        )
        user = db.fetchone("SELECT full_name, phone, email FROM users WHERE email = %s", (email,))
    except Exception:
        traceback.print_exc()
        inbox = []
        user = {}

    return render_template("messages.html", inbox=inbox, user=user)


@app.route("/cancel/<int:booking_id>", methods=["POST"])
def cancel_booking(booking_id):
    if not logged_in():
        return redirect("/")

    email = session["user"]
    reason = request.form.get("reason", "").strip()

    try:
        booking = db.fetchone(
            """
            SELECT b.id, b.user_email, r.name AS room_name
            FROM bookings b JOIN rooms r ON b.room_id = r.id
            WHERE b.id = %s AND b.user_email = %s
            """,
            (booking_id, email)
        )

        if not booking:
            flash("Booking not found.", "error")
            return redirect("/my-bookings")

        user = db.fetchone("SELECT full_name, phone FROM users WHERE email = %s", (email,))

        db.execute(
            "UPDATE bookings SET cancel_status = 'Pending Cancellation', cancel_reason = %s WHERE id = %s",
            (reason or "No reason provided", booking_id)
        )

        body = (
            f"Cancellation request for Booking #{booking_id} - '{booking['room_name']}'.\n\n"
            f"Reason: {reason or 'No reason provided'}\n\n"
            f"User: {user['full_name'] if user else ''}\n"
            f"Email: {email}\n"
            f"Phone: {user['phone'] if user else ''}"
        )
        db.execute(
            "INSERT INTO messages (user_email, subject, body) VALUES (%s, %s, %s)",
            (email, f"Cancellation Request - Booking #{booking_id}", body)
        )

        flash("Cancellation request submitted. Awaiting admin approval.", "success")
    except Exception:
        traceback.print_exc()
        flash("Failed to submit cancellation request.", "error")

    return redirect("/my-bookings")


@app.route("/admin/bookings/approve-cancel/<int:booking_id>", methods=["POST"])
def approve_cancel(booking_id):
    guard = admin_required()
    if guard:
        return guard
    try:
        db.execute("DELETE FROM bookings WHERE id = %s", (booking_id,))
        flash("Cancellation approved and booking deleted.", "success")
    except Exception:
        traceback.print_exc()
        flash("Failed to approve cancellation.", "error")
    return redirect("/admin/bookings")


@app.route("/admin/bookings/reject-cancel/<int:booking_id>", methods=["POST"])
def reject_cancel(booking_id):
    guard = admin_required()
    if guard:
        return guard
    try:
        db.execute(
            "UPDATE bookings SET cancel_status = 'None', cancel_reason = NULL WHERE id = %s",
            (booking_id,)
        )
        flash("Cancellation request rejected.", "success")
    except Exception:
        traceback.print_exc()
        flash("Failed to reject cancellation.", "error")
    return redirect("/admin/bookings")


@app.route("/admin/messages")
def admin_messages():
    guard = admin_required()
    if guard:
        return guard
    try:
        msgs = db.fetchall("SELECT * FROM messages ORDER BY created_at DESC")
    except Exception:
        traceback.print_exc()
        msgs = []
    return render_template("admin_messages.html", msgs=msgs)


@app.route("/admin/messages/reply/<int:msg_id>", methods=["POST"])
def admin_reply(msg_id):
    guard = admin_required()
    if guard:
        return guard
    reply = request.form.get("reply", "").strip()
    if reply:
        try:
            db.execute(
                "UPDATE messages SET reply = %s, replied_at = NOW() WHERE id = %s",
                (reply, msg_id)
            )
            flash("Reply sent.", "success")
        except Exception:
            traceback.print_exc()
            flash("Failed to send reply.", "error")
    return redirect("/admin/messages")


# =========================
# ADMIN
# =========================
@app.route("/admin")
def admin_dashboard():
    guard = admin_required()
    if guard:
        return guard

    try:
        total_users = db.fetchone("SELECT COUNT(*) AS c FROM users")["c"]
        total_bookings = db.fetchone("SELECT COUNT(*) AS c FROM bookings")["c"]
        total_rooms = db.fetchone("SELECT COUNT(*) AS c FROM rooms")["c"]
        pending_payments = db.fetchone("SELECT COUNT(*) AS c FROM bookings WHERE payment_status = 'Pending'")["c"]
        revenue_row = db.fetchone("SELECT COALESCE(SUM(amount), 0) AS r FROM payments WHERE payment_status = 'Paid'")
        total_revenue = revenue_row["r"] if revenue_row else 0
        recent_bookings = db.fetchall(
            """
            SELECT b.id, b.user_email, r.name AS room_name, b.checkin, b.checkout, b.payment_status
            FROM bookings b JOIN rooms r ON b.room_id = r.id
            ORDER BY b.created_at DESC LIMIT 5
            """
        )
    except Exception:
        traceback.print_exc()
        total_users = total_bookings = total_rooms = pending_payments = total_revenue = 0
        recent_bookings = []

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_bookings=total_bookings,
        total_rooms=total_rooms,
        pending_payments=pending_payments,
        total_revenue=total_revenue,
        recent_bookings=recent_bookings,
    )


@app.route("/admin/profile", methods=["GET", "POST"])
def admin_profile():
    guard = admin_required()
    if guard:
        return guard

    email = session["admin"]

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        try:
            if new_password:
                if new_password != confirm_password:
                    flash("Passwords do not match.", "error")
                    return redirect("/admin/profile")
                db.execute(
                    "UPDATE users SET full_name = %s, phone = %s, password = %s WHERE email = %s",
                    (full_name, phone, generate_password_hash(new_password), email)
                )
            else:
                db.execute(
                    "UPDATE users SET full_name = %s, phone = %s WHERE email = %s",
                    (full_name, phone, email)
                )
            flash("Profile updated.", "success")
        except Exception:
            traceback.print_exc()
            flash("Failed to update profile.", "error")
        return redirect("/admin/profile")

    try:
        admin = db.fetchone("SELECT * FROM users WHERE email = %s", (email,))
        total_bookings = db.fetchone("SELECT COUNT(*) AS c FROM bookings")["c"]
        total_users = db.fetchone("SELECT COUNT(*) AS c FROM users")["c"]
        total_rooms = db.fetchone("SELECT COUNT(*) AS c FROM rooms")["c"]
        total_messages = db.fetchone("SELECT COUNT(*) AS c FROM messages")["c"]
        pending_cancel = db.fetchone("SELECT COUNT(*) AS c FROM bookings WHERE cancel_status = 'Pending Cancellation'")["c"]
        revenue_row = db.fetchone("SELECT COALESCE(SUM(amount), 0) AS r FROM payments WHERE payment_status = 'Paid'")
        total_revenue = revenue_row["r"] if revenue_row else 0
    except Exception:
        traceback.print_exc()
        admin = {"full_name": "", "phone": "", "email": email, "role": "admin", "created_at": None}
        total_bookings = total_users = total_rooms = total_messages = pending_cancel = total_revenue = 0

    return render_template(
        "admin_profile.html",
        admin=admin,
        total_bookings=total_bookings,
        total_users=total_users,
        total_rooms=total_rooms,
        total_messages=total_messages,
        pending_cancel=pending_cancel,
        total_revenue=total_revenue,
    )


@app.route("/admin/bookings")
def admin_bookings():
    guard = admin_required()
    if guard:
        return guard
    try:
        bookings = db.fetchall(
            """
            SELECT b.*, r.name AS room_name,
                   p.id AS payment_id, p.amount, p.payment_status AS pay_status, p.payment_method, p.reference_number
            FROM bookings b
            JOIN rooms r ON b.room_id = r.id
            LEFT JOIN payments p ON p.booking_id = b.id
            ORDER BY b.created_at DESC
            """
        )
    except Exception:
        traceback.print_exc()
        bookings = []
    return render_template("admin_bookings.html", bookings=bookings)


@app.route("/admin/payments")
def admin_payments():
    guard = admin_required()
    if guard:
        return guard
    try:
        payments = db.fetchall(
            """
            SELECT p.*, r.name AS room_name
            FROM payments p
            JOIN bookings b ON p.booking_id = b.id
            JOIN rooms r ON b.room_id = r.id
            ORDER BY p.paid_at DESC NULLS LAST
            """
        )
    except Exception:
        traceback.print_exc()
        payments = []
    return render_template("admin_payments.html", payments=payments)


@app.route("/admin/rooms", methods=["GET", "POST"])
def admin_rooms():
    guard = admin_required()
    if guard:
        return guard
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "0").strip()
        description = request.form.get("description", "").strip()
        image = request.form.get("image", "").strip()
        category = request.form.get("category", "Standard")
        if name:
            try:
                db.execute(
                    "INSERT INTO rooms (name, price, description, image, category) VALUES (%s, %s, %s, %s, %s)",
                    (name, price, description, image, category)
                )
                flash("Room added.", "success")
            except Exception:
                traceback.print_exc()
                flash("Failed to add room.", "error")
        return redirect("/admin/rooms")
    try:
        room_list = db.fetchall("SELECT * FROM rooms ORDER BY id DESC")
    except Exception:
        traceback.print_exc()
        room_list = []
    return render_template("admin_rooms.html", rooms=room_list)


@app.route("/admin/rooms/delete/<int:room_id>", methods=["POST"])
def admin_delete_room(room_id):
    guard = admin_required()
    if guard:
        return guard
    try:
        db.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
        flash("Room deleted.", "success")
    except Exception:
        traceback.print_exc()
        flash("Failed to delete room.", "error")
    return redirect("/admin/rooms")


@app.route("/admin/rooms/toggle/<int:room_id>", methods=["POST"])
def admin_toggle_room(room_id):
    guard = admin_required()
    if guard:
        return guard
    try:
        db.execute("UPDATE rooms SET available = NOT available WHERE id = %s", (room_id,))
    except Exception:
        traceback.print_exc()
    return redirect("/admin/rooms")


@app.route("/admin/users")
def admin_users():
    guard = admin_required()
    if guard:
        return guard
    try:
        users = db.fetchall("SELECT id, full_name, phone, email, role, created_at FROM users ORDER BY created_at DESC")
    except Exception:
        traceback.print_exc()
        users = []
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/delete/<user_id>", methods=["POST"])
def admin_delete_user(user_id):
    guard = admin_required()
    if guard:
        return guard
    try:
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        flash("User deleted.", "success")
    except Exception:
        traceback.print_exc()
        flash("Failed to delete user.", "error")
    return redirect("/admin/users")


@app.route("/admin/payments/update/<int:payment_id>", methods=["POST"])
def admin_update_payment(payment_id):
    guard = admin_required()
    if guard:
        return guard
    status = request.form.get("status", "Pending")
    try:
        db.execute(
            "UPDATE payments SET payment_status = %s, paid_at = CASE WHEN %s = 'Paid' THEN NOW() ELSE paid_at END WHERE id = %s",
            (status, status, payment_id)
        )
        flash("Payment updated.", "success")
    except Exception:
        traceback.print_exc()
        flash("Failed to update payment.", "error")
    return redirect("/admin/payments")


@app.route("/admin/bookings/confirm/<int:booking_id>", methods=["POST"])
def admin_confirm_booking(booking_id):
    guard = admin_required()
    if guard:
        return guard
    try:
        db.execute("UPDATE bookings SET payment_status = 'Paid' WHERE id = %s", (booking_id,))
        db.execute("UPDATE payments SET payment_status = 'Paid', paid_at = NOW() WHERE booking_id = %s", (booking_id,))
        flash("Booking confirmed.", "success")
    except Exception:
        traceback.print_exc()
        flash("Failed to confirm booking.", "error")
    return redirect("/admin/bookings")


@app.route("/admin/bookings/reject/<int:booking_id>", methods=["POST"])
def admin_reject_booking(booking_id):
    guard = admin_required()
    if guard:
        return guard
    try:
        db.execute("UPDATE bookings SET payment_status = 'Cancelled' WHERE id = %s", (booking_id,))
        flash("Booking rejected.", "success")
    except Exception:
        traceback.print_exc()
        flash("Failed to reject booking.", "error")
    return redirect("/admin/bookings")


@app.route("/admin/bookings/delete/<int:booking_id>", methods=["POST"])
def admin_delete_booking(booking_id):
    guard = admin_required()
    if guard:
        return guard
    try:
        db.execute("DELETE FROM bookings WHERE id = %s", (booking_id,))
        flash("Booking deleted.", "success")
    except Exception:
        traceback.print_exc()
        flash("Failed to delete booking.", "error")
    return redirect("/admin/bookings")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)