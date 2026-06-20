#!/usr/bin/env python3
"""BrightMind Server v2 — Simple House Points per student, Live Events, Videos"""
from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
import sqlite3, json, os, random, time, socket, threading, webbrowser

app = Flask(__name__, static_folder='.')
CORS(app)
PORT = int(os.environ.get('PORT', 5000))
IS_RAILWAY = bool(os.environ.get('RAILWAY_ENVIRONMENT'))
DB_FILE = 'brightmind.db'

def get_db():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS rooms (
            code TEXT PRIMARY KEY, name TEXT DEFAULT 'My Classroom',
            color TEXT DEFAULT '#1a73e8', announcement TEXT,
            disco REAL DEFAULT 0, created REAL, updated REAL
        );
        CREATE TABLE IF NOT EXISTS students (
            name TEXT, room_code TEXT, lang TEXT DEFAULT 'en',
            yr INTEGER DEFAULT 1, stars INTEGER DEFAULT 0,
            prog TEXT DEFAULT '{}', last_seen REAL, hp INTEGER DEFAULT 0,
            PRIMARY KEY (name, room_code)
        );
        CREATE TABLE IF NOT EXISTS homework (
            id TEXT PRIMARY KEY, room_code TEXT,
            title TEXT, subject TEXT, year TEXT, due TEXT,
            instructions TEXT, type TEXT DEFAULT 'manual',
            questions TEXT DEFAULT '[]', description TEXT DEFAULT '',
            theme TEXT DEFAULT 'blue', created REAL
        );
        CREATE TABLE IF NOT EXISTS submissions (
            hw_id TEXT, student_name TEXT,
            answers TEXT DEFAULT '{}', score INTEGER DEFAULT 0,
            submitted_at REAL, PRIMARY KEY (hw_id, student_name)
        );
        CREATE TABLE IF NOT EXISTS chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_code TEXT, name TEXT, text TEXT,
            role TEXT DEFAULT 'student', time REAL
        );
        CREATE TABLE IF NOT EXISTS actlog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_code TEXT, name TEXT, txt TEXT, time REAL
        );
        CREATE TABLE IF NOT EXISTS live_events (
            id TEXT PRIMARY KEY, room_code TEXT,
            type TEXT, title TEXT, data TEXT DEFAULT '{}',
            active INTEGER DEFAULT 1, answers TEXT DEFAULT '{}',
            created REAL, ended REAL
        );
        CREATE TABLE IF NOT EXISTS media (
            id TEXT PRIMARY KEY, room_code TEXT,
            type TEXT DEFAULT 'video', url TEXT,
            title TEXT, description TEXT DEFAULT '', created REAL
        );
    ''')
    db.commit(); db.close()
    print('Database ready.')

def touch(code):
    db = get_db()
    db.execute('UPDATE rooms SET updated=? WHERE code=?', (time.time(), code))
    db.commit(); db.close()

def gen_code():
    db = get_db()
    for _ in range(1000):
        code = ''.join(random.choices('0123456789', k=4))
        if not db.execute('SELECT 1 FROM rooms WHERE code=?', (code,)).fetchone():
            db.close(); return code
    db.close(); return '9999'

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return 'localhost'

# ── Pages ────────────────────────────────────────────────────────
@app.route('/'); 
@app.route('/index.html')
def index(): return send_from_directory('.', 'index.html')
@app.route('/teacher')
def teacher(): return send_from_directory('.', 'teacher.html')
@app.route('/student')
def student(): return send_from_directory('.', 'student.html')
@app.route('/join/<code>')
def join_redirect(code): return redirect(f'/student?room={code}')

# ── Rooms ────────────────────────────────────────────────────────
@app.route('/api/rooms/create', methods=['POST'])
def create_room():
    d = request.json or {}; code = gen_code(); now = time.time()
    db = get_db()
    db.execute('INSERT INTO rooms (code,name,color,created,updated) VALUES (?,?,?,?,?)',
               (code, d.get('name','My Classroom'), d.get('color','#1a73e8'), now, now))
    db.commit(); db.close()
    return jsonify({'ok': True, 'code': code})

@app.route('/api/rooms/<code>', methods=['GET'])
def get_room(code):
    db = get_db(); r = db.execute('SELECT * FROM rooms WHERE code=?', (code,)).fetchone(); db.close()
    if not r: return jsonify({'ok': False, 'error': 'Room not found!'}), 404
    return jsonify({'ok': True, 'room': dict(r)})

@app.route('/api/rooms/<code>', methods=['PATCH'])
def patch_room(code):
    d = request.json or {}; db = get_db()
    for k in ['name', 'color', 'announcement']:
        if k in d: db.execute(f'UPDATE rooms SET {k}=? WHERE code=?', (d[k], code))
    db.execute('UPDATE rooms SET updated=? WHERE code=?', (time.time(), code))
    db.commit(); db.close(); return jsonify({'ok': True})

@app.route('/api/rooms', methods=['GET'])
def list_rooms():
    db = get_db(); rows = db.execute('SELECT code,name,color FROM rooms').fetchall()
    result = {}
    for r in rows:
        stus = db.execute('SELECT COUNT(*) FROM students WHERE room_code=?', (r['code'],)).fetchone()[0]
        hws = db.execute('SELECT COUNT(*) FROM homework WHERE room_code=?', (r['code'],)).fetchone()[0]
        result[r['code']] = {'code':r['code'],'name':r['name'],'color':r['color'],'students':stus,'homework':hws}
    db.close(); return jsonify({'ok': True, 'rooms': result})

# ── Students ─────────────────────────────────────────────────────
@app.route('/api/rooms/<code>/students', methods=['POST'])
def reg_student(code):
    db = get_db()
    if not db.execute('SELECT 1 FROM rooms WHERE code=?', (code,)).fetchone():
        db.close(); return jsonify({'ok': False, 'error': 'Room not found'}), 404
    d = request.json or {}; name = d.get('name','').strip()
    if not name: db.close(); return jsonify({'ok': False}), 400
    db.execute('''INSERT INTO students (name,room_code,lang,yr,stars,prog,last_seen,hp)
                  VALUES (?,?,?,?,?,?,?,?)
                  ON CONFLICT(name,room_code) DO UPDATE SET
                  lang=excluded.lang, yr=excluded.yr, stars=excluded.stars,
                  prog=excluded.prog, last_seen=excluded.last_seen''',
               (name, code, d.get('lang','en'), d.get('yr',1),
                d.get('stars',0), json.dumps(d.get('prog',{})), time.time(), d.get('hp',0)))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True})

# ── House Points (per student — simple!) ──────────────────────────
@app.route('/api/rooms/<code>/students/<name>/hp', methods=['POST'])
def award_hp(code, name):
    d = request.json or {}
    amount = int(d.get('amount', 1))
    reason = d.get('reason', 'Good work!')
    db = get_db()
    db.execute('UPDATE students SET hp=hp+? WHERE name=? AND room_code=?', (amount, name, code))
    db.execute('INSERT INTO actlog (room_code,name,txt,time) VALUES (?,?,?,?)',
               (code, 'Teacher', f'🏆 +{amount} HP to {name} — {reason}', time.time()))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True})

# ── Homework ─────────────────────────────────────────────────────
@app.route('/api/rooms/<code>/homework', methods=['POST'])
def add_homework(code):
    d = request.json or {}; hw_id = f"hw_{int(time.time()*1000)}"
    db = get_db()
    db.execute('''INSERT INTO homework
                  (id,room_code,title,subject,year,due,instructions,type,questions,description,theme,created)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
               (hw_id, code, d.get('title',''), d.get('subject',''), d.get('year','Both'),
                d.get('due',''), d.get('instructions',''), d.get('type','manual'),
                json.dumps(d.get('questions',[])), d.get('description',''),
                d.get('theme','blue'), time.time()))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True, 'id': hw_id})

