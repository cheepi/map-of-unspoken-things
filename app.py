from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
import os
import re
from sqlalchemy import text
from sqlalchemy.orm import joinedload
from sqlalchemy import inspect

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, nullable=False)
    password = db.Column(db.String, nullable=False)
    profile_pic = db.Column(db.String)
    entries = db.relationship('Entry', backref='user', cascade='all, delete')

class Entry(db.Model):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String)
    gmaps_link = db.Column(db.String)
    pin_color = db.Column(db.String, default='#cccccc')
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    active = db.Column(db.Boolean, default=True)
    tags = db.relationship('Tag', secondary='entry_tags', backref='entries')

class Tag(db.Model):
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)

class EntryTag(db.Model):
    __tablename__ = 'entry_tags'
    entry_id = db.Column(db.Integer, db.ForeignKey('entries.id'), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), primary_key=True)

class UserSummary(db.Model):
    __tablename__ = 'user_summary'
    __table_args__ = {'extend_existing': True}
    user_id     = db.Column(db.Integer, primary_key=True)
    username    = db.Column(db.String)
    entry_count = db.Column(db.Integer)
    tag_count   = db.Column(db.Integer)

# Initialize DB
with app.app_context():
    db.create_all()
    db.session.execute(text('DROP TABLE IF EXISTS user_summary CASCADE;'))
    db.session.execute(text('''
        CREATE OR REPLACE VIEW user_summary AS
        SELECT
            u.id               AS user_id,
            u.username         AS username,
            COUNT(DISTINCT e.id)   AS entry_count,
            COUNT(DISTINCT t.id)   AS tag_count
        FROM users u
        LEFT JOIN entries e      ON u.id = e.user_id AND e.active = true
        LEFT JOIN entry_tags et  ON e.id = et.entry_id
        LEFT JOIN tags t         ON et.tag_id = t.id
        GROUP BY u.id;
    '''))
    db.session.commit()

# Auth
from functools import wraps

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper

# Utility
def extract_lat_lon_from_gmaps(url):
    m = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    m2 = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m2:
        return float(m2.group(1)), float(m2.group(2))
    return None, None

# Routes
@app.route('/')
def root():
    if 'user_id' not in session:
        return render_template('index.html')
    return redirect(url_for('home'))

@app.route('/register', methods=['GET','POST'])
def register():
    error = ''
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        if not username or not password:
            error = 'Username dan password tidak boleh kosong.'
        elif User.query.filter_by(username=username).first():
            error = 'Username sudah dipakai.'
        else:
            user = User(username=username, password=password)
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET','POST'])
def login():
    error = ''
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('home'))
        error = 'Username atau password salah.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('root'))

@app.route('/home')
@login_required
def home():
    # helper buat convert ORM obj → dict + nambahin user data
    def to_dict(e):
        base = {c.key: getattr(e, c.key) for c in inspect(e).mapper.column_attrs}
        # ambil username & profile_pic dari relationship user
        base['username']    = e.user.username
        base['profile_pic'] = e.user.profile_pic
        return base

    # ambil user sekarang
    current_user = User.query.get(session['user_id'])

    # Sidebar: entri user sendiri
    user_entries = (Entry.query
        .filter_by(user_id=current_user.id, active=True)
        .order_by(Entry.id.desc())
        .all()
    )

    # Semua entri (utama), eager‐load User biar nggak n+1 query
    q = request.args.get('q','').strip().lower()
    query_base = Entry.query.options(joinedload(Entry.user)).filter(Entry.active==True)

    if q:
        like = f"%{q}%"
        # join tag & user untuk search
        query_base = query_base.join(User).outerjoin(EntryTag).outerjoin(Tag).filter(
            (User.username.ilike(like))|
            (Entry.title.ilike(like))|
            (Entry.description.ilike(like))|
            (Tag.name.ilike(like))
        )
    all_entries = query_base.order_by(Entry.id.desc()).all()

    # Convert ke JSON list
    json_user_entries = [to_dict(e) for e in user_entries]
    json_all_entries  = [to_dict(e) for e in all_entries]

    return render_template('home.html',
        user_entries      = user_entries,
        json_user_entries = json_user_entries,
        all_entries       = all_entries,
        json_all_entries  = json_all_entries,
        username          = current_user.username,
        query             = q
    )

@app.route('/entries')
@login_required
def entries():
    ents = Entry.query.filter_by(user_id=session['user_id'])\
                      .order_by(Entry.id.desc()).all()
    json_list = [{c.key: getattr(e, c.key) for c in inspect(e).mapper.column_attrs} for e in ents]
    return render_template('entries.html',
                           entries=ents,
                           json_entries=json_list)

