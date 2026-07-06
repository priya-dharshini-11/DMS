def check_inactive_users():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.email, a.last_active_at
        FROM users u
        LEFT JOIN activity_logs a ON u.id = a.user_id
    """)
    rows = cur.fetchall()
    for user in rows:
        if not user["last_active_at"]:
            continue
        inactive_days = (datetime.now() - user["last_active_at"]).days
        if inactive_days >= 30:
            send_email(user["email"], "Dead Man's Switch Reminder", "Please confirm you are active.")
        if inactive_days >= 45:
            trigger_emergency_release(user["id"])
    cur.close()