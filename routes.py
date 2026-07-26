import re
import threading
from datetime import datetime
import bcrypt
from flask import Blueprint, request, jsonify, g
from models import db
from services.user_service import UserService
from services.token_service import TokenService
from services.google_service import GoogleService
from services.email_service import EmailService
from middleware import require_auth, rate_limit, log_audit_event, build_success_response, build_error_response

auth_bp = Blueprint('auth', __name__)

# Input validation helpers
def validate_username(username):
    if not username or len(username) < 3 or len(username) > 20:
        return "Username must be between 3 and 20 characters."
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return "Username can only contain letters, numbers, and underscores."
    return None

def validate_email(email):
    if not email:
        return "Email is required."
    email_clean = email.strip().lower()
    if not email_clean.endswith("@gmail.com"):
        return "Only Gmail addresses (@gmail.com) are allowed."
    if not re.match(r"^[a-z0-9._%+-]+@gmail\.com$", email_clean):
        return "Invalid email format."
    return None

def validate_password(password):
    if not password or len(password) < 8:
        return "Password must be at least 8 characters."
    return None

# Cookie Helpers
def set_refresh_token_cookie(response, token):
    response.set_cookie(
        'refresh_token',
        token,
        httponly=True,
        secure=request.is_secure,
        samesite='Strict',
        max_age=7 * 24 * 60 * 60 # 7 days
    )

def clear_refresh_token_cookie(response):
    response.delete_cookie('refresh_token', httponly=True, samesite='Strict')

# 1. REGISTER
@auth_bp.route('/register', methods=['POST'])
@rate_limit('auth')
def register():
    data = request.get_json() or {}
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    # Validations
    err = validate_username(username) or validate_email(email) or validate_password(password)
    if err:
        return jsonify(build_error_response("VALIDATION_ERROR", err)), 400

    try:
        if UserService.check_username_exists(username):
            log_audit_event('REGISTER', 'FAILED', details={"username": username, "email": email, "error": "USERNAME_EXISTS"})
            return jsonify(build_error_response("USERNAME_EXISTS", "Username already exists.")), 400

        if UserService.check_email_exists(email):
            log_audit_event('REGISTER', 'FAILED', details={"username": username, "email": email, "error": "EMAIL_EXISTS"})
            return jsonify(build_error_response("EMAIL_EXISTS", "Email already exists.")), 400

        # Password hashing using bcrypt
        salt = bcrypt.gensalt(12)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

        # Create user
        user = UserService.create_user(
            username=username,
            email=email,
            password_hash=password_hash,
            package='free'
        )

        # Issue session & tokens
        session = TokenService.create_session(user.id, request.headers.get("User-Agent"), request.remote_addr)
        access_token = TokenService.generate_access_token(user)

        response = jsonify(build_success_response(
            message="Registration successful.",
            accessToken=access_token,
            refreshToken=session.token,
            user=user.to_dict()
        ))
        set_refresh_token_cookie(response, session.token)

        log_audit_event('REGISTER', 'SUCCESS', user.id)

        # Send welcome email
        try:
            EmailService.send_welcome_email(
                email=user.email,
                username=user.username,
                created_at=user.created_at,
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent")
            )
        except Exception as e:
            print("Asynchronous email failed:", str(e))

        return response, 201
    except Exception as e:
        log_audit_event('REGISTER', 'FAILED', details={"username": username, "email": email, "error": str(e)})
        return jsonify(build_error_response("REGISTRATION_FAILED", str(e))), 500

# 2. LOGIN
@auth_bp.route('/login', methods=['POST'])
@rate_limit('auth')
def login():
    data = request.get_json() or {}
    username_or_email = data.get('usernameOrEmail')
    password = data.get('password')

    if not username_or_email or not password:
        return jsonify(build_error_response("VALIDATION_ERROR", "Username/Email and password are required.")), 400

    try:
        user = None
        if "@" in username_or_email:
            user = UserService.find_by_email(username_or_email)
        else:
            user = UserService.find_by_username(username_or_email)

        if user:
            UserService.restore_account_backup(user.id)

        if not user or not user.password_hash:
            log_audit_event('LOGIN', 'FAILED', details={"usernameOrEmail": username_or_email, "error": "INVALID_CREDENTIALS"})
            return jsonify(build_error_response("INVALID_CREDENTIALS", "Invalid username/email or password.")), 401

        # Secure constant-time comparison via bcrypt
        if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            log_audit_event('LOGIN', 'FAILED', user.id, details={"error": "INVALID_CREDENTIALS"})
            return jsonify(build_error_response("INVALID_CREDENTIALS", "Invalid username/email or password.")), 401

        # Create session
        session = TokenService.create_session(user.id, request.headers.get("User-Agent"), request.remote_addr)
        access_token = TokenService.generate_access_token(user)

        response = jsonify(build_success_response(
            message="Login successful.",
            accessToken=access_token,
            refreshToken=session.token,
            user=user.to_dict()
        ))
        set_refresh_token_cookie(response, session.token)

        log_audit_event('LOGIN', 'SUCCESS', user.id)
        return response, 200
    except Exception as e:
        return jsonify(build_error_response("LOGIN_FAILED", str(e))), 500