@app.route('/api/rooms/<code>/homework/<hw_id>', methods=['DELETE'])
def del_homework(code, hw_id):
    db = get_db()
    db.execute('DELETE FROM homework WHERE id=? AND room_code=?', (hw_id, code))
    db.execute('DELETE FROM submissions WHERE hw_id=?', (hw_id,))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True})

@app.route('/api/rooms/<code>/homework/<hw_id>/submit', methods=['POST'])
def submit_hw(code, hw_id):
    d = request.json or {}
    student = d.get('student','anon')
    score = d.get('score', 0)
    total = d.get('total', 1)
    db = get_db()
    db.execute('''INSERT INTO submissions (hw_id,student_name,answers,score,submitted_at)
                  VALUES (?,?,?,?,?)
                  ON CONFLICT(hw_id,student_name) DO UPDATE SET
                  answers=excluded.answers, score=excluded.score, submitted_at=excluded.submitted_at''',
               (hw_id, student, json.dumps(d.get('answers',{})), score, time.time()))
    # Auto-award 1 HP if score >= 70%
    if total > 0 and score / total >= 0.7:
        db.execute('UPDATE students SET hp=hp+1 WHERE name=? AND room_code=?', (student, code))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True})

# ── Chat ─────────────────────────────────────────────────────────
@app.route('/api/rooms/<code>/chat', methods=['POST'])
def send_chat(code):
    d = request.json or {}; db = get_db()
    db.execute('INSERT INTO chat (room_code,name,text,role,time) VALUES (?,?,?,?,?)',
               (code, d.get('name',''), d.get('text',''), d.get('role','student'), time.time()))
    db.execute('''DELETE FROM chat WHERE room_code=? AND id NOT IN
                  (SELECT id FROM chat WHERE room_code=? ORDER BY time DESC LIMIT 100)''', (code, code))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True})

