from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import get_db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn, cur = get_db()
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['profile_pic'] = user.get('profile_pic') 
            return redirect(url_for('main.home'))
        else:
            return render_template('login.html', error="Username atau password salah.")
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn, cur = get_db()
        
        cur.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cur.fetchone():
            return render_template('register.html', error="Username sudah dipakai.")
        
        hashed_pw = generate_password_hash(password)
        cur.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, hashed_pw))
        conn.commit()
        return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.home'))

@auth_bp.route('/delete_profile', methods=['POST'])
def delete_profile():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    conn, cur = get_db()
    uid = session['user_id']
    cur.execute('DELETE FROM entry_tags WHERE entry_id IN (SELECT id FROM entries WHERE user_id = %s)', (uid,))
    cur.execute('DELETE FROM entries WHERE user_id = %s', (uid,))
    cur.execute('DELETE FROM users WHERE id = %s', (uid,))
    conn.commit()
    session.clear()
    return redirect(url_for('main.home'))