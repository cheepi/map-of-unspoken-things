from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.db import get_db
from werkzeug.security import generate_password_hash
from functools import wraps

profile_bp = Blueprint('profile', __name__)

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('auth.login'))
        return view(*args, **kwargs)
    return wrapped_view

@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn, cur = get_db()
    user_id = session['user_id']

    if request.method == 'POST':
        username = request.form['username']
        profile_pic = request.form['profile_pic']
        password = request.form['password']

        if password:
            hashed_pw = generate_password_hash(password)
            cur.execute('UPDATE users SET username=%s, profile_pic=%s, password=%s WHERE id=%s', (username, profile_pic, hashed_pw, user_id))
        else:
            cur.execute('UPDATE users SET username=%s, profile_pic=%s WHERE id=%s', (username, profile_pic, user_id))
        
        conn.commit()
        session['username'] = username
        session['profile_pic'] = profile_pic  # session update
        return redirect(url_for('profile.profile'))

    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = dict(cur.fetchone())

    cur.execute("SELECT COUNT(*) as c FROM entries WHERE user_id = %s AND active = 1", (user_id,))
    user_data['entry_count'] = cur.fetchone()['c']

    cur.execute("""
        SELECT COUNT(DISTINCT t.id) as c
        FROM tags t
        JOIN entry_tags et ON t.id = et.tag_id
        JOIN entries e ON et.entry_id = e.id
        WHERE e.user_id = %s AND e.active = 1
    """, (user_id,))
    user_data['tag_count'] = cur.fetchone()['c']

    return render_template('profile.html', user=user_data)

@profile_bp.route('/archive_all_entries', methods=['POST'])
@login_required
def archive_all_entries():
    conn, cur = get_db()
    user_id = session['user_id']
    cur.execute('UPDATE entries SET active = 0 WHERE user_id = %s', (user_id,))
    conn.commit()
    return redirect(url_for('profile.profile'))