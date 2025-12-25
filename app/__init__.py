from flask import Flask
from dotenv import load_dotenv
import os
from .db import close_db

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'kunci_rahasia_default_ganti_nanti')

    app.teardown_appcontext(close_db)

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.entries import entries_bp
    from app.routes.profile import profile_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(entries_bp)
    app.register_blueprint(profile_bp)

    return app