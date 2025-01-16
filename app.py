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
        name TEXT NOT NULL,
        study_time INTEGER NOT NULL,
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
        PRIMARY KEY (class_id, student_id),
        FOREIGN KEY (class_id) REFERENCES Classes(class_id),
        FOREIGN KEY (student_id) REFERENCES Students(student_id)  
        )
        ''') #have to make junction table here so it can have many to many relationship
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teachers(
        teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL
        )
        ''')
    conn.commit()
    conn.close()

#init_db()

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
        conn = sqlite3.connect('to_do_list.db')
        cursor = conn.cursor()
        if session['user_type'] == 'teacher':
            cursor.execute("SELECT COUNT(*) FROM teachers WHERE username = ?", (username,))
            if cursor.fetchone()[0] > 0:
                flash('Username already exists', 'error')
            else:
                cursor.execute("INSERT INTO teachers (username, password, name) VALUES (?, ?, ?)", (username, hashed_password, name))
                conn.commit()
                flash('Registration successful. Please login', 'success')
                conn.close()
                return redirect('/login')
        else:
            cursor.execute("SELECT COUNT(*) FROM students WHERE username = ?", (username,))
            if cursor.fetchone()[0] > 0:
                flash('Username already exists', 'error')
            else:
                cursor.execute("INSERT INTO students (username, password, name) VALUES (?, ?, ?)", (username, hashed_password, name))
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
        return redirect('/dashboard')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')