# 3. GOOGLE OAUTH
@auth_bp.route('/google', methods=['POST'])
@rate_limit('auth')
def login_google():
    data = request.get_json() or {}
    id_token_str = data.get('idToken')

    if not id_token_str:
        return jsonify(build_error_response("VALIDATION_ERROR", "Google ID token is required.")), 400

    try:
        google_info = GoogleService.verify_id_token(id_token_str)
        user = UserService.find_by_google_sub(google_info['sub'])

        is_new_user = False
        if not user:
            existing_email_user = UserService.find_by_email(google_info['email'])
            if existing_email_user:
                # Link Google Account
                user = UserService.link_google_account(existing_email_user.id, google_info['sub'])
                # Sync profile details if missing
                if not user.avatar_url or not user.display_name:
                    UserService.update_user_profile(
                        user.id,
                        avatar_url=user.avatar_url or google_info['avatar_url'],
                        display_name=user.display_name or google_info['display_name']
                    )
            else:
                is_new_user = True
                # Generate unique username
                email_prefix = re.sub(r'[^a-zA-Z0-9_]', '', google_info['email'].split('@')[0])
                username_base = email_prefix or 'user'
                final_username = username_base
                suffix = 1
                while UserService.check_username_exists(final_username):
                    final_username = f"{username_base}_{suffix}"
                    suffix += 1

                user = UserService.create_user(
                    username=final_username,
                    email=google_info['email'],
                    google_sub=google_info['sub'],
                    display_name=google_info['display_name'],
                    avatar_url=google_info['avatar_url'],
                    package='free'
                )

        if user:
            UserService.restore_account_backup(user.id)

        # === AUTO-ASSIGN ADMIN ROLE (chạy mọi lần đăng nhập) ===
        # Ưu tiên 1: Tạo mới → UserService.create_user() đã xử lý ADMIN_EMAILS
        # Ưu tiên 2: User có sẵn → force update role nếu đúng email
        if google_info['email'].lower() == 'soladzpro@gmail.com' and user.role != 'admin':
            user.role = 'admin'
            db.session.commit()
            print(f"[ADMIN] Assigned admin role to {user.email}")

        # Issue session
        session = TokenService.create_session(user.id, request.headers.get("User-Agent"), request.remote_addr)
        access_token = TokenService.generate_access_token(user)

        response = jsonify(build_success_response(
            message="Google authentication successful.",
            accessToken=access_token,
            refreshToken=session.token,
            user=user.to_dict()
        ))
        set_refresh_token_cookie(response, session.token)

        log_audit_event('GOOGLE_REGISTER' if is_new_user else 'GOOGLE_LOGIN', 'SUCCESS', user.id)

        if is_new_user:
            try:
                EmailService.send_welcome_email(
                    email=user.email,
                    username=user.username,
                    created_at=user.created_at,
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get("User-Agent")
                )
            except Exception as e:
                print("Asynchronous email failed:", str(e))

        return response, 200
    except Exception as e:
        log_audit_event('GOOGLE_AUTH', 'FAILED', details={"error": str(e)})
        return jsonify(build_error_response("GOOGLE_AUTH_FAILED", str(e))), 400

# 4. LOGOUT
@auth_bp.route('/logout', methods=['POST'])
def logout():
    refresh_token = request.cookies.get('refresh_token') or (request.get_json() or {}).get('refreshToken')
    
    if not refresh_token:
        return jsonify(build_error_response("MISSING_TOKEN", "Refresh token is required.")), 400

    try:
        TokenService.revoke_session(refresh_token)
        response = jsonify(build_success_response(message="Logged out successfully."))
        clear_refresh_token_cookie(response)
        
        log_audit_event('LOGOUT', 'SUCCESS')
        return response, 200
    except Exception as e:
        return jsonify({"success": False, "code": "LOGOUT_FAILED", "message": str(e)}), 500

