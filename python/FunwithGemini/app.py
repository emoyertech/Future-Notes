import os, sqlite3, secrets, re
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, make_response, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "ultimate-marketplace-v3-key"

# --- CONFIGURATION ---
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- 1. DATABASE & AUTO-REPAIR ---
def get_db_connection():
    """Opens a fresh connection for every request."""
    conn = sqlite3.connect('marketplace.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes tables and fixes missing columns (Migrations)."""
    conn = get_db_connection()
    # Users table
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        username TEXT UNIQUE, 
        password TEXT,
        reset_token TEXT,
        role TEXT DEFAULT 'user')''')
    
    # Vehicles table
    conn.execute('''CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, make TEXT, model TEXT, year INTEGER, 
        price INTEGER, mileage INTEGER, image_path TEXT)''')

    # Ensure reset_token exists if db was created early
    cursor = conn.execute("PRAGMA table_info(users)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'reset_token' not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")

    conn.commit()
    conn.close()
    print("✅ Database ready.")

# --- 2. DECORATORS ---
def login_required(f):
    @wraps(f)  # CRITICAL: Prevents 'AssertionError' by preserving function names
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 3. AUTHENTICATION ROUTES ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handles account creation."""
    if request.method == 'POST':
        user = request.form['username']
        pwd = generate_password_hash(request.form['password'])
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user, pwd))
            conn.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return render_template('register.html', error="Username already taken.")
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (user,)).fetchone()
        conn.close()
        
        if row and check_password_hash(row['password'], pwd):
            session['user_id'] = row['id']
            session['username'] = row['username']
            session['role'] = row['role']
            return redirect(url_for('home'))
        
        return render_template('login.html', error="Invalid username or password.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- 4. MARKETPLACE ROUTES ---

@app.route('/')
@login_required
def home():
    """Main marketplace feed."""
    conn = get_db_connection()
    cars = conn.execute("SELECT * FROM vehicles ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('index.html', cars=cars)

@app.route('/create', methods=['POST'])
@login_required
def create_listing():
    """Saves a new vehicle listing."""
    file = request.files.get('photo')
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = get_db_connection()
        conn.execute('''INSERT INTO vehicles (user_id, make, model, year, price, mileage, image_path) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (session['user_id'], request.form['make'], request.form['model'], 
                      request.form['year'], request.form['price'], request.form['mileage'], filename))
        conn.commit()
        conn.close()
    return redirect(url_for('home'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- 5. STARTUP ---
if __name__ == '__main__':
    init_db()
    app.run(debug=True, use_reloader=False)
