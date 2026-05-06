import os
import traceback
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
    return email and "@" in email and "." in email and len(email) >= 5


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
            "DELETE FROM bookings WHERE id = %s AND user_id = %s",
            (booking_id, user["id"])
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