from datetime import datetime
import sqlite3
from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY")

def init_db():
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS students(
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL
        )
        ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teachers(
        teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL
        )
        ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS classes(
        class_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        teacher_id INTEGER NOT NULL,
        FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
        )
        ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS classes_students( 
        class_id INTEGER,
        student_id INTEGER,
        study_time INTEGER,
        PRIMARY KEY (class_id, student_id),
        FOREIGN KEY (class_id) REFERENCES Classes(class_id),
        FOREIGN KEY (student_id) REFERENCES Students(student_id)  
        )
        ''') #have to make junction table here so it can have many to many relationship
    conn.commit()
    conn.close()

init_db()

def find_duplicate(cursor, username): #do i need this function?? - could it be used to find duplicate class codes or something?
    cursor.execute("SELECT COUNT(*) FROM students WHERE username = ?", (username,))
    student_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM teachers WHERE username = ?", (username,))
    teacher_count = cursor.fetchone()[0]
    if student_count > 0 or teacher_count > 0:
        return True

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        name = request.form.get("name")
        hashed_password = generate_password_hash(password)
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        if find_duplicate(cursor, username):
            flash('Username already exists', 'error')
        else:
            if session['user_type'] == 'teacher':
                cursor.execute("INSERT INTO teachers (username, password, name) VALUES (?, ?, ?)", (username, hashed_password, name))
                conn.commit()
                flash('Registration successful. Please login', 'success')
                conn.close()
                return redirect('/login')
            else:
                cursor.execute("INSERT INTO students (username, password, name, study_time) VALUES (?, ?, ?, 0)", (username, hashed_password, name))
                conn.commit()
                flash('Registration successful. Please login', 'success')
                conn.close()
                return redirect('/login')
    user_type = request.args.get("user_type")
    if user_type == "teacher":
        session['user_type'] = 'teacher'
        print("teacher")
    else:
        session['user_type'] = 'student'
        print("student")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE username = ?", (username,))
        student_record = cursor.fetchone()
        cursor.execute("SELECT * FROM teachers WHERE username = ?", (username,))
        teacher_record = cursor.fetchone()
        conn.close()
        if student_record and check_password_hash(student_record[2], password): #user is array from database - password is in 3rd slot (begins from 0)
            session['user_id'] = student_record[0]
            session['username'] = student_record[1]
            session['name'] = student_record[3]
            session['user_type'] = 'student'
            flash('Login successful', 'success')
            return redirect('/dashboard')
        elif teacher_record and check_password_hash(teacher_record[2], password):
            session['user_id'] = teacher_record[0]
            session['username'] = teacher_record[1]
            session['name'] = teacher_record[3]
            session['user_type'] = 'teacher'
            flash('Login successful', 'success')
            return redirect('/dashboard')
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/dashboard', methods=["GET"])
def dashboard():
    if 'user_id' not in session:
        session.clear()
        return redirect('/login')
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    if session['user_type'] == 'student':
        cursor.execute('''
        SELECT classes.class_id, classes.name
            FROM classes
            JOIN classes_students ON classes.class_id = classes_students.class_id
            JOIN students ON students.student_id = classes_students.student_id
            WHERE students.student_id = ?
            ''', (session['user_id'],))
    else:
        cursor.execute("SELECT * FROM classes WHERE teacher_id = ?", (session['user_id'],))
    classes = cursor.fetchall()
    conn.close()
    return render_template('dashboard.html', classes=classes)

@app.route('/create_class', methods=["POST"])
def create_class():
    class_name = request.form.get("class_name")
    teacher_id = session['user_id']
    if not class_name:
        flash('You have not entered a valid name', 'error')
        return redirect('/dashboard')
    else:
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO classes (name, teacher_id) VALUES (?, ?)", (class_name, teacher_id))
        conn.commit()
        conn.close()
        flash('Class created successfully', 'success')
        return redirect('/dashboard')

@app.route('/add_study', methods=["POST"])
def add_study(class_id):
    print(class_id)
    return redirect('/dashboard')

@app.route('/join_class', methods=["POST"])
def join_class():
    class_id = request.form.get("class_id")
    student_id = session['user_id']
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM classes WHERE class_id = ?", (class_id,))
    class_count = cursor.fetchone()[0]
    if class_count == 0:
        flash("We couldn't find the class you were looking for", 'error')
        return redirect('/dashboard')
    else:
        cursor.execute("INSERT INTO classes_students (class_id, student_id) VALUES (?, ?)", (class_id, student_id))
        conn.commit()
        conn.close()
        flash('Class joined successfully', 'success')
        return redirect('/dashboard')
    