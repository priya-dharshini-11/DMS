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
import secrets
import hashlib
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

def is_valid_nominee_email(email):
    """
    Validate nominee email structure before saving it.
    """
    if not email:
        return False

    if len(email) > 254:
        return False

    if email.count("@") != 1:
        return False

    local, domain = email.rsplit("@", 1)

    if not local or len(local) > 64:
        return False

    if not domain or len(domain) > 253:
        return False

    if not re.match(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$", local):
        return False

    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False

    domain_pattern = (
        r"^(?=.{1,253}$)"
        r"(?:[A-Za-z0-9]"
        r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
        r"[A-Za-z]{2,63}$"
    )

    if not re.match(domain_pattern, domain):
        return False

    return True

def send_email(to, subject, body, attachments=None):
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = app.config["MAIL_USERNAME"]
    msg["To"] = to

    msg.set_content("This email contains HTML content.")
    msg.add_alternative(body, subtype="html")

    if attachments:
        for filename, mimetype, file_path in attachments:
            with open(file_path, "rb") as file:
                file_data = file.read()

            maintype, subtype = mimetype.split("/", 1)

            msg.add_attachment(
                file_data,
                maintype=maintype,
                subtype=subtype,
                filename=filename
            )

    with smtplib.SMTP(
        app.config["MAIL_SERVER"],
        app.config["MAIL_PORT"],
        timeout=10
    ) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(
            app.config["MAIL_USERNAME"],
            app.config["MAIL_PASSWORD"]
        )
        smtp.send_message(msg)

def reset_dms_cycle(user_id, event_type, cur=None):
    if event_type not in ("LOGIN", "ACTIVITY_VERIFIED"):
        raise ValueError("Invalid DMS activity event type")

    now = datetime.now()
    next_checkin = now + timedelta(days=30)

    own_cursor = False

    if cur is None:
        cur = mysql.connection.cursor()
        own_cursor = True

    # Cancel any unfinished release when the user becomes active again.
    cur.execute("""
        SELECT id
        FROM releases
        WHERE user_id=%s
          AND status IN ('PENDING', 'PROCESSING')
        FOR UPDATE
    """, (user_id,))

    pending_releases = cur.fetchall()

    for release in pending_releases:

        release_id = release["id"]

        cur.execute("""
            UPDATE release_deliveries
            SET status='CANCELLED',
                error_message=%s
            WHERE release_id=%s
              AND status IN ('PENDING', 'FAILED')
        """, (
            "Release cancelled because user became active",
            release_id
        ))

        cur.execute("""
            UPDATE releases
            SET status='CANCELLED',
                completed_at=%s
            WHERE id=%s
              AND status IN ('PENDING', 'PROCESSING')
        """, (
            now,
            release_id
        ))

        cur.execute("""
            INSERT INTO activity_history
            (user_id, event_type, description)
            VALUES (
                %s,
                'RELEASE_CANCELLED',
                'Pending release cancelled because user became active'
            )
        """, (user_id,))

    cur.execute("""
        SELECT dms_state
        FROM activity_logs
        WHERE user_id=%s
    """, (user_id,))

    activity = cur.fetchone()

    if activity:
        cur.execute("""
            UPDATE activity_logs
            SET
                last_active_at=%s,
                dms_state='ACTIVE',
                warning_started_at=NULL,
                grace_started_at=NULL,
                release_deadline=NULL,
                released_at=NULL,
                checkin_reminder_sent_at=NULL,
                next_checkin_at=%s
            WHERE user_id=%s
        """, (now, next_checkin, user_id))
    else:
        cur.execute("""
            INSERT INTO activity_logs
            (user_id, last_active_at, dms_state, next_checkin_at)
            VALUES (%s, %s, 'ACTIVE', %s)
        """, (user_id, now, next_checkin))

    description = (
        "User login"
        if event_type == "LOGIN"
        else "User verified activity"
    )

    cur.execute("""
        INSERT INTO activity_history
        (user_id, event_type, description)
        VALUES (%s, %s, %s)
    """, (user_id, event_type, description))

    if own_cursor:
        mysql.connection.commit()
        cur.close()

def send_checkin_reminders():
    """
    Send the scheduled DMS check-in reminder to users
    whose check-in date has arrived.

    A reminder is sent only once for each DMS cycle.
    """

    now = datetime.now()

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT
            u.id,
            u.name,
            u.email,
            a.next_checkin_at,
            a.checkin_reminder_sent_at
        FROM users u
        JOIN activity_logs a ON u.id = a.user_id
        WHERE u.role = 'user'
          AND a.dms_state = 'ACTIVE'
          AND a.next_checkin_at <= %s
          AND a.checkin_reminder_sent_at IS NULL
    """, (now,))

    users = cur.fetchall()

    for user in users:

         # Generate a unique check-in token
        token = secrets.token_urlsafe(32)

        # Store only the SHA-256 hash in the database
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Token remains valid for 24 hours
        expires_at = now + timedelta(hours=24)

        cur.execute("""
            INSERT INTO dms_checkin_tokens
            (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """, (
            user["id"],token_hash,expires_at))

        subject = "Dead Man's Switch - Check-in Required"

        body = f"""
<html>
<body>

<p>Hi {user["name"]},</p>

<p>
This is your scheduled <strong>Dead Man's Switch</strong>
check-in reminder.
</p>

<p>
Your DMS account is waiting for activity confirmation.
</p>

<p>
Please confirm that you are active to keep your DMS cycle active.
</p>

<p>
<a href="http://127.0.0.1:5000/checkin/{token}"
   style="
       display:inline-block;
       padding:12px 24px;
       background-color:#0d6efd;
       color:white;
       text-decoration:none;
       border-radius:6px;
       font-weight:bold;
   ">
   I'M ACTIVE
</a>
</p>

<p>
If you do not confirm your activity, your account may eventually
enter the DMS grace and release process.
</p>

<p>
Regards,<br>
<strong>Dead Man's Switch</strong>
</p>

</body>
</html>
"""

        send_email(user["email"], subject, body)

        cur.execute("""
            UPDATE activity_logs
            SET checkin_reminder_sent_at=%s
            WHERE user_id=%s
              AND checkin_reminder_sent_at IS NULL
        """, (now, user["id"]))

        cur.execute("""
            INSERT INTO activity_history
            (user_id, event_type, description)
            VALUES
            (%s, 'REMINDER_SENT',
             'Scheduled DMS check-in reminder sent')
        """, (user["id"],))

    mysql.connection.commit()
    cur.close()

def process_dms_cycles():
    """
    Process DMS state transitions.

    ACTIVE
        -> GRACE
        -> FINAL_WARNING
        -> RELEASE_READY

    This function only changes DMS state.
    It does NOT send emails or release vault items yet.
    """

    now = datetime.now()

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT
            user_id,
            dms_state,
            next_checkin_at,
            grace_started_at,
            release_deadline
        FROM activity_logs
    """)

    activities = cur.fetchall()

    for activity in activities:

        user_id = activity["user_id"]
        state = activity["dms_state"]
        next_checkin = activity["next_checkin_at"]
        grace_started = activity["grace_started_at"]
        release_deadline = activity["release_deadline"]

        # -------------------------------------------------
        # ACTIVE → GRACE
        # -------------------------------------------------
        if state == "ACTIVE":

            if next_checkin and now >= next_checkin:

                cur.execute("""
                    UPDATE activity_logs
                    SET
                        dms_state='GRACE',
                        grace_started_at=%s
                    WHERE user_id=%s
                      AND dms_state='ACTIVE'
                      AND next_checkin_at <= %s
                """, (now, user_id, now))

                cur.execute("""
                    INSERT INTO activity_history
                    (user_id, event_type, description)
                    VALUES (%s, 'GRACE_STARTED', 'DMS grace period started')
                """, (user_id,))

        # -------------------------------------------------
        # GRACE → FINAL_WARNING
        # -------------------------------------------------
        elif state == "GRACE":

            if grace_started:
                final_warning_time = grace_started + timedelta(days=90)

                if now >= final_warning_time:

                    release_deadline = now + timedelta(days=7)

                    cur.execute("""
                        UPDATE activity_logs
                        SET
                            dms_state='FINAL_WARNING',
                            warning_started_at=%s,
                            release_deadline=%s
                        WHERE user_id=%s
                          AND dms_state='GRACE'
                          AND grace_started_at <= %s
                    """, (
                        now,
                        release_deadline,
                        user_id,
                        grace_started
                    ))

                    cur.execute("""
                        INSERT INTO activity_history
                        (user_id, event_type, description)
                        VALUES (%s, 'FINAL_WARNING',
                                'Final 7-day warning period started')
                    """, (user_id,))

        # -------------------------------------------------
        # FINAL_WARNING → RELEASE_READY
        # -------------------------------------------------
        elif state == "FINAL_WARNING":

            if release_deadline and now >= release_deadline:

                cur.execute("""
                    UPDATE activity_logs
                    SET
                        dms_state='RELEASE_READY'
                    WHERE user_id=%s
                      AND dms_state='FINAL_WARNING'
                      AND release_deadline <= %s
                """, (user_id, now))

    mysql.connection.commit()
    cur.close()

def process_release_ready_users():
    """
    Process users whose DMS state has reached RELEASE_READY.

    This phase creates the release transaction and delivery records.
    It does NOT send emails yet.
    """

    cur = mysql.connection.cursor()

    try:
        cur.execute("""
            SELECT user_id
            FROM activity_logs
            WHERE dms_state='RELEASE_READY'
            FOR UPDATE
        """)

        ready_users = cur.fetchall()

        for activity in ready_users:

            user_id = activity["user_id"]

            # Re-check the state while holding the transaction lock.
            cur.execute("""
                SELECT dms_state
                FROM activity_logs
                WHERE user_id=%s
                FOR UPDATE
            """, (user_id,))

            current_state = cur.fetchone()

            if not current_state:
                continue

            if current_state["dms_state"] != "RELEASE_READY":
                continue

            # Prevent duplicate release records.
            cur.execute("""
                SELECT id
                FROM releases
                WHERE user_id=%s
                  AND status IN ('PENDING', 'PROCESSING', 'COMPLETED')
                LIMIT 1
            """, (user_id,))

            existing_release = cur.fetchone()

            if existing_release:
                continue

            # Get nominees belonging to this user.
            cur.execute("""
                SELECT id
                FROM nominees
                WHERE user_id=%s
            """, (user_id,))

            nominees = cur.fetchall()

            # Get only vault items explicitly selected for release.
            cur.execute("""
                SELECT id
                FROM vault_data
                WHERE user_id=%s
                  AND release_enabled=1
            """, (user_id,))

            vault_items = cur.fetchall()

            # Create release record even when there is
            # nothing to deliver. This preserves the event.
            cur.execute("""
                INSERT INTO releases
                (user_id, release_reason, status, started_at)
                VALUES (%s, %s, 'PROCESSING', %s)
            """, (
                user_id,
                "DMS inactivity release",
                datetime.now()
            ))

            release_id = cur.lastrowid

            # Create one delivery record for every
            # nominee × selected vault item combination.
            for nominee in nominees:
                for item in vault_items:

                    cur.execute("""
                        INSERT INTO release_deliveries
                        (release_id, nominee_id, vault_item_id, status)
                        VALUES (%s, %s, %s, 'PENDING')
                    """, (
                        release_id,
                        nominee["id"],
                        item["id"]
                    ))

            # Record the release event.
            cur.execute("""
                INSERT INTO activity_history
                (user_id, event_type, description)
                VALUES (
                    %s,
                    'RELEASE_TRIGGERED',
                    'DMS release transaction created'
                )
            """, (user_id,))

            
        mysql.connection.commit()

    except Exception:
        mysql.connection.rollback()
        raise

    finally:
        cur.close()

def deliver_pending_releases():
    """
    Deliver pending or failed DMS release deliveries.

    SENT deliveries are never resent.
    PENDING and FAILED deliveries may be retried.

    Release state:
    - All deliveries SENT -> COMPLETED and user becomes RELEASED
    - Any delivery still FAILED/PENDING -> PARTIAL
    """

    cur = mysql.connection.cursor()

    try:
        # Process releases that still have deliveries to complete.
        cur.execute("""
            SELECT
                r.id AS release_id,
                r.user_id
            FROM releases r
            WHERE r.status IN ('PROCESSING', 'PARTIAL')
            ORDER BY r.id
        """)

        releases = cur.fetchall()

        for release in releases:

            release_id = release["release_id"]
            user_id = release["user_id"]

            # Get owner details.
            cur.execute("""
                SELECT name, email
                FROM users
                WHERE id=%s
            """, (user_id,))

            owner = cur.fetchone()

            if not owner:
                continue

            # Get only deliveries that still need processing.
            cur.execute("""
                SELECT
                    rd.id AS delivery_id,
                    rd.nominee_id,
                    rd.vault_item_id,
                    rd.status AS delivery_status,
                    n.name AS nominee_name,
                    n.email AS nominee_email,
                    v.title,
                    v.item_type,
                    v.content,
                    v.file_path,
                    v.file_name,
                    v.original_file_name,
                    v.file_type
                FROM release_deliveries rd
                JOIN nominees n
                    ON rd.nominee_id = n.id
                JOIN vault_data v
                    ON rd.vault_item_id = v.id
                WHERE rd.release_id=%s
                  AND rd.status IN ('PENDING', 'FAILED')
                ORDER BY rd.id
            """, (release_id,))

            pending_deliveries = cur.fetchall()

            # Process each individual delivery.
            for delivery in pending_deliveries:

                delivery_id = delivery["delivery_id"]
                nominee_email = delivery["nominee_email"]
                nominee_name = delivery["nominee_name"]

                body_parts = [
                    "<h2>Dead Man's Switch Release</h2>",
                    f"<p>Hello {nominee_name},</p>",
                    f"<p>This message contains digital items released by "
                    f"{owner['name']} through the Dead Man's Switch system.</p>"
                ]

                attachments = []
                delivery_failed = False
                failure_reason = None

                item = delivery

                if item["item_type"] == "text":

                    body_parts.append(
                        f"<h3>{item['title']}</h3>"
                    )

                    body_parts.append(
                        f"<p>{item['content'] or ''}</p>"
                    )

                else:

                    file_path = item["file_path"]

                    if not file_path or not os.path.exists(file_path):

                        delivery_failed = True
                        failure_reason = "Release file not found"

                    else:

                        attachments.append((
                            item["original_file_name"]
                            or item["file_name"],
                            item["file_type"]
                            or "application/octet-stream",
                            file_path
                        ))

                if delivery_failed:

                    cur.execute("""
                        UPDATE release_deliveries
                        SET status='FAILED',
                            error_message=%s
                        WHERE id=%s
                          AND status IN ('PENDING', 'FAILED')
                    """, (
                        failure_reason,
                        delivery_id
                    ))

                    continue

                try:

                    send_email(
                        nominee_email,
                        "Dead Man's Switch - Released Items",
                        "".join(body_parts),
                        attachments=attachments
                    )

                    cur.execute("""
                        UPDATE release_deliveries
                        SET status='SENT',
                            sent_at=%s,
                            error_message=NULL
                        WHERE id=%s
                          AND status IN ('PENDING', 'FAILED')
                    """, (
                        datetime.now(),
                        delivery_id
                    ))

                    cur.execute("""
                        INSERT INTO activity_history
                        (user_id, event_type, description)
                        VALUES (
                            %s,
                            'NOMINEE_NOTIFIED',
                            'Release notification sent to nominee'
                        )
                    """, (user_id,))

                except Exception as error:

                    cur.execute("""
                        UPDATE release_deliveries
                        SET status='FAILED',
                            error_message=%s
                        WHERE id=%s
                          AND status IN ('PENDING', 'FAILED')
                    """, (
                        str(error)[:255],
                        delivery_id
                    ))

            # Check the complete delivery state after processing.
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(status='SENT') AS sent_count,
                    SUM(status='FAILED') AS failed_count,
                    SUM(status='PENDING') AS pending_count
                FROM release_deliveries
                WHERE release_id=%s
            """, (release_id,))

            delivery_status = cur.fetchone()

            total = delivery_status["total"] or 0
            sent_count = delivery_status["sent_count"] or 0
            failed_count = delivery_status["failed_count"] or 0
            pending_count = delivery_status["pending_count"] or 0

            # Every delivery succeeded.
            if total > 0 and sent_count == total:

                cur.execute("""
                    UPDATE releases
                    SET status='COMPLETED',
                        completed_at=%s
                    WHERE id=%s
                      AND status IN ('PROCESSING', 'PARTIAL')
                """, (
                    datetime.now(),
                    release_id
                ))

                cur.execute("""
                    UPDATE activity_logs
                    SET dms_state='RELEASED',
                        released_at=%s
                    WHERE user_id=%s
                      AND dms_state='RELEASE_READY'
                """, (
                    datetime.now(),
                    user_id
                ))

                cur.execute("""
                    INSERT INTO activity_history
                    (user_id, event_type, description)
                    VALUES (
                        %s,
                        'RELEASE_CONFIRMED',
                        'All selected vault items were released successfully'
                    )
                """, (user_id,))

            # Some deliveries still need retry.
            elif failed_count > 0 or pending_count > 0:

                cur.execute("""
                    UPDATE releases
                    SET status='PARTIAL',
                        completed_at=NULL
                    WHERE id=%s
                      AND status IN ('PROCESSING', 'PARTIAL')
                """, (release_id,))

        mysql.connection.commit()

    except Exception:
        mysql.connection.rollback()
        raise

    finally:
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
            reset_dms_cycle(user["id"], "LOGIN")
            return redirect(url_for("dashboard"))

        flash("Invalid user credentials")
    return render_template("login.html")

@app.route("/checkin/<token>", methods=["GET", "POST"])
def checkin(token):

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now()

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT *
        FROM dms_checkin_tokens
        WHERE token_hash=%s
    """, (token_hash,))

    checkin_token = cur.fetchone()

    if not checkin_token:
        cur.close()
        return render_template(
            "checkin_expired.html"
        )

    if checkin_token["used_at"] is not None:
        cur.close()
        return render_template(
            "checkin_expired.html"
        )

    if now >= checkin_token["expires_at"]:
        cur.close()
        return render_template(
            "checkin_expired.html"
        )

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        cur.execute("""
            SELECT *
            FROM users
            WHERE email=%s
              AND role='user'
        """, (email,))

        user = cur.fetchone()

        if user and user["id"] == checkin_token["user_id"]:

            if check_password_hash(
                user["password_hash"],
                password
            ):

                try:
                    cur.execute("""
                    UPDATE dms_checkin_tokens
                    SET used_at=%s
                    WHERE id=%s
                    AND used_at IS NULL
                    """, (
                    now,
                    checkin_token["id"]
                    ))

                    if cur.rowcount != 1:
                        mysql.connection.rollback()
                        cur.close()
                        return render_template("checkin_expired.html")

                    reset_dms_cycle(
                    user["id"],
                    "ACTIVITY_VERIFIED",
                    cur=cur
                    )

                    mysql.connection.commit()
                    cur.close()

                    return render_template(
                    "checkin_success.html",
                    name=user["name"]
                )

                except Exception:
                    mysql.connection.rollback()
                    cur.close()

                    flash("Unable to verify activity. Please try again.")
                    return render_template("checkin.html")

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

            cur.execute("""
    INSERT INTO activity_history
    (user_id, event_type, description)
    VALUES (%s, 'VAULT_ITEM_ADDED', 'Vault item added')
""", (session["user_id"],))

            mysql.connection.commit()
            flash("File vault item added")

        else:
            cur.execute("""
            INSERT INTO vault_data
            (user_id, title, item_type, content, release_enabled)
            VALUES (%s, %s, 'text', %s, %s)
            """, (session["user_id"], title, content, release_enabled))

            cur.execute("""
            INSERT INTO activity_history
            (user_id, event_type, description)
            VALUES (%s, 'VAULT_ITEM_ADDED', 'Vault item added')
            """, (session["user_id"],))

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

