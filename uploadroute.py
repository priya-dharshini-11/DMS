from werkzeug.utils import secure_filename

@app.route("/documents", methods=["GET", "POST"])
def documents():
    if "user_id" not in session:
        return redirect(url_for("login"))
    cur = mysql.connection.cursor()
    if request.method == "POST":
        file = request.files.get("file")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(path)
            cur.execute(
                "INSERT INTO documents (user_id, file_name, file_path) VALUES (%s, %s, %s)",
                (session["user_id"], filename, path)
            )
            mysql.connection.commit()
            flash("File uploaded successfully")
        else:
            flash("Only PDF, JPG, JPEG, and PNG files are allowed")
    cur.execute("SELECT * FROM documents WHERE user_id=%s", (session["user_id"],))
    data = cur.fetchall()
    cur.close()
    return render_template("documents.html", data=data)