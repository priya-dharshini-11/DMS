from flask import Flask, render_template, request, redirect, session, flash, url_for, send_from_directory
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()
from config import Config
import os
import re
import uuid
# from flask_bootstrap import Bootstrap
from datetime import datetime, timedelta


app = Flask(__name__)
# app.config['BOOTSTRAP_SERVE_LOCAL'] = True
app.config.from_object(Config)
mysql = MySQL(app)
mail = Mail(app)
# Bootstrap(app)
scheduler = BackgroundScheduler(daemon=True)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif",
    "pdf",
    "doc", "docx",
    "xls", "xlsx",
    "ppt", "pptx",
    "txt", "md",
    "csv",
    "ods"
}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    if "user_id" not in session:
        return redirect(url_for("log"))

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT file_name FROM vault_data WHERE file_name=%s AND user_id=%s",
        (filename, session["user_id"])
    )
    item = cur.fetchone()
    cur.close()

    if not item:
        return "Access denied", 403

    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

@app.before_request
def make_session_permanent():
    session.permanent = True



def send_email(to, subject, body):
    msg = Message(subject, recipients=[to], body=body)
    mail.send(msg)

def update_activity(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM activity_logs WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE activity_logs SET last_active_at=NOW() WHERE user_id=%s", (user_id,))
    else:
        cur.execute("INSERT INTO activity_logs (user_id, last_active_at) VALUES (%s, NOW())", (user_id,))
    mysql.connection.commit()
    cur.close()

def check_inactive_users():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT u.id, u.email, a.last_active_at
        FROM users u
        JOIN activity_logs a ON u.id = a.user_id
    """)
    users = cur.fetchall()
    for user in users:
        last_active = user["last_active_at"]
        if last_active and datetime.now() - last_active > timedelta(days=1):
            send_email(user["email"], "Dead Man's Switch Reminder", "Please confirm you are active.")
    cur.close()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = generate_password_hash(request.form["password"])
        admin_key = request.form.get("admin_key", "").strip()

        role = "user"
        if admin_key:
            if admin_key == app.config["ADMIN_REGISTRATION_KEY"]:
                role = "admin"
            else:
                flash("Invalid admin registration key.")
                return redirect(url_for("register"))

        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            (name, email, password, role)
        )
        mysql.connection.commit()
        cur.close()

        flash("Registration successful. Please login.")
        return redirect(url_for("log"))
    return render_template("register.html")

@app.route("/login")
def log():
    return render_template('log.html')

@app.route("/usrlogin", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s AND role='user'", (email,))
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = "user" 
            update_activity(user["id"])
            return redirect(url_for("dashboard"))

        flash("Invalid user credentials")
    return render_template("login.html")

@app.route("/alogin", methods=["GET", "POST"])
def alogin():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s AND role='admin'", (email,))
        admin = cur.fetchone()
        cur.close()

        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session.permanent = True
            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["name"]
            session["role"] = "admin"
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials")
    return render_template("alogin.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("log"))
    update_activity(session["user_id"])
    return render_template("dashboard.html", name=session["name"])

@app.route("/vault", methods=["GET", "POST"])
def vault():
    if "user_id" not in session:
        return redirect(url_for("log"))
    cur = mysql.connection.cursor()
    if request.method == "POST":
        title = request.form["title"].strip()
        content = request.form.get("content","").strip()
        release_enabled = 1 if request.form.get("release_enabled") == "on" else 0
        file =request.files.get("file")

        if file and file.filename:
            if not allowed_file(file.filename):
                flash("File type not allowed")
                return redirect(url_for("vault"))

            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            original_filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{original_filename}"

            file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
            file.save(file_path)

            cur.execute("""
            INSERT INTO vault_data
            (user_id, title, item_type, file_name, original_file_name, file_path, file_type, release_enabled)
            VALUES (%s, %s, 'file', %s, %s, %s, %s, %s)
            """, (session["user_id"],title,unique_filename,original_filename,file_path,file.mimetype,release_enabled))
            mysql.connection.commit()
            flash("File vault item added")

        else:
            cur.execute("""
            INSERT INTO vault_data
            (user_id, title, item_type, content, release_enabled)
            VALUES (%s, %s, 'text', %s, %s)
            """, (session["user_id"], title, content, release_enabled))
            mysql.connection.commit()
            flash("Text vault item added")

    cur.execute("SELECT * FROM vault_data WHERE user_id=%s ORDER BY created_at DESC", (session["user_id"],))
    data = cur.fetchall()
    cur.close()

    return render_template("vault.html", data=data)

@app.route("/view-vault")
def view_vault():
    if "user_id" not in session:
        return redirect(url_for("log"))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM vault_data WHERE user_id=%s ORDER BY created_at DESC", (session["user_id"],))
    data = cur.fetchall()
    cur.close()

    return render_template("view_vault.html", data=data)

@app.route("/delete-vault/<int:item_id>", methods=["POST"])
def delete_vault(item_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM vault_data WHERE id=%s AND user_id=%s", (item_id, session["user_id"]))
    item = cur.fetchone()

    if not item:
        cur.close()
        flash("Vault item not found")
        return redirect(url_for("view_vault"))
    
    if item["item_type"] == "file" and item["file_name"]:
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], item["file_name"])
        if os.path.exists(file_path):
            os.remove(file_path)

    cur.execute("DELETE FROM vault_data WHERE id=%s AND user_id=%s", (item_id, session["user_id"]))
    mysql.connection.commit()
    cur.close()

    flash("Vault item deleted")
    return redirect(url_for("view_vault"))

@app.route("/nominees", methods=["GET", "POST"])
def nominees():
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        relation = request.form.get("relation", "").strip()

        # Validate name
        if not name:
            flash("Nominee name cannot be empty.")
            cur.close()
            return redirect(url_for("nominees"))

        if len(name) > 100:
            flash("Nominee name is too long.")
            cur.close()
            return redirect(url_for("nominees"))

        # Validate email
        email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        if not re.match(email_pattern, email):
            flash("Please enter a valid nominee email address.")
            cur.close()
            return redirect(url_for("nominees"))

        # Validate relation
        if not relation:
            flash("Relationship cannot be empty.")
            cur.close()
            return redirect(url_for("nominees"))

        if len(relation) > 100:
            flash("Relationship is too long.")
            cur.close()
            return redirect(url_for("nominees"))

        # Check for duplicate nominee email for this user
        cur.execute(
            "SELECT id FROM nominees WHERE user_id=%s AND email=%s",
            (session["user_id"], email)
        )

        existing_nominee = cur.fetchone()

        if existing_nominee:
            flash("This nominee has already been added.")
            cur.close()
            return redirect(url_for("nominees"))

        # Insert nominee
        cur.execute(
            """
            INSERT INTO nominees (user_id, name, email, relation)
            VALUES (%s, %s, %s, %s)
            """,
            (session["user_id"], name, email, relation)
        )

        mysql.connection.commit()
        flash("Nominee added successfully.")

    cur.execute(
        "SELECT * FROM nominees WHERE user_id=%s ORDER BY created_at DESC",
        (session["user_id"],)
    )

    data = cur.fetchall()
    cur.close()

    return render_template("nominees.html", data=data)

@app.route("/delete-nominee/<int:nominee_id>", methods=["POST"])
def delete_nominee(nominee_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    # Make sure this nominee belongs to the logged-in user
    cur.execute(
        "SELECT id FROM nominees WHERE id=%s AND user_id=%s",
        (nominee_id, session["user_id"])
    )
    nominee = cur.fetchone()

    if not nominee:
        cur.close()
        flash("Nominee not found.")
        return redirect(url_for("nominees"))

    cur.execute(
        "DELETE FROM nominees WHERE id=%s AND user_id=%s",
        (nominee_id, session["user_id"])
    )

    mysql.connection.commit()
    cur.close()

    flash("Nominee deleted successfully.")
    return redirect(url_for("nominees"))

@app.route("/edit-nominee/<int:nominee_id>", methods=["GET", "POST"])
def edit_nominee(nominee_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    # Make sure this nominee belongs to the logged-in user
    cur.execute(
        "SELECT * FROM nominees WHERE id=%s AND user_id=%s",
        (nominee_id, session["user_id"])
    )

    nominee = cur.fetchone()

    if not nominee:
        cur.close()
        flash("Nominee not found.")
        return redirect(url_for("nominees"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        relation = request.form.get("relation", "").strip()

        # Validate name
        if not name:
            flash("Nominee name cannot be empty.")
            cur.close()
            return redirect(url_for("edit_nominee", nominee_id=nominee_id))

        if len(name) > 100:
            flash("Nominee name is too long.")
            cur.close()
            return redirect(url_for("edit_nominee", nominee_id=nominee_id))

        # Validate email
        email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        if not re.match(email_pattern, email):
            flash("Please enter a valid nominee email address.")
            cur.close()
            return redirect(url_for("edit_nominee", nominee_id=nominee_id))

        # Validate relation
        if not relation:
            flash("Relationship cannot be empty.")
            cur.close()
            return redirect(url_for("edit_nominee", nominee_id=nominee_id))

        if len(relation) > 100:
            flash("Relationship is too long.")
            cur.close()
            return redirect(url_for("edit_nominee", nominee_id=nominee_id))

        # Check whether another nominee of the same user already uses this email
        cur.execute(
            """
            SELECT id FROM nominees
            WHERE user_id=%s AND email=%s AND id!=%s
            """,
            (session["user_id"], email, nominee_id)
        )

        existing_nominee = cur.fetchone()

        if existing_nominee:
            flash("Another nominee with this email already exists.")
            cur.close()
            return redirect(url_for("edit_nominee", nominee_id=nominee_id))

        # Update nominee
        cur.execute(
            """
            UPDATE nominees
            SET name=%s, email=%s, relation=%s
            WHERE id=%s AND user_id=%s
            """,
            (name, email, relation, nominee_id, session["user_id"])
        )

        mysql.connection.commit()
        cur.close()

        flash("Nominee updated successfully.")
        return redirect(url_for("nominees"))

    cur.close()

    return render_template("edit_nominee.html", nominee=nominee)

@app.route("/activity")
def activity():
    if "user_id" not in session:
        return redirect(url_for("login"))
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM activity_logs WHERE user_id=%s", (session["user_id"],))
    data = cur.fetchone()
    cur.close()
    return render_template(r"activity.html", activity=data)

@app.route("/admin-dashboard")
def admin_dashboard():
    if session.get("role") != "admin" or "admin_id" not in session:
        return redirect(url_for("alogin"))

    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) AS total_users FROM users where role='user' ")
    total_users = cur.fetchone()["total_users"]

    cur.execute("SELECT COUNT(*) AS active_users FROM activity_logs WHERE last_active_at >= NOW() - INTERVAL 30 DAY")
    active_users = cur.fetchone()["active_users"]

    cur.execute("SELECT COUNT(*) AS total_vault_items FROM vault_data")
    total_vault_items = cur.fetchone()["total_vault_items"]

    cur.execute("SELECT COUNT(*) AS total_releases FROM releases")
    total_releases = cur.fetchone()["total_releases"]

    cur.execute("SELECT COUNT(*) AS verified_users FROM users WHERE is_verified = 1")
    verified_users = cur.fetchone()["verified_users"]

    cur.execute("SELECT COUNT(*) AS total_admins FROM users WHERE role = 'admin'")
    total_admins = cur.fetchone()["total_admins"]

    cur.execute("""
    SELECT
        u.id,
        u.name,
        COUNT(DISTINCT v.id) AS vault_count,
        COUNT(DISTINCT n.id) AS nominee_count
    FROM users u
    LEFT JOIN vault_data v ON u.id = v.user_id
    LEFT JOIN nominees n ON u.id = n.user_id
    GROUP BY u.id, u.name
    ORDER BY u.id
    """)
    user_stats = cur.fetchall()

    return render_template(
    "admin.html",
    total_users=total_users,
    active_users=active_users,
    total_vault_items=total_vault_items,
    total_releases=total_releases,
    verified_users=verified_users,
    total_admins=total_admins,
    user_stats=user_stats,
    admin_name=session.get("admin_name")
)
@app.route("/about")
def about():
    return render_template("about.html")

if __name__ == "__main__":
    scheduler.add_job(func=check_inactive_users, trigger="interval", hours=24)
    scheduler.start()
    app.run(debug=True)