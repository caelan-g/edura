from datetime import datetime
import sqlite3
from flask import Flask, render_template, request, redirect, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
import random
import time

#TO DO LIST
### session database
### student timer feature
### teacher ability to remove students
### dashboard ui revamp for students
### class view ui revamp for teachers
### landing page revamp

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
        join_code INTEGER UNIQUE,
        FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
        )
        ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS classes_students( 
        class_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        total_study_time INTEGER NOT NULL,
        PRIMARY KEY (class_id, student_id),
        FOREIGN KEY (class_id) REFERENCES classes(class_id),
        FOREIGN KEY (student_id) REFERENCES students(student_id)  
        )
        ''') #have to make junction table here so it can have many to many relationship
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS study_sessions( 
        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        start_time DATETIME NOT NULL,
        end_time DATETIME NOT NULL,
        description TEXT,
        FOREIGN KEY (class_id, student_id) REFERENCES classes_students(class_id, student_id)  
        )
        ''')
    conn.commit()
    conn.close()

def find_duplicate(cursor, username): #do i need this function?? - could it be used to find duplicate class codes or something?
    cursor.execute("SELECT COUNT(*) FROM students WHERE username = ?", (username,))
    student_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM teachers WHERE username = ?", (username,))
    teacher_count = cursor.fetchone()[0]
    if student_count > 0 or teacher_count > 0:
        return True
    
def generate_join_code(class_id):
    join_code = ''
    for i in range(0, 6, 1):
        join_code += str(random.randint(0,9))
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT join_code FROM classes")
    existing_join_code = str(cursor.fetchall()) #kinda bad but works
    while join_code in existing_join_code:
        join_code = ''
        for i in range(0, 6, 1):
            join_code += str(random.randint(0,9))
        
    cursor.execute("UPDATE classes SET join_code = ? WHERE class_id = ?", (join_code, class_id))
    conn.commit()
    conn.close()
    return join_code

def add_student(conn, cursor, student_id, class_id):
    cursor.execute("SELECT COUNT(*) FROM classes_students WHERE (class_id, student_id) = (?, ?)", (class_id, student_id))
    class_duplicate = cursor.fetchone()[0]
    if class_duplicate > 0:
        conn.close()
        flash("Already in class", 'error')
        return redirect('/dashboard')
    else:
        cursor.execute("INSERT INTO classes_students (class_id, student_id, total_study_time) VALUES (?, ?, ?)", (class_id, student_id, 0))
        conn.commit()
        conn.close()
        flash('Class joined successfully', 'success')
        return redirect('/dashboard')

def auth_teacher(teacher_id, class_id):
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT teacher_id FROM classes WHERE class_id = ?", (class_id,))
    required_teacher_id = cursor.fetchone()[0]
    conn.close()
    if teacher_id == required_teacher_id:
        return True
    else:
        return False

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY")
init_db()

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
            session['start_study_time'] = None
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

@app.route('/add_study', methods=["GET", "POST"])
def add_study():
    start_study_time = session['start_study_time']
    class_id = request.args.get('class_id')
    user_id = session['user_id']
    if start_study_time:
        end_study_time = datetime.now().replace(tzinfo=None)
        start_study_time = start_study_time.replace(tzinfo=None)
        study_time = int((end_study_time - start_study_time).total_seconds())
        description = 'test session' #request.form.get('description')
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute('''
        SELECT classes_students.total_study_time 
            FROM classes_students 
            WHERE student_id = ?
            AND class_id = ?''', (user_id, class_id))
        total_study_time = int(cursor.fetchone()[0])
        total_study_time += study_time
        cursor.execute("UPDATE classes_students SET total_study_time = ? WHERE (class_id, student_id) = (?, ?)", (total_study_time, class_id, user_id))
        cursor.execute('''
        INSERT INTO study_sessions (class_id, student_id, start_time, end_time, description)
            VALUES (?, ?, ?, ?, ?)''', (class_id, user_id, start_study_time, end_study_time, description))
        conn.commit()
        conn.close()
        flash(f'Nice job studying for {study_time} seconds! Study time updated to {total_study_time} seconds', 'success')
        session['start_study_time'] = None
        return redirect('/dashboard')
    else:
        session['study_time'] = 10
        session['start_study_time'] = datetime.now().replace(tzinfo=None)
        return redirect('/dashboard')
    

