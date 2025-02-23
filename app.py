from datetime import datetime
import sqlite3
from flask import Flask, render_template, request, redirect, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
import random
import time
import math
from bokeh.plotting import figure
from bokeh.embed import components

#TO DO LIST
### student ability to edit, delete sessions
### log file
### datetime filter (sessions, logs)
### teacher classview/dashboard graphs
### 2fac auth
### input validation/sanitisation
### enhancing session management - '6.1 To-Do List Changes'
### student dashboard completion
### settings completion (can edit etc)
### join code revamp - only on first page reload, clear on logout
### landing page revamp
### footer(s)
### RESPONSIVE!!
### final ui - (icon, logo, class customization)
### internal documentation
### mock data

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
        if session['user_type'] == 'teacher':
            flash('Student added successfully', 'success')
        else:
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
    
def render_bar_graph(name_list, data):
    plot = figure(x_range=name_list, toolbar_location=None, sizing_mode="stretch_both", tools="")
    plot.vbar(x=name_list, top=data, line_width=0, width=0.9, fill_color="rgb(59, 130, 246)")
    plot.background_fill_color = 'white'
    plot.border_fill_color = 'white'
    plot.y_range.start = 0
    plot.outline_line_color = 'white'
    plot.yaxis.visible = False
    plot.xgrid.grid_line_color = None
    plot.ygrid.grid_line_alpha = 0.5
    plot.ygrid.grid_line_dash = [6, 4]
    return components(plot)

def convertToSeconds(timeString):
    #timeString is in the format hour:minutes:seconds with each taking up 2 length (if that makes sense)
    times = timeString.split(':')
    print(times)
    total = int(times[0])*3600 + int(times[1])*60 + int(times[2])
    return total
    
    

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY")
init_db()

@app.template_filter('dateTimeFormat')
def date_time_format_filter(date_time):
    date = (date_time.split()[0]).split('-')
    date_obj = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
    day_of_week = date_obj.strftime("%A")
    day_month_year = f'{day_of_week}, {date[2] if date[2][0] != '0' else date[2][1]}-{date[2] if date[1][0] != '0' else date[1][1]}-{date[0]}'
    return day_month_year

@app.template_filter('duration')
def duration_filter(start_time, end_time):
    start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f")
    hours = (end_time - start_time).total_seconds() / 3600
    minutes = round((hours - round(hours, 0)) * 60, 0)
    if hours > 1:
        return f"{round(hours, 0)}h {str(minutes).replace(".0", "")}m"
    else:
        return f"{str(minutes).replace(".0", "")}m"
    
@app.template_filter('timeFormat')
def time_filter_filter(seconds):
    hours = int(seconds) / 3600
    minutes = math.floor((hours - math.floor(hours)) * 60)
    if hours >= 1:
        return f"{math.floor(hours)}h {str(minutes).replace(".0", "")}m"
    else:
        return f"{str(minutes).replace(".0", "")}m"
    
@app.template_filter('timeEditFormat')
def time_edit_filter(time):
    hours = int(time) / 3600
    minutes = (hours - math.floor(hours)) * 60
    seconds = round((minutes - math.floor(minutes)) * 60, 0)
    hours = str(math.floor(hours))
    minutes = str(math.floor(minutes)).replace(".0", "")
    seconds = str(seconds).replace(".0", "")

    return f"{'0' + hours if len(hours) == 1 else hours}:{'0' + minutes if len(minutes) == 1 else minutes}:{'0' + seconds if len(seconds) == 1 else seconds}"
    
@app.template_filter('getStudentName')
def get_student_name(student_id):
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT students.name FROM students WHERE student_id = ?", (student_id,))
    student_name = cursor.fetchone()[0]
    conn.close()
    return student_name

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
    else:
        session['user_type'] = 'student'
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
            session['study_class_id'] = None
            session['timer_sec'] = 0
            session['timer_min'] = 0
            session['timer_hr'] = 0
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
    session['page'] = 'dashboard'
    script = None
    div = None
    if 'user_id' not in session:
        session.clear()
        return redirect('/login')
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    if session['user_type'] == 'student':
        cursor.execute('''
        SELECT classes_students.total_study_time
            FROM classes_students 
            WHERE student_id = ? ORDER BY class_id DESC
            ''', (session['user_id'],))
        
        total_study_time = cursor.fetchall()
        time_data = []
        for i in total_study_time:
            time_data.append(i[0])
        
        cursor.execute('''
        SELECT classes.class_id, classes.name
            FROM classes 
            JOIN classes_students ON classes.class_id = classes_students.class_id
            JOIN students ON students.student_id = classes_students.student_id
            WHERE students.student_id = ? ORDER BY classes.class_id DESC
            ''', (session['user_id'],))
        classes = cursor.fetchall()
        class_name = []
        
        if classes:
            k = int(round(1/len(classes) * 100, 0))
            #print(k)
            for i in classes:
                if len(i[1]) > k:
                    new = i[1][:k] + '...'
                    class_name.append(new)
                else:
                    class_name.append(i[1])
            script, div = render_bar_graph(class_name, time_data)
        else:
            script, div = None, None
            
    else:
        cursor.execute("SELECT * FROM classes WHERE teacher_id = ?", (session['user_id'],))
        classes = cursor.fetchall()
    conn.close()
    return render_template('dashboard.html', classes=classes, script=script, div=div)

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
    user_id = session['user_id']
    if start_study_time:
        class_id = session['study_class_id']
        description = request.form.get('description')
        session['study_class_id'] = None
        session['timer_sec'] = 0
        session['timer_min'] = 0
        session['timer_hr'] = 0
        end_study_time = datetime.now().replace(tzinfo=None)
        start_study_time = start_study_time.replace(tzinfo=None)
        study_time = int((end_study_time - start_study_time).total_seconds())
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
        session['start_study_time'] = datetime.now().replace(tzinfo=None)
        session['study_class_id'] = request.args.get('class_id')
        return redirect('/dashboard')
    

