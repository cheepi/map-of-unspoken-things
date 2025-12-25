from flask import Blueprint, render_template, request, session
from app.db import get_db
import datetime

main_bp = Blueprint('main', __name__)

@main_bp.route('/', methods=['GET'])
def home():
    conn, cur = get_db()
    
    now = datetime.datetime.now().hour
    if 5 <= now < 11: greeting = "Pagi! Udah ngopi?"
    elif 11 <= now < 15: greeting = "Siang. Panas ya di situ?"
    elif 15 <= now < 18: greeting = "Sore! Makan dulu enak tuh."
    else: greeting = "Malem!"

    #stats
    cur.execute("""
        SELECT 
            COUNT(*) as total_stories, 
            COUNT(DISTINCT user_id) as total_writers 
        FROM entries 
        WHERE active = 1
    """)
    stats = cur.fetchone()
    
    total_stories = stats['total_stories']
    total_writers = stats['total_writers']

    #data entries and tags
    query = request.args.get('q', '').strip()
    
    if query:
        #search
        search_term = f"%{query}%"
        cur.execute('''
            SELECT e.*, u.username, u.profile_pic,
            string_agg(t.name, ',') as tags_list
            FROM entries e 
            JOIN users u ON e.user_id = u.id 
            LEFT JOIN entry_tags et ON e.id = et.entry_id
            LEFT JOIN tags t ON et.tag_id = t.id
            WHERE e.active = 1 AND (
                e.title ILIKE %s OR 
                e.description ILIKE %s OR
                u.username ILIKE %s OR
                t.name ILIKE %s
            )
            GROUP BY e.id, u.id, u.username, u.profile_pic
            ORDER BY e.created_at DESC
        ''', (search_term, search_term, search_term, search_term))
    else:
        #home
        cur.execute('''
            SELECT e.*, u.username, u.profile_pic,
            string_agg(t.name, ',') as tags_list
            FROM entries e 
            JOIN users u ON e.user_id = u.id 
            LEFT JOIN entry_tags et ON e.id = et.entry_id
            LEFT JOIN tags t ON et.tag_id = t.id
            WHERE e.active = 1
            GROUP BY e.id, u.id, u.username, u.profile_pic
            ORDER BY e.created_at DESC
        ''')
    
    all_entries = cur.fetchall()

    #sidebar
    user_entries = []
    if 'user_id' in session:
        cur.execute('SELECT * FROM entries WHERE user_id = %s AND active = 1 ORDER BY id DESC', (session['user_id'],))
        user_entries = cur.fetchall()

    return render_template('home.html', 
                           all_entries=all_entries, 
                           json_all_entries=all_entries, 
                           user_entries=user_entries, 
                           query=query,
                           greeting=greeting,
                           total_stories=total_stories,
                           total_writers=total_writers)