@app.route('/join_code', methods=["GET", "POST"])
def join_code():
    join_code = request.form.get("join_code")
    student_id = session['user_id']
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM classes WHERE join_code = ?", (join_code,))
    print(join_code)
    class_count = cursor.fetchone()[0]
    if class_count == 0:
        flash("We couldn't find the class you were looking for", 'error')
        return redirect('/dashboard')
    else:
        cursor.execute("SELECT class_id FROM classes WHERE join_code = ?", (join_code,))
        class_id = cursor.fetchone()[0]
        add_student(conn, cursor, student_id, class_id)
        return redirect('/dashboard')
        
    
@app.route('/view_class/<int:class_id>', methods=['GET', 'POST'])
def view_class(class_id):
    join_code = generate_join_code(class_id)
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM classes WHERE class_id = ?", (class_id,))
    class_entity = cursor.fetchone()
    conn.close()
    if session['user_type'] == 'teacher':
        if class_entity:
            if auth_teacher(session['user_id'], class_id):
                conn = sqlite3.connect('study_app.db')
                cursor = conn.cursor()
                cursor.execute('''
                SELECT students.student_id, students.name, classes_students.total_study_time
                    FROM students
                    JOIN classes_students ON students.student_id = classes_students.student_id
                    JOIN classes ON classes.class_id = classes_students.class_id
                    WHERE classes.class_id = ?
                    ''', (class_id,))
                class_data = cursor.fetchall()
                cursor.execute("SELECT * FROM study_sessions WHERE class_id = ? ORDER BY start_time DESC", (class_id,))
                session_data = cursor.fetchall()
                conn.close()
                
                total = 0
                sum = 0
                for row in class_data:
                    total += int(row[2])
                    sum += 1
                if total > 0:
                    average_study_time = round(total/sum, 1)
                else:
                    average_study_time = 0
                return render_template('view-class.html', class_data=class_data, class_entity=class_entity, average_study_time=average_study_time, join_code=join_code, session_data=session_data)
            else:
                flash('You are not the owner of this class', 'error')
                return redirect('/dashboard')
        else:
            flash('Class does not exist')
            return redirect('/dashboard')
    else:
        flash('Please login to continue')
        return redirect('/')
    
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect('/')
    
@app.route('/settings', methods=['GET'])
def settings():
    return render_template('settings.html')
    
@app.route('/update_class', methods=['POST'])
def update_class():
    edit_class_id = int(request.form.get("class_id"))
    new_class_name = request.form.get("class_name")
    if new_class_name:
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE classes SET name = ? WHERE class_id = ?", (new_class_name, edit_class_id))
        conn.commit()
        conn.close()
    else:
        flash('Please input a name', 'error')
    return redirect('/dashboard')

@app.route('/delete_class/<int:class_id>', methods=['POST'])
def delete_class(class_id):
    if session['user_type'] == 'teacher' and auth_teacher(session['user_id'], class_id):
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM classes WHERE class_id = ?", (class_id,))
        cursor.execute("DELETE FROM classes_students WHERE class_id = ?", (class_id,))
        conn.commit()
        conn.close()
        flash('Class deleted', 'success')
        return redirect('/dashboard') #bug here - doens't show on first reload due to js
    else:
        flash('You are not the owner of this class', 'error')
        return redirect('/dashboard')

@app.route('/reload_join_code', methods=['POST'])
def reload_join_code():
    generate_join_code()
    return render_template('view_class')

@app.route('/invite_student', methods=['GET', 'POST'])
def invite_student():
    student_username = request.form.get('student_username')
    class_id = request.form.get("class_id")
    print(f'id is {class_id}')
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT student_id FROM students WHERE username = ?', (student_username,))
    student_id = cursor.fetchone()
    if student_id:
        student_id = student_id[0]
        add_student(conn, cursor, student_id, class_id)
        return redirect(url_for('view_class', class_id=class_id))
    else:      
        flash('Student not found', 'error')
        conn.close()
        return redirect(url_for('view_class', class_id=class_id))