@app.route('/join_code', methods=["GET", "POST"])
def join_code():
    join_code = request.form.get("join_code")
    student_id = session['user_id']
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM classes WHERE join_code = ?", (join_code,))
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
    session['page'] = 'view_class'
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
        flash('Please login to continue', 'error')
        return redirect('/')
    
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect('/')
    
@app.route('/settings', methods=['GET'])
def settings():
    if session['user_id']:
        session['page'] = 'settings'
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        if session['user_type'] == 'student':
            cursor.execute("SELECT * FROM students WHERE student_id = ?", (session['user_id'],))
        else:
            cursor.execute("SELECT * FROM teachers WHERE teacher_id = ?", (session['user_id'],))
        user_data = cursor.fetchall()[0]
        conn.close()
        print(user_data)
        return render_template('settings.html', user_data=user_data)
    else:
        flash('Please login to continue', 'error')
        return redirect('/')
    
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

@app.route('/update_session_timer', methods=['POST'])
def update_session_timer():
    data = request.get_json()
    timer_sec = data.get('timer_sec')
    timer_min = data.get('timer_min')
    timer_hr = data.get('timer_hr')

    session['timer_sec'] = timer_sec
    session['timer_min'] = timer_min
    session['timer_hr'] = timer_hr
    return 'f'

@app.route('/reload_join_code', methods=['POST'])
def reload_join_code():
    generate_join_code()
    return render_template('view_class')

@app.route('/invite_student', methods=['GET', 'POST'])
def invite_student():
    student_username = request.form.get('student_username')
    class_id = request.form.get("class_id")
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
    
@app.route('/sessions')
def sessions():
    if session['user_id'] and session['user_type'] == 'student': 
        session['page'] = 'sessions'
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM study_sessions WHERE student_id = ? ORDER BY end_time DESC', (session['user_id'],))
        session_data = cursor.fetchall()
        conn.close()
        return render_template('sessions.html', session_data=session_data)
    else:
        flash("Please login to continue", "error")
        return redirect('/login')
    
@app.route('/remove_student', methods=['POST'])
def remove_student():
    if session['user_id'] and session['user_type'] == 'teacher': 
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM classes_students WHERE student_id = ? AND class_id = ?', (student_id, class_id))
        cursor.execute('DELETE FROM study_sessions WHERE student_id = ? AND class_id = ?', (student_id, class_id))
        conn.commit()
        conn.close()
        flash('Student removed', 'success')
        return redirect(f'/view_class/{class_id}')
    else:  
        flash('Please login to continue', 'error')
        return redirect('/login')
    

@app.route('/add_study_time', methods=['POST'])
def add_study_time():
    if session['user_id'] and session['user_type'] == 'teacher': 
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        conn.commit()
        conn.close()
        flash('Study time added', 'success')
        #return redirect(f'/view_class/{class_id}')
    else:  
        flash('Please login to continue', 'error')
        return redirect('/login')

@app.route('/subtract_study_time', methods=['POST'])
def subtract_study_time():
    if session['user_id'] and session['user_type'] == 'teacher': 
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        conn.commit()
        conn.close()
        flash('Study time subtracted', 'success')
        return redirect(f'/view_class/{class_id}')
    else:  
        flash('Please login to continue', 'error')
        return redirect('/login')
    
@app.route('/edit_study_time', methods=['POST'])
def edit_study_time():
    if session['user_id'] and session['user_type'] == 'teacher':
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        new_study_time = request.form.get('new_study_time')
        study_time_seconds = convertToSeconds(new_study_time)
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE classes_students SET total_study_time = ? WHERE student_id = ? AND class_id = ?', (study_time_seconds, student_id, class_id))
        print(study_time_seconds)
        conn.commit()
        conn.close()
        flash(f'Study time successfully updated', 'success')
        return redirect(f'/view_class/{class_id}')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')
        
@app.route('/delete_session', methods=['POST'])
def delete_session():
    if session['user_id'] and session['user_type'] == 'teacher':
        session_id = request.form.get('session_id')
        class_id = request.form.get('class_id')
        student_id = request.form.get('student_id')
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM study_sessions WHERE session_id = ?', (session_id,))
        study_session = cursor.fetchall()[0]
        end_time = datetime.strptime(study_session[4], "%Y-%m-%d %H:%M:%S.%f")
        start_time = datetime.strptime(study_session[3], "%Y-%m-%d %H:%M:%S")
        session_duration = int((end_time - start_time).total_seconds())
        cursor.execute('SELECT total_study_time FROM classes_students WHERE student_id = ? AND class_id = ?', (student_id, class_id))
        total_study_time = cursor.fetchone()[0]
        print(f'old total: {total_study_time}')
        new_total = total_study_time - session_duration
        print(f'new total: {new_total}')
        cursor.execute('UPDATE classes_students SET total_study_time = ? WHERE student_id = ? AND class_id = ?', (new_total, student_id, class_id))
        cursor.execute('DELETE FROM study_sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
        flash(f'Session deleted', 'success')
        return redirect(f'/view_class/{class_id}')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')