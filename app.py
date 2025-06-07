from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
import os
import re

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
    db.session.execute('''
        CREATE VIEW IF NOT EXISTS user_summary AS
        SELECT
            u.id               AS user_id,
            u.username         AS username,
            COUNT(DISTINCT e.id)   AS entry_count,
            COUNT(DISTINCT t.id)   AS tag_count
        FROM users u
        LEFT JOIN entries e      ON u.id = e.user_id AND e.active = 1
        LEFT JOIN entry_tags et  ON e.id = et.entry_id
        LEFT JOIN tags t         ON et.tag_id = t.id
        GROUP BY u.id;
    ''')
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
    from sqlalchemy import inspect

    def to_dict(obj):
        return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}

    current_user = User.query.get(session['user_id'])
    user_entries = Entry.query.filter_by(user_id=current_user.id, active=True)\
                              .order_by(Entry.id.desc()).all()

    q = request.args.get('q','').strip().lower()
    if q:
        like = f"%{q}%"
        all_entries = Entry.query.join(User).outerjoin(EntryTag).outerjoin(Tag).filter(
            Entry.active==True,
            (User.username.ilike(like))|
            (Entry.title.ilike(like))|
            (Entry.description.ilike(like))|
            (Tag.name.ilike(like))
        ).order_by(Entry.id.desc()).all()
    else:
        all_entries = Entry.query.filter_by(active=True).order_by(Entry.id.desc()).all()

    json_user_entries = [to_dict(e) for e in user_entries]
    json_all_entries  = [to_dict(e) for e in all_entries]

    return render_template('home.html',
        user_entries=user_entries,
        json_user_entries=json_user_entries,
        all_entries=all_entries,
        json_all_entries=json_all_entries,
        username=current_user.username,
        query=q
    )

@app.route('/entries')
@login_required
def entries():
    current_user = User.query.get(session['user_id'])
    entries = Entry.query.filter_by(user_id=current_user.id)\
                        .order_by(Entry.id.desc()).all()
    return render_template('entries.html', entries=entries)

@app.route('/add_entry', methods=['GET','POST'])
@login_required
def add_entry():
    error = ''
    if request.method == 'POST':
        title = request.form['title'].strip()
        if not title:
            error = 'Judul wajib diisi.'
            return render_template('add_entry.html', error=error)

        entry = Entry(
            user_id=session['user_id'],
            title=title,
            description=request.form['description'].strip(),
            image_url=request.form['image_url'].strip(),
            gmaps_link=request.form['gmaps_link'].strip(),
            pin_color=request.form['pin_color'].strip() or '#cccccc'
        )

        # parse dari gmaps_link
        lat_val, lon_val = extract_lat_lon_from_gmaps(entry.gmaps_link)
        # override kalau ada klik peta (field lat/lon)
        lat = request.form.get('lat','').strip()
        lon = request.form.get('lon','').strip()
        if lat and lon:
            try:
                lat_val, lon_val = float(lat), float(lon)
            except ValueError:
                pass
        entry.latitude, entry.longitude = lat_val, lon_val

        # proses tags
        tags_raw = request.form['tags'].split(',')
        for t in tags_raw:
            name = t.strip().lower()
            if name:
                tag = Tag.query.filter_by(name=name).first() or Tag(name=name)
                entry.tags.append(tag)

        db.session.add(entry)
        db.session.commit()
        return redirect(url_for('home'))

    return render_template('add_entry.html', error=error)

@app.route('/edit_entry/<int:id>', methods=['GET','POST'])
@login_required
def edit_entry(id):
    entry = Entry.query.get_or_404(id)
    if entry.user_id != session['user_id']:
        return redirect(url_for('entries'))

    error = ''
    if request.method == 'POST':
        title = request.form['title'].strip()
        if not title:
            error = 'Judul wajib diisi.'
            return render_template('edit_entry.html',
                                   entry=entry,
                                   existing_tags=', '.join([t.name for t in entry.tags]),
                                   error=error)

        entry.title       = title
        entry.description = request.form['description'].strip()
        entry.image_url   = request.form['image_url'].strip()
        entry.gmaps_link  = request.form['gmaps_link'].strip()
        entry.pin_color   = request.form['pin_color'].strip() or '#cccccc'

        # parse dari gmaps_link
        lat_val, lon_val = extract_lat_lon_from_gmaps(entry.gmaps_link)
        # override kalau ada klik peta
        lat = request.form.get('lat','').strip()
        lon = request.form.get('lon','').strip()
        if lat and lon:
            try:
                lat_val, lon_val = float(lat), float(lon)
            except ValueError:
                pass
        entry.latitude, entry.longitude = lat_val, lon_val

        # update tags
        entry.tags.clear()
        for name in request.form['tags'].split(','):
            n = name.strip().lower()
            if n:
                tag = Tag.query.filter_by(name=n).first() or Tag(name=n)
                entry.tags.append(tag)

        db.session.commit()
        return redirect(url_for('entries'))

    existing_tags = ', '.join([t.name for t in entry.tags])
    return render_template('edit_entry.html',
                           entry=entry,
                           existing_tags=existing_tags,
                           error=error)

@app.route('/delete_entry/<int:id>', methods=['POST'])
@login_required
def delete_entry(id):
    entry = Entry.query.get_or_404(id)
    if entry.user_id == session['user_id']:
        # soft-delete
        entry.active = False
        # clear pivot di entry_tags
        entry.tags.clear()
        db.session.commit()
    return redirect(url_for('entries'))

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    user_id = session['user_id']
    # ambil ringkasan dari view
    summary = UserSummary.query.filter_by(user_id=user_id).first()
    if not summary:
        return redirect(url_for('logout'))

    user = User.query.get(user_id)
    error = ''
    if request.method == 'POST':
        new_username = request.form['username'].strip()
        new_password = request.form['password'].strip()
        new_pic     = request.form['profile_pic'].strip() or None

        # cek unik username
        if new_username and new_username != user.username and User.query.filter_by(username=new_username).first():
            error = 'Username sudah dipakai.'
        else:
            user.username   = new_username or user.username
            user.password   = new_password or user.password
            user.profile_pic = new_pic
            db.session.commit()

            # refresh summary setelah update
            summary = UserSummary.query.filter_by(user_id=user_id).first()
            popup_message = 'profil berhasil diperbarui.'
            return render_template('profile.html',
                                   user=user,
                                   entry_count=summary.entry_count,
                                   tag_count=summary.tag_count,
                                   error='',
                                   popup_message=popup_message)

    return render_template('profile.html',
                           user=user,
                           entry_count=summary.entry_count,
                           tag_count=summary.tag_count,
                           error=error)

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