# ── Media ────────────────────────────────────────────────────────
@app.route('/api/rooms/<code>/media', methods=['POST'])
def add_media(code):
    d = request.json or {}; mid = f"m_{int(time.time()*1000)}"
    db = get_db()
    db.execute('INSERT INTO media (id,room_code,type,url,title,description,created) VALUES (?,?,?,?,?,?,?)',
               (mid, code, 'video', d.get('url',''), d.get('title','Video'), d.get('description',''), time.time()))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True, 'id': mid})

@app.route('/api/rooms/<code>/media/<mid>', methods=['DELETE'])
def del_media(code, mid):
    db = get_db()
    db.execute('DELETE FROM media WHERE id=? AND room_code=?', (mid, code))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True})

# ── Disco ────────────────────────────────────────────────────────
@app.route('/api/rooms/<code>/disco', methods=['POST'])
def disco(code):
    db = get_db()
    db.execute('UPDATE rooms SET disco=? WHERE code=?', (time.time(), code))
    db.commit(); db.close()
    return jsonify({'ok': True})

# ── Activity log ─────────────────────────────────────────────────
@app.route('/api/rooms/<code>/log', methods=['POST'])
def log_act(code):
    d = request.json or {}; db = get_db()
    db.execute('INSERT INTO actlog (room_code,name,txt,time) VALUES (?,?,?,?)',
               (code, d.get('name',''), d.get('txt',''), time.time()))
    db.execute('''DELETE FROM actlog WHERE room_code=? AND id NOT IN
                  (SELECT id FROM actlog WHERE room_code=? ORDER BY time DESC LIMIT 50)''', (code, code))
    db.commit(); db.close()
    return jsonify({'ok': True})

# ── Live Events ──────────────────────────────────────────────────
@app.route('/api/rooms/<code>/events', methods=['POST'])
def create_event(code):
    d = request.json or {}; eid = f"ev_{int(time.time()*1000)}"
    db = get_db()
    db.execute('UPDATE live_events SET active=0,ended=? WHERE room_code=? AND active=1', (time.time(), code))
    db.execute('INSERT INTO live_events (id,room_code,type,title,data,active,answers,created) VALUES (?,?,?,?,?,1,?,?)',
               (eid, code, d.get('type','quiz'), d.get('title','Live Event'),
                json.dumps(d.get('data',{})), json.dumps({}), time.time()))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True, 'id': eid})

@app.route('/api/rooms/<code>/events/<eid>/answer', methods=['POST'])
def answer_event(code, eid):
    d = request.json or {}; student = d.get('student',''); answer = d.get('answer','')
    db = get_db()
    ev = db.execute('SELECT * FROM live_events WHERE id=? AND active=1', (eid,)).fetchone()
    if not ev: db.close(); return jsonify({'ok': False}), 404
    answers = json.loads(ev['answers'] or '{}')
    answers[student] = {'answer': answer, 'time': time.time()}
    db.execute('UPDATE live_events SET answers=? WHERE id=?', (json.dumps(answers), eid))
    data = json.loads(ev['data'] or '{}')
    correct = data.get('correct','')
    is_correct = bool(correct and answer == correct)
    stars_earned = 3 if is_correct else 0
    if is_correct:
        db.execute('UPDATE students SET hp=hp+1 WHERE name=? AND room_code=?', (student, code))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True, 'correct': is_correct if correct else None, 'stars': stars_earned})

