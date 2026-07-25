import time
import json
from functools import wraps
from flask import request, jsonify, g, make_response
from config import Config
from models import db, AuditLog
from services.token_service import TokenService

# Lightweight in-memory rate limiter to avoid redis dependencies on Windows
_rate_limit_store = {}

def rate_limit(limit_type="global"):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip rate limiting in development and test modes (unless explicitly enabled)
            if Config.ENV in ("development", "test") and not request.headers.get("x-test-rate-limit"):
                return f(*args, **kwargs)

            ip = request.remote_addr or "unknown_ip"
            now = time.time()
            
            # Determine threshold
            if limit_type == "auth":
                window = Config.RATE_LIMIT_WINDOW_MINUTES * 60
                max_attempts = Config.BRUTE_FORCE_MAX_ATTEMPTS
            else:
                window = Config.RATE_LIMIT_WINDOW_MINUTES * 60
                max_attempts = Config.RATE_LIMIT_MAX

            # Initialize key in store
            key = f"{limit_type}:{ip}"
            if key not in _rate_limit_store:
                _rate_limit_store[key] = []

            # Clean expired timestamps
            _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window]

            if len(_rate_limit_store[key]) >= max_attempts:
                return jsonify({
                    "success": False,
                    "code": "TOO_MANY_REQUESTS",
                    "message": "Too many requests. Please try again later."
                }), 429

            # Record current timestamp
            _rate_limit_store[key].append(now)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # require_auth already set g.user
        user_id = g.user.get('userId')
        from services.user_service import UserService
        user = UserService.find_by_id(user_id)
        if not user or user.role != 'admin':
            return jsonify({
                "success": False,
                "code": "FORBIDDEN",
                "message": "Admin access required."
            }), 403
        return f(*args, **kwargs)
    return decorated_function

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({
                "success": False,
                "code": "UNAUTHORIZED",
                "message": "Authorization token is required."
            }), 401

        token = auth_header.split(" ")[1]
        try:
            payload = TokenService.verify_access_token(token)
            g.user = payload
        except Exception as e:
            return jsonify({
                "success": False,
                "code": "TOKEN_EXPIRED_OR_INVALID",
                "message": str(e)
            }), 401

        return f(*args, **kwargs)
    return decorated_function

def add_cors_headers(response=None):
    """Add CORS headers to allow frontend to connect from any origin (development).
    When credentials: 'include' is used, Access-Control-Allow-Origin must echo the specific origin, not '*'.
    """
    if response is None:
        from flask import make_response as flask_make_response
        response = flask_make_response()
    
    origin = request.headers.get('Origin', 'http://localhost:5000')
    response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, x-test-rate-limit'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    if request.method == 'OPTIONS':
        response.status_code = 200
    return response

def log_audit_event(event: str, status: str, user_id: str = None, details: dict = None):
    try:
        user_agent = request.headers.get("User-Agent")
        ip_address = request.remote_addr or request.headers.get("X-Forwarded-For")
        
        # Sanitize details
        sanitized_details = None
        if details:
            sanitized_details = details.copy()
            sanitized_details.pop("password", None)
            sanitized_details.pop("token", None)
            sanitized_details.pop("idToken", None)
            sanitized_details = json.dumps(sanitized_details)

        log = AuditLog(
            user_id=user_id,
            event=event,
            status=status,
            user_agent=user_agent,
            ip_address=ip_address,
            details=sanitized_details
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print("Failed to write audit log:", str(e))
