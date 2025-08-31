"""
Hotel Management App — Flask + SQLite (Single File)

How to run:
1) Install deps:  pip install flask
2) Start server:  python hotel_management_app.py
3) Open in browser: http://127.0.0.1:5000

Features:
- SQLite database with tables: rooms, guests, bookings
- Simple Bootstrap UI (list/add rooms, guests, create bookings)
- Check-in / Check-out actions
- Basic validation and foreign keys
- REST-style JSON endpoints (GET collections)

For a real project, switch to SQLAlchemy and add authentication.
"""
from __future__ import annotations
import os
import sqlite3
from contextlib import closing
from datetime import datetime, date
from typing import Any, Dict, Iterable, List, Tuple

from flask import Flask, g, redirect, render_template_string, request, url_for, jsonify, flash

# ---------------------------
# Config
# ---------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "hotel.db")
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY)

# ---------------------------
# Database helpers
# ---------------------------

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db

@app.teardown_appcontext
def close_db(exception: Exception | None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('Single','Double','Suite')),
    price_per_night REAL NOT NULL CHECK(price_per_night >= 0),
    status TEXT NOT NULL DEFAULT 'Available' CHECK(status IN ('Available','Occupied','Maintenance'))
);

CREATE TABLE IF NOT EXISTS guests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    guest_id INTEGER NOT NULL,
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'Booked' CHECK(status IN ('Booked','Checked-In','Checked-Out','Cancelled')),
    total_amount REAL NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
    FOREIGN KEY(guest_id) REFERENCES guests(id) ON DELETE CASCADE
);
"""


def init_db():
    with closing(get_db()) as db:
        db.executescript(SCHEMA_SQL)
        db.commit()

# Initialize DB if missing
if not os.path.exists(DB_PATH):
    with app.app_context():
        init_db()

# ---------------------------
# Templates (Jinja via render_template_string)
# ---------------------------
BASE = r"""
{% set title = title or 'Hotel Manager' %}
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body class="bg-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
      <div class="container">
        <a class="navbar-brand" href="{{ url_for('index') }}">🏨 Hotel Manager</a>
        <div>
          <a class="btn btn-sm btn-outline-light me-2" href="{{ url_for('rooms') }}">Rooms</a>
          <a class="btn btn-sm btn-outline-light me-2" href="{{ url_for('guests') }}">Guests</a>
          <a class="btn btn-sm btn-warning" href="{{ url_for('bookings') }}">Bookings</a>
        </div>
      </div>
    </nav>

    <main class="container">
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          <div class="alert alert-info">{{ messages|join('\n') }}</div>
        {% endif %}
      {% endwith %}
      {{ content|safe }}
    </main>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
