from datetime import datetime, timedelta
import sqlite3
from flask import Flask, render_template, request, redirect, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import os
import random
import math
import logging
import uuid
import re
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import pyotp
import qrcode   
import bleach

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=120)
COLOURS = ["#AEC6CF",
"#B2F2BB",
"#FFFACD",
"#D7BDE2",
"#F7CAC9",
"#B2DFDB",
"#FFDAB9"]
TYPES = ['teacher', 'student']
ALLOWED_TAGS = ['b', 'i', 'u', 'strong', 'em', 'a']
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}

app.config.update(
    SESSION_COOKIE_SECURE=True,  # Enforces HTTPS for session cookies
    SESSION_COOKIE_HTTPONLY=True,  # Prevents client-side JS from accessing session cookies
    SESSION_COOKIE_SAMESITE='Strict'  # Prevents cross-site request forgery (CSRF)
)

def init_db():
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS students(
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        mfa_secret TEXT
        )
        ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teachers(
        teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,        
        name TEXT NOT NULL,
        mfa_secret TEXT
        )
        ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS classes(
        class_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        teacher_id INTEGER NOT NULL,
        join_code INTEGER UNIQUE,
        colour TEXT,
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
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teacher_tasks( 
        teacher_task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        due_date DATETIME,
        duration INTEGER,
        description TEXT NOT NULL,
        FOREIGN KEY (class_id) REFERENCES classes(class_id)
        )
        ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS student_tasks( 
        student_task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_task_id INTEGER,
        class_id INTEGER,
        student_id INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        due_date DATETIME,
        duration INTEGER,
        description TEXT,
        completed BOOLEAN DEFAULT 0,
        completed_at DATETIME,
        FOREIGN KEY (class_id, student_id) REFERENCES classes_students(class_id, student_id),
        FOREIGN KEY (teacher_task_id) REFERENCES teacher_tasks(teacher_task_id)
        )
        ''')
    conn.commit()
    conn.close()

def find_duplicate(cursor, username): 
    cursor.execute("SELECT COUNT(*) FROM students WHERE username = ?", (username,))
    student_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM teachers WHERE username = ?", (username,))
    teacher_count = cursor.fetchone()[0]
    if student_count > 0 or teacher_count > 0:
        return True
    
def is_valid(text):
    text = str(text)
    return isinstance(text, str) and 0 < len(text) <= 255 and re.match(r"^[a-zA-Z0-9\s.,'-]+$", text)

def san_input(user_input):
    return bleach.clean(user_input, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)

def verify(auth='student'):
    if 'user_id' in session and 'csrf_token' in session:
        if auth == 'teacher':
            if session['user_type'] == 'teacher':
                return True
        if session['user_id']:
            return True
    return False
    
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
            app.logger.info(f'Student:{student_id} added to class:{class_id}')
            flash('Student added successfully', 'success')
        else:
            flash('Class joined successfully', 'success')
        return redirect('/dashboard')

def auth_teacher(teacher_id, class_id):
    if get_class(class_id):
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute("SELECT teacher_id FROM classes WHERE class_id = ?", (class_id,))
        required_teacher_id = cursor.fetchone()[0]
        conn.close()
        if teacher_id == required_teacher_id:
            return True
        else:
            return False
    else:
        return False
    
def get_tasks(cursor, user_data, class_id=None):
    if session['user_type'] == 'teacher': #meaning its a teacher
        if not class_id:
            cursor.execute('''
                SELECT 
                    t.teacher_task_id,
                    t.class_id,
                    c.name AS class_name,
                    c.colour,
                    t.created_at,
                    t.due_date,
                    t.duration,
                    t.description,
                    GROUP_CONCAT(
                        CASE WHEN st.completed = 1 
                        THEN st.student_id 
                        END
                    ) AS completed_student_ids,
                    GROUP_CONCAT(
                        CASE WHEN st.completed = 0 OR st.completed IS NULL 
                        THEN st.student_id 
                        END
                    ) AS incomplete_student_ids,
                    COUNT(DISTINCT st.student_id) AS total_students,
                    COUNT(DISTINCT CASE WHEN st.completed = 1 THEN st.student_id END) AS completed_count,
                    COUNT(DISTINCT CASE WHEN st.completed = 0 OR st.completed IS NULL THEN st.student_id END) AS incomplete_count
                FROM teacher_tasks t
                JOIN classes c ON t.class_id = c.class_id
                LEFT JOIN student_tasks st ON t.teacher_task_id = st.teacher_task_id
                WHERE c.teacher_id = ?
                GROUP BY t.teacher_task_id, t.class_id, c.name, c.colour, t.created_at, t.due_date, t.duration, t.description
                ORDER BY t.created_at DESC
            ''', (user_data[0],))    
        else:
            cursor.execute('''
                SELECT 
                    t.teacher_task_id,
                    t.class_id,
                    c.name AS class_name,
                    c.colour,
                    t.created_at,
                    t.due_date,
                    t.duration,
                    t.description,
                    GROUP_CONCAT(
                        CASE WHEN st.completed = 1 
                        THEN st.student_id 
                        END
                    ) AS completed_student_ids,
                    GROUP_CONCAT(
                        CASE WHEN st.completed = 0 OR st.completed IS NULL 
                        THEN st.student_id 
                        END
                    ) AS incomplete_student_ids,
                    COUNT(DISTINCT st.student_id) AS total_students,
                    COUNT(DISTINCT CASE WHEN st.completed = 1 THEN st.student_id END) AS completed_count,
                    COUNT(DISTINCT CASE WHEN st.completed = 0 OR st.completed IS NULL THEN st.student_id END) AS incomplete_count
                FROM teacher_tasks t
                JOIN classes c ON t.class_id = c.class_id
                LEFT JOIN student_tasks st ON t.teacher_task_id = st.teacher_task_id
                WHERE c.teacher_id = ?
                AND t.class_id = ?
                GROUP BY t.teacher_task_id, t.class_id, c.name, c.colour, t.created_at, t.due_date, t.duration, t.description
                ORDER BY t.created_at DESC
            ''', (user_data[0], class_id))
        task_data = cursor.fetchall()
        return task_data
    else: #its a student
        cursor.execute('''
            SELECT 
            st.student_task_id,
            COALESCE(tt.class_id, st.class_id) AS class_id,
            c.name AS class_name,
            c.colour,
            st.created_at,
            COALESCE(tt.due_date, st.due_date) AS due_date,
            st.duration,
            COALESCE(tt.description, st.description) AS description,
            st.completed,
            st.completed_at,
            st.teacher_task_id
            FROM student_tasks st
            LEFT JOIN teacher_tasks tt ON st.teacher_task_id = tt.teacher_task_id
            LEFT JOIN classes c ON COALESCE(tt.class_id, st.class_id) = c.class_id
            WHERE st.student_id = ?
            ORDER BY st.completed, st.created_at DESC
        ''', (user_data[0],))
        task_data = cursor.fetchall()
        #print(task_data)
    return task_data

    
def get_class(class_id):
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM classes WHERE class_id = ?", (class_id,))
    class_entity = cursor.fetchone()
    conn.close()
    return class_entity
    
def clear_mfa(id):
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE teachers SET mfa_secret = ? WHERE teacher_id = ?", (None, id))
    conn.commit()
    conn.close()  

def convertToSeconds(timeString):
    #timeString is in the format hour:minutes:seconds with each taking up 2 length (if that makes sense)
    times = timeString.split(':')
    #print(times)
    total = int(times[0])*3600 + int(times[1])*60 + int(times[2])
    return total
    
def updateTotalStudyTime(cursor, student_id, class_id, time):
    cursor.execute('SELECT total_study_time FROM classes_students WHERE student_id = ? AND class_id = ?', (student_id, class_id))
    total_study_time = cursor.fetchone()[0]
    #print(time)
    new_total = total_study_time + time
    if new_total < 0:
        new_total = 0
    cursor.execute('UPDATE classes_students SET total_study_time = ? WHERE student_id = ? AND class_id = ?', (new_total, student_id, class_id))
    
def is_valid_time(time): # will need work
    #print(time)
    first_index = -1
    for i in range(len(time)):
        if time[i] == ':':
            if first_index == -1:
                first_index = i
            elif i > first_index + 1:
                for x in time.split(':'):
                    if not x.isdigit() or len(x) > 2:
                        return False  # Found the same character separated by other characters
                return True
    return False

def colourDictionary():
    return {
        "#AEC6CF": "bg-[#AEC6CF]",
        "#B2F2BB": "bg-[#B2F2BB]",
        "#FFFACD": "bg-[#FFFACD]",
        "#D7BDE2": "bg-[#D7BDE2]",
        "#F7CAC9": "bg-[#F7CAC9]",
        "#B2DFDB": "bg-[#B2DFDB]",
        "#FFDAB9": "bg-[#FFDAB9]"
    }
    
def random_month_sessions(cursor, user_id):
    """Generate random study sessions for the past 30 days"""
    # Get all classes the student is enrolled in
    cursor.execute('''
        SELECT class_id FROM classes_students 
        WHERE student_id = ?
    ''', (user_id,))
    
    class_ids = [row[0] for row in cursor.fetchall()]
    
    if not class_ids:
        print(f"No classes found for user {user_id}")
        return
    
    # Sample descriptions for random sessions
    descriptions = [
        "Study session", "Homework", "Reading", "Practice problems", 
        "Review notes", "Project work", "Assignment", "Exam prep",
        "Research", "Group study", "Lab work", "Tutorial"
    ]
    
    # Generate sessions for each of the past 30 days
    for day_offset in range(30):
        # Calculate the date for this iteration
        session_date = datetime.now().date() - timedelta(days=day_offset)
        
        # Randomly decide if there should be a session this day (80% chance)
        if random.random() < 0.8:
            # Choose a random class
            class_id = random.choice(class_ids)
            
            # Generate random duration between 10-100 minutes
            duration_minutes = random.randint(10, 100)
            duration_seconds = duration_minutes * 60
            
            # Generate random start time (between 8 AM and 8 PM)
            start_hour = random.randint(8, 19)
            start_minute = random.randint(0, 59)
            start_second = random.randint(0, 59)
            
            # Create start_time and end_time
            start_time = datetime.combine(session_date, datetime.min.time().replace(
                hour=start_hour, minute=start_minute, second=start_second
            ))
            end_time = start_time + timedelta(seconds=duration_seconds)
            
            # Choose random description
            description = random.choice(descriptions)
            
            # Insert the session
            cursor.execute('''
                INSERT INTO study_sessions (class_id, student_id, start_time, end_time, description)
                VALUES (?, ?, ?, ?, ?)
            ''', (class_id, user_id, start_time, end_time, description))
            
            # Update the total study time for this class
            cursor.execute('''
                UPDATE classes_students 
                SET total_study_time = total_study_time + ?
                WHERE student_id = ? AND class_id = ?
            ''', (duration_seconds, user_id, class_id))
    
    print(f"Generated random sessions for user {user_id} over the past 30 days")
    
def check_password(password):
    return bool(re.search(r'(?=.*[A-Z])(?=.*[a-z])(?=.*\d)', password) and len(password) >= 8)

def get_daily_totals(cursor, user_id, days):
    cutoff_date = (datetime.now().date() - timedelta(days=days)).strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT DATE(start_time) as session_date,
               SUM(
                   CAST(
                       (strftime('%s', end_time) - strftime('%s', start_time)) 
                       AS INTEGER
                   )
               ) as total_seconds
        FROM study_sessions
        WHERE student_id = ?
        AND DATE(start_time) >= ?
        GROUP BY session_date
        ORDER BY session_date DESC
    """, (user_id, cutoff_date))

    results = cursor.fetchall()

    # Fill in days with no study time as 0
    daily_totals = {}
    for date_str, total_seconds in results:
        daily_totals[date_str] = total_seconds or 0

    output = []
    for day_offset in range(days + 1):  # today + back 'days'
        target_date = (datetime.now().date() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        output.append((target_date, daily_totals.get(target_date, 0)))

    print(output)
    return output


log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)
logging.basicConfig(filename='record.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per minute"])
init_db()

@app.before_request
def make_session_permanent():
    session.permanent = True

@app.template_filter('dateTimeFormat')
def date_time_format_filter(date_time):
    if date_time is None or date_time == '':
        return "No date set"
    try:
        # Try parsing with microseconds first
        try:
            date_obj = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            # If that fails, try without microseconds
            try:
                date_obj = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                date_obj = datetime.strptime(date_time, "%Y-%m-%d")
        
        day_of_week = date_obj.strftime("%A")
        day_month_year = f'{day_of_week}, {int(date_obj.day)}/{int(date_obj.month)}/{date_obj.year}'
        return day_month_year
    except (ValueError, TypeError):
        return "Invalid date"

@app.template_filter('duration')
def duration_filter(start_time, end_time, type='readable'):
    start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    try:
        end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f")
    except:
        end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    total_seconds = (end_time - start_time).total_seconds()
    hours =  total_seconds / 3600
    minutes = round((hours - math.floor(hours)) * 60, 0)
    if type == 'seconds':
        return total_seconds
    elif type == 'readable':
        if hours > 1:
            return f'{math.floor(hours)}h {str(minutes).replace(".0", "")}m'
        else:
            return f'{str(minutes).replace(".0", "")}m'
    
@app.template_filter('sessionStats')
def session_stats(session_data, student_id, stat):
    if session_data:
        total = 0
        for session in session_data:
            if session[2] == student_id:
                total = total + 1
        if stat == 'total':
            return total
        elif stat == 'average':
            total_time = 0
            for session in session_data:
                if session[2] == student_id:
                    total_time = total_time + int(duration_filter(session[3], session[4], 'seconds'))
            if session == 0: 
                return time_filter_filter(total_time/total)
    return 0
    
@app.template_filter('timeFormat')
def time_filter_filter(seconds):
    hours = int(seconds) / 3600
    minutes = math.floor((hours - math.floor(hours)) * 60)
    if hours >= 1:
        return f'{math.floor(hours)}h {str(minutes).replace(".0", "")}m'
    else:
        return f'{str(minutes).replace(".0", "")}m'
    
@app.template_filter('timeEditFormat')
def time_edit_filter(time):
    hours = int(time) / 3600
    minutes = (hours - math.floor(hours)) * 60
    seconds = round((minutes - math.floor(minutes)) * 60, 0)
    hours = str(math.floor(hours))
    minutes = str(math.floor(minutes)).replace(".0", "")
    seconds = str(seconds).replace(".0", "")

    return f'{"0" + hours if len(hours) == 1 else hours}:{"0" + minutes if len(minutes) == 1 else minutes}:{"0" + seconds if len(seconds) == 1 else seconds}'
    
@app.template_filter('getStudentName')
def get_student_name(student_id):
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT students.name FROM students WHERE student_id = ?", (student_id,))
    student_name = cursor.fetchone()[0]
    conn.close()
    return student_name

@app.template_filter('getAllStudentIds')
def get_all_student_ids(completed_ids, incomplete_ids):
    """Combine completed and incomplete student IDs into a single list"""
    all_ids = []
    
    # Add completed student IDs
    if completed_ids and str(completed_ids).strip():
        completed_list = str(completed_ids).split(',')
        all_ids.extend([id.strip() for id in completed_list if id.strip()])
    
    # Add incomplete student IDs  
    if incomplete_ids and str(incomplete_ids).strip():
        incomplete_list = str(incomplete_ids).split(',')
        all_ids.extend([id.strip() for id in incomplete_list if id.strip()])
    
    return all_ids

@app.template_filter('getStudentStatus')
def get_student_status(student_id, completed_ids, incomplete_ids):
    """Check if a student has completed the task or not"""
    # Convert to strings and split
    completed_list = []
    if completed_ids and str(completed_ids).strip():
        completed_list = [id.strip() for id in str(completed_ids).split(',') if id.strip()]
    
    incomplete_list = []
    if incomplete_ids and str(incomplete_ids).strip():
        incomplete_list = [id.strip() for id in str(incomplete_ids).split(',') if id.strip()]
    
    student_id_str = str(student_id).strip()
    
    if student_id_str in completed_list:
        return 'completed'
    elif student_id_str in incomplete_list:
        return 'incomplete'
    else:
        return 'unknown'

@app.template_filter('colourDictionary')
def colour_dictionary_filter(colour):
    return colourDictionary().get(colour, "bg-steelblue")

@app.template_filter('dueDateStatus')
def due_date_status_filter(due_date):
    if due_date is None or due_date == '':
        return None
    
    try:
        # Parse the due date
        due_date_obj = datetime.strptime(due_date, "%Y-%m-%d")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        due_date_obj = due_date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate days difference
        days_diff = (due_date_obj - today).days
        
        if days_diff < 0:
            return {
                'status': 'overdue',
                'days': abs(days_diff),
                'text': f'{abs(days_diff)} day{"s" if abs(days_diff) != 1 else ""} overdue'
            }
        elif days_diff <= 3:
            if days_diff == 0:
                return {
                    'status': 'due_today',
                    'days': 0,
                    'text': 'Due today'
                }
            else:
                return {
                    'status': 'due_soon',
                    'days': days_diff,
                    'text': f'Due in {days_diff} day{"s" if days_diff != 1 else ""}'
                }
        else:
            return {
                'status': 'due_later',
                'days': days_diff,
                'text': 'Due'
            }
    except (ValueError, TypeError):
        return None

@app.route('/')
def index():
    return render_template("index.html")


@app.route('/generate_test_data')
def generate_test_data():
    """One-time route to generate test data for the current user"""
    if verify():
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        
        # Check if user already has sessions to avoid duplicates
        cursor.execute("SELECT COUNT(*) FROM study_sessions WHERE student_id = ?", (session['user_id'],))
        existing_sessions = cursor.fetchone()[0]
        
        if existing_sessions > 0:
            flash(f'User already has {existing_sessions} study sessions. Test data not generated.', 'info')
        else:
            random_month_sessions(cursor, session['user_id'])
            conn.commit()
            flash('Test data generated successfully!', 'success')
        
        conn.close()
        return redirect('/dashboard')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        second_password = request.form.get("second_password")
        type = request.form.get("type")
        name = request.form.get("name")
        hashed_password = generate_password_hash(password)
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        if is_valid(username) and is_valid(password) and is_valid(name) and ' ' not in username and ' ' not in password:
            if type in TYPES:
                if find_duplicate(cursor, username):
                    flash('Username already exists', 'error')
                elif not check_password(str(password)):
                    flash('Password must contain 8 characters, an uppercase and lowercase letter and a number.', 'error')
                elif password != second_password:
                    flash('Passwords do not match', 'error')
                else:
                    if type == 'teacher':
                        cursor.execute("INSERT INTO teachers (username, password, name) VALUES (?, ?, ?)", (username, hashed_password, name))
                        conn.commit()
                        conn.close()
                        flash("Welcome! Your account has been successfully created.", 'success')
                        
                        return redirect('/login')
                    else:
                        cursor.execute("INSERT INTO students (username, password, name) VALUES (?, ?, ?)", (username, hashed_password, name))
                        conn.commit()
                        conn.close()
                        flash("Welcome! Your account has been successfully created.", 'success')
                        return redirect('/login')
            else:
                flash('Invalid type', 'error')
                return redirect('/register')
        else:
            flash('Please enter a valid username or password', 'error')
            return redirect('/register')
    user_type = request.args.get("user_type")
    if user_type == "teacher":
        session['user_type'] = 'teacher'
    else:
        session['user_type'] = 'student'
    return render_template('register.html', types=TYPES)

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute")
def login():
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        if is_valid(username) and is_valid(password):
            conn = sqlite3.connect('study_app.db')
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students WHERE username = ?", (username,))
            student_record = cursor.fetchone()
            cursor.execute("SELECT * FROM teachers WHERE username = ?", (username,))
            teacher_record = cursor.fetchone()
            conn.close()
            if student_record and check_password_hash(student_record[2], password): #user is array from database - password is in 3rd slot (begins from 0)
                session['user_type'] = 'student'
                session['pending_user'] = student_record[0]
                if not student_record[4]:
                    flash('Login successful', 'success')
                    app.logger.info(f'Student:{student_record[0]} logged in')
                    return redirect('/skip_mfa')
                else:
                    return redirect('/verify_mfa')
            elif teacher_record and check_password_hash(teacher_record[2], password):
                session['pending_user'] = teacher_record[0]
                session['user_type'] = 'teacher'
                if not teacher_record[4]:
                    flash('Login successful', 'success')
                    app.logger.info(f'Teacher:{teacher_record[0]} logged in')
                    return redirect('/skip_mfa')
                else:
                    return redirect('/verify_mfa')
            flash("Your username or password don't match our records", 'error')
        else:
            flash('Please enter a valid username or password', 'error')
    return render_template('login.html')

@app.route('/setup_mfa')
def setup_mfa():
    user_id = session.get('user_id')
    conn = sqlite3.connect('study_app.db')
    cursor = conn.cursor()
    
    if session.get('user_type') == 'teacher':
        cursor.execute("SELECT mfa_secret FROM teachers WHERE teacher_id = ?", (user_id,))
    else:
        cursor.execute("SELECT mfa_secret FROM students WHERE student_id = ?", (user_id,))

    secret = cursor.fetchone()
    if secret:
        secret = secret[0]  # Extract actual value

    if not secret:
        secret = pyotp.random_base32()
        if session['user_type'] == 'teacher':
            cursor.execute("UPDATE teachers SET mfa_secret = ? WHERE teacher_id = ?", (secret, user_id))
        else:
            cursor.execute("UPDATE students SET mfa_secret = ? WHERE student_id = ?", (secret, user_id))
        conn.commit()

    conn.close()

    totp = pyotp.TOTP(secret)
    
    uri = totp.provisioning_uri(name=f'user{user_id}@edura.com', issuer_name="Edura")
    qr = qrcode.make(uri)
    qr_path = "static/images/qrcode.png"
    qr.save(qr_path)

    return render_template("setup-mfa.html", qr_path=qr_path)

@app.route('/skip_mfa')
def skip_mfa():
    if session['pending_user']:
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        user_id = session['pending_user']
        session['user_id'] = user_id
        if session['user_type'] == 'student':
            cursor.execute("SELECT * FROM students WHERE student_id = ?", (user_id,))
            student_record = cursor.fetchone()
            session['username'] = student_record[1]
            session['start_study_time'] = None
            session['study_class_id'] = None
            session['timer_sec'] = 0
            session['timer_min'] = 0
            session['timer_hr'] = 0
        else:
            cursor.execute("SELECT * FROM teachers WHERE teacher_id = ?", (user_id,))
            teacher_record = cursor.fetchone()
            session['username'] = teacher_record[1]
        session['csrf_token'] = str(uuid.uuid4())  # Add a CSRF token
        del session['pending_user']
        return redirect('/dashboard')
    else:
        flash('Please login to continue')
        session.clear()
        return redirect('/login')

@app.route('/verify_mfa', methods=['GET', 'POST'])
def verify_mfa():
    if 'pending_user' not in session:
        return redirect('/login')
    user_id = session['pending_user']
    if request.method == 'POST':
        # Retrieves the code from the text box
        otp_code = request.form['otp']
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        if session['user_type'] == 'teacher':
            cursor.execute("SELECT mfa_secret FROM teachers WHERE teacher_id = ?", (user_id,))
        else:
            cursor.execute("SELECT mfa_secret FROM students WHERE student_id = ?", (user_id,))
        secret = cursor.fetchone()[0]
        totp = pyotp.TOTP(secret)
        # Compares the input code to the database 
        if totp.verify(otp_code):
            if session['user_type'] == 'student':
                cursor.execute("SELECT * FROM students WHERE student_id = ?", (user_id,))
                student_record = cursor.fetchone()
                session['user_id'] = user_id
                session['username'] = student_record[1]
                session['start_study_time'] = None
                session['study_class_id'] = None
                session['timer_sec'] = 0
                session['timer_min'] = 0
                session['timer_hr'] = 0
            else:
                cursor.execute("SELECT * FROM teachers WHERE teacher_id = ?", (user_id,))
                teacher_record = cursor.fetchone()
                session['username'] = teacher_record[1]
            
            session['csrf_token'] = str(uuid.uuid4())  # Add a CSRF token
            del session['pending_user']
            conn.close()
            flash('Login successful', 'success')
            return redirect('/dashboard')
        flash("Invalid 2FA code", "error")
    return render_template("verify-mfa.html")

@app.route('/dashboard', methods=["GET"])
def dashboard():
    if verify():
        session['page'] = 'dashboard'
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        
        if session['user_type'] == 'student':
            cursor.execute("SELECT * FROM students WHERE student_id = ?", (session['user_id'],))
            student_data = cursor.fetchall()[0]
            task_data = get_tasks(cursor, student_data)
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
            SELECT classes.class_id, classes.name, classes.colour, teachers.name
                FROM classes 
                JOIN classes_students ON classes.class_id = classes_students.class_id
                JOIN students ON students.student_id = classes_students.student_id
                JOIN teachers ON teachers.teacher_id = classes.teacher_id
                WHERE students.student_id = ? ORDER BY classes.class_id DESC
                ''', (session['user_id'],))
            classes = cursor.fetchall()
            
            cursor.execute("SELECT s.session_id, s.start_time, s.end_time, s.description, c.name, c.colour FROM study_sessions s JOIN classes c ON s.class_id = c.class_id WHERE s.student_id = ? ORDER BY s.end_time DESC LIMIT 5", (session['user_id'],))
            sessions = cursor.fetchall()

            daily_totals = get_daily_totals(cursor, session['user_id'], 30)
            graph_days = [day[0] for day in daily_totals]
            graph_totals = [day[1] for day in daily_totals]
            
            cursor.execute("SELECT * FROM students WHERE student_id = ?", (session['user_id'],))
            student_data = cursor.fetchall()[0]
            
            # Prepare donut chart data for Chart.js
            class_name = []
            colour_data = []
            
            if classes and time_data:
                for i, class_info in enumerate(classes):
                    if i < len(time_data) and time_data[i] > 0:  # Only include classes with study time
                        class_name.append(class_info[1])  # class name
                        colour_data.append(class_info[2])  # class colour
                
                # Filter time_data to match the filtered classes
                filtered_time_data = [time_data[i] for i, class_info in enumerate(classes) if i < len(time_data) and time_data[i] > 0]
                time_data = filtered_time_data
            
            return render_template('dashboard.html', 
                                 task_data=task_data, 
                                 user_data=student_data, 
                                 colours=COLOURS, 
                                 classes=classes, 
                                 sessions=sessions, 
                                 graph_days=graph_days, 
                                 graph_totals=graph_totals,
                                 donut_labels=class_name,
                                 donut_data=time_data,
                                 donut_colors=colour_data)  
        else:
            cursor.execute("""
                SELECT c.*, COUNT(cs.student_id) as student_count 
                FROM classes c 
                LEFT JOIN classes_students cs ON c.class_id = cs.class_id 
                WHERE c.teacher_id = ? 
                GROUP BY c.class_id
            """, (session['user_id'],))
            classes = cursor.fetchall()
            cursor.execute("SELECT * FROM teachers WHERE teacher_id = ?", (session['user_id'],))
            teacher_data = cursor.fetchall()[0]
            conn.close()
            return render_template('dashboard.html', user_data=teacher_data, colours=COLOURS, classes=classes)

    else:
        flash('Please login to continue')
        return redirect('/login')

