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

PACKAGE_FEATURES = {
    'free': {
        'max_users': 100,
        'social_login': False,
        'session_management': False,
        'audit_logging': False,
        'priority_support': False,
    },
    'pro': {
        'max_users': 10000,
        'social_login': True,
        'session_management': True,
        'audit_logging': False,
        'priority_support': True,
    },
    'enterprise': {
        'max_users': None,
        'social_login': True,
        'session_management': True,
        'audit_logging': True,
        'priority_support': True,
    },
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
    def _extract_package_from_backup(backup: dict) -> str:
        """Extract the package name from a backup document, supporting both old flat format
        and new rich format with package_quota.current_package."""
        # New format: package_quota.current_package
        pkg_quota = backup.get('package_quota', {})
        if isinstance(pkg_quota, dict) and pkg_quota.get('current_package'):
            return pkg_quota.get('current_package')
        # Old format: flat package field
        if backup.get('package'):
            return backup.get('package')
        return None

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

        # Check if there's an existing backup for this email (survived redeploy)
        # If so, restore the package from backup instead of defaulting to 'free'
        try:
            backups = SanityService.get_account_backups(email=normalized_email)
            if backups:
                latest = sorted(
                    backups,
                    key=lambda item: item.get('updated_at') or item.get('created_at') or '',
                    reverse=True
                )[0]
                backup_pkg = UserService._extract_package_from_backup(latest)
                if backup_pkg and backup_pkg != 'free':
                    normalized_package = backup_pkg
                    print(f"[BACKUP] Restored package '{normalized_package}' for new user {normalized_email} from backup")
        except Exception as exc:
            print(f"[BACKUP] Failed to check backups for {normalized_email}: {exc}")

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
        Uses the rich JSON format from example_json_packup_data/user_json_backup_data.json
        including package_quota, apikeys, websites, and payment_history.
        Only creates a new backup if the data has actually changed since the last backup.
        Runs synchronously in a background thread - uses only Sanity API, no DB needed.
        """
        try:
            # Check if data changed by comparing with latest backup (Sanity only, no DB)
            existing_backups = SanityService.get_account_backups(user_id=user_id)
            if existing_backups:
                latest = sorted(
                    existing_backups,
                    key=lambda item: item.get('updated_at') or item.get('created_at') or '',
                    reverse=True
                )[0]
                # Check if package_quota data changed (supports both formats)
                latest_pkg = latest.get('package_quota', {}).get('current_package', '') or latest.get('package', '')
                if (latest_pkg == package and
                    latest.get('role') == role and
                    latest.get('display_name') == display_name and
                    latest.get('avatar_url') == avatar_url):
                    return

            # Build simple backup data first (works without DB context)
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
                'package_used': 0,
                'package_remaining': None,
                'package_features': PACKAGE_FEATURES.get(package, PACKAGE_FEATURES['free']),
                'apikeys': [],
                'website_domains': [],
                'payment_history': [],
            }

            # Try to enrich with DB data if app context is available
            try:
                from flask import current_app
                if current_app:
                    with current_app.app_context():
                        from models import ApiKey, Website, Order as OrderModel, User as UserModel
                        
                        user = UserService.find_by_id(user_id)
                        if user:
                            # Package usage stats
                            limit = PACKAGE_LIMITS.get(package, 100)
                            used_count = UserModel.query.filter_by(package=package).count()
                            backup_data['package_used'] = used_count
                            backup_data['package_remaining'] = None if limit is None else max(limit - used_count, 0)
                            
                            # API keys
                            keys = ApiKey.query.filter_by(user_id=user_id).order_by(ApiKey.created_at.desc()).all()
                            backup_data['apikeys'] = [k.to_dict() for k in keys]
                            
                            # Website domains
                            websites = Website.query.filter_by(user_id=user_id, active=True).all()
                            backup_data['website_domains'] = [w.domain for w in websites]
                            
                            # Payment history
                            orders = OrderModel.query.filter_by(user_id=user_id).order_by(OrderModel.created_at.desc()).all()
                            backup_data['payment_history'] = [
                                {
                                    'order_id': o.id,
                                    'package': o.package,
                                    'amount': o.amount,
                                    'currency': o.currency,
                                    'status': o.status,
                                    'payment_proof_url': o.payment_proof_url,
                                    'created_at': o.created_at.isoformat(),
                                    'reviewed_at': o.reviewed_at.isoformat() if o.reviewed_at else None,
                                }
                                for o in orders
                            ]
            except Exception:
                pass  # Non-critical enrichment, skip if no context

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
    def restore_account_backup(user_id: str, email: str = None) -> None:
        """Restore the latest backup snapshot for a user from Sanity when local state is missing.
        Uses email as the primary lookup key (stable across redeploys) with user_id as fallback.
        Runs synchronously to ensure data is available immediately after login.
        Restores all critical fields (package, display_name, avatar_url, role).
        """
        try:
            from flask import current_app
            with current_app.app_context():
                user = UserService.find_by_id(user_id)
                if not user:
                    return

                # Lookup by email first (stable across redeploys), fallback to user_id
                backups = SanityService.get_account_backups(user_id=user_id, email=email or user.email)
                if not backups:
                    return user

                latest = sorted(
                    backups,
                    key=lambda item: item.get('updated_at') or item.get('created_at') or '',
                    reverse=True
                )[0]

                needs_commit = False

                # Restore display_name if missing
                if not user.display_name and latest.get('display_name') is not None:
                    user.display_name = latest.get('display_name')
                    needs_commit = True

                # Restore avatar_url if missing
                if not user.avatar_url and latest.get('avatar_url') is not None:
                    user.avatar_url = latest.get('avatar_url')
                    needs_commit = True

                # ALWAYS restore package from backup (supports both old flat and new rich format)
                # This ensures package upgrades survive redeploy
                backup_package = UserService._extract_package_from_backup(latest)
                if backup_package:
                    package_rank = {"free": 0, "pro": 1, "enterprise": 2}
                    current_rank = package_rank.get(user.package, 0)
                    backup_rank = package_rank.get(backup_package, 0)
                    if backup_rank > current_rank or backup_package != 'free':
                        user.package = backup_package
                        # Try to get package_activated_at from both formats
                        pkg_quota = latest.get('package_quota', {})
                        activated_at = (pkg_quota.get('package_activated_at') if isinstance(pkg_quota, dict) 
                                        else latest.get('package_activated_at'))
                        if activated_at:
                            try:
                                user.package_activated_at = datetime.fromisoformat(activated_at)
                            except (ValueError, TypeError):
                                pass
                        needs_commit = True

                # Restore role if missing
                if not user.role and latest.get('role'):
                    user.role = latest.get('role', user.role)
                    needs_commit = True

                if needs_commit:
                    db.session.commit()
                    print(f"[BACKUP] Restored account for {user.email} (package: {user.package})")
            
            return user
        except Exception as exc:
            print(f"Backup restore failed for user {user_id}: {exc}")

    @staticmethod
    def get_pending_requests() -> list:
        """Get all users who have requested a package upgrade (orders with pending status)."""
        from models import Order
        return Order.query.filter_by(status='pending').order_by(Order.created_at.desc()).all()