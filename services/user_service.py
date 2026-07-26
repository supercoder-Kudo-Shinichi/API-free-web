import re
import bcrypt
from models import db, User

PACKAGE_LIMITS = {
    'free': 100,
    'pro': 10000,
    'enterprise': None,
}

class UserService:
    @staticmethod
    def normalize_username(username: str) -> str:
        return username.strip()

    @staticmethod
    def normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if not normalized.endswith("@gmail.com"):
            raise ValueError("Only Gmail addresses are accepted.")
        if not re.match(r"^[a-z0-9._%+-]+@gmail\.com$", normalized):
            raise ValueError("Invalid email format.")
        return normalized

    @staticmethod
    def find_by_id(user_id: str) -> User:
        return db.session.get(User, user_id)

    @staticmethod
    def find_by_username(username: str) -> User:
        trimmed = username.strip().lower()
        return User.query.filter(db.func.lower(User.username) == trimmed).first()

    @staticmethod
    def find_by_email(email: str) -> User:
        normalized = UserService.normalize_email(email)
        return User.query.filter_by(email=normalized).first()

    @staticmethod
    def find_by_google_sub(google_sub: str) -> User:
        return User.query.filter_by(google_sub=google_sub).first()

    @staticmethod
    def check_username_exists(username: str, exclude_user_id: str = None) -> bool:
        trimmed = username.strip().lower()
        query = User.query.filter(db.func.lower(User.username) == trimmed)
        if exclude_user_id:
            query = query.filter(User.id != exclude_user_id)
        return query.first() is not None

    @staticmethod
    def check_email_exists(email: str, exclude_user_id: str = None) -> bool:
        normalized = UserService.normalize_email(email)
        query = User.query.filter_by(email=normalized)
        if exclude_user_id:
            query = query.filter(User.id != exclude_user_id)
        return query.first() is not None

    @staticmethod
    def get_package_limit(package: str) -> int | None:
        normalized_package = (package or 'free').lower()
        return PACKAGE_LIMITS.get(normalized_package)

    @staticmethod
    def enforce_package_quota(package: str) -> None:
        limit = UserService.get_package_limit(package)
        if limit is None:
            return

        current_count = User.query.filter_by(package=(package or 'free').lower()).count()
        if current_count >= limit:
            raise ValueError(f"{(package or 'free').lower()} package has reached its user limit of {limit}.")

    @staticmethod
    def create_user(username: str, email: str, password_hash: str = None, google_sub: str = None, avatar_url: str = None, display_name: str = None, package: str = 'free') -> User:
        normalized_username = UserService.normalize_username(username)
        normalized_email = UserService.normalize_email(email)
        normalized_package = (package or 'free').lower()

        if normalized_package not in PACKAGE_LIMITS:
            raise ValueError("Invalid package.")

        if UserService.check_username_exists(normalized_username):
            raise ValueError("Username already exists.")

        if UserService.check_email_exists(normalized_email):
            raise ValueError("Email already exists.")

        if google_sub and UserService.find_by_google_sub(google_sub):
            raise ValueError("Google account already linked.")

        UserService.enforce_package_quota(normalized_package)

        # Admin email detection (auto-assign admin role)
        ADMIN_EMAILS = ['soladzpro@gmail.com']
        role = 'admin' if normalized_email in ADMIN_EMAILS else 'user'

        user = User(
            username=normalized_username,
            email=normalized_email,
            password_hash=password_hash,
            google_sub=google_sub,
            avatar_url=avatar_url,
            display_name=display_name,
            role=role,
            package=normalized_package,
        )
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def update_user_profile(user_id: str, username: str = None, display_name: str = None, avatar_url: str = None) -> User:
        user = UserService.find_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        if username is not None:
            normalized_username = UserService.normalize_username(username)
            if UserService.check_username_exists(normalized_username, user_id):
                raise ValueError("Username already exists.")
            user.username = normalized_username

        if display_name is not None:
            user.display_name = display_name

        if avatar_url is not None:
            user.avatar_url = avatar_url

        db.session.commit()
        return user

    @staticmethod
    def link_google_account(user_id: str, google_sub: str) -> User:
        user = UserService.find_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        existing = UserService.find_by_google_sub(google_sub)
        if existing:
            raise ValueError("Google account already linked.")

        user.google_sub = google_sub
        db.session.commit()
        return user

    @staticmethod
    def unlink_google_account(user_id: str) -> User:
        user = UserService.find_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        if not user.password_hash:
            raise ValueError("Cannot unlink Google account without a password set.")

        user.google_sub = None
        db.session.commit()
        return user

    # === ADMIN METHODS ===

    @staticmethod
    def get_all_users(page: int = 1, per_page: int = 20) -> tuple:
        """Get paginated list of all users. Returns (users, total_count)."""
        pagination = User.query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return pagination.items, pagination.total

    @staticmethod
    def approve_package(user_id: str, package: str, admin_id: str) -> User:
        """Admin approves a package upgrade for a user."""
        from datetime import datetime

        user = UserService.find_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        valid_packages = ['pro', 'enterprise']
        if package not in valid_packages:
            raise ValueError(f"Invalid package. Valid: {', '.join(valid_packages)}")

        UserService.enforce_package_quota(package)

        user.package = package
        user.package_activated_at = datetime.utcnow()
        db.session.commit()

        # Log audit
        from middleware import log_audit_event
        log_audit_event('PACKAGE_APPROVED', 'SUCCESS', user_id, details={
            'package': package,
            'approved_by': admin_id,
        })

        return user

    @staticmethod
    def reject_package(user_id: str, admin_id: str) -> User:
        """Admin rejects a package upgrade request."""
        user = UserService.find_by_id(user_id)
        if not user:
            raise ValueError("User not found.")

        from middleware import log_audit_event
        log_audit_event('PACKAGE_REJECTED', 'SUCCESS', user_id, details={
            'approved_by': admin_id,
        })

        return user

    @staticmethod
    def get_pending_requests() -> list:
        """Get all users who have requested a package upgrade (orders with pending status)."""
        from models import Order
        return Order.query.filter_by(status='pending').order_by(Order.created_at.desc()).all()