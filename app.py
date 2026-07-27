import os
from flask import Flask, jsonify, send_from_directory
from config import Config
from models import db
from routes import auth_bp
from routes_payment import payment_bp
from routes_social import social_bp
from middleware import add_cors_headers, log_audit_event
from services.user_service import UserService
from models import User
from flask_socketio import SocketIO
from socketio_events import register_socketio_events

# Use threading for Windows compatibility
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

def create_app(config_class=Config, test_config=None):
    # Get the absolute path to the frontend directory
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
    app = Flask(__name__, static_folder=frontend_dir, static_url_path='')

    app.config.from_object(config_class)

    # Apply test overrides before any extensions are initialized
    if test_config is not None:
        app.config.update(test_config)

    # When running with an in-memory SQLite database (e.g., during tests),
    # configure SQLAlchemy to use a StaticPool with a single shared connection.
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if 'sqlite:///:memory:' in db_uri and 'SQLALCHEMY_ENGINE_OPTIONS' not in app.config:
        from sqlalchemy.pool import StaticPool
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {'check_same_thread': False},
            'poolclass': StaticPool,
        }

    # Initialize extensions
    db.init_app(app)
    socketio.init_app(app)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(payment_bp, url_prefix='/api')
    app.register_blueprint(social_bp, url_prefix='/api')

    # Register SocketIO events
    register_socketio_events(socketio)

    # Apply CORS headers after every request
    @app.after_request
    def after_request(response):
        return add_cors_headers(response)

    # Serve frontend static files
    @app.route('/')
    def serve_index():
        return send_from_directory(frontend_dir, 'index.html')

    @app.route('/<path:path>')
    def serve_frontend(path):
        file_path = os.path.join(frontend_dir, path)
        # If file exists, serve it; otherwise redirect to index.html (SPA behavior)
        if os.path.isfile(file_path):
            return send_from_directory(frontend_dir, path)
        # For frontend routes that aren't files, redirect to login.html
        if path in ['login', 'register', 'dashboard', 'docs', 'admin', 'social']:
            return send_from_directory(frontend_dir, f'{path}.html')
        return send_from_directory(frontend_dir, 'index.html')

    # Health check endpoint
    @app.route('/health', methods=['GET'])
    def health():
        try:
            # Check database connection with a short timeout using the engine directly
            with db.engine.connect() as connection:
                connection.execute(db.text("SELECT 1"))
            return jsonify({"status": "ok", "database": "connected"}), 200
        except Exception as e:
            app.logger.exception("Health check failed")
            return jsonify({"status": "error", "database": "disconnected", "error": str(e)}), 500

    # Global Error Handler to prevent leakage of traceback info
    @app.errorhandler(500)
    def handle_internal_error(error):
        app.logger.error(f"Internal Server Error: {str(error)}")
        response = {
            "success": False,
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred on the server."
        }
        if app.config["ENV"] == "development" or app.config["ENV"] == "test":
            response["message"] = str(error)
        return jsonify(response), 500

    # Create tables
    with app.app_context():
        db.create_all()
        # Migration: add theme_preference column if not exists (for existing databases)
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            columns = [c['name'] for c in inspector.get_columns('users')]
            if 'theme_preference' not in columns:
                db.session.execute(db.text('ALTER TABLE users ADD COLUMN theme_preference VARCHAR(20) DEFAULT NULL'))
                db.session.commit()
                print("[MIGRATION] Added theme_preference column to users table")
        except Exception as e:
            print(f"[MIGRATION] Note: {e}")

    return app

# Module-level app instance for production use (Gunicorn, etc.)
app = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=Config.PORT, allow_unsafe_werkzeug=True)

