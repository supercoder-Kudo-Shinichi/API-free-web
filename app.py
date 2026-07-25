import os
from flask import Flask, jsonify, send_from_directory
from config import Config
from models import db
from routes import auth_bp
from routes_payment import payment_bp
from middleware import add_cors_headers, log_audit_event

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

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(payment_bp, url_prefix='/api')

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
        if path in ['login', 'register', 'dashboard', 'docs', 'admin']:
            return send_from_directory(frontend_dir, f'{path}.html')
        return send_from_directory(frontend_dir, 'index.html')

    # Health check endpoint
    @app.route('/health', methods=['GET'])
    def health():
        try:
            # Check database connection
            db.session.execute(db.text("SELECT 1"))
            return jsonify({"status": "ok", "database": "connected"}), 200
        except Exception as e:
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

    return app

# Module-level app instance for production use (Gunicorn, etc.)
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=Config.PORT)

