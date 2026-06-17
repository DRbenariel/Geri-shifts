"""
app.py — Flask application factory.

Run dev:   python frontend/server.py
Run prod:  gunicorn 'frontend.app:create_app()' --bind 0.0.0.0:$PORT
"""
import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from .config import HERE
from .routes import register_blueprints


def create_app():
    app = Flask(__name__, static_folder=None)
    CORS(app)

    # ---- static serving — frontend/ is the web root ----
    @app.route('/')
    def index():
        return send_from_directory(os.path.join(HERE, 'admin'), 'index.html')

    @app.route('/<path:path>')
    def static_proxy(path):
        return send_from_directory(HERE, path)

    register_blueprints(app)
    return app
