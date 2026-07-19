from flask import Flask, render_template, request, redirect, session, flash, url_for
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.config.from_object(Config)
mysql = MySQL(app)
mail = Mail(app)
scheduler = BackgroundScheduler(daemon=True)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

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
        if last_active and datetime.now() - last_active > timedelta(days=30):
            send_email(user["email"], "Dead Man's Switch Reminder", "Please confirm you are active.")
    cur.close()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)", (name, email, password))
        mysql.connection.commit()
        cur.close()
        flash("Registration successful. Please login.")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            update_activity(user["id"])
            return redirect(url_for("dashboard"))
        flash("Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    update_activity(session["user_id"])
    return render_template("dashboard.html", name=session["name"])

@app.route("/vault", methods=["GET", "POST"])
def vault():
    if "user_id" not in session:
        return redirect(url_for("login"))
    cur = mysql.connection.cursor()
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        cur.execute("INSERT INTO vault_data (user_id, title, content) VALUES (%s, %s, %s)",
                    (session["user_id"], title, content))
        mysql.connection.commit()
        flash("Vault item added")
    cur.execute("SELECT * FROM vault_data WHERE user_id=%s", (session["user_id"],))
    data = cur.fetchall()
    cur.close()
    return render_template("vault.html", data=data)

@app.route("/nominees", methods=["GET", "POST"])
def nominees():
    if "user_id" not in session:
        return redirect(url_for("login"))
    cur = mysql.connection.cursor()
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        relation = request.form["relation"]
        cur.execute("INSERT INTO nominees (user_id, name, email, relation) VALUES (%s, %s, %s, %s)",
                    (session["user_id"], name, email, relation))
        mysql.connection.commit()
        flash("Nominee added")
    cur.execute("SELECT * FROM nominees WHERE user_id=%s", (session["user_id"],))
    data = cur.fetchall()
    cur.close()
    return render_template("nominees.html", data=data)

@app.route("/activity")
def activity():
    if "user_id" not in session:
        return redirect(url_for("login"))
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM activity_logs WHERE user_id=%s", (session["user_id"],))
    data = cur.fetchone()
    cur.close()
    return render_template("activity.html", activity=data)

@app.route("/admin")
def admin():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    cur.close()
    return render_template("admin.html", users=users)

if __name__ == "__main__":
    scheduler.add_job(func=check_inactive_users, trigger="interval", hours=24)
    scheduler.start()
    app.run(debug=True)