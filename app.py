from flask import Flask, jsonify, request
import os
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from datetime import datetime

app = Flask(__name__)
CORS(app)

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'event_management'),
    'port': int(os.getenv('DB_PORT', '3306')),
    'autocommit': False,
}


def get_db():
    db = mysql.connector.connect(**DB_CONFIG)
    if not db.is_connected():
        raise Error('Database connection failed')
    return db


def fetch_one(query, params=()):
    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute(query, params)
        return cur.fetchone()
    finally:
        cur.close()
        db.close()


def fetch_all(query, params=()):
    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()
        db.close()


@app.get('/')
def home():
    return 'EventFlow Backend is Running!'


@app.get('/health')
def health():
    try:
        db = get_db()
        db.close()
        return jsonify({'status': 'success', 'backend': 'running', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'error', 'backend': 'running', 'database': 'disconnected', 'message': str(e)}), 500


@app.get('/users')
def get_users():
    try:
        users = fetch_all('SELECT user_id,name,email,role,phone,created_at FROM users ORDER BY user_id DESC')
        return jsonify(users)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.post('/register')
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    phone = str(data.get('phone', '')).strip()
    role = str(data.get('role', 'student')).strip().lower()

    if not name or not email or not password:
        return jsonify({'message': 'Name, email and password are required'}), 400
    if role not in ('student', 'admin'):
        role = 'student'

    try:
        db = get_db()
        cur = db.cursor()
        cur.execute('SELECT user_id FROM users WHERE email=%s', (email,))
        if cur.fetchone():
            cur.close(); db.close()
            return jsonify({'message': 'Email already registered'}), 409

        cur.execute(
            'INSERT INTO users (name,email,password,role,phone) VALUES (%s,%s,%s,%s,%s)',
            (name, email, password, role, phone),
        )
        user_id = cur.lastrowid
        db.commit()
        cur.close(); db.close()
        return jsonify({'message': 'Registration successful', 'user_id': user_id, 'role': role}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.post('/login')
def login():
    data = request.get_json(silent=True) or {}

    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))

    if not email or not password:
        return jsonify({
            'message': 'Email and password are required'
        }), 400

    try:
        user = fetch_one(
            '''
            SELECT user_id, name, email, role, phone, created_at
            FROM users
            WHERE email=%s AND password=%s
            ''',
            (email, password)
        )

        if not user:
            return jsonify({
                'message': 'Invalid email or password'
            }), 401

        return jsonify({
            'message': 'Login successful',
            'user': user
        }), 200

    except Exception as e:
        return jsonify({
            'message': str(e)
        }), 500