@app.route('/add_study', methods=["GET", "POST"])
def add_study():
    if verify():
        start_study_time = session['start_study_time']
        user_id = session['user_id']
        if start_study_time:
            class_id = session['study_class_id']
            description = request.form.get('description')
            if not is_valid(description):
                flash('Please enter a valid description', 'error')
                return redirect('/dashboard')
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
            flash(f'{time_filter_filter(study_time)} session logged.', 'success')
            app.logger.info(f'Student:{user_id} logged study time')
            session['start_study_time'] = None
            return redirect('/dashboard')
        else:
            session['start_study_time'] = datetime.now().replace(tzinfo=None)
            session['study_class_id'] = request.args.get('class_id')
            return redirect('/dashboard')
    else:
        flash('Please login to continue')
        return redirect('/login')
  
@app.route('/sessions')
def sessions():
    if verify(): 
        session['page'] = 'sessions'
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.session_id, s.start_time, s.end_time, s.description, c.name, c.colour 
            FROM study_sessions s 
            JOIN classes c ON s.class_id = c.class_id 
            WHERE s.student_id = ? 
            ORDER BY s.end_time DESC
        ''', (session['user_id'],))
        session_data = cursor.fetchall()
        conn.close()
        return render_template('sessions.html', session_data=session_data)
    else:
        flash("Please login to continue", "error")
        return redirect('/login')  
    
@app.route('/settings', methods=['GET'])
def settings():
    if verify():
        session['page'] = 'settings'
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        if session['user_type'] == 'student':
            cursor.execute("SELECT * FROM students WHERE student_id = ?", (session['user_id'],))
        else:
            cursor.execute("SELECT * FROM teachers WHERE teacher_id = ?", (session['user_id'],))
        user_data = cursor.fetchall()[0]
        conn.close()
        #print(user_data)
        return render_template('settings.html', user_data=user_data)
    else:
        flash('Please login to continue', 'error')
        return redirect('/')
    
@app.route('/update_username', methods=['POST'])
def update_username():
    if verify():
        username = request.form.get('username')
        if is_valid(username) and ' ' not in username:
            user_id = session['user_id']
            conn = sqlite3.connect('study_app.db')
            cursor = conn.cursor()
            if not find_duplicate(cursor, username):
                if session['user_type'] == 'teacher':
                    cursor.execute('UPDATE teachers SET username = ? WHERE teacher_id = ?', (username, user_id))
                    app.logger.info(f'Teacher:{user_id} updated their username')
                else:
                    cursor.execute('UPDATE students SET username = ? WHERE student_id = ?', (username, user_id))
                    app.logger.info(f'Student:{user_id} updated their username')
                conn.commit()
                conn.close()
                session['username'] = username
                flash('Username successfully updated', 'success')
                return redirect('/settings')
            else:
                flash('Username is taken', 'error')
                return redirect('/settings')
        else:
            flash('Invalid username', 'error')
            return redirect('/settings')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')

@app.route('/update_display_name', methods=['POST'])
def update_display_name():
    if verify():
        display_name = request.form.get('display_name')
        if is_valid(display_name):
            user_id = session['user_id']
            conn = sqlite3.connect('study_app.db')
            cursor = conn.cursor()
            if session['user_type'] == 'teacher':
                cursor.execute('UPDATE teachers SET name = ? WHERE teacher_id = ?', (display_name, user_id))
                app.logger.info(f'Teacher:{user_id} updated their display name')
            else:
                cursor.execute('UPDATE students SET name = ? WHERE student_id = ?', (display_name, user_id))
                app.logger.info(f'Student:{user_id} updated their display name')
            conn.commit()
            conn.close()            
            flash('Display name successfully updated', 'success')
            return redirect('/settings')
        else:
            flash('Invalid display name', 'error')
            return redirect('/settings')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')
    
@app.route('/logout')
def logout():
    if session['user_type'] == 'teacher':
        app.logger.info(f'Teacher:{session["user_id"]} logged out')
    else:
        app.logger.info(f'Student:{session["user_id"]} logged out')
    session.clear()
    flash('You have been logged out', 'success')
    return redirect('/login')





@app.route('/create_class', methods=["POST"])
def create_class():
    if verify('teacher'):
        class_name = request.form.get("class_name")
        teacher_id = session['user_id']
        colour = request.form.get("colour")
        if colour and colour not in COLOURS:
            flash('Invalid colour selection', 'error')
            return redirect('/dashboard')
        elif not colour:
            colour = COLOURS[random.randint(0,6)]
        if not class_name or not is_valid(class_name):
            flash('You have not entered a valid name', 'error')
            return redirect('/dashboard')
        else:
            conn = sqlite3.connect('study_app.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO classes (name, teacher_id, colour) VALUES (?, ?, ?)", (class_name, teacher_id, colour))
            conn.commit()
            conn.close()
            app.logger.info(f'Class:{class_name} created by teacher:{teacher_id}')
            flash('Class created successfully', 'success')
            return redirect('/dashboard')
    else:
        flash('Please login to continue')
        return redirect('/login')
    
@app.route('/update_class', methods=['POST'])
def update_class():
    if verify('teacher'):
        edit_class_id = int(request.form.get("class_id"))
        new_colour = request.form.get("colour")
        if is_valid(edit_class_id) and new_colour in COLOURS:
            if auth_teacher(session['user_id'], edit_class_id):
                new_class_name = request.form.get("class_name")
                if new_class_name and is_valid(new_class_name):
                    conn = sqlite3.connect('study_app.db')
                    cursor = conn.cursor()
                    cursor.execute("UPDATE classes SET name = ?, colour = ? WHERE class_id = ?", (new_class_name, new_colour, edit_class_id))
                    conn.commit()
                    conn.close()
                    app.logger.info(f'Class:{edit_class_id} updated by teacher:{session["user_id"]}')
                    flash('Class updated successfully', 'success')
                else:
                    flash('Please input a valid class name', 'error')
                return redirect('/dashboard')
            else:
                flash('You are not the owner of this class', 'error')
                return redirect('/dashboard')
        else:
            flash('Invalid class id or colour', 'error')
            return redirect('/dashboard')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')


@app.route('/join_code', methods=["GET", "POST"])
def join_code():
    if verify():
        join_code = request.form.get("join_code")
        if is_valid(join_code) and len(join_code) == 6 and join_code.isdigit():
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
        else:
            flash('Please enter a valid join-code', 'error')
            return redirect('/dashboard')
    else:
        flash('Please login to continue')
        return redirect('/login')
        
@app.route('/view_class/<int:class_id>', methods=['GET', 'POST'])
@limiter.limit("30 per minute")
def view_class(class_id):
    if verify('teacher'):
        if is_valid(str(class_id)):
            session['page'] = 'view_class'
            join_code = generate_join_code(class_id)
            class_entity = get_class(class_id)
            if class_entity:
                if auth_teacher(session['user_id'], class_id):
                    conn = sqlite3.connect('study_app.db')
                    cursor = conn.cursor()
                    
                    sort_by = request.args.get('sort_by', 'name')
                    if sort_by == 'study_time':
                        cursor.execute('''
                        SELECT students.student_id, students.name, classes_students.total_study_time
                            FROM students
                            JOIN classes_students ON students.student_id = classes_students.student_id
                            JOIN classes ON classes.class_id = classes_students.class_id
                            WHERE classes.class_id = ?
                            ORDER BY classes_students.total_study_time DESC
                            ''', (class_id,))
                    else:
                        cursor.execute('''
                        SELECT students.student_id, students.name, classes_students.total_study_time
                            FROM students
                            JOIN classes_students ON students.student_id = classes_students.student_id
                            JOIN classes ON classes.class_id = classes_students.class_id
                            WHERE classes.class_id = ?
                            ORDER BY students.name ASC
                            ''', (class_id,))
                    
                    class_data = cursor.fetchall()
                    cursor.execute("SELECT * FROM study_sessions WHERE class_id = ? ORDER BY start_time DESC", (class_id,))
                    session_data = cursor.fetchall()
                    
                    # Get teacher data for get_tasks function
                    cursor.execute("SELECT * FROM teachers WHERE teacher_id = ?", (session['user_id'],))
                    teacher_data = cursor.fetchall()[0]
                    task_data = get_tasks(cursor, teacher_data, class_id)
                    conn.close()
                    
                    if class_data:
                        total = 0
                        sum = 0
                        for row in class_data:
                            total += int(row[2])
                            sum += 1
                        if total > 0:
                            average_study_time = round(total/sum, 1)
                        else:
                            average_study_time = 0
                    else:
                        average_study_time = 0
                    
                    return render_template('view-class.html', class_data=class_data, class_entity=class_entity, average_study_time=average_study_time, join_code=join_code, session_data=session_data, task_data=task_data)
                else:
                    flash('You are not the owner of this class', 'error')
                    return redirect('/dashboard')
            else:
                flash('Class does not exist')
                return redirect('/dashboard')
        else:
            flash('Invalid class id', 'error')
            return redirect('/dashboard')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')
    
@app.route('/invite_student', methods=['GET', 'POST'])
def invite_student():
    if verify('teacher'):
        student_username = request.form.get('student_username')
        class_id = request.form.get("class_id")
        if is_valid(class_id) and is_valid(student_username):
            if auth_teacher(session['user_id'], class_id):
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
            else:
                flash('You are not the owner of this class', 'error')
                return ('/dashboard')
        else:
            flash('Please enter a valid username', 'error')
            return redirect('/dashboard')
    else:
        flash('Please login to continue')
        return redirect('/login')
    
@app.route('/remove_student', methods=['POST'])
def remove_student():
    if verify('teacher'):
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        if is_valid(student_id) and is_valid(class_id):
            if auth_teacher(session['user_id'], class_id):
                conn = sqlite3.connect('study_app.db')
                cursor = conn.cursor()
                cursor.execute('DELETE FROM classes_students WHERE student_id = ? AND class_id = ?', (student_id, class_id))
                cursor.execute('DELETE FROM study_sessions WHERE student_id = ? AND class_id = ?', (student_id, class_id))
                conn.commit()
                conn.close()
                app.logger.info(f'Student:{student_id} removed by teacher:{session["user_id"]} from class:{class_id}')
                flash('Student removed', 'success')
                return redirect(f'/view_class/{class_id}')
            else:
                flash('You are not the owner of this class', 'error')
                return redirect('/dashboard')
        else:
            flash('Invalid student id or class id', 'error')
            return redirect('/dashboard')
    else:  
        flash('Please login to continue', 'error')
        return redirect('/login')

@app.route('/edit_study_time', methods=['POST'])
def edit_study_time():
    if verify('teacher'):
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        new_study_time = request.form.get('new_study_time')
        if is_valid_time(new_study_time) and is_valid(student_id) and is_valid(class_id):
            if auth_teacher(session['user_id'], class_id):
                study_time_seconds = convertToSeconds(new_study_time)
                conn = sqlite3.connect('study_app.db')
                cursor = conn.cursor()
                cursor.execute('UPDATE classes_students SET total_study_time = ? WHERE student_id = ? AND class_id = ?', (study_time_seconds, student_id, class_id))
                #print(study_time_seconds)
                conn.commit()
                conn.close()
                app.logger.info(f'Study time for student:{student_id} in class:{class_id} updated by teacher:{session["user_id"]}')
                flash(f'Study time successfully updated', 'success')
                return redirect(f'/view_class/{class_id}')
            else:
                flash('You are not the owner of this class', 'error')
                return redirect('/dashboard')
        elif not is_valid(student_id) or not is_valid(class_id):
            flash('Invalid student id or class id', 'error')
            return redirect('/dashboard')
        else:
            flash('Please enter a valid time', 'error')
            return redirect(f'/view_class/{class_id}')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')

@app.route('/update_session', methods=['POST'])
def update_session():
    if verify('teacher'):
        session_id = request.form.get("session_id")
        student_id = request.form.get("student_id")
        class_id = request.form.get("class_id")
        if is_valid(session_id) and is_valid(class_id) and is_valid(student_id):
            if auth_teacher(session['user_id'], class_id):
                duration = math.floor(float(request.form.get("duration")))
                new_session_duration = request.form.get('new_session_duration')
                description = request.form.get('session_description')
                if is_valid_time(new_session_duration) and is_valid(description):
                    new_duration = convertToSeconds(new_session_duration)
                    conn = sqlite3.connect('study_app.db')
                    cursor = conn.cursor()
                    cursor.execute('SELECT end_time FROM study_sessions WHERE session_id = ?', (session_id,))
                    end_time = datetime.strptime(cursor.fetchone()[0], "%Y-%m-%d %H:%M:%S.%f")
                    new_end_time = end_time + timedelta(seconds=(new_duration - duration))
                    cursor.execute('UPDATE study_sessions SET end_time = ?, description = ? WHERE session_id = ?', (new_end_time, description, session_id))
                    updateTotalStudyTime(cursor, student_id, class_id, new_duration - duration)
                    conn.commit()
                    conn.close()
                    app.logger.info(f'Session:{session_id} updated by teacher:{session["user_id"]}')
                    flash(f'Session time successfully updated', 'success')
                    return redirect(f'/view_class/{class_id}')
                else:
                    flash('Invalid time or description', 'error')
                    return redirect(f'/view_class/{class_id}')
            else:
                flash('You are not the owner of this class', 'error')
                return redirect('/dashboard')
        else:
            flash('Invalid class, student or session id', 'error')
            return redirect('/dashboard')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')
        
@app.route('/delete_session', methods=['POST'])
def delete_session():
    if verify('teacher'):
        session_id = request.form.get('session_id')
        class_id = request.form.get('class_id')
        student_id = request.form.get('student_id')
        if is_valid(session_id) and is_valid(class_id) and is_valid(student_id):
            if auth_teacher(session['user_id'], class_id):
                conn = sqlite3.connect('study_app.db')
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM study_sessions WHERE session_id = ?', (session_id,))
                study_session = cursor.fetchall()[0]
                end_time = datetime.strptime(study_session[4], "%Y-%m-%d %H:%M:%S.%f")
                start_time = datetime.strptime(study_session[3], "%Y-%m-%d %H:%M:%S")
                session_duration = int((end_time - start_time).total_seconds())
                updateTotalStudyTime(cursor, student_id, class_id, session_duration * -1)
                cursor.execute('DELETE FROM study_sessions WHERE session_id = ?', (session_id,))
                conn.commit()
                conn.close()
                app.logger.info(f'Session:{session_id} deleted by teacher:{session["user_id"]}')
                flash(f'Session deleted successfully', 'success')
                return redirect(f'/view_class/{class_id}')
            else:
                flash('You are not the owner of this class', 'error')
                return redirect('/dashboard')
        else:
            flash('Invalid class, student or session id', 'error')
            return redirect('/dashboard')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')

@app.route('/delete_class/<int:class_id>', methods=['POST'])
def delete_class(class_id):
    if verify('teacher'):
        if is_valid(class_id):
            if auth_teacher(session['user_id'], class_id):
                
                
                conn = sqlite3.connect('study_app.db')
                cursor = conn.cursor()
                cursor.execute("DELETE FROM classes WHERE class_id = ?", (class_id,))
                cursor.execute("DELETE FROM classes_students WHERE class_id = ?", (class_id,))
                conn.commit()
                conn.close()
                app.logger.info(f'Class:{class_id} deleted by teacher:{session["user_id"]}')
                flash('Class deleted', 'success')
                return redirect('/dashboard') #bug here - doens't show on first reload due to js
            else:
                flash('You are not the owner of this class', 'error')
                return redirect('/dashboard')
        else:
            flash('Invalid class id', 'error')
            return redirect("/dasboard")
    else:
        flash('Please login to continue')
        return redirect('/login')

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

@app.route('/cancel_mfa')
def cancel_mfa():
    if verify():
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        if session['user_type'] == 'student':
            cursor.execute("UPDATE students SET mfa_secret = ? WHERE student_id = ?", (None, session['user_id']))
        else:
            cursor.execute("UPDATE teachers SET mfa_secret = ? WHERE teacher_id = ?", (None, session['user_id']))
        conn.commit()
        conn.close()  
        return redirect('/dashboard')
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')
    
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(Exception)
def handle_exception(e):
    flash("An unexpected error occurred. Please try again later.", 'error')
    if session.get('user_id'):
        return redirect(f"/{session['page']}")
    else:
        return redirect('/')
    
@app.errorhandler(429)
def rate_limit_exceeded(e):
    flash("Too many attempts. Please try again later.", 'error')
    return redirect('/')

@app.route('/delete_account', methods=['POST'])
def delete_account():
    if verify():
        user_id = session['user_id']
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        if session['user_type'] == 'teacher':
            cursor.execute('DELETE FROM classes WHERE teacher_id = ?', (user_id,))
            cursor.execute('DELETE FROM teachers WHERE teacher_id = ?', (user_id,))
            app.logger.info(f'Teacher:{user_id} deleted their account')
        else:
            cursor.execute('DELETE FROM study_sessions WHERE student_id = ?', (user_id,))
            cursor.execute('DELETE FROM classes_students WHERE student_id = ?', (user_id,))
            cursor.execute('DELETE FROM students WHERE student_id = ?', (user_id,))
            app.logger.info(f'Student:{user_id} deleted their account')
    conn.commit()
    conn.close()
    flash('Account deleted', 'success')
    return redirect("/logout")


@app.route('/tasks', methods=['GET'])
def tasks():
    if verify():
        session['page'] = 'tasks'
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        if session['user_type'] == 'teacher':
            cursor.execute("SELECT * FROM teachers WHERE teacher_id = ?", (session['user_id'],))
            user_data = cursor.fetchall()[0]
            cursor.execute("SELECT * FROM classes WHERE teacher_id = ?", (session['user_id'],))
            class_data = cursor.fetchall()
            
        else:
            cursor.execute("SELECT * FROM students WHERE student_id = ?", (session['user_id'],))
            user_data = cursor.fetchall()[0]
            
            cursor.execute('''
                SELECT classes.* FROM classes 
                JOIN classes_students ON classes.class_id = classes_students.class_id 
                WHERE classes_students.student_id = ?
            ''', (session['user_id'],))
            class_data = cursor.fetchall()
        
        task_data = get_tasks(cursor, user_data)
        #print(task_data)

        conn.close()
        #print(user_data)
        return render_template('tasks.html', user_data=user_data, class_data=class_data, task_data=task_data)
    else:
        flash('Please login to continue', 'error')
        return redirect('/')
    
@app.route('/create_task', methods=["POST"])
def create_task():
    task_description = request.form.get("task_description")
    class_id = request.form.get("class_id")
    due_date = request.form.get("due_date")
    created_at = datetime.now()

    if not due_date or due_date.strip() == "":
        due_date = None
    
    duration = request.form.get("duration")
    if not duration or duration.strip() == "":
        duration = None
    if not task_description or not is_valid(task_description):
        flash('You have not entered a valid description', 'error')
        return redirect('/tasks')
    elif due_date is not None and not isinstance(datetime.strptime(due_date, '%Y-%m-%d'), datetime):
        flash('Please enter a valid due date', 'error')
        return redirect('/tasks')
    elif duration is not None and not duration.isnumeric():
        flash('Please enter a valid duration', 'error')
        return redirect('/tasks')

    else:
        
        if verify('teacher'): 
            teacher_id = session['user_id']
            conn = sqlite3.connect('study_app.db')
            cursor = conn.cursor()
            
            cursor.execute("INSERT INTO teacher_tasks (class_id, created_at, due_date, duration, description) VALUES (?, ?, ?, ?, ?)", (class_id, created_at, due_date, duration, task_description))
            teacher_task_id = cursor.lastrowid
            
            cursor.execute("SELECT student_id FROM classes_students WHERE class_id = ?", (class_id,))
            student_ids = cursor.fetchall()
            
            for student_id in student_ids:
                cursor.execute("INSERT INTO student_tasks (teacher_task_id, student_id, created_at) VALUES (?, ?, ?)", (teacher_task_id, student_id[0], created_at,))
            
            conn.commit()
            conn.close()
            app.logger.info(f'Task:{task_description} created by teacher:{teacher_id} for ALL students in class:{class_id}')
            flash('Task created successfully', 'success')
            return redirect(request.referrer or f'/{session["page"]}')
        
        elif verify('student'):
            student_id = session['user_id']
            conn = sqlite3.connect('study_app.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO student_tasks (class_id, student_id, created_at, due_date, duration, description) VALUES (?, ?, ?, ?, ?, ?)", (class_id, student_id, created_at, due_date, duration, task_description))
            conn.commit()
            conn.close()
            app.logger.info(f'Task:{task_description} created by student:{student_id}')
            flash('Task created successfully', 'success')
            return redirect(f'/{session["page"]}')
        
        else:
            flash('Please login to continue')
            return redirect('/login')
    
    
@app.route('/edit_task', methods=["POST"])
def edit_task():
    task_id = request.form.get("task_id")
    task_description = request.form.get("task_description")
    class_id = request.form.get("class_id")
    due_date = request.form.get("due_date")

    if not due_date or due_date.strip() == "":
        due_date = None
    
    duration = request.form.get("duration")
    if not duration or duration.strip() == "":
        duration = None
        
    if not task_description or not is_valid(task_description):
        flash('You have not entered a valid description', 'error')
        return redirect('/tasks')
    elif due_date is not None and not isinstance(datetime.strptime(due_date, '%Y-%m-%d'), datetime):
        flash('Please enter a valid due date', 'error')
        return redirect('/tasks')
    elif duration is not None and not duration.isnumeric():
        flash('Please enter a valid duration', 'error')
        return redirect('/tasks')
    else:
        if session['user_type'] == 'teacher' and verify('teacher'): 
            teacher_id = session['user_id']
            conn = sqlite3.connect('study_app.db')
            cursor = conn.cursor()
            
            # Check if the teacher owns this task
            cursor.execute("""
                SELECT c.teacher_id FROM teacher_tasks tt 
                JOIN classes c ON tt.class_id = c.class_id 
                WHERE tt.teacher_task_id = ?
            """, (task_id,))
            result = cursor.fetchone()
            
            if result and result[0] == teacher_id:
                cursor.execute("""
                    UPDATE teacher_tasks 
                    SET class_id = ?, due_date = ?, duration = ?, description = ? 
                    WHERE teacher_task_id = ?
                """, (class_id, due_date, duration, task_description, task_id))
                conn.commit()
                app.logger.info(f'Task:{task_id} edited by teacher:{teacher_id}')
                flash('Task updated successfully', 'success')
            else:
                flash('You are not the owner of this task', 'error')
            
            conn.close()
            return redirect(request.referrer or f'/{session["page"]}')

        elif verify('student'):
            student_id = session['user_id']
            conn = sqlite3.connect('study_app.db')
            cursor = conn.cursor()
            
            # Check if the student owns this task (personal task, not assigned)
            cursor.execute("""
                SELECT student_id FROM student_tasks 
                WHERE student_task_id = ? AND teacher_task_id IS NULL
            """, (task_id,))
            result = cursor.fetchone()
            
            if result and result[0] == student_id:
                cursor.execute("""
                    UPDATE student_tasks 
                    SET class_id = ?, due_date = ?, duration = ?, description = ? 
                    WHERE student_task_id = ?
                """, (class_id, due_date, duration, task_description, task_id))
                conn.commit()
                app.logger.info(f'Task:{task_id} edited by student:{student_id}')
                flash('Task updated successfully', 'success')
            else:
                flash('You can only edit your own personal tasks', 'error')
            
            conn.close()
            return redirect(request.referrer or f'/{session["page"]}')
        
        else:
            flash('Please login to continue', 'error')
            return redirect('/login')
    
@app.route('/delete_task', methods=["POST"])
def delete_task():
    task_id = request.form.get("task_id")
    if session['user_type'] == 'teacher' and verify('teacher'): 
        teacher_id = session['user_id']
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        
        # Check if the teacher owns this task
        cursor.execute("""
            SELECT c.teacher_id FROM teacher_tasks tt 
            JOIN classes c ON tt.class_id = c.class_id 
            WHERE tt.teacher_task_id = ?
        """, (task_id,))
        result = cursor.fetchone()
        
        if result and result[0] == teacher_id:
            # Delete related student tasks first (cascading delete)
            cursor.execute('DELETE FROM student_tasks WHERE teacher_task_id = ?', (task_id,))
            # Then delete the teacher task
            cursor.execute('DELETE FROM teacher_tasks WHERE teacher_task_id = ?', (task_id,))
            conn.commit()
            app.logger.info(f'Task:{task_id} deleted by teacher:{teacher_id}')
            flash('Task deleted successfully', 'success')
        else:
            flash('You are not the owner of this task', 'error')
        
        conn.close()
        return redirect(request.referrer or f'/{session["page"]}')
    
    elif verify('student'):
        student_id = session['user_id']
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        
        # Check if the student owns this task (personal task, not assigned)
        cursor.execute("""
            SELECT student_id FROM student_tasks 
            WHERE student_task_id = ? AND teacher_task_id IS NULL
        """, (task_id,))
        result = cursor.fetchone()
        
        if result and result[0] == student_id:
            cursor.execute('DELETE FROM student_tasks WHERE student_task_id = ?', (task_id,))
            conn.commit()
            app.logger.info(f'Task:{task_id} deleted by student:{student_id}')
            flash('Task deleted successfully', 'success')
        else:
            flash('You can only delete your own personal tasks', 'error')
        
        conn.close()
        return redirect(request.referrer or f'/{session["page"]}')
    
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')  

@app.route('/complete_task', methods=["POST"])
def complete_task():
    task_id = request.form.get("task_id")
    if verify('student'):
        student_id = session['user_id']
        conn = sqlite3.connect('study_app.db')
        cursor = conn.cursor()
        
        # Check if the student owns this task 
        cursor.execute("""
            SELECT student_id, completed FROM student_tasks 
            WHERE student_task_id = ?
        """, (task_id,))
        result = cursor.fetchone()
        
        if result and result[0] == student_id:
            if result[1] == 0:  # Compare with integer 0 instead of string '0'
                cursor.execute('UPDATE student_tasks SET completed = 1, completed_at = ? WHERE student_task_id = ?', (datetime.now(), task_id))
            else:
                cursor.execute('UPDATE student_tasks SET completed = 0, completed_at = NULL WHERE student_task_id = ?', (task_id,))
            conn.commit()
            app.logger.info(f'Task:{task_id} deleted by student:{student_id}')
            flash('Task completed', 'success')
            return redirect(f"/{session['page']}")
        else:
            flash('You can only complete your own tasks', 'error')
        
        conn.close()
        return redirect(f"/{session['page']}")
    
    else:
        flash('Please login to continue', 'error')
        return redirect('/login')  