@app.route('/add_entry', methods=['GET','POST'])
@login_required
def add_entry():
    error = ''
    if request.method == 'POST':
        title = request.form['title'].strip()
        if not title:
            return render_template('add_entry.html', error='Judul wajib diisi.')
        ent = Entry(
            user_id    = session['user_id'],
            title      = title,
            description= request.form['description'].strip(),
            image_url  = request.form['image_url'].strip(),
            gmaps_link = request.form['gmaps_link'].strip(),
            pin_color  = request.form['pin_color'].strip() or '#cccccc'
        )
        lat, lon = extract_lat_lon_from_gmaps(ent.gmaps_link)
        if request.form.get('lat') and request.form.get('lon'):
            try:
                lat = float(request.form['lat']); lon = float(request.form['lon'])
            except: pass
        ent.latitude, ent.longitude = lat, lon

        for t in request.form['tags'].split(','):
            name = t.strip().lower()
            if not name: continue
            tag = Tag.query.filter_by(name=name).first() or Tag(name=name)
            ent.tags.append(tag)

        db.session.add(ent)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('add_entry.html', error='')

@app.route('/edit_entry/<int:id>', methods=['GET','POST'])
@login_required
def edit_entry(id):
    ent = Entry.query.get_or_404(id)
    if ent.user_id != session['user_id']:
        return redirect(url_for('entries'))
    existing_tags = ', '.join([t.name for t in ent.tags])

    if request.method == 'POST':
        title = request.form['title'].strip()
        if not title:
            return render_template('edit_entry.html', entry=ent, existing_tags=existing_tags, error='Judul wajib diisi.')
        ent.title       = title
        ent.description = request.form['description'].strip()
        ent.image_url   = request.form['image_url'].strip()
        ent.gmaps_link  = request.form['gmaps_link'].strip()
        ent.pin_color   = request.form['pin_color'].strip() or '#cccccc'
        lat, lon = extract_lat_lon_from_gmaps(ent.gmaps_link)
        if request.form.get('lat') and request.form.get('lon'):
            try:
                lat = float(request.form['lat']); lon = float(request.form['lon'])
            except: pass
        ent.latitude, ent.longitude = lat, lon

        ent.tags.clear()
        for name in request.form['tags'].split(','):
            n = name.strip().lower()
            if not n: continue
            tag = Tag.query.filter_by(name=n).first() or Tag(name=n)
            ent.tags.append(tag)

        db.session.commit()
        return redirect(url_for('entries'))

    return render_template('edit_entry.html', entry=ent, existing_tags=existing_tags, error='')
    

@app.route('/delete_entry/<int:id>', methods=['POST'])
@login_required
def delete_entry(id):
    entry = Entry.query.get_or_404(id)
    if entry.user_id == session['user_id']:
        entry.active = False
        entry.tags.clear()
        db.session.commit()
    return redirect(url_for('entries'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # pakai raw SQL untuk ambil user + summary dari VIEW
    row = db.session.execute(text('''
        SELECT
            u.id, u.username, u.password, u.profile_pic,
            us.entry_count, us.tag_count
        FROM users u
        JOIN user_summary us ON u.id = us.user_id
        WHERE u.id = :uid
    '''), {'uid': session['user_id']}).mappings().first()

    if not row:
        return redirect(url_for('logout'))

    error = ''
    if request.method == 'POST':
        new_username = request.form['username'].strip()
        new_password = request.form['password'].strip()
        new_pic_url  = request.form['profile_pic'].strip() or None

        # jika kosong, pakai yang lama
        final_username = new_username or row['username']
        final_password = new_password or row['password']

        # cek unique username
        if final_username != row['username'] and \
           db.session.query(User).filter_by(username=final_username).first():
            error = 'Username sudah dipakai.'
            return render_template('profile.html', user=row, error=error)

        # update users
        db.session.execute(text('''
            UPDATE users
               SET username    = :uname,
                   password    = :pwd,
                   profile_pic = :pic
             WHERE id = :uid
        '''), {
            'uname': final_username,
            'pwd':   final_password,
            'pic':   new_pic_url,
            'uid':   session['user_id']
        })
        db.session.commit()

        # ambil ulang data setelah update
        row = db.session.execute(text('''
            SELECT
                u.id, u.username, u.password, u.profile_pic,
                us.entry_count, us.tag_count
            FROM users u
            JOIN user_summary us ON u.id = us.user_id
            WHERE u.id = :uid
        '''), {'uid': session['user_id']}).mappings().first()

        popup_message = 'Profil berhasil diperbarui.'
        return render_template('profile.html',
                               user=row,
                               error='',
                               popup_message=popup_message)

    return render_template('profile.html', user=row, error=error)

@app.route('/delete_profile', methods=['POST'])
@login_required
def delete_profile():
    user = User.query.get(session['user_id'])
    db.session.delete(user)
    db.session.commit()
    session.clear()
    return redirect(url_for('root'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT',5000)))