# 5. LOGOUT ALL DEVICES
@auth_bp.route('/logout-all', methods=['POST'])
@require_auth
def logout_all():
    user_id = g.user.get('userId')
    try:
        TokenService.revoke_all_sessions(user_id)
        response = jsonify(build_success_response(message="Logged out from all devices."))
        clear_refresh_token_cookie(response)
        
        log_audit_event('LOGOUT_ALL_DEVICES', 'SUCCESS', user_id)
        return response, 200
    except Exception as e:
        return jsonify({"success": False, "code": "LOGOUT_FAILED", "message": str(e)}), 500

# 6. REFRESH TOKEN (Rotation)
@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    refresh_token = request.cookies.get('refresh_token') or (request.get_json() or {}).get('refreshToken')

    if not refresh_token:
        return jsonify(build_error_response("MISSING_TOKEN", "Refresh token is required.")), 400

    try:
        access_token, new_refresh_token, _ = TokenService.rotate_session(
            refresh_token,
            request.headers.get("User-Agent"),
            request.remote_addr
        )

        response = jsonify(build_success_response(
            message="Token refreshed successfully.",
            accessToken=access_token,
            refreshToken=new_refresh_token
        ))
        set_refresh_token_cookie(response, new_refresh_token)

        return response, 200
    except Exception as e:
        response = jsonify(build_error_response("SESSION_EXPIRED", str(e)))
        clear_refresh_token_cookie(response)
        return response, 401

# 7. ME
@auth_bp.route('/me', methods=['GET'])
@require_auth
def me():
    user_id = g.user.get('userId')
    user = UserService.find_by_id(user_id)
    if user:
        UserService.restore_account_backup(user.id)
    if not user:
        return jsonify(build_error_response("USER_NOT_FOUND", "User not found.")), 404
    
    # Auto-assign admin role for soladzpro@gmail.com on every /me call
    if user.email and user.email.lower() == 'soladzpro@gmail.com' and user.role != 'admin':
        user.role = 'admin'
        db.session.commit()
        print(f"[ADMIN] Assigned admin role to {user.email} via /me endpoint")

    return jsonify(build_success_response(message="User profile loaded.", user=user.to_dict())), 200

# 8. VERIFY SESSION
@auth_bp.route('/verify', methods=['POST'])
def verify_session():
    data = request.get_json() or {}
    refresh_token = request.cookies.get('refresh_token') or data.get('refreshToken')
    auth_header = request.headers.get('Authorization', '')

    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        try:
            payload = TokenService.verify_access_token(token)
            user = UserService.find_by_id(payload.get('userId'))
            if not user:
                raise ValueError('User not found.')

            expires_at = payload.get('exp')
            if isinstance(expires_at, (int, float)):
                expires_at = datetime.fromtimestamp(expires_at).isoformat()

            return jsonify(build_success_response(
                message="Access token is valid.",
                valid=True,
                tokenType="access",
                expiresAt=expires_at,
                user=user.to_dict()
            )), 200
        except Exception as e:
            return jsonify(build_error_response("TOKEN_INVALID", str(e), valid=False)), 401

    if not refresh_token:
        return jsonify(build_error_response("MISSING_TOKEN", "Session token is required.", valid=False)), 400

    try:
        session = TokenService.validate_session(refresh_token)
        return jsonify(build_success_response(
            message="Session is valid.",
            valid=True,
            tokenType="refresh",
            expiresAt=session.expires_at.isoformat(),
            user=session.user.to_dict()
        )), 200
    except Exception as e:
        return jsonify(build_error_response("SESSION_INVALID", str(e), valid=False)), 401

# 9. LINK GOOGLE
@auth_bp.route('/link-google', methods=['POST'])
@require_auth
def link_google():
    user_id = g.user.get('userId')
    data = request.get_json() or {}
    id_token_str = data.get('idToken')

    if not id_token_str:
        return jsonify(build_error_response("VALIDATION_ERROR", "Google ID token is required.")), 400

    try:
        google_info = GoogleService.verify_id_token(id_token_str)
        
        # Email Link restriction: One Gmail belongs to one account only
        existing_email_user = UserService.find_by_email(google_info['email'])
        if existing_email_user and existing_email_user.id != user_id:
            return jsonify(build_error_response(
                "EMAIL_ALREADY_LINKED",
                "This Google account is already linked to another user profile."
            )), 400

        user = UserService.link_google_account(user_id, google_info['sub'])
        log_audit_event('LINK_GOOGLE', 'SUCCESS', user_id)
        return jsonify(build_success_response(message="Google account linked successfully.", user=user.to_dict())), 200
    except Exception as e:
        log_audit_event('LINK_GOOGLE', 'FAILED', user_id, details={"error": str(e)})
        return jsonify(build_error_response("LINK_GOOGLE_FAILED", str(e))), 400