@app.get('/users/<int:user_id>')
def get_user(user_id):
    try:
        user = fetch_one(
            'SELECT user_id,name,email,role,phone,created_at FROM users WHERE user_id=%s',
            (user_id,),
        )
        if not user:
            return jsonify({'message': 'User not found'}), 404
        return jsonify(user)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.put('/users/<int:user_id>')
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    phone = str(data.get('phone', '')).strip()
    if not name:
        return jsonify({'message': 'Name is required'}), 400
    try:
        db = get_db(); cur = db.cursor()
        cur.execute('UPDATE users SET name=%s, phone=%s WHERE user_id=%s', (name, phone, user_id))
        db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Profile updated'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.post('/forgot-password')
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()
    if not email:
        return jsonify({'message': 'Email is required'}), 400
    try:
        user = fetch_one('SELECT user_id FROM users WHERE email=%s', (email,))
        if not user:
            return jsonify({'message': 'Email not found'}), 404
        return jsonify({'message': 'Password reset request accepted'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/events')
def get_events():
    try:
        rows = fetch_all('''
            SELECT e.event_id,e.title,e.description,e.venue,e.event_date,e.event_time,
                   e.available_seats,e.created_by,e.created_at,
                   u.name AS creator_name
            FROM events e LEFT JOIN users u ON e.created_by=u.user_id
            ORDER BY e.event_date ASC,e.event_time ASC
        ''')
        for row in rows:
            if row.get('event_date'):
                row['event_date'] = row['event_date'].isoformat()
            if row.get('event_time'):
                row['event_time'] = str(row['event_time'])
            if row.get('created_at'):
                row['created_at'] = row['created_at'].isoformat()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.post('/events')
def create_event():
    data = request.get_json(silent=True) or {}
    title = str(data.get('title', '')).strip()
    description = str(data.get('description', '')).strip()
    venue = str(data.get('venue', '')).strip()
    event_date = data.get('event_date')
    event_time = data.get('event_time')
    seats = int(data.get('available_seats', 100))
    created_by = data.get('created_by')

    if not title or not event_date or not event_time:
        return jsonify({'message': 'Title, date and time are required'}), 400
    try:
        db = get_db(); cur = db.cursor()
        cur.execute('''INSERT INTO events
            (title,description,venue,event_date,event_time,available_seats,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (title, description, venue, event_date, event_time, seats, created_by))
        event_id = cur.lastrowid
        db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Event created', 'event_id': event_id}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/events/<int:event_id>')
def get_event(event_id):
    try:
        row = fetch_one('SELECT * FROM events WHERE event_id=%s', (event_id,))
        if not row:
            return jsonify({'message': 'Event not found'}), 404
        if row.get('event_date'): row['event_date'] = row['event_date'].isoformat()
        if row.get('event_time'): row['event_time'] = str(row['event_time'])
        if row.get('created_at'): row['created_at'] = row['created_at'].isoformat()
        return jsonify(row)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.put('/events/<int:event_id>')
def update_event(event_id):
    data = request.get_json(silent=True) or {}
    fields = ['title','description','venue','event_date','event_time','available_seats']
    values = [data.get(f) for f in fields]
    if not data.get('title') or not data.get('event_date') or not data.get('event_time'):
        return jsonify({'message': 'Title, date and time are required'}), 400
    try:
        db = get_db(); cur = db.cursor()
        cur.execute('''UPDATE events SET title=%s,description=%s,venue=%s,event_date=%s,
                       event_time=%s,available_seats=%s WHERE event_id=%s''', (*values, event_id))
        db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Event updated'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.delete('/events/<int:event_id>')
def delete_event(event_id):
    try:
        db = get_db(); cur = db.cursor()
        cur.execute('DELETE FROM events WHERE event_id=%s', (event_id,))
        db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Event deleted'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/events/search')
def search_events():
    q = str(request.args.get('q', '')).strip()
    try:
        rows = fetch_all('''SELECT * FROM events
                            WHERE title LIKE %s OR description LIKE %s OR venue LIKE %s
                            ORDER BY event_date ASC''', (f'%{q}%', f'%{q}%', f'%{q}%'))
        for row in rows:
            if row.get('event_date'): row['event_date'] = row['event_date'].isoformat()
            if row.get('event_time'): row['event_time'] = str(row['event_time'])
        return jsonify(rows)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.post('/registrations')
def register_event():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    event_id = data.get('event_id')
    if not user_id or not event_id:
        return jsonify({'message': 'user_id and event_id are required'}), 400
    try:
        db = get_db(); cur = db.cursor(dictionary=True)
        cur.execute('SELECT available_seats FROM events WHERE event_id=%s', (event_id,))
        event = cur.fetchone()
        if not event:
            cur.close(); db.close(); return jsonify({'message': 'Event not found'}), 404
        if int(event['available_seats']) <= 0:
            cur.close(); db.close(); return jsonify({'message': 'No seats available'}), 409
        cur.execute('SELECT registration_id FROM registrations WHERE user_id=%s AND event_id=%s', (user_id,event_id))
        if cur.fetchone():
            cur.close(); db.close(); return jsonify({'message': 'Already registered'}), 409
        cur.execute('INSERT INTO registrations (user_id,event_id) VALUES (%s,%s)', (user_id,event_id))
        registration_id = cur.lastrowid
        cur.execute('UPDATE events SET available_seats=available_seats-1 WHERE event_id=%s', (event_id,))
        db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Registration successful', 'registration_id': registration_id}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/registrations/user/<int:user_id>')
def user_registrations(user_id):
    try:
        rows = fetch_all('''SELECT r.registration_id,r.registration_date,r.status,
                           e.event_id,e.title,e.description,e.venue,e.event_date,e.event_time
                           FROM registrations r JOIN events e ON r.event_id=e.event_id
                           WHERE r.user_id=%s ORDER BY e.event_date ASC''', (user_id,))
        for row in rows:
            if row.get('event_date'): row['event_date'] = row['event_date'].isoformat()
            if row.get('event_time'): row['event_time'] = str(row['event_time'])
            if row.get('registration_date'): row['registration_date'] = row['registration_date'].isoformat()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.delete('/registrations/<int:registration_id>')
def cancel_registration(registration_id):
    try:
        db = get_db(); cur = db.cursor(dictionary=True)
        cur.execute('SELECT event_id,status FROM registrations WHERE registration_id=%s', (registration_id,))
        reg = cur.fetchone()
        if not reg:
            cur.close(); db.close(); return jsonify({'message': 'Registration not found'}), 404
        if reg['status'] == 'cancelled':
            cur.close(); db.close(); return jsonify({'message': 'Already cancelled'})
        cur.execute("UPDATE registrations SET status='cancelled' WHERE registration_id=%s", (registration_id,))
        cur.execute('UPDATE events SET available_seats=available_seats+1 WHERE event_id=%s', (reg['event_id'],))
        db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Registration cancelled'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/events/<int:event_id>/participants')
def event_participants(event_id):
    try:
        rows = fetch_all('''SELECT r.registration_id,r.status,r.registration_date,
                           u.user_id,u.name,u.email,u.phone
                           FROM registrations r JOIN users u ON r.user_id=u.user_id
                           WHERE r.event_id=%s ORDER BY u.name''', (event_id,))
        for row in rows:
            if row.get('registration_date'): row['registration_date'] = row['registration_date'].isoformat()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/notifications/<int:user_id>')
def get_notifications(user_id):
    try:
        rows = fetch_all('SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC', (user_id,))
        for row in rows:
            if row.get('created_at'): row['created_at'] = row['created_at'].isoformat()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.post('/notifications')
def create_notification():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id'); title = data.get('title'); message = data.get('message')
    if not user_id or not title or not message:
        return jsonify({'message': 'user_id, title and message are required'}), 400
    try:
        db = get_db(); cur = db.cursor()
        cur.execute('INSERT INTO notifications (user_id,title,message) VALUES (%s,%s,%s)', (user_id,title,message))
        nid = cur.lastrowid; db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Notification created', 'notification_id': nid}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.put('/notifications/<int:notification_id>/read')
def mark_notification_read(notification_id):
    try:
        db = get_db(); cur = db.cursor()
        cur.execute('UPDATE notifications SET is_read=TRUE WHERE notification_id=%s', (notification_id,))
        db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Notification marked as read'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.post('/feedback')
def create_feedback():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id'); event_id = data.get('event_id'); rating = int(data.get('rating', 0)); comment = data.get('comment','')
    if not user_id or not event_id or rating < 1 or rating > 5:
        return jsonify({'message': 'Valid user_id, event_id and rating 1-5 are required'}), 400
    try:
        db = get_db(); cur = db.cursor()
        cur.execute('INSERT INTO feedback (user_id,event_id,rating,comment) VALUES (%s,%s,%s,%s)', (user_id,event_id,rating,comment))
        fid = cur.lastrowid; db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Feedback submitted', 'feedback_id': fid}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/feedback/event/<int:event_id>')
def get_feedback(event_id):
    try:
        rows = fetch_all('''SELECT f.feedback_id,f.rating,f.comment,f.created_at,u.name
                           FROM feedback f JOIN users u ON f.user_id=u.user_id
                           WHERE f.event_id=%s ORDER BY f.created_at DESC''', (event_id,))
        for row in rows:
            if row.get('created_at'): row['created_at'] = row['created_at'].isoformat()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.post('/reminders')
def create_reminder():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id'); event_id = data.get('event_id'); reminder_time = data.get('reminder_time')
    if not user_id or not event_id or not reminder_time:
        return jsonify({'message': 'user_id, event_id and reminder_time are required'}), 400
    try:
        db = get_db(); cur = db.cursor()
        cur.execute('INSERT INTO reminders (user_id,event_id,reminder_time) VALUES (%s,%s,%s)', (user_id,event_id,reminder_time))
        rid = cur.lastrowid; db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Reminder saved', 'reminder_id': rid}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/reminders/<int:user_id>')
def get_reminders(user_id):
    try:
        rows = fetch_all('''SELECT r.*,e.title,e.event_date,e.event_time
                           FROM reminders r JOIN events e ON r.event_id=e.event_id
                           WHERE r.user_id=%s ORDER BY r.reminder_time ASC''', (user_id,))
        for row in rows:
            for key in ('reminder_time','created_at'):
                if row.get(key): row[key] = row[key].isoformat()
            if row.get('event_date'): row['event_date'] = row['event_date'].isoformat()
            if row.get('event_time'): row['event_time'] = str(row['event_time'])
        return jsonify(rows)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.post('/verifications')
def create_verification():
    data = request.get_json(silent=True) or {}
    event_id = data.get('event_id'); admin_id = data.get('admin_id'); status = data.get('status','pending'); remarks = data.get('remarks','')
    if not event_id or not admin_id:
        return jsonify({'message': 'event_id and admin_id are required'}), 400
    if status not in ('pending','approved','rejected'): status = 'pending'
    try:
        db = get_db(); cur = db.cursor()
        cur.execute('INSERT INTO event_verifications (event_id,admin_id,status,remarks,verified_at) VALUES (%s,%s,%s,%s,%s)',
                    (event_id,admin_id,status,remarks,datetime.now() if status != 'pending' else None))
        vid = cur.lastrowid; db.commit(); cur.close(); db.close()
        return jsonify({'message': 'Verification saved', 'verification_id': vid}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/verifications')
def get_verifications():
    try:
        rows = fetch_all('''SELECT v.*,e.title,u.name AS admin_name
                           FROM event_verifications v
                           JOIN events e ON v.event_id=e.event_id
                           JOIN users u ON v.admin_id=u.user_id
                           ORDER BY v.verification_id DESC''')
        for row in rows:
            if row.get('verified_at'): row['verified_at'] = row['verified_at'].isoformat()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.get('/admin/dashboard')
def admin_dashboard():
    try:
        total_events = fetch_one('SELECT COUNT(*) AS count FROM events')['count']
        total_users = fetch_one('SELECT COUNT(*) AS count FROM users')['count']
        registrations = fetch_one("SELECT COUNT(*) AS count FROM registrations WHERE status='registered'")['count']
        today_events = fetch_one('SELECT COUNT(*) AS count FROM events WHERE event_date=CURDATE()')['count']
        return jsonify({
            'total_events': total_events,
            'total_users': total_users,
            'registrations': registrations,
            'today_events': today_events,
        })
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.route('/admin/reports')
def admin_reports():
    try:
        total_events_result = fetch_all(
            "SELECT COUNT(*) AS total FROM events"
        )
        total_events = total_events_result[0]['total']

        total_registrations_result = fetch_all(
            "SELECT COUNT(*) AS total FROM registrations "
            "WHERE status = 'registered'"
        )
        total_registrations = total_registrations_result[0]['total']

        completed_events_result = fetch_all(
            "SELECT COUNT(*) AS total FROM events "
            "WHERE event_date < CURDATE()"
        )
        completed_events = completed_events_result[0]['total']

        cancelled_result = fetch_all(
            "SELECT COUNT(*) AS total FROM registrations "
            "WHERE status = 'cancelled'"
        )
        cancelled = cancelled_result[0]['total']

        popular = fetch_all("""
            SELECT
                e.title,
                COUNT(r.registration_id) AS registrations
            FROM events e
            LEFT JOIN registrations r
                ON e.event_id = r.event_id
                AND r.status = 'registered'
            GROUP BY e.event_id, e.title
            ORDER BY registrations DESC
            LIMIT 5
        """)

        monthly = fetch_all("""
            SELECT
                DATE_FORMAT(registration_date, '%Y-%m') AS month,
                COUNT(*) AS registrations
            FROM registrations
            WHERE status = 'registered'
            GROUP BY DATE_FORMAT(registration_date, '%Y-%m')
            ORDER BY month DESC
            LIMIT 6
        """)

        return jsonify({
            'total_events': total_events,
            'total_registrations': total_registrations,
            'completed_events': completed_events,
            'cancelled': cancelled,
            'popular_events': popular,
            'monthly_registrations': monthly
        })

    except Exception as e:
        return jsonify({
            'message': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
