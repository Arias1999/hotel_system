from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import hashlib
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "secret123")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
DB = "hotel.db"


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                description TEXT,
                image TEXT,
                category TEXT DEFAULT 'Standard'
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                room_id INTEGER NOT NULL,
                checkin TEXT NOT NULL,
                checkout TEXT NOT NULL,
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            );
        """)

        # Seed rooms if empty
        count = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO rooms (name, price, description, image, category) VALUES (?, ?, ?, ?, ?)",
                [
                    ("Deluxe Room",        2500, "Spacious room with city view and a king-size bed.",          "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=600", "Standard"),
                    ("Standard Room",      1500, "Comfortable room with all essential amenities.",             "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=600", "Standard"),
                    ("Ocean Suite",        5000, "Luxury suite with a private balcony and ocean view.",        "https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?w=600", "Suite"),
                    ("Family Room",        3500, "Large room with two beds, perfect for families.",            "https://images.unsplash.com/photo-1566665797739-1674de7a421a?w=600", "Family"),
                    ("Presidential Suite", 9500, "Top-floor suite with panoramic views and butler service.",   "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=600", "Suite"),
                    ("Twin Room",          1800, "Two single beds ideal for friends or colleagues.",           "https://images.unsplash.com/photo-1595576508898-0ad5c879a061?w=600", "Standard"),
                    ("Honeymoon Suite",    6500, "Romantic suite with jacuzzi and rose petal decor.",          "https://images.unsplash.com/photo-1611892440504-42a792e24d32?w=600", "Luxury"),
                    ("Garden View Room",   2000, "Peaceful room overlooking the hotel garden.",                "https://images.unsplash.com/photo-1512918728675-ed5a9ecdebfd?w=600", "Standard"),
                    ("Business Room",      2200, "Equipped with work desk, fast Wi-Fi and city view.",         "https://images.unsplash.com/photo-1590490360182-c33d57733427?w=600", "Luxury"),
                    ("Penthouse",         12000, "Exclusive penthouse with private pool and rooftop terrace.", "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=600", "Luxury"),
                    ("Skyline Room",        2800, "Modern room with stunning skyline views and smart TV.",      "https://images.unsplash.com/photo-1618773928121-c32242e63f39?w=600", "Standard"),
                    ("Royal Suite",         8000, "Opulent suite with antique furnishings and butler service.", "https://images.unsplash.com/photo-1578683010236-d716f9a3f461?w=600", "Suite"),
                ]
            )


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def valid_email(email):
    return "@" in email and "." in email and len(email) >= 5


def logged_in():
    return "user" in session


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
        with get_db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ? AND password = ?", (email, password)
            ).fetchone()
        if user:
            session["user"] = email
            return redirect("/home")
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
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
            try:
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_password)
                    )
                flash("Account created! Please log in.", "success")
                return redirect("/")
            except sqlite3.IntegrityError:
                flash("Email already registered.", "error")

    return render_template("signup.html", email=email)


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
    with get_db() as conn:
        if category == "All":
            rooms = conn.execute("SELECT * FROM rooms").fetchall()
        else:
            rooms = conn.execute("SELECT * FROM rooms WHERE category = ?", (category,)).fetchall()
        categories = [r["category"] for r in conn.execute("SELECT DISTINCT category FROM rooms").fetchall()]
    return render_template("rooms.html", rooms=rooms, categories=categories, active_category=category)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/room/<int:room_id>")
def room_detail(room_id):
    if not logged_in():
        return redirect("/signup")
    with get_db() as conn:
        room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        rooms = conn.execute("SELECT * FROM rooms").fetchall()
        categories = [r["category"] for r in conn.execute("SELECT DISTINCT category FROM rooms").fetchall()]
    if not room:
        return redirect("/rooms")
    return render_template("room_detail.html", room=room, rooms=rooms, categories=categories, active_category="All")


@app.route("/book/<int:room_id>", methods=["GET", "POST"])
def book(room_id):
    if not logged_in():
        return redirect("/")
    with get_db() as conn:
        room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if not room:
        flash("Room not found.", "error")
        return redirect("/rooms")

    checkin = ""
    checkout = ""
    if request.method == "POST":
        checkin = request.form.get("checkin", "")
        checkout = request.form.get("checkout", "")

        if not checkin or not checkout:
            flash("Please select both check-in and check-out dates.", "error")
            return render_template("booking.html", room=room, checkin=checkin, checkout=checkout)

        if checkin >= checkout:
            flash("Check-out date must be after check-in date.", "error")
            return render_template("booking.html", room=room, checkin=checkin, checkout=checkout)

        with get_db() as conn:
            conflict = conn.execute(
                "SELECT 1 FROM bookings WHERE room_id = ? AND NOT (checkout <= ? OR checkin >= ?)",
                (room_id, checkin, checkout)
            ).fetchone()
            if conflict:
                flash("This room is already booked for the selected dates. Please choose another date range.", "error")
                return render_template("booking.html", room=room, checkin=checkin, checkout=checkout)

            conn.execute(
                "INSERT INTO bookings (user_email, room_id, checkin, checkout) VALUES (?, ?, ?, ?)",
                (session["user"], room_id, checkin, checkout)
            )

        flash("Booking confirmed!", "success")
        return redirect("/my-bookings")

    return render_template("booking.html", room=room, checkin=checkin, checkout=checkout)


@app.route("/my-bookings")
def my_bookings():
    if not logged_in():
        return redirect("/")
    with get_db() as conn:
        bookings = conn.execute("""
            SELECT bookings.id, rooms.name, rooms.price, bookings.checkin, bookings.checkout
            FROM bookings
            JOIN rooms ON bookings.room_id = rooms.id
            WHERE bookings.user_email = ?
            ORDER BY bookings.checkin DESC
        """, (session["user"],)).fetchall()
    return render_template("my_bookings.html", bookings=bookings)


@app.route("/cancel/<int:booking_id>", methods=["POST"])
def cancel(booking_id):
    if not logged_in():
        return redirect("/")
    with get_db() as conn:
        conn.execute(
            "DELETE FROM bookings WHERE id = ? AND user_email = ?",
            (booking_id, session["user"])
        )
    flash("Booking cancelled.", "success")
    return redirect("/my-bookings")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
