from flask import Flask, request, jsonify, send_from_directory, session
import sqlite3
import os
from datetime import datetime
import hashlib
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Change this in production
UPLOAD_DIR = "uploads"
DATABASE = "chat_app.db"

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mp3', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_icon(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    icons = {
        'pdf': '📄', 'txt': '📄', 'doc': '📄', 'docx': '📄',
        'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️', 'gif': '🖼️',
        'mp4': '🎥', 'mp3': '🎵', 'zip': '📦', 'rar': '📦'
    }
    return icons.get(ext, '📁')

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Rooms table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')
    
    # Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            room_id INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            message_type TEXT DEFAULT 'text',
            FOREIGN KEY (room_id) REFERENCES rooms (id)
        )
    ''')
    
    # Create default room
    cursor.execute('SELECT COUNT(*) FROM rooms WHERE name = "General"')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO rooms (name) VALUES ("General")')
    
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@app.route("/", methods=["GET"])
def index():
    return send_from_directory(".", "index.html")

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password required"}), 400
    
    if len(username) < 3 or len(password) < 4:
        return jsonify({"status": "error", "message": "Username min 3 chars, password min 4 chars"}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                      (username, hash_password(password)))
        conn.commit()
        session['username'] = username
        return jsonify({"status": "success", "message": "Registration successful"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "Username already exists"}), 400
    finally:
        conn.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT password FROM users WHERE username = ?', (username,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0] == hash_password(password):
        session['username'] = username
        return jsonify({"status": "success", "message": "Login successful"})
    else:
        return jsonify({"status": "error", "message": "Invalid username or password"}), 401

@app.route("/logout", methods=["POST"])
def logout():
    session.pop('username', None)
    return jsonify({"status": "success", "message": "Logged out"})

@app.route("/check_auth", methods=["GET"])
def check_auth():
    if 'username' in session:
        return jsonify({"authenticated": True, "username": session['username']})
    return jsonify({"authenticated": False})

@app.route("/rooms", methods=["GET"])
def get_rooms():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM rooms ORDER BY name')
    rooms = [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(rooms)

@app.route("/create_room", methods=["POST"])
def create_room():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    
    data = request.json
    room_name = data.get('name', '').strip()
    
    if not room_name or len(room_name) < 3:
        return jsonify({"status": "error", "message": "Room name must be at least 3 characters"}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('INSERT INTO rooms (name) VALUES (?)', (room_name,))
        conn.commit()
        return jsonify({"status": "success", "message": "Room created successfully"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "Room name already exists"}), 400
    finally:
        conn.close()

@app.route("/messages/<int:room_id>", methods=["GET"])
def get_messages(room_id):
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT username, message, timestamp, file_path, message_type 
        FROM messages 
        WHERE room_id = ? 
        ORDER BY timestamp ASC
    ''', (room_id,))
    
    messages = []
    for row in cursor.fetchall():
        messages.append({
            "username": row[0],
            "message": row[1],
            "timestamp": row[2],
            "file_path": row[3],
            "message_type": row[4]
        })
    
    conn.close()
    return jsonify(messages)

@app.route("/send", methods=["POST"])
def send_message():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    
    data = request.json
    message = data.get('message', '').strip()
    room_id = data.get('room_id', 1)
    
    if not message:
        return jsonify({"status": "error", "message": "Message cannot be empty"}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (username, message, room_id, timestamp) 
        VALUES (?, ?, ?, ?)
    ''', (session['username'], message, room_id, get_timestamp()))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success"})

@app.route("/upload", methods=["POST"])
def upload_file():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file selected"}), 400
    
    file = request.files['file']
    room_id = request.form.get('room_id', 1)
    
    if file.filename == '':
        return jsonify({"status": "error", "message": "No file selected"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"status": "error", "message": "File type not allowed"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to avoid conflicts
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{int(datetime.now().timestamp())}{ext}"
        file_path = os.path.join(UPLOAD_DIR, filename)
        file.save(file_path)
        
        file_url = f"/files/{filename}"
        file_icon = get_file_icon(filename)
        message = f"{file_icon} <a href='{file_url}' target='_blank' class='file-link'>{file.filename}</a>"
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (username, message, room_id, timestamp, file_path, message_type) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session['username'], message, room_id, get_timestamp(), filename, 'file'))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "file_url": file_url})

@app.route("/files/<filename>")
def download_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000, debug=True)