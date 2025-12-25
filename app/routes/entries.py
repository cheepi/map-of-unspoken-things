import re
import os
import requests
import base64
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from app.db import get_db

entries_bp = Blueprint('entries', __name__)

# spotify helper
def get_spotify_token():
    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    
    if not client_id or not client_secret: 
        return None
    
    auth_str = f"{client_id}:{client_secret}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {'Authorization': f'Basic {b64_auth}'}
    
    try:
        response = requests.post('https://accounts.spotify.com/api/token', headers=headers, data={'grant_type': 'client_credentials'}, timeout=5)
        if response.status_code == 200:
            return response.json().get('access_token')
    except Exception as e:
        print(f"Spotify Token Error: {e}")
    return None

def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('auth.login'))
        return view(*args, **kwargs)
    return wrapped_view

@entries_bp.route('/spotify_search')
def spotify_search():
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    token = get_spotify_token()
    if not token:
        return jsonify([])
    
    try:
        headers = {'Authorization': f'Bearer {token}'}        
        track_id_match = re.search(r'(?:track/|spotify:track:)([a-zA-Z0-9]+)', query)
        
        if track_id_match:
            track_id = track_id_match.group(1)
            
            resp = requests.get(
                f'https://api.spotify.com/v1/tracks/{track_id}', 
                headers=headers,
                timeout=5
            )
            
            if resp.status_code == 200:
                item = resp.json()
                img = ''
                if item['album']['images']:
                    img = item['album']['images'][0]['url']
                
                return jsonify([{
                    'id': item['id'],
                    'name': item['name'],
                    'artist': item['artists'][0]['name'],
                    'image': img,
                    'url': item['external_urls']['spotify'] 
                }])
            else:
                return jsonify([])
                
        else:
            resp = requests.get(
                'https://api.spotify.com/v1/search',
                headers=headers,
                params={'q': query, 'type': 'track', 'limit': 5},
                timeout=5
            )
            
            if resp.status_code != 200:
                return jsonify([])
            
            data = resp.json()
            tracks = []
            
            for item in data.get('tracks', {}).get('items', []):
                img = ''
                if item['album']['images']:
                    img = item['album']['images'][1]['url'] if len(item['album']['images']) > 1 else item['album']['images'][0]['url']
                
                tracks.append({
                    'id': item['id'],
                    'name': item['name'],
                    'artist': item['artists'][0]['name'],
                    'image': img,
                    'url': item['external_urls']['spotify'] 
                })
            
            return jsonify(tracks)
            
    except Exception as e:
        print(f"Spotify search error: {e}")
        return jsonify([])

@entries_bp.route('/entries')
@login_required
def my_entries():
    conn, cur = get_db()
    cur.execute('SELECT * FROM entries WHERE user_id = %s ORDER BY id DESC', (session['user_id'],))
    entries = cur.fetchall()
    return render_template('entries.html', entries=entries)

@entries_bp.route('/add_entry', methods=['GET', 'POST'])
@login_required
def add_entry():
    if request.method == 'POST':
        title = request.form['title']
        desc = request.form.get('description', '')
        img = request.form.get('image_url', '')
        gmaps = request.form.get('gmaps_link', '')
        
        spot_url = request.form.get('spotify_link', '')
        
        color = request.form.get('pin_color', '#ff4757')
        lat = request.form.get('latitude') 
        lon = request.form.get('longitude')
        tags = request.form.get('tags', '')

        try: 
            lat_val, lon_val = float(lat), float(lon)
        except: 
            lat_val, lon_val = None, None

        conn, cur = get_db()
        cur.execute('''
            INSERT INTO entries (user_id, title, description, image_url, gmaps_link, spotify_url, pin_color, latitude, longitude, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1) RETURNING id
        ''', (session['user_id'], title, desc, img, gmaps, spot_url, color, lat_val, lon_val))
        
        new_id = cur.fetchone()['id']
        
        if tags:
            for t in [x.replace(' ', '') for x in tags.split(',') if x.strip()]:
                cur.execute('SELECT id FROM tags WHERE name = %s', (t,))
                row = cur.fetchone()
                
                if row:
                    tid = row['id']
                else:
                    cur.execute('INSERT INTO tags (name) VALUES (%s) RETURNING id', (t,))
                    result = cur.fetchone() 
                    tid = result['id']
                
                cur.execute('INSERT INTO entry_tags (entry_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (new_id, tid))
        
        conn.commit()
        return redirect(url_for('main.home'))
    return render_template('add_entry.html')

@entries_bp.route('/edit_entry/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_entry(id):
    conn, cur = get_db()
    cur.execute('SELECT * FROM entries WHERE id = %s AND user_id = %s', (id, session['user_id']))
    entry = cur.fetchone()
    
    if not entry: return redirect(url_for('entries.my_entries'))

    cur.execute('SELECT t.name FROM tags t JOIN entry_tags et ON t.id = et.tag_id WHERE et.entry_id = %s', (id,))
    tags_list = [row['name'] for row in cur.fetchall()]
    existing_tags = ', '.join(tags_list)

    if request.method == 'POST':
        new_spot = request.form.get('spotify_link')
        
        if new_spot:
            spot_url = new_spot.split('?')[0]
        else:
            spot_url = entry['spotify_url']

        cur.execute('''
            UPDATE entries 
            SET title=%s, description=%s, image_url=%s, gmaps_link=%s, spotify_url=%s, pin_color=%s, latitude=%s, longitude=%s 
            WHERE id=%s
        ''', (
            request.form['title'], 
            request.form.get('description', ''), 
            request.form.get('image_url', ''), 
            request.form.get('gmaps_link', ''), 
            spot_url,  
            request.form.get('pin_color', '#ff4757'), 
            request.form.get('latitude'), 
            request.form.get('longitude'), 
            id
        ))
                
        cur.execute('DELETE FROM entry_tags WHERE entry_id = %s', (id,))
        tags = request.form.get('tags', '')
        if tags:
            for t in [x.replace(' ', '') for x in tags.split(',') if x.strip()]:
                cur.execute('SELECT id FROM tags WHERE name = %s', (t,))
                row = cur.fetchone()
                
                if row:
                    tid = row['id']
                else:
                    cur.execute('INSERT INTO tags (name) VALUES (%s) RETURNING id', (t,))
                    result = cur.fetchone()
                    tid = result['id']
                
                cur.execute('INSERT INTO entry_tags (entry_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (id, tid))

        conn.commit()
        return redirect(url_for('entries.my_entries'))
        
    return render_template('edit_entry.html', entry=entry, existing_tags=existing_tags)

@entries_bp.route('/archive_entry/<int:id>', methods=['POST'])
@login_required
def archive_entry(id):
    conn, cur = get_db()
    cur.execute('UPDATE entries SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = %s AND user_id = %s', (id, session['user_id']))
    conn.commit()
    return redirect(url_for('entries.my_entries'))

@entries_bp.route('/delete_entry_permanent/<int:id>', methods=['POST'])
@login_required
def delete_entry_permanent(id):
    conn, cur = get_db()
    cur.execute('DELETE FROM entry_tags WHERE entry_id = %s', (id,))
    cur.execute('DELETE FROM entries WHERE id = %s AND user_id = %s', (id, session['user_id']))
    conn.commit()
    return redirect(url_for('entries.my_entries'))