@app.route("/edit-vault/<int:item_id>", methods=["GET", "POST"])
def edit_vault(item_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    # Make sure this vault item belongs to the logged-in user
    cur.execute(
        """
        SELECT *
        FROM vault_data
        WHERE id=%s AND user_id=%s
        """,
        (item_id, session["user_id"])
    )
    item = cur.fetchone()

    if not item:
        cur.close()
        flash("Vault item not found.")
        return redirect(url_for("view_vault"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        release_enabled = 1 if request.form.get("release_enabled") == "on" else 0

        if not title:
            flash("Title cannot be empty.")
            cur.close()
            return redirect(url_for("edit_vault", item_id=item_id))

        if len(title) > 150:
            flash("Title is too long.")
            cur.close()
            return redirect(url_for("edit_vault", item_id=item_id))

        cur.execute(
            """
            UPDATE vault_data
            SET title=%s, release_enabled=%s
            WHERE id=%s AND user_id=%s
            """,
            (title, release_enabled, item_id, session["user_id"])
        )

        cur.execute("""
        INSERT INTO activity_history
        (user_id, event_type, description)
        VALUES (%s, 'VAULT_ITEM_UPDATED', 'Vault item updated')
        """, (session["user_id"],))

        mysql.connection.commit()
        cur.close()

        flash("Vault item updated successfully.")
        return redirect(url_for("view_vault"))

    cur.close()
    return render_template("edit_vault.html", item=item)

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

    cur.execute("""
    INSERT INTO activity_history
    (user_id, event_type, description)
    VALUES (%s, 'VAULT_ITEM_DELETED', 'Vault item deleted')
    """, (session["user_id"],))

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
        # Validate email
        if not is_valid_nominee_email(email):
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

        cur.execute(
        """
        INSERT INTO activity_history
        (user_id, event_type, description)
        VALUES (%s, 'NOMINEE_ADDED', 'Nominee added')
        """,
        (session["user_id"],)
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

    cur.execute(
        """
        INSERT INTO activity_history
        (user_id, event_type, description)
        VALUES (%s, 'NOMINEE_DELETED', 'Nominee deleted')
        """,
        (session["user_id"],)
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
        # Validate email
        if not is_valid_nominee_email(email):
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

        # Check whether anything actually changed
        if (
            name == nominee["name"]
            and email == nominee["email"]
            and relation == nominee["relation"]
        ):
            cur.close()
            flash("No changes were made.")
            return redirect(url_for("nominees"))

        # Update nominee
        cur.execute(
             """
            UPDATE nominees
            SET name=%s, email=%s, relation=%s
            WHERE id=%s AND user_id=%s
            """,
            (name, email, relation, nominee_id, session["user_id"])
        )

        cur.execute(
            """
            INSERT INTO activity_history
            (user_id, event_type, description)
            VALUES (%s, 'NOMINEE_UPDATED', 'Nominee updated')
            """,
            (session["user_id"],)
        )

        mysql.connection.commit()
        cur.close()
        flash("Nominee updated successfully.")
        return redirect(url_for("nominees"))

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
    app.run(debug=True)