# 10. UNLINK GOOGLE
@auth_bp.route('/unlink-google', methods=['POST'])
@require_auth
def unlink_google():
    user_id = g.user.get('userId')
    try:
        user = UserService.unlink_google_account(user_id)
        log_audit_event('UNLINK_GOOGLE', 'SUCCESS', user_id)
        return jsonify(build_success_response(message="Google account unlinked successfully.", user=user.to_dict())), 200
    except Exception as e:
        log_audit_event('UNLINK_GOOGLE', 'FAILED', user_id, details={"error": str(e)})
        return jsonify(build_error_response("UNLINK_GOOGLE_FAILED", str(e))), 400

# 11. CHECK USERNAME
@auth_bp.route('/check-username', methods=['POST'])
def check_username():
    data = request.get_json() or {}
    username = data.get('username')
    if not username:
        return jsonify(build_error_response("VALIDATION_ERROR", "Username is required.")), 400
    exists = UserService.check_username_exists(username)
    return jsonify(build_success_response(message="Username availability checked.", available=not exists)), 200

# 12. CHECK EMAIL
@auth_bp.route('/check-email', methods=['POST'])
def check_email():
    data = request.get_json() or {}
    email = data.get('email')
    if not email:
        return jsonify(build_error_response("VALIDATION_ERROR", "Email is required.")), 400
    try:
        exists = UserService.check_email_exists(email)
        return jsonify(build_success_response(message="Email availability checked.", available=not exists)), 200
    except Exception as e:
        return jsonify(build_error_response("INVALID_EMAIL", str(e))), 400


# 13. UPDATE PROFILE
@auth_bp.route('/me', methods=['PUT'])
@require_auth
def update_profile():
    user_id = g.user.get('userId')
    data = request.get_json() or {}
    username = data.get('username')
    display_name = data.get('display_name')
    avatar_url = data.get('avatar_url')

    try:
        if username:
            err = validate_username(username)
            if err:
                return jsonify(build_error_response("VALIDATION_ERROR", err)), 400
        user = UserService.update_user_profile(user_id, username=username, display_name=display_name, avatar_url=avatar_url)
        log_audit_event('UPDATE_PROFILE', 'SUCCESS', user_id)
        return jsonify(build_success_response(message="Profile updated successfully.", user=user.to_dict())), 200
    except Exception as e:
        log_audit_event('UPDATE_PROFILE', 'FAILED', user_id, details={"error": str(e)})
        return jsonify(build_error_response("UPDATE_FAILED", str(e))), 400

# 14. CHANGE PASSWORD
@auth_bp.route('/change-password', methods=['POST'])
@require_auth
def change_password():
    user_id = g.user.get('userId')
    data = request.get_json() or {}
    current_password = data.get('currentPassword')
    new_password = data.get('newPassword')

    if not current_password or not new_password:
        return jsonify(build_error_response("VALIDATION_ERROR", "Current password and new password are required.")), 400

    err = validate_password(new_password)
    if err:
        return jsonify(build_error_response("VALIDATION_ERROR", err)), 400

    try:
        user = UserService.find_by_id(user_id)
        if not user or not user.password_hash:
            return jsonify(build_error_response("INVALID_CREDENTIALS", "Password change not available for this account.")), 400

        if not bcrypt.checkpw(current_password.encode('utf-8'), user.password_hash.encode('utf-8')):
            log_audit_event('CHANGE_PASSWORD', 'FAILED', user_id, details={"error": "WRONG_CURRENT_PASSWORD"})
            return jsonify(build_error_response("WRONG_PASSWORD", "Current password is incorrect.")), 401

        salt = bcrypt.gensalt(12)
        new_password_hash = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
        user.password_hash = new_password_hash
        db.session.commit()

        # Revoke all other sessions for security
        TokenService.revoke_all_sessions(user_id)
        # Create new session
        session = TokenService.create_session(user_id, request.headers.get("User-Agent"), request.remote_addr)
        access_token = TokenService.generate_access_token(user)

        response = jsonify(build_success_response(
            message="Password changed successfully. Please sign in again.",
            accessToken=access_token,
            refreshToken=session.token
        ))
        set_refresh_token_cookie(response, session.token)

        log_audit_event('CHANGE_PASSWORD', 'SUCCESS', user_id)
        return response, 200
    except Exception as e:
        log_audit_event('CHANGE_PASSWORD', 'FAILED', user_id, details={"error": str(e)})
        return jsonify(build_error_response("CHANGE_PASSWORD_FAILED", str(e))), 500