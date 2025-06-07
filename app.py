from flask import Flask, render_template, request, redirect, session, url_for, g
import sqlite3
import os
import re

app = Flask(__name__)
# simpan DB di /tmp (writable)
SRC_DB = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'database.db')
DATABASE = os.path.join('/tmp', 'database.db')


def get_db():
    if 'db' not in g:
        # copy db awal kalau belum ada
        if not os.path.exists(DATABASE):
            import shutil
            shutil.copy(SRC_DB, DATABASE)
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db



@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()

    # Tabel users
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            profile_pic TEXT
        );
    ''')

    # Tabel entries, dengan kolom active untuk soft‐delete
    db.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            image_url TEXT,
            gmaps_link TEXT,
            pin_color TEXT,
            latitude REAL,
            longitude REAL,
            active INTEGER NOT NULL DEFAULT 1,   -- 1 = aktif, 0 = dihapus/inaktif
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')

    # Tabel tags
    db.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
    ''')

    # Pivot entry_tags (many-to-many)
    db.execute('''
        CREATE TABLE IF NOT EXISTS entry_tags (
            entry_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (entry_id, tag_id),
            FOREIGN KEY (entry_id) REFERENCES entries(id),
            FOREIGN KEY (tag_id)   REFERENCES tags(id)
        );
    ''')

    # VIEW user_summary: hanya menghitung entri yg active = 1
    db.execute('''
        CREATE VIEW IF NOT EXISTS user_summary AS
        SELECT
            u.id               AS user_id,
            u.username         AS username,
            COUNT(DISTINCT e.id)   AS entry_count,
            COUNT(DISTINCT t.id)   AS tag_count
        FROM users u
        LEFT JOIN entries e      ON u.id = e.user_id
                                AND e.active = 1
        LEFT JOIN entry_tags et  ON e.id = et.entry_id
        LEFT JOIN tags t         ON et.tag_id = t.id
        GROUP BY u.id;
    ''')

    db.commit()


def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper


def extract_lat_lon_from_gmaps(url):
    """
    Ekstrak latitude/longitude dari Google Maps URL.
    Mendukung pola:
      1) https://www.google.com/maps/@LAT,LON,ZOOMz
      2) https://maps.google.com/?q=LAT,LON
    Jika gagal, kembalikan (None, None).
    """
    # Pola "/@LAT,LON,"
    m = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Pola "?q=LAT,LON"
    m2 = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m2:
        return float(m2.group(1)), float(m2.group(2))
    return None, None


@app.route('/')
def root():
    # Jika belum login, tampilkan landing page
    if 'user_id' not in session:
        return render_template('index.html')
    # Jika sudah login, redirect ke home
    return redirect(url_for('home'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = ''
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        if not username or not password:
            error = 'Username dan password tidak boleh kosong.'
        else:
            db = get_db()
            existing = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (username,)
            ).fetchone()
            if existing:
                error = 'Username sudah dipakai, coba yang lain.'
            else:
                db.execute(
                    'INSERT INTO users (username, password) VALUES (?, ?)',
                    (username, password)
                )
                db.commit()
                return redirect(url_for('login'))
    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        db = get_db()
        user = db.execute(
            'SELECT id, username FROM users WHERE username = ? AND password = ?',
            (username, password)
        ).fetchone()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('home'))
        else:
            error = 'Username atau password salah.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('root'))


@app.route('/home')
@login_required
def home():
    db = get_db()
    current_user_id = session['user_id']

    # Ambil entri user sendiri (sidebar), hanya yg active = 1
    user_entries = db.execute(
        'SELECT * FROM entries WHERE user_id = ? AND active = 1 ORDER BY id DESC',
        (current_user_id,)
    ).fetchall()

    # Search / Filter via parameter `q`
    q = request.args.get('q', '').strip().lower()
    if q:
        like_q = f'%{q}%'
        all_entries = db.execute(
            '''
            SELECT DISTINCT
                e.id, e.user_id,
                u.username,
                u.profile_pic,
                e.title, e.description, e.image_url,
                e.latitude, e.longitude, e.pin_color,
                e.gmaps_link
            FROM entries e
            JOIN users u ON e.user_id = u.id
            LEFT JOIN entry_tags et ON e.id = et.entry_id
            LEFT JOIN tags t ON et.tag_id = t.id
            WHERE e.active = 1
              AND (LOWER(u.username) LIKE ?
                   OR LOWER(e.title) LIKE ?
                   OR LOWER(e.description) LIKE ?
                   OR LOWER(t.name) LIKE ?)
            ORDER BY e.id DESC
            ''', (like_q, like_q, like_q, like_q)
        ).fetchall()
    else:
        all_entries = db.execute(
            '''
            SELECT
                e.id, e.user_id,
                u.username,
                u.profile_pic,
                e.title, e.description, e.image_url,
                e.latitude, e.longitude, e.pin_color,
                e.gmaps_link
            FROM entries e
            JOIN users u ON e.user_id = u.id
            WHERE e.active = 1
            ORDER BY e.id DESC
            '''
        ).fetchall()

    # Convert Row → dict untuk JSON
    user_ent_list = [dict(r) for r in user_entries]
    all_ent_list  = [dict(r) for r in all_entries]

    return render_template(
        'home.html',
        user_entries      = user_entries,
        json_user_entries = user_ent_list,
        all_entries       = all_entries,
        json_all_entries  = all_ent_list,
        username          = session['username'],
        query             = q
    )


