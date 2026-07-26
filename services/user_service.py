import re
import threading
from datetime import datetime
import bcrypt
from flask import current_app
from models import db, User
from services.sanity_service import SanityService

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
        UserService.sync_account_backup(user)
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
        UserService.sync_account_backup(user)
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
        UserService.sync_account_backup(user)
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
        UserService.sync_account_backup(user)
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
        UserService.sync_account_backup(user)

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
    def _sync_account_backup_sync(user_id: str, username: str, email: str, package: str, package_activated_at: str, role: str, display_name: str, avatar_url: str, created_at: str, updated_at: str) -> None:
        """Persist a backup snapshot of the user's package/account state to Sanity.
        Only creates a new backup if the data has actually changed since the last backup.
        Runs synchronously in a background thread - uses only Sanity API, no DB needed.
        """
        try:
            existing_backups = SanityService.get_account_backups(user_id=user_id)
            if existing_backups:
                latest = sorted(
                    existing_backups,
                    key=lambda item: item.get('updated_at') or item.get('created_at') or '',
                    reverse=True
                )[0]
                if (latest.get('package') == package and
                    latest.get('role') == role and
                    latest.get('display_name') == display_name and
                    latest.get('avatar_url') == avatar_url):
                    return

            backup_data = {
                'user_id': user_id,
                'username': username,
                'email': email,
                'package': package,
                'package_activated_at': package_activated_at,
                'role': role,
                'display_name': display_name,
                'avatar_url': avatar_url,
                'created_at': created_at,
                'updated_at': updated_at,
                'backup_source': 'app',
            }
            SanityService.save_account_backup(backup_data)
        except Exception as exc:
            print(f"Backup sync failed for user {user_id}: {exc}")

    @staticmethod
    def sync_account_backup(user: User) -> None:
        """Persist a backup snapshot asynchronously in a background thread.
        This prevents the Sanity API call from blocking the HTTP response."""
        # Extract all needed data from user object before threading
        thread = threading.Thread(
            target=UserService._sync_account_backup_sync,
            args=(
                user.id,
                user.username,
                user.email,
                user.package,
                user.package_activated_at.isoformat() if user.package_activated_at else None,
                user.role,
                user.display_name,
                user.avatar_url,
                user.created_at.isoformat(),
                user.updated_at.isoformat() if user.updated_at else None,
            ),
            daemon=True
        )
        thread.start()

    @staticmethod
    def _restore_account_backup_sync(user_id: str) -> None:
        """Restore the latest backup snapshot for a user from Sanity when local state is missing.
        Only restores fields that are None/empty in the current user record.
        Runs synchronously in a background thread.
        """
        try:
            from app import app as _flask_app
            with _flask_app.app_context():
                user = UserService.find_by_id(user_id)
                if not user:
                    return

                backups = SanityService.get_account_backups(user_id=user_id)
                if not backups:
                    return

                latest = sorted(
                    backups,
                    key=lambda item: item.get('updated_at') or item.get('created_at') or '',
                    reverse=True
                )[0]

                needs_commit = False

                if not user.display_name and latest.get('display_name') is not None:
                    user.display_name = latest.get('display_name')
                    needs_commit = True
                if not user.avatar_url and latest.get('avatar_url') is not None:
                    user.avatar_url = latest.get('avatar_url')
                    needs_commit = True
                if not user.package_activated_at and latest.get('package'):
                    user.package = latest.get('package', user.package)
                    if latest.get('package_activated_at'):
                        user.package_activated_at = datetime.fromisoformat(latest['package_activated_at'])
                    needs_commit = True
                if not user.role and latest.get('role'):
                    user.role = latest.get('role', user.role)
                    needs_commit = True

                if needs_commit:
                    db.session.commit()
        except Exception as exc:
            print(f"Backup restore failed for user {user_id}: {exc}")

    @staticmethod
    def restore_account_backup(user_id: str) -> None:
        """Restore the latest backup snapshot asynchronously in a background thread.
        This prevents the Sanity API call from blocking the HTTP response."""
        thread = threading.Thread(
            target=UserService._restore_account_backup_sync,
            args=(user_id,),
            daemon=True
        )
        thread.start()

    @staticmethod
    def get_pending_requests() -> list:
        """Get all users who have requested a package upgrade (orders with pending status)."""
        from models import Order
        return Order.query.filter_by(status='pending').order_by(Order.created_at.desc()).all()