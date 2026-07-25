import jwt
import secrets
from datetime import datetime, timedelta
from config import Config
from models import db, Session, User

class TokenService:
    @staticmethod
    def generate_access_token(user: User) -> str:
        payload = {
            "userId": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(minutes=Config.JWT_ACCESS_EXPIRES_IN_MINUTES)
        }
        return jwt.encode(payload, Config.JWT_ACCESS_SECRET, algorithm="HS256")

    @staticmethod
    def verify_access_token(token: str) -> dict:
        try:
            return jwt.decode(token, Config.JWT_ACCESS_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise ValueError("Access token is expired.")
        except jwt.InvalidTokenError:
            raise ValueError("Access token is invalid.")

    @staticmethod
    def create_session(user_id: str, user_agent: str = None, ip_address: str = None) -> Session:
        token = secrets.token_hex(40)
        expires_at = datetime.utcnow() + timedelta(days=Config.JWT_REFRESH_EXPIRES_IN_DAYS)
        
        session = Session(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address
        )
        db.session.add(session)
        db.session.commit()
        return session

    @staticmethod
    def rotate_session(refresh_token: str, user_agent: str = None, ip_address: str = None) -> tuple:
        # Use a fresh engine connection to bypass the session's open transaction state.
        # This ensures we read the truly latest committed data, not a cached snapshot.
        with db.engine.connect() as conn:
            row = conn.execute(
                db.text("SELECT id, user_id, revoked, expires_at FROM sessions WHERE token = :token"),
                {"token": refresh_token}
            ).fetchone()

        if not row:
            raise ValueError("Session expired, revoked, or reuse detected.")

        session_id = row[0]
        user_id = row[1]
        is_revoked = bool(row[2])
        expires_at = row[3]

        # Parse expires_at if it's a string (SQLite returns strings for datetime)
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        # Replay Attack / Reuse detection
        if is_revoked or (expires_at and expires_at < datetime.utcnow()):
            # Security: Revoke all active sessions for this user due to suspected reuse attack
            TokenService.revoke_all_sessions(user_id)
            raise ValueError("Session expired, revoked, or reuse detected.")

        # Revoke current session (marking it rotated)
        db.session.execute(
            db.text("UPDATE sessions SET revoked = 1 WHERE id = :session_id"),
            {"session_id": session_id}
        )
        db.session.commit()

        # Load the user for token generation
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found.")

        # Create new session and return new token pair
        new_session = TokenService.create_session(user_id, user_agent, ip_address)
        access_token = TokenService.generate_access_token(user)

        return access_token, new_session.token, new_session


    @staticmethod
    def revoke_session(refresh_token: str) -> None:
        session = Session.query.filter_by(token=refresh_token).first()
        if session:
            session.revoked = True
            db.session.commit()

    @staticmethod
    def revoke_all_sessions(user_id: str) -> None:
        Session.query.filter_by(user_id=user_id).update({"revoked": True}, synchronize_session="fetch")
        db.session.commit()

    @staticmethod
    def validate_session(refresh_token: str) -> Session:
        session = Session.query.filter_by(token=refresh_token).first()
        if not session or session.revoked or session.expires_at < datetime.utcnow():
            raise ValueError("Session is invalid, expired, or revoked.")
        return session