@app.route('/entries')
@login_required
def entries():
    db = get_db()
    user_id = session['user_id']
    rows = db.execute(
        'SELECT * FROM entries WHERE user_id = ? ORDER BY id DESC',
        (user_id,)
    ).fetchall()

    # Convert Row → dict untuk JSON
    entry_list = [dict(r) for r in rows]
    return render_template(
        'entries.html',
        entries      = rows,
        json_entries = entry_list
    )


@app.route('/add_entry', methods=['GET', 'POST'])
@login_required
def add_entry():
    error = ''
    if request.method == 'POST':
        title       = request.form['title'].strip()
        description = request.form['description'].strip()
        image_url   = request.form['image_url'].strip()
        gmaps_link  = request.form['gmaps_link'].strip()
        pin_color   = request.form['pin_color'].strip() or '#cccccc'
        tags_raw    = request.form['tags'].strip()
        lat         = request.form['lat'].strip()
        lon         = request.form['lon'].strip()

        if not title:
            error = 'Judul wajib diisi.'
            return render_template('add_entry.html', error=error, existing_tags="", entry=None)

        # 1) Parsing pertama kali dari gmaps_link (jika ada)
        lat_val = None
        lon_val = None
        if gmaps_link:
            parsed = extract_lat_lon_from_gmaps(gmaps_link)
            if parsed[0] is not None and parsed[1] is not None:
                lat_val, lon_val = parsed

        # 2) Jika user mengisi lat/lon (klik peta), override
        if lat and lon:
            try:
                lat_val = float(lat)
                lon_val = float(lon)
            except ValueError:
                pass

        db = get_db()
        cursor = db.execute(
            '''INSERT INTO entries
               (user_id, title, description, image_url, gmaps_link, pin_color, latitude, longitude)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (session['user_id'], title, description, image_url, gmaps_link, pin_color, lat_val, lon_val)
        )
        entry_id = cursor.lastrowid

        # Proses tags: split by coma, simpan ke tags, lalu pivot
        if tags_raw:
            tag_names = [t.strip().lower() for t in tags_raw.split(',') if t.strip()]
            for tname in tag_names:
                row = db.execute('SELECT id FROM tags WHERE name = ?', (tname,)).fetchone()
                if row:
                    tag_id = row['id']
                else:
                    res = db.execute('INSERT INTO tags (name) VALUES (?)', (tname,))
                    tag_id = res.lastrowid
                db.execute('INSERT INTO entry_tags (entry_id, tag_id) VALUES (?, ?)', (entry_id, tag_id))

        db.commit()
        return redirect(url_for('home'))

    # GET
    return render_template('add_entry.html', error=error, existing_tags="", entry=None)


@app.route('/edit_entry/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_entry(id):
    db = get_db()
    user_id = session['user_id']
    entry = db.execute(
        'SELECT * FROM entries WHERE id = ? AND user_id = ?',
        (id, user_id)
    ).fetchone()
    if not entry:
        return redirect(url_for('entries'))

    # Ambil tags yang sudah terkait
    existing_tag_rows = db.execute(
        'SELECT t.name FROM tags t '
        'JOIN entry_tags et ON t.id = et.tag_id '
        'WHERE et.entry_id = ?',
        (id,)
    ).fetchall()
    existing_tags = ', '.join([r['name'] for r in existing_tag_rows])

    error = ''
    if request.method == 'POST':
        title       = request.form['title'].strip()
        description = request.form['description'].strip()
        image_url   = request.form['image_url'].strip()
        gmaps_link  = request.form['gmaps_link'].strip()
        pin_color   = request.form['pin_color'].strip() or '#cccccc'
        tags_raw    = request.form['tags'].strip()
        lat         = request.form['lat'].strip()
        lon         = request.form['lon'].strip()

        if not title:
            error = 'Judul wajib diisi.'
            return render_template('edit_entry.html',
                                   entry=entry,
                                   existing_tags=existing_tags,
                                   error=error)

        # 1) Parsing dari gmaps_link (jika ada)
        lat_val = None
        lon_val = None
        if gmaps_link:
            parsed = extract_lat_lon_from_gmaps(gmaps_link)
            if parsed[0] is not None and parsed[1] is not None:
                lat_val, lon_val = parsed

        # 2) Override jika user meng‐klik peta
        if lat and lon:
            try:
                lat_val = float(lat)
                lon_val = float(lon)
            except ValueError:
                pass

        # UPDATE entries
        db.execute(
            '''UPDATE entries
               SET title      = ?,
                   description= ?,
                   image_url  = ?,
                   gmaps_link = ?,
                   pin_color  = ?,
                   latitude   = ?,
                   longitude  = ?
               WHERE id = ?''',
            (title, description, image_url, gmaps_link, pin_color, lat_val, lon_val, id)
        )

        # Hapus pivot tags lama
        db.execute('DELETE FROM entry_tags WHERE entry_id = ?', (id,))

        # Proses tags baru
        if tags_raw:
            tag_names = [t.strip().lower() for t in tags_raw.split(',') if t.strip()]
            for tname in tag_names:
                row = db.execute('SELECT id FROM tags WHERE name = ?', (tname,)).fetchone()
                if row:
                    tag_id = row['id']
                else:
                    res = db.execute('INSERT INTO tags (name) VALUES (?)', (tname,))
                    tag_id = res.lastrowid
                db.execute('INSERT INTO entry_tags (entry_id, tag_id) VALUES (?, ?)', (id, tag_id))

        db.commit()
        return redirect(url_for('entries'))

    # GET: tampilkan form dengan prefill data
    return render_template('edit_entry.html',
                           entry=entry,
                           existing_tags=existing_tags,
                           error=error)


@app.route('/delete_entry/<int:id>', methods=['POST'])
@login_required
def delete_entry(id):
    db = get_db()
    user_id = session['user_id']
    # Soft‐delete: set active = 0
    db.execute('UPDATE entries SET active = 0 WHERE id = ? AND user_id = ?', (id, user_id))
    # Hapus pivot tags agar VIEW dan data tetap konsisten
    db.execute('DELETE FROM entry_tags WHERE entry_id = ?', (id,))
    db.commit()
    return redirect(url_for('entries'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    user_id = session['user_id']

    # Ambil data user plus ringkasan dari VIEW
    row = db.execute('''
        SELECT
            u.id, u.username, u.password, u.profile_pic,
            us.entry_count, us.tag_count
        FROM users u
        JOIN user_summary us ON u.id = us.user_id
        WHERE u.id = ?
    ''', (user_id,)).fetchone()

    if not row:
        return redirect(url_for('logout'))

    error = ''
    if request.method == 'POST':
        # Baca input, boleh dikosongkan
        new_username = request.form['username'].strip()
        new_password = request.form['password'].strip()
        new_pic_url  = request.form['profile_pic'].strip()

        # Jika user tidak mengisi username baru, pakai yang lama
        if not new_username:
            final_username = row['username']
        else:
            final_username = new_username

        # Cek unik hanya apabila user memang mengganti username
        if final_username != row['username']:
            exists = db.execute(
                'SELECT id FROM users WHERE username = ?',
                (final_username,)
            ).fetchone()
            if exists:
                error = 'Username sudah dipakai.'
                return render_template('profile.html', user=row, error=error)

        # Jika password dikosongkan, tetap pakai password lama
        final_password = new_password if new_password else row['password']

        db.execute(
            'UPDATE users SET username = ?, password = ?, profile_pic = ? WHERE id = ?',
            (final_username, final_password, new_pic_url or None, user_id)
        )
        db.commit()

        # Setelah update, ambil ulang data user (beserta VIEW user_summary)
        row = db.execute('''
            SELECT
                u.id, u.username, u.password, u.profile_pic,
                us.entry_count, us.tag_count
            FROM users u
            JOIN user_summary us ON u.id = us.user_id
            WHERE u.id = ?
        ''', (user_id,)).fetchone()

        popup_message = 'Profil berhasil diperbarui.'
        # Kirim juga popup_message ke template
        return render_template('profile.html', user=row, error='', popup_message=popup_message)

    return render_template('profile.html', user=row, error=error)


@app.route('/delete_profile', methods=['POST'])
@login_required
def delete_profile():
    db = get_db()
    user_id = session['user_id']
    # Hapus entry_tags → entries → users
    db.execute('DELETE FROM entry_tags WHERE entry_id IN (SELECT id FROM entries WHERE user_id = ?)', (user_id,))
    db.execute('DELETE FROM entries WHERE user_id = ?', (user_id,))
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    session.clear()
    return redirect(url_for('root'))


if __name__ == '__main__':
    with app.app_context():
        init_db()   # Pastikan tabel & VIEW dibuat jika belum ada
    app.run(debug=True, host='0.0.0.0', port=5000)