"""


def page(title: str, body: str) -> str:
    return render_template_string(BASE, title=title, content=body)

# ---------------------------
# Utility
# ---------------------------

def rows_to_list(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    return [dict(row) for row in cur.fetchall()]


def compute_total_amount(price_per_night: float, check_in: str, check_out: str) -> float:
    d1 = datetime.strptime(check_in, "%Y-%m-%d").date()
    d2 = datetime.strptime(check_out, "%Y-%m-%d").date()
    nights = max((d2 - d1).days, 0)
    return round(price_per_night * nights, 2)

# ---------------------------
# Index
# ---------------------------
@app.route("/")
def index():
    db = get_db()
    stats = {}
    stats["rooms_total"] = db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    stats["rooms_available"] = db.execute("SELECT COUNT(*) FROM rooms WHERE status='Available'").fetchone()[0]
    stats["guests_total"] = db.execute("SELECT COUNT(*) FROM guests").fetchone()[0]
    stats["bookings_today"] = db.execute(
        "SELECT COUNT(*) FROM bookings WHERE date(created_at)=date('now')"
    ).fetchone()[0]

    body = f"""
    <div class='row g-3'>
      <div class='col-md-3'>
        <div class='card shadow-sm'><div class='card-body'>
          <h6 class='text-muted'>Total Rooms</h6>
          <div class='display-6'>{stats['rooms_total']}</div>
        </div></div>
      </div>
      <div class='col-md-3'>
        <div class='card shadow-sm'><div class='card-body'>
          <h6 class='text-muted'>Available</h6>
          <div class='display-6'>{stats['rooms_available']}</div>
        </div></div>
      </div>
      <div class='col-md-3'>
        <div class='card shadow-sm'><div class='card-body'>
          <h6 class='text-muted'>Guests</h6>
          <div class='display-6'>{stats['guests_total']}</div>
        </div></div>
      </div>
      <div class='col-md-3'>
        <div class='card shadow-sm'><div class='card-body'>
          <h6 class='text-muted'>Bookings Today</h6>
          <div class='display-6'>{stats['bookings_today']}</div>
        </div></div>
      </div>
    </div>

    <div class='mt-4 d-flex gap-2'>
      <a class='btn btn-primary' href='{url_for('rooms')}'>Manage Rooms</a>
      <a class='btn btn-secondary' href='{url_for('guests')}'>Manage Guests</a>
      <a class='btn btn-warning' href='{url_for('bookings')}'>Manage Bookings</a>
    </div>
    """
    return page("Dashboard", body)

# ---------------------------
# Rooms
# ---------------------------
@app.route("/rooms", methods=["GET", "POST"])
def rooms():
    db = get_db()
    if request.method == "POST":
        number = request.form.get("number", "").strip()
        rtype = request.form.get("type", "Single")
        price = request.form.get("price", "0").strip()
        if not number:
            flash("Room number is required")
        else:
            try:
                db.execute(
                    "INSERT INTO rooms(number, type, price_per_night) VALUES(?,?,?)",
                    (number, rtype, float(price or 0)),
                )
                db.commit()
                flash("Room added ✔")
                return redirect(url_for("rooms"))
            except sqlite3.IntegrityError as e:
                flash(f"Error: {e}")
    cur = db.execute("SELECT * FROM rooms ORDER BY id DESC")
    rooms_ = rows_to_list(cur)

    body = render_template_string(r"""
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h3>Rooms</h3>
      <form method="post" class="row row-cols-lg-auto g-2 align-items-center">
        <div class="col"><input class="form-control" name="number" placeholder="Room #" required></div>
        <div class="col">
          <select class="form-select" name="type">
            <option>Single</option>
            <option>Double</option>
            <option>Suite</option>
          </select>
        </div>
        <div class="col"><input class="form-control" name="price" type="number" step="0.01" placeholder="Price / night" required></div>
        <div class="col"><button class="btn btn-primary" type="submit">Add Room</button></div>
      </form>
    </div>

    <div class="table-responsive shadow-sm">
      <table class="table table-striped table-hover align-middle mb-0">
        <thead class="table-dark">
          <tr><th>ID</th><th>Number</th><th>Type</th><th>Price</th><th>Status</th></tr>
        </thead>
        <tbody>
          {% for r in rooms %}
          <tr>
            <td>{{ r.id }}</td>
            <td>{{ r.number }}</td>
            <td>{{ r.type }}</td>
            <td>₹ {{ '%.2f'|format(r.price_per_night) }}</td>
            <td>{{ r.status }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    """, rooms=rooms_)
    return page("Rooms", body)

# ---------------------------
# Guests
# ---------------------------
@app.route("/guests", methods=["GET", "POST"])
def guests():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        if not name:
            flash("Guest name is required")
        else:
            db.execute("INSERT INTO guests(name, phone, email) VALUES(?,?,?)", (name, phone, email))
            db.commit()
            flash("Guest added ✔")
            return redirect(url_for("guests"))

    guests_ = rows_to_list(get_db().execute("SELECT * FROM guests ORDER BY id DESC"))

    body = render_template_string(r"""
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h3>Guests</h3>
      <form method="post" class="row row-cols-lg-auto g-2 align-items-center">
        <div class="col"><input class="form-control" name="name" placeholder="Full name" required></div>
        <div class="col"><input class="form-control" name="phone" placeholder="Phone"></div>
        <div class="col"><input class="form-control" name="email" placeholder="Email"></div>
        <div class="col"><button class="btn btn-primary" type="submit">Add Guest</button></div>
      </form>
    </div>

    <div class="table-responsive shadow-sm">
      <table class="table table-striped table-hover align-middle mb-0">
        <thead class="table-dark"><tr><th>ID</th><th>Name</th><th>Phone</th><th>Email</th></tr></thead>
        <tbody>
          {% for g in guests %}
          <tr><td>{{ g.id }}</td><td>{{ g.name }}</td><td>{{ g.phone }}</td><td>{{ g.email }}</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    """, guests=guests_)
    return page("Guests", body)

# ---------------------------
# Bookings
# ---------------------------
@app.route("/bookings", methods=["GET", "POST"])
def bookings():
    db = get_db()
    # Handle actions: check-in, check-out, cancel
    action = request.args.get("action")
    bid = request.args.get("id")
    if action and bid:
        if action == "checkin":
            db.execute("UPDATE bookings SET status='Checked-In' WHERE id=?", (bid,))
            db.execute("UPDATE rooms SET status='Occupied' WHERE id=(SELECT room_id FROM bookings WHERE id=?)", (bid,))
            db.commit()
            flash("Guest checked in ✔")
        elif action == "checkout":
            db.execute("UPDATE bookings SET status='Checked-Out' WHERE id=?", (bid,))
            db.execute("UPDATE rooms SET status='Available' WHERE id=(SELECT room_id FROM bookings WHERE id=?)", (bid,))
            db.commit()
            flash("Guest checked out ✔")
        elif action == "cancel":
            db.execute("UPDATE bookings SET status='Cancelled' WHERE id=?", (bid,))
            db.execute("UPDATE rooms SET status='Available' WHERE id=(SELECT room_id FROM bookings WHERE id=?)", (bid,))
            db.commit()
            flash("Booking cancelled ✖")
        return redirect(url_for("bookings"))

    if request.method == "POST":
        room_id = request.form.get("room_id")
        guest_id = request.form.get("guest_id")
        check_in = request.form.get("check_in")
        check_out = request.form.get("check_out")

        # validate dates
        try:
            d_in = datetime.strptime(check_in, "%Y-%m-%d").date()
            d_out = datetime.strptime(check_out, "%Y-%m-%d").date()
            assert d_out > d_in, "Check-out must be after check-in"
        except Exception as e:
            flash(f"Invalid dates: {e}")
            return redirect(url_for("bookings"))

        # Ensure room exists & get price
        row = db.execute("SELECT id, price_per_night FROM rooms WHERE id=?", (room_id,)).fetchone()
        if not row:
            flash("Invalid room")
            return redirect(url_for("bookings"))
        total = compute_total_amount(row["price_per_night"], check_in, check_out)

        db.execute(
            "INSERT INTO bookings(room_id, guest_id, check_in, check_out, total_amount) VALUES(?,?,?,?,?)",
            (room_id, guest_id, check_in, check_out, total),
        )
        db.execute("UPDATE rooms SET status='Occupied' WHERE id=?", (room_id,))
        db.commit()
        flash("Booking created ✔")
        return redirect(url_for("bookings"))

    rooms_available = rows_to_list(db.execute("SELECT id, number FROM rooms WHERE status!='Maintenance' ORDER BY number"))
    guests_all = rows_to_list(db.execute("SELECT id, name FROM guests ORDER BY id DESC"))

    bookings_ = rows_to_list(db.execute(
        """
        SELECT b.id, r.number AS room_number, g.name AS guest_name,
               b.check_in, b.check_out, b.status, b.total_amount
        FROM bookings b
        JOIN rooms r ON r.id = b.room_id
        JOIN guests g ON g.id = b.guest_id
        ORDER BY b.id DESC
        """
    ))

    body = render_template_string(r"""
    <h3 class="mb-3">Bookings</h3>

    <form method="post" class="card shadow-sm mb-4">
      <div class="card-body row g-3 align-items-end">
        <div class="col-md-3">
          <label class="form-label">Room</label>
          <select class="form-select" name="room_id" required>
            {% for r in rooms %}<option value="{{ r.id }}">#{{ r.number }}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-3">
          <label class="form-label">Guest</label>
          <select class="form-select" name="guest_id" required>
            {% for g in guests %}<option value="{{ g.id }}">{{ g.name }}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-2">
          <label class="form-label">Check-in</label>
          <input class="form-control" type="date" name="check_in" required>
        </div>
        <div class="col-md-2">
          <label class="form-label">Check-out</label>
          <input class="form-control" type="date" name="check_out" required>
        </div>
        <div class="col-md-2">
          <button class="btn btn-warning w-100" type="submit">Create Booking</button>
        </div>
      </div>
    </form>

    <div class="table-responsive shadow-sm">
      <table class="table table-striped table-hover align-middle mb-0">
        <thead class="table-dark">
          <tr><th>ID</th><th>Room</th><th>Guest</th><th>Check-in</th><th>Check-out</th><th>Status</th><th>Total</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {% for b in bookings %}
          <tr>
            <td>{{ b.id }}</td>
            <td>#{{ b.room_number }}</td>
            <td>{{ b.guest_name }}</td>
            <td>{{ b.check_in }}</td>
            <td>{{ b.check_out }}</td>
            <td>{{ b.status }}</td>
            <td>₹ {{ '%.2f'|format(b.total_amount) }}</td>
            <td class="d-flex gap-2">
              <a class="btn btn-sm btn-success" href="{{ url_for('bookings', action='checkin', id=b.id) }}">Check-in</a>
              <a class="btn btn-sm btn-info" href="{{ url_for('bookings', action='checkout', id=b.id) }}">Check-out</a>
              <a class="btn btn-sm btn-outline-danger" href="{{ url_for('bookings', action='cancel', id=b.id) }}">Cancel</a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    """, rooms=rooms_available, guests=guests_all, bookings=bookings_)
    return page("Bookings", body)

# ---------------------------
# Simple JSON APIs
# ---------------------------
@app.route("/api/rooms")
def api_rooms():
    data = rows_to_list(get_db().execute("SELECT * FROM rooms ORDER BY id DESC"))
    return jsonify(data)

@app.route("/api/guests")
def api_guests():
    data = rows_to_list(get_db().execute("SELECT * FROM guests ORDER BY id DESC"))
    return jsonify(data)

@app.route("/api/bookings")
def api_bookings():
    data = rows_to_list(get_db().execute(
        """
        SELECT b.*, r.number AS room_number, g.name AS guest_name
        FROM bookings b
        JOIN rooms r ON r.id = b.room_id
        JOIN guests g ON g.id = b.guest_id
        ORDER BY b.id DESC
        """
    ))
    return jsonify(data)

# ---------------------------
# Seed helper (optional)
# ---------------------------
@app.route("/seed")
def seed():
    db = get_db()
    # Add rooms if empty
    count = db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    if count == 0:
        db.executemany(
            "INSERT INTO rooms(number, type, price_per_night, status) VALUES(?,?,?,?)",
            [
                ("101", "Single", 1500, "Available"),
                ("102", "Double", 2500, "Available"),
                ("201", "Suite", 5000, "Maintenance"),
            ],
        )
    # Add guests if empty
    if db.execute("SELECT COUNT(*) FROM guests").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO guests(name, phone, email) VALUES(?,?,?)",
            [
                ("Aarav Sharma", "9999999999", "aarav@example.com"),
                ("Isha Patel", "8888888888", "isha@example.com"),
            ],
        )
    db.commit()
    flash("Seeded sample data ✔")
    return redirect(url_for("index"))

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    print("\nHotel Management running → http://127.0.0.1:5000")
    print("Seed sample data at → /seed (optional)\n")
    app.run(debug=True)