@app.route('/api/rooms/<code>/events/<eid>/end', methods=['POST'])
def end_event(code, eid):
    db = get_db()
    db.execute('UPDATE live_events SET active=0,ended=? WHERE id=? AND room_code=?', (time.time(), eid, code))
    db.commit(); db.close(); touch(code)
    return jsonify({'ok': True})

@app.route('/api/rooms/<code>/events/active', methods=['GET'])
def get_active_event(code):
    db = get_db()
    ev = db.execute('SELECT * FROM live_events WHERE room_code=? AND active=1 ORDER BY created DESC LIMIT 1', (code,)).fetchone()
    if not ev: db.close(); return jsonify({'ok': True, 'event': None})
    result = {**dict(ev), 'data': json.loads(ev['data'] or '{}'), 'answers': json.loads(ev['answers'] or '{}')}
    db.close(); return jsonify({'ok': True, 'event': result})

# ── Poll ─────────────────────────────────────────────────────────
@app.route('/api/rooms/<code>/poll', methods=['GET'])
def poll(code):
    db = get_db()
    r = db.execute('SELECT * FROM rooms WHERE code=?', (code,)).fetchone()
    if not r: db.close(); return jsonify({'ok': False, 'error': 'Room not found'}), 404
    stus = db.execute('SELECT * FROM students WHERE room_code=?', (code,)).fetchall()
    students = {s['name']: {**dict(s), 'prog': json.loads(s['prog'] or '{}')} for s in stus}
    hw_rows = db.execute('SELECT * FROM homework WHERE room_code=? ORDER BY created DESC', (code,)).fetchall()
    homework = []
    for h in hw_rows:
        hw = dict(h); hw['questions'] = json.loads(h['questions'] or '[]')
        subs = db.execute('SELECT * FROM submissions WHERE hw_id=?', (h['id'],)).fetchall()
        hw['submissions'] = {s['student_name']: {'score': s['score'], 'answers': json.loads(s['answers'] or '{}'), 'time': s['submitted_at']} for s in subs}
        homework.append(hw)
    chat = list(reversed([dict(c) for c in db.execute('SELECT * FROM chat WHERE room_code=? ORDER BY time DESC LIMIT 50', (code,)).fetchall()]))
    actlog = [dict(l) for l in db.execute('SELECT * FROM actlog WHERE room_code=? ORDER BY time DESC LIMIT 12', (code,)).fetchall()]
    media = [dict(m) for m in db.execute('SELECT * FROM media WHERE room_code=? ORDER BY created DESC', (code,)).fetchall()]
    ev = db.execute('SELECT * FROM live_events WHERE room_code=? AND active=1 ORDER BY created DESC LIMIT 1', (code,)).fetchone()
    active_event = None
    if ev:
        active_event = {**dict(ev), 'data': json.loads(ev['data'] or '{}'), 'answers': json.loads(ev['answers'] or '{}')}
    db.close()
    return jsonify({'ok': True, 'name': r['name'], 'color': r['color'],
                    'announcement': r['announcement'], 'disco': r['disco'],
                    'students': students, 'homework': homework, 'chat': chat,
                    'actLog': actlog, 'media': media, 'active_event': active_event, 'updated': r['updated']})

@app.route('/api/info')
def server_info():
    ip = get_local_ip(); db = get_db()
    rooms = db.execute('SELECT COUNT(*) FROM rooms').fetchone()[0]
    students = db.execute('SELECT COUNT(*) FROM students').fetchone()[0]
    db.close()
    return jsonify({'ok': True, 'ip': ip, 'rooms': rooms, 'students': students, 'railway': IS_RAILWAY})

if __name__ == '__main__':
    init_db()
    if IS_RAILWAY:
        print(f'BrightMind running on Railway port {PORT}')
    else:
        ip = get_local_ip()
        print('\n' + '='*55)
        print('  🌟  BrightMind is running!')
        print('='*55)
        print(f'\n  Teacher:  http://localhost:{PORT}/teacher')
        print(f'  Students: http://{ip}:{PORT}/student')
        print(f'\n  Share the student URL with parents!')
        print('  Press Ctrl+C to stop\n')
        threading.Timer(1.5, lambda: webbrowser.open(f'http://localhost:{PORT}/teacher')).start()
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
