import os
import sqlite3
from sqlite3 import IntegrityError
from flask import (
    Flask, g, render_template, request, redirect, url_for, session, flash, current_app
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILENAME = "db.sqlite3"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    db_path = app.config["DATABASE"]
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Create tables if they do not exist
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            priority TEXT NOT NULL DEFAULT 'Medium',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.commit()

    # Ensure priority column exists for older databases
    cur.execute("PRAGMA table_info(tasks)")
    if "priority" not in [row[1] for row in cur.fetchall()]:
        cur.execute(
            "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'Medium'"
        )
        conn.commit()

    # Insert a default admin user if no users exist
    cur.execute("SELECT COUNT(1) FROM users")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            ("admin", generate_password_hash("password")),
        )
        conn.commit()
    conn.close()


def create_app(test_config=None):
    app = Flask(__name__, template_folder="templates")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key"),
        DATABASE=os.path.join(BASE_DIR, DB_FILENAME),
    )

    if test_config is not None:
        app.config.update(test_config)

    # Initialize DB if needed
    init_db(app)

    # Teardown
    app.teardown_appcontext(close_db)

    @app.route("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")
            if not username:
                flash("Username is required", "error")
            elif not password:
                flash("Password is required", "error")
            elif password != confirm:
                flash("Passwords do not match", "error")
            else:
                db = get_db()
                try:
                    db.execute(
                        "INSERT INTO users (username, password) VALUES (?, ?)",
                        (username, generate_password_hash(password)),
                    )
                    db.commit()
                    flash("Registration successful. Please log in.", "success")
                    return redirect(url_for("login"))
                except IntegrityError:
                    flash("Username already taken", "error")
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            db = get_db()
            cur = db.execute(
                "SELECT id, username, password FROM users WHERE username = ?",
                (username,),
            )
            user = cur.fetchone()
            if user and check_password_hash(user["password"], password):
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("dashboard"))
            flash("Invalid credentials", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    def dashboard():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        db = get_db()
        cur = db.execute(
            "SELECT id, title, completed, priority FROM tasks WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        tasks = cur.fetchall()
        pending_count = sum(1 for t in tasks if t["completed"] == 0)
        return render_template("dashboard.html", tasks=tasks, pending_count=pending_count)

    @app.route("/offers")
    def offers():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        offers = [
            {
                "name": "Zain Speed Unlimited",
                "description": "Unlimited 5G data for the fastest streaming, browsing and work-from-home experience.",
                "price": "129 SAR/month",
                "details": ["Unlimited local data", "Free 5G access", "30 GB roaming pack"],
                "theme": "primary",
            },
            {
                "name": "Weekly Voice Bundle",
                "description": "Stay connected with 500 local minutes and 100 SMS every week.",
                "price": "29 SAR/week",
                "details": ["500 local minutes", "100 SMS", "Valid for 7 days"],
                "theme": "secondary",
            },
            {
                "name": "Premium Family Share",
                "description": "Share 60 GB with up to 4 family members on one premium plan.",
                "price": "199 SAR/month",
                "details": ["60 GB shared data", "4 lines included", "Priority customer support"],
                "theme": "dark",
            },
            {
                "name": "Zain Connect Plus",
                "description": "Perfect for remote work with 20 GB data, unlimited social apps, and nightly data.",
                "price": "59 SAR/month",
                "details": ["20 GB data", "Unlimited social apps", "Night-time unlimited data"],
                "theme": "info",
            },
        ]
        return render_template("offers.html", offers=offers)

    @app.route("/profile", methods=["GET", "POST"])
    def profile():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        db = get_db()
        if request.method == "POST":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            cur = db.execute("SELECT password FROM users WHERE id = ?", (user_id,))
            user = cur.fetchone()
            if not user or not check_password_hash(user["password"], current_password):
                flash("Current password is incorrect", "error")
            elif not new_password:
                flash("New password is required", "error")
            elif new_password != confirm_password:
                flash("New passwords do not match", "error")
            else:
                db.execute(
                    "UPDATE users SET password = ? WHERE id = ?",
                    (generate_password_hash(new_password), user_id),
                )
                db.commit()
                flash("Password updated successfully", "success")
                return redirect(url_for("profile"))

        cur = db.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        username = user["username"] if user else "User"

        cur = db.execute(
            "SELECT COUNT(1) AS pending FROM tasks WHERE user_id = ? AND completed = 0",
            (user_id,),
        )
        pending_count = cur.fetchone()["pending"]
        cur = db.execute(
            "SELECT COUNT(1) AS completed FROM tasks WHERE user_id = ? AND completed = 1",
            (user_id,),
        )
        completed_count = cur.fetchone()["completed"]

        return render_template(
            "profile.html",
            username=username,
            pending_count=pending_count,
            completed_count=completed_count,
        )

    @app.route("/team")
    def team():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        members = [
            {"name": "Aisha Al-Harbi", "title": "Team Leader", "avatar": "A"},
            {"name": "Omar Saeed", "title": "Network Engineer", "avatar": "O"},
            {"name": "Nada Kassem", "title": "IT Specialist", "avatar": "N"},
            {"name": "Fahad Al-Mansour", "title": "Security Analyst", "avatar": "F"},
            {"name": "Lina Youssef", "title": "Service Desk Coordinator", "avatar": "L"},
            {"name": "Yousef Ibrahim", "title": "Infrastructure Architect", "avatar": "Y"},
        ]
        return render_template("team.html", members=members)

    @app.route("/analytics")
    def analytics():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        stats = {
            "tasks_total": len(get_db().execute("SELECT id FROM tasks WHERE user_id = ?", (user_id,)).fetchall()),
            "tasks_completed": len(get_db().execute("SELECT id FROM tasks WHERE user_id = ? AND completed = 1", (user_id,)).fetchall()),
            "tasks_pending": len(get_db().execute("SELECT id FROM tasks WHERE user_id = ? AND completed = 0", (user_id,)).fetchall()),
        }
        return render_template("analytics.html", stats=stats)

    @app.route("/support", methods=["GET", "POST"])
    def support():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        subject = ""
        description = ""
        if request.method == "POST":
            subject = request.form.get("subject", "").strip()
            description = request.form.get("description", "").strip()
            if not subject:
                flash("Subject is required.", "error")
            elif not description:
                flash("Description is required.", "error")
            else:
                db = get_db()
                db.execute(
                    "INSERT INTO support_tickets (user_id, subject, description) VALUES (?, ?, ?)",
                    (user_id, subject, description),
                )
                db.commit()
                flash("Your support ticket was submitted successfully.", "success")
                return redirect(url_for("support"))

        return render_template("support.html", subject=subject, description=description)

    @app.route("/add", methods=["POST"])
    def add_task():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        title = request.form.get("title", "").strip()
        priority = request.form.get("priority", "Medium")
        if priority not in ("High", "Medium", "Low"):
            priority = "Medium"
        if title:
            db = get_db()
            db.execute(
                "INSERT INTO tasks (user_id, title, completed, priority) VALUES (?, ?, 0, ?)",
                (user_id, title, priority),
            )
            db.commit()
        return redirect(url_for("dashboard"))

    @app.route("/complete_task/<int:task_id>", methods=["POST"])
    def complete_task(task_id):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        db = get_db()
        cur = db.execute(
            "SELECT completed FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        task = cur.fetchone()
        if task is not None:
            new_value = 0 if task["completed"] else 1
            db.execute(
                "UPDATE tasks SET completed = ? WHERE id = ? AND user_id = ?",
                (new_value, task_id, user_id),
            )
            db.commit()
        return redirect(url_for("dashboard"))

    @app.route("/delete_task/<int:task_id>", methods=["POST"])
    def delete_task(task_id):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        db = get_db()
        db.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        db.commit()
        return redirect(url_for("dashboard"))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="127.0.0.1", port=5000)
