from flask import Flask, render_template, request, redirect, session, flash
import hashlib
import os
from datetime import datetime
from dotenv import load_dotenv
import db
load_dotenv()



app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "secret123")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def valid_email(email):
    return "@" in email and "." in email and len(email) >= 5


def logged_in():
    return "user" in session


def is_admin():
    if not logged_in():
        return False
    user = db.fetchone("SELECT is_admin FROM users WHERE email = %s", (session["user"],))
    return user and user["is_admin"]


def admin_required():
    if not is_admin():
        flash("Access denied.", "error")
        return redirect("/home")
    return None


# ── AUTH ──────────────────────────────────────────────

@app.route("/")
def landing():
    if logged_in():
        return redirect("/home")
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if logged_in():
        return redirect("/home")
    if request.method == "POST":
        email = request.form["email"]
        password = hash_password(request.form["password"])
        user = db.fetchone(
            "SELECT * FROM users WHERE email = %s AND password = %s", (email, password)
        )
        if user:
            session["user"] = email
            session["is_admin"] = bool(user["is_admin"])
            return redirect("/home")
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    email = ""
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm_password = request.form.get("confirm_password", "")

        if not valid_email(email):
            flash("Please provide a valid email address.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
        elif password != confirm_password:
            flash("Passwords do not match.", "error")
        else:
            hashed_password = hash_password(password)
            existing = db.fetchone("SELECT id FROM users WHERE email = %s", (email,))
            if existing:
                flash("Email already registered.", "error")
                return render_template("register.html", email=email)
            db.execute(
                "INSERT INTO users (email, password) VALUES (%s, %s)", (email, hashed_password)
            )
            flash("Account created! Please log in.", "success")
            return redirect("/")

    return render_template("register.html", email=email)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ── PAGES ─────────────────────────────────────────────

@app.route("/home")
def home():
    if not logged_in():
        return redirect("/")
    return render_template("index.html")


@app.route("/rooms")
def rooms():
    if not logged_in():
        return redirect("/")
    category = request.args.get("category", "All")
    if category == "All":
        rooms_list = db.fetchall("SELECT * FROM rooms")
    else:
        rooms_list = db.fetchall("SELECT * FROM rooms WHERE category = %s", (category,))
    categories = [r["category"] for r in db.fetchall("SELECT DISTINCT category FROM rooms")]
    return render_template("rooms.html", rooms=rooms_list, categories=categories, active_category=category)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/room/<int:room_id>")
def room_detail(room_id):
    if not logged_in():
        return redirect("/register")
    room = db.fetchone("SELECT * FROM rooms WHERE id = %s", (room_id,))
    if not room:
        return redirect("/rooms")
    rooms_list = db.fetchall("SELECT * FROM rooms")
    categories = [r["category"] for r in db.fetchall("SELECT DISTINCT category FROM rooms")]
    return render_template("room_detail.html", room=room, rooms=rooms_list, categories=categories, active_category="All")


@app.route("/book/<int:room_id>", methods=["GET", "POST"])
def book(room_id):
    if not logged_in():
        return redirect("/")
    room = db.fetchone("SELECT * FROM rooms WHERE id = %s", (room_id,))
    if not room:
        flash("Room not found.", "error")
        return redirect("/rooms")

    checkin = ""
    checkout = ""
    payment_method = "Cash"

    if request.method == "POST":
        checkin = request.form.get("checkin", "")
        checkout = request.form.get("checkout", "")
        payment_method = request.form.get("payment_method", "Cash")

        if not checkin or not checkout:
            flash("Please select both check-in and check-out dates.", "error")
            return render_template("booking.html", room=room, checkin=checkin, checkout=checkout, payment_method=payment_method)

        if checkin >= checkout:
            flash("Check-out date must be after check-in date.", "error")
            return render_template("booking.html", room=room, checkin=checkin, checkout=checkout, payment_method=payment_method)

        valid_methods = ["Cash", "GCash", "Visa", "Mastercard", "PayPal", "Maya", "Credit Card"]
        if payment_method not in valid_methods:
            payment_method = "Cash"

        conflict = db.fetchone(
            "SELECT 1 FROM bookings WHERE room_id = %s AND NOT (checkout <= %s OR checkin >= %s)",
            (room_id, checkin, checkout)
        )
        if conflict:
            flash("This room is already booked for the selected dates. Please choose another date range.", "error")
            return render_template("booking.html", room=room, checkin=checkin, checkout=checkout, payment_method=payment_method)

        booking = db.execute_returning(
            "INSERT INTO bookings (user_email, room_id, checkin, checkout, payment_method, payment_status) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (session["user"], room_id, checkin, checkout, payment_method, "Pending")
        )

        try:
            checkin_dt = datetime.fromisoformat(checkin)
            checkout_dt = datetime.fromisoformat(checkout)
            nights = max((checkout_dt - checkin_dt).days, 0)
            amount = float(room["price"]) * nights
        except Exception:
            amount = 0

        db.execute(
            "INSERT INTO payments (booking_id, user_email, amount, payment_method, payment_status) VALUES (%s, %s, %s, %s, %s)",
            (booking["id"], session["user"], amount, payment_method, "Pending")
        )
        flash("Booking confirmed!", "success")
        return redirect(f"/booking-confirmation/{booking['id']}")

    return render_template("booking.html", room=room, checkin=checkin, checkout=checkout, payment_method=payment_method)


@app.route("/booking-confirmation/<int:booking_id>")
def booking_confirmation(booking_id):
    if not logged_in():
        return redirect("/")
    booking = db.fetchone(
        """
        SELECT bookings.id, bookings.checkin, bookings.checkout, bookings.user_email,
               bookings.payment_method, bookings.payment_status,
               rooms.name AS room_name, rooms.price AS room_price,
               payments.id AS payment_id, payments.amount, payments.payment_status AS pay_status,
               payments.payment_method AS pay_method, payments.paid_at
        FROM bookings
        JOIN rooms ON bookings.room_id = rooms.id
        LEFT JOIN payments ON payments.booking_id = bookings.id
        WHERE bookings.id = %s AND bookings.user_email = %s
        """,
        (booking_id, session["user"])
    )
    if not booking:
        flash("Booking not found.", "error")
        return redirect("/my-bookings")

    nights = 0
    total = 0
    try:
        checkin_date = datetime.fromisoformat(booking["checkin"])
        checkout_date = datetime.fromisoformat(booking["checkout"])
        nights = max((checkout_date - checkin_date).days, 0)
        total = float(booking["room_price"]) * nights
    except Exception:
        pass

    return render_template("booking_confirmation.html", booking={
        "id": booking["id"],
        "room_name": booking["room_name"],
        "room_price": booking["room_price"],
        "checkin": booking["checkin"],
        "checkout": booking["checkout"],
        "user_email": booking["user_email"],
        "payment_method": booking["pay_method"] or booking["payment_method"],
        "payment_status": booking["pay_status"] or booking["payment_status"] or "Pending",
        "payment_id": booking["payment_id"],
        "amount": booking["amount"] or total,
        "paid_at": booking["paid_at"],
        "nights": nights,
        "total": total,
    })


@app.route("/my-bookings")
def my_bookings():
    if not logged_in():
        return redirect("/")
    rows = db.fetchall(
        """
        SELECT bookings.id, rooms.name, rooms.price, bookings.checkin, bookings.checkout,
               bookings.payment_method, bookings.payment_status,
               payments.id AS payment_id, payments.amount, payments.payment_status AS pay_status,
               payments.payment_method AS pay_method, payments.paid_at
        FROM bookings
        JOIN rooms ON bookings.room_id = rooms.id
        LEFT JOIN payments ON payments.booking_id = bookings.id
        WHERE bookings.user_email = %s
        ORDER BY bookings.checkin DESC
        """,
        (session["user"],)
    )

    bookings = []
    for row in rows:
        nights = 0
        total = 0
        try:
            checkin_date = datetime.fromisoformat(row["checkin"])
            checkout_date = datetime.fromisoformat(row["checkout"])
            nights = max((checkout_date - checkin_date).days, 0)
            total = float(row["price"]) * nights
        except Exception:
            pass
        bookings.append({
            "id": row["id"],
            "name": row["name"],
            "price": row["price"],
            "checkin": row["checkin"],
            "checkout": row["checkout"],
            "payment_method": row["pay_method"] or row["payment_method"],
            "payment_status": row["pay_status"] or row["payment_status"] or "Pending",
            "payment_id": row["payment_id"],
            "amount": float(row["amount"]) if row["amount"] else total,
            "paid_at": row["paid_at"],
            "nights": nights,
            "total": total,
        })

    return render_template("my_bookings.html", bookings=bookings)


@app.route("/cancel/<int:booking_id>", methods=["POST"])
def cancel(booking_id):
    if not logged_in():
        return redirect("/")
    db.execute(
        "DELETE FROM bookings WHERE id = %s AND user_email = %s",
        (booking_id, session["user"])
    )
    flash("Booking cancelled.", "success")
    return redirect("/my-bookings")


@app.route("/settings")
def settings():
    if not logged_in():
        return redirect("/")
    return render_template("settings.html", user_email=session["user"])


@app.route("/profile")
def profile():
    if not logged_in():
        return redirect("/")
    user_email = session["user"]
    booking_count = db.fetchone("SELECT COUNT(*) AS c FROM bookings WHERE user_email = %s", (user_email,))["c"]
    room_count = db.fetchone("SELECT COUNT(*) AS c FROM rooms")["c"]
    return render_template("profile.html", user_email=user_email, booking_count=booking_count, room_count=room_count)


# ── ADMIN ─────────────────────────────────────────────

@app.route("/admin")
def admin_dashboard():
    guard = admin_required()
    if guard: return guard

    total_users    = db.fetchone("SELECT COUNT(*) AS c FROM users")["c"]
    total_rooms    = db.fetchone("SELECT COUNT(*) AS c FROM rooms")["c"]
    total_bookings = db.fetchone("SELECT COUNT(*) AS c FROM bookings")["c"]
    total_revenue  = db.fetchone("SELECT COALESCE(SUM(amount),0) AS c FROM payments WHERE payment_status = 'Paid'")["c"]
    pending_payments = db.fetchone("SELECT COUNT(*) AS c FROM payments WHERE payment_status = 'Pending'")["c"]
    recent_bookings = db.fetchall("""
        SELECT bookings.id, bookings.user_email, rooms.name AS room_name,
               bookings.checkin, bookings.checkout, bookings.payment_status
        FROM bookings
        JOIN rooms ON bookings.room_id = rooms.id
        ORDER BY bookings.id DESC LIMIT 5
    """)
    return render_template("admin_dashboard.html",
        total_users=total_users, total_rooms=total_rooms,
        total_bookings=total_bookings, total_revenue=total_revenue,
        pending_payments=pending_payments, recent_bookings=recent_bookings
    )


@app.route("/admin/bookings")
def admin_bookings():
    guard = admin_required()
    if guard: return guard
    rows = db.fetchall("""
        SELECT bookings.id, bookings.user_email, rooms.name AS room_name,
               bookings.checkin, bookings.checkout,
               bookings.payment_method, bookings.payment_status,
               payments.amount, payments.payment_status AS pay_status
        FROM bookings
        JOIN rooms ON bookings.room_id = rooms.id
        LEFT JOIN payments ON payments.booking_id = bookings.id
        ORDER BY bookings.id DESC
    """)
    return render_template("admin_bookings.html", bookings=rows)


@app.route("/admin/bookings/delete/<int:booking_id>", methods=["POST"])
def admin_delete_booking(booking_id):
    guard = admin_required()
    if guard: return guard
    db.execute("DELETE FROM bookings WHERE id = %s", (booking_id,))
    flash("Booking deleted.", "success")
    return redirect("/admin/bookings")


@app.route("/admin/payments")
def admin_payments():
    guard = admin_required()
    if guard: return guard
    rows = db.fetchall("""
        SELECT payments.id, payments.booking_id, payments.user_email,
               payments.amount, payments.payment_method, payments.payment_status, payments.paid_at,
               rooms.name AS room_name
        FROM payments
        JOIN bookings ON bookings.id = payments.booking_id
        JOIN rooms ON rooms.id = bookings.room_id
        ORDER BY payments.id DESC
    """)
    return render_template("admin_payments.html", payments=rows)


@app.route("/admin/payments/update/<int:payment_id>", methods=["POST"])
def admin_update_payment(payment_id):
    guard = admin_required()
    if guard: return guard
    status = request.form.get("status", "Pending")
    if status not in ["Pending", "Paid", "Cancelled"]:
        status = "Pending"
    db.execute("UPDATE payments SET payment_status = %s WHERE id = %s", (status, payment_id))
    db.execute("""
        UPDATE bookings SET payment_status = %s
        WHERE id = (SELECT booking_id FROM payments WHERE id = %s)
    """, (status, payment_id))
    flash("Payment status updated.", "success")
    return redirect("/admin/payments")


@app.route("/admin/rooms")
def admin_rooms():
    guard = admin_required()
    if guard: return guard
    rooms_list = db.fetchall("SELECT * FROM rooms ORDER BY id")
    return render_template("admin_rooms.html", rooms=rooms_list)


@app.route("/admin/rooms/add", methods=["POST"])
def admin_add_room():
    guard = admin_required()
    if guard: return guard
    name        = request.form.get("name", "").strip()
    price       = request.form.get("price", 0)
    description = request.form.get("description", "").strip()
    image       = request.form.get("image", "").strip()
    category    = request.form.get("category", "Standard").strip()
    if name and price:
        db.execute(
            "INSERT INTO rooms (name, price, description, image, category) VALUES (%s, %s, %s, %s, %s)",
            (name, float(price), description, image, category)
        )
        flash("Room added.", "success")
    return redirect("/admin/rooms")


@app.route("/admin/rooms/delete/<int:room_id>", methods=["POST"])
def admin_delete_room(room_id):
    guard = admin_required()
    if guard: return guard
    db.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
    flash("Room deleted.", "success")
    return redirect("/admin/rooms")


@app.route("/admin/users")
def admin_users():
    guard = admin_required()
    if guard: return guard
    users = db.fetchall("""
        SELECT users.id, users.email, users.is_admin,
               COUNT(bookings.id) AS booking_count
        FROM users
        LEFT JOIN bookings ON bookings.user_email = users.email
        GROUP BY users.id, users.email, users.is_admin
        ORDER BY users.id
    """)
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    guard = admin_required()
    if guard: return guard
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    flash("User deleted.", "success")
    return redirect("/admin/users")


@app.route("/admin/sql", methods=["GET", "POST"])
def admin_sql():
    guard = admin_required()
    if guard: return guard
    results, columns, error, query = [], [], None, ""
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        try:
            rows = db.fetchall(query)
            if rows:
                columns = list(rows[0].keys())
                results = [list(r.values()) for r in rows]
        except Exception as e:
            error = str(e)
    return render_template("admin_sql.html", query=query, columns=columns, results=results, error=error)


if __name__ == "__main__":
    app.run(debug=True)
