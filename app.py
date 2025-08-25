from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, qrcode, io, secrets, string, random, datetime, csv
from functools import wraps

BASE_DIR = os.path.dirname(__file__)
DB = os.path.join(BASE_DIR, "data.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # users: id, name, email, password, role (student/teacher)
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        teacher_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS attendance_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER,
        subject_id INTEGER,
        unique_code TEXT,
        created_at TEXT,
        expires_at TEXT
    );
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        subject_id INTEGER,
        session_id INTEGER,
        created_at TEXT
    );
    """)
    conn.commit()
    conn.close()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET','devsecret1234')

# Helpers
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role')!=role:
                flash('Unauthorized access','danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register/<role>', methods=['GET','POST'])
def register(role):
    if role not in ('student','teacher'):
        return "Invalid role", 400
    if request.method=='POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",(name,email,password,role))
            conn.commit()
            flash('Registered successfully. Please login.','success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Error: '+str(e),'danger')
        finally:
            conn.close()
    return render_template('register.html', role=role)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?",(email,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id']=user['id']; session['name']=user['name']; session['role']=user['role']; session['email']=user['email']
            flash('Logged in','success')
            if user['role']=='teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid credentials','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); flash('Logged out','info'); return redirect(url_for('index'))

# Teacher routes
@app.route('/teacher/dashboard')
@login_required(role='teacher')
def teacher_dashboard():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM subjects WHERE teacher_id=?",(session['user_id'],))
    subjects = cur.fetchall()
    # fetch recent sessions
    cur.execute("SELECT s.*, subj.name as subject_name FROM attendance_sessions s LEFT JOIN subjects subj ON subj.id=s.subject_id WHERE s.teacher_id=? ORDER BY s.created_at DESC",(session['user_id'],))
    sessions = cur.fetchall()
    conn.close()
    return render_template('teacher_dashboard.html', subjects=subjects, sessions=sessions)

@app.route('/teacher/subjects/add', methods=['POST'])
@login_required(role='teacher')
def add_subject():
    name = request.form['name']
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO subjects (name, teacher_id) VALUES (?,?)",(name, session['user_id']))
    conn.commit(); conn.close(); flash('Subject added','success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/session/generate', methods=['POST'])
@login_required(role='teacher')
def generate_session():
    subject_id = request.form['subject_id']
    length = 6
    unique_code = ''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(length))
    created_at = datetime.datetime.utcnow().isoformat()
    expires_at = (datetime.datetime.utcnow()+datetime.timedelta(minutes=30)).isoformat()  # 30 minutes expiry
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO attendance_sessions (teacher_id, subject_id, unique_code, created_at, expires_at) VALUES (?,?,?,?,?)",(session['user_id'], subject_id, unique_code, created_at, expires_at))
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    flash('Session generated. Share QR or code with students.','success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/session/<int:session_id>/qr')
@login_required(role='teacher')
def serve_qr(session_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM attendance_sessions WHERE id=? AND teacher_id=?",(session_id, session['user_id']))
    s = cur.fetchone()
    conn.close()
    if not s:
        return "Not found",404
    qr_content = f"session:{s['id']};subject:{s['subject_id']};code:{s['unique_code']}"
    img = qrcode.make(qr_content)
    buf = io.BytesIO(); img.save(buf,'PNG'); buf.seek(0)
    return send_file(buf, mimetype='image/png', download_name='qr.png')

@app.route('/teacher/session/<int:session_id>/export')
@login_required(role='teacher')
def export_session(session_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT a.*, u.name as student_name, u.email as student_email FROM attendance a JOIN users u ON u.id=a.student_id WHERE a.session_id=?",(session_id,))
    rows = cur.fetchall()
    conn.close()
    si = io.StringIO(); cw = csv.writer(si)
    cw.writerow(['student_id','student_name','student_email','subject_id','session_id','marked_at'])
    for r in rows:
        cw.writerow([r['student_id'], r['student_name'], r['student_email'], r['subject_id'], r['session_id'], r['created_at']])
    mem = io.BytesIO(); mem.write(si.getvalue().encode('utf-8')); mem.seek(0)
    return send_file(mem, mimetype='text/csv', download_name=f'session_{session_id}_attendance.csv', as_attachment=True)

# Student routes
@app.route('/student/dashboard')
@login_required(role='student')
def student_dashboard():
    conn = get_db(); cur = conn.cursor()
    # subjects - show all subjects
    cur.execute("SELECT subj.*, u.name as teacher_name FROM subjects subj LEFT JOIN users u ON u.id=subj.teacher_id")
    subjects = cur.fetchall()
    # attendance summary
    cur.execute("SELECT subj.id as subject_id, subj.name as subject_name, COUNT(a.id) as marks FROM subjects subj LEFT JOIN attendance a ON a.subject_id=subj.id AND a.student_id=? GROUP BY subj.id",(session['user_id'],))
    summary = cur.fetchall()
    conn.close()
    return render_template('student_dashboard.html', subjects=subjects, summary=summary)

@app.route('/student/mark', methods=['POST'])
@login_required(role='student')
def mark_attendance():
    # two modes: code entry or qr scanner sends content
    code = request.form.get('code','').strip()
    qr_content = request.form.get('qr_content','').strip()
    conn = get_db(); cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    if qr_content:
        try:
            parts = dict([p.split(':',1) for p in qr_content.split(';')])
            session_id = int(parts.get('session','0'))
            cur.execute("SELECT * FROM attendance_sessions WHERE id=?",(session_id,))
            s = cur.fetchone()
            if s:
                if s['expires_at'] and s['expires_at'] < now:
                    flash('Session expired','danger'); conn.close(); return redirect(url_for('student_dashboard'))
                cur.execute("SELECT * FROM attendance WHERE student_id=? AND session_id=?",(session['user_id'], session_id))
                if cur.fetchone():
                    flash('Already marked','info'); conn.close(); return redirect(url_for('student_dashboard'))
                cur.execute("INSERT INTO attendance (student_id, subject_id, session_id, created_at) VALUES (?,?,?,?)",(session['user_id'], s['subject_id'], session_id, now))
                conn.commit(); flash('Attendance marked via QR','success'); conn.close(); return redirect(url_for('student_dashboard'))
        except Exception as e:
            flash('Invalid QR content','danger'); conn.close(); return redirect(url_for('student_dashboard'))
    elif code:
        cur.execute("SELECT * FROM attendance_sessions WHERE unique_code=?",(code,))
        s = cur.fetchone()
        if not s:
            flash('Invalid code','danger'); conn.close(); return redirect(url_for('student_dashboard'))
        if s['expires_at'] and s['expires_at'] < now:
            flash('Session expired','danger'); conn.close(); return redirect(url_for('student_dashboard'))
        cur.execute("SELECT * FROM attendance WHERE student_id=? AND session_id=?",(session['user_id'], s['id']))
        if cur.fetchone():
            flash('Already marked','info'); conn.close(); return redirect(url_for('student_dashboard'))
        cur.execute("INSERT INTO attendance (student_id, subject_id, session_id, created_at) VALUES (?,?,?,?)",(session['user_id'], s['subject_id'], s['id'], now))
        conn.commit(); flash('Attendance marked via Code','success'); conn.close(); return redirect(url_for('student_dashboard'))
    flash('No data provided','warning'); conn.close(); return redirect(url_for('student_dashboard'))


if __name__=='__main__':
    if not os.path.exists(DB):
        init_db()
        print('Initialized DB at', DB)
    app.run(host='0.0.0.0', port=5000, debug=True)
