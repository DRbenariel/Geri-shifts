"""
app.py — Flask application factory.

Run dev:   python frontend/server.py
Run prod:  gunicorn 'frontend.app:create_app()' --bind 0.0.0.0:$PORT
"""
import os
from datetime import timedelta

from flask import Flask, session, send_from_directory
from flask_cors import CORS

from .config import HERE
from .routes import register_blueprints
from .auth import install_guards


def create_app():
    app = Flask(__name__, static_folder=None)
    CORS(app, supports_credentials=True)

    # ---- session / security ----
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-insecure-key-change-me')
    app.permanent_session_lifetime = timedelta(days=7)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        # Secure cookies in production (Render sets RENDER=true / serves HTTPS).
        SESSION_COOKIE_SECURE=bool(os.environ.get('SESSION_COOKIE_SECURE')
                                   or os.environ.get('RENDER')),
    )

    # ---- root: login page when logged-out, app when logged-in ----
    @app.route('/')
    def index():
        page = 'index.html' if session.get('user') else 'login.html'
        folder = os.path.join(HERE, 'admin') if page == 'index.html' else os.path.join(HERE, 'pages')
        return send_from_directory(folder, page)

    @app.route('/login')
    def login_page():
        return send_from_directory(os.path.join(HERE, 'pages'), 'login.html')

    @app.route('/<path:path>')
    def static_proxy(path):
        return send_from_directory(HERE, path)

    install_guards(app)
    register_blueprints(app)
    return app
