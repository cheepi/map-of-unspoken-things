import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import g

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(
            dbname=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASS'),
            host=os.environ.get('DB_HOST'),
            port=os.environ.get('DB_PORT')
        )
        # RealDictCursor biar hasil query bisa dipanggil pake nama kolom (ex: user['username'])
        g.cursor = g.db.cursor(cursor_factory=RealDictCursor)
    return g.db, g.cursor

def close_db(e=None):
    db = g.pop('db', None)
    cursor = g.pop('cursor', None)
    
    if cursor is not None:
        cursor.close()
    if db is not None:
        db.close()