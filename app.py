from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "assignment_portal_secret"

DATABASE = "assignment_portal.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT,
            due_date TEXT NOT NULL,
            max_marks INTEGER NOT NULL,
            faculty_id INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER,
            student_id INTEGER,
            project_link TEXT,
            work_notes TEXT,
            submitted_at TEXT,
            marks INTEGER,
            feedback TEXT,
            status TEXT DEFAULT 'Submitted'
        )
    """)

    conn.commit()
    conn.close()


@app.route("/")
def home():
    if "user_id" in session:
        if session["role"] == "faculty":
            return redirect("/faculty")
        return redirect("/student")

    return redirect("/login")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, password)
        ).fetchone()

        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "faculty":
                return redirect("/faculty")
            else:
                return redirect("/student")

        flash("Invalid email or password")

    return render_template("login.html")


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        conn = get_db()

        try:
            conn.execute(
                "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                (name, email, password, role)
            )
            conn.commit()
            flash("Registration successful. Please login.")
            return redirect("/login")

        except sqlite3.IntegrityError:
            flash("Email already registered.")

        finally:
            conn.close()

    return render_template("register.html")


# ---------------- FACULTY DASHBOARD ----------------

@app.route("/faculty")
def faculty():

    if "user_id" not in session or session["role"] != "faculty":
        return redirect("/login")

    conn = get_db()

    assignments = conn.execute(
        "SELECT * FROM assignments WHERE faculty_id=?",
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "faculty.html",
        assignments=assignments
    )


# ---------------- CREATE ASSIGNMENT ----------------

@app.route("/create-assignment", methods=["GET", "POST"])
def create_assignment():

    if "user_id" not in session or session["role"] != "faculty":
        return redirect("/login")

    if request.method == "POST":

        title = request.form["title"]
        subject = request.form["subject"]
        description = request.form["description"]
        due_date = request.form["due_date"]
        max_marks = request.form["max_marks"]

        if not title or not subject or not due_date or not max_marks:
            flash("Please fill all required fields.")
            return redirect("/create-assignment")

        try:
            max_marks = int(max_marks)

            if max_marks <= 0:
                flash("Maximum marks must be greater than 0.")
                return redirect("/create-assignment")

        except ValueError:
            flash("Maximum marks must be a number.")
            return redirect("/create-assignment")

        conn = get_db()

        conn.execute("""
            INSERT INTO assignments
            (title, subject, description, due_date, max_marks, faculty_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title,
            subject,
            description,
            due_date,
            max_marks,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        flash("Assignment created successfully!")
        return redirect("/faculty")

    return render_template("create_assignment.html")


# ---------------- VIEW SUBMISSIONS ----------------

@app.route("/submissions/<int:assignment_id>", methods=["GET", "POST"])
def submissions(assignment_id):

    if "user_id" not in session or session["role"] != "faculty":
        return redirect("/login")

    conn = get_db()

    assignment = conn.execute(
        "SELECT * FROM assignments WHERE id=?",
        (assignment_id,)
    ).fetchone()

    if request.method == "POST":

        submission_id = request.form["submission_id"]
        marks = request.form["marks"]
        feedback = request.form["feedback"]

        try:
            marks = int(marks)

            if marks < 0 or marks > assignment["max_marks"]:
                flash(
                    f"Marks must be between 0 and {assignment['max_marks']}."
                )
                return redirect(f"/submissions/{assignment_id}")

        except ValueError:
            flash("Marks must be a number.")
            return redirect(f"/submissions/{assignment_id}")

        conn.execute("""
            UPDATE submissions
            SET marks=?, feedback=?, status='Graded'
            WHERE id=?
        """, (marks, feedback, submission_id))

        conn.commit()

        flash("Grade saved successfully.")

    submissions_list = conn.execute("""
        SELECT submissions.*, users.name, users.email
        FROM submissions
        JOIN users ON submissions.student_id = users.id
        WHERE submissions.assignment_id=?
    """, (assignment_id,)).fetchall()

    conn.close()

    return render_template(
        "submissions.html",
        assignment=assignment,
        submissions=submissions_list
    )


# ---------------- STUDENT DASHBOARD ----------------

@app.route("/student")
def student():

    if "user_id" not in session or session["role"] != "student":
        return redirect("/login")

    conn = get_db()

    assignments = conn.execute("""
        SELECT assignments.*,
        submissions.id AS submission_id,
        submissions.status,
        submissions.marks,
        submissions.feedback
        FROM assignments
        LEFT JOIN submissions
        ON assignments.id = submissions.assignment_id
        AND submissions.student_id=?
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "student.html",
        assignments=assignments
    )


# ---------------- SUBMIT ASSIGNMENT ----------------

@app.route("/submit/<int:assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):

    if "user_id" not in session or session["role"] != "student":
        return redirect("/login")

    project_link = request.form["project_link"]
    work_notes = request.form["work_notes"]

    conn = get_db()

    assignment = conn.execute(
        "SELECT * FROM assignments WHERE id=?",
        (assignment_id,)
    ).fetchone()

    # Check duplicate submission
    existing = conn.execute("""
        SELECT * FROM submissions
        WHERE assignment_id=? AND student_id=?
    """, (assignment_id, session["user_id"])).fetchone()

    if existing:
        flash("You have already submitted this assignment.")
        conn.close()
        return redirect("/student")

    # Check deadline
    due_date = datetime.strptime(
        assignment["due_date"],
        "%Y-%m-%d"
    ).date()

    today = datetime.now().date()

    if today > due_date:
        flash("Submission rejected. Assignment deadline has passed.")
        conn.close()
        return redirect("/student")

    conn.execute("""
        INSERT INTO submissions
        (assignment_id, student_id, project_link, work_notes,
         submitted_at, status)
        VALUES (?, ?, ?, ?, ?, 'Submitted')
    """, (
        assignment_id,
        session["user_id"],
        project_link,
        work_notes,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    flash("Assignment submitted successfully!")
    return redirect("/student")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


init_db()

if __name__ == "__main__":
    app.run(debug=True)