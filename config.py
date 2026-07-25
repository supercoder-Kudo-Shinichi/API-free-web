import os
import re
from dotenv import load_dotenv

# Load env variables
load_dotenv()

class Config:
    PORT = int(os.getenv("PORT", 5000))
    ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "flask-secret-key-clerk-clone-98765")
    
    # Auto-fix Railway's PostgreSQL connection string (postgres:// → postgresql://)
    _raw_db_url = os.getenv("DATABASE_URL", "sqlite:///dev.db")
    if _raw_db_url and _raw_db_url.startswith("postgres://"):
        _raw_db_url = re.sub(r"^postgres://", "postgresql://", _raw_db_url)
    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Allow up to 20MB JSON body (for base64 images)
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    JWT_ACCESS_SECRET = os.getenv("JWT_ACCESS_SECRET", "access-token-secret-key-12345")
    JWT_REFRESH_SECRET = os.getenv("JWT_REFRESH_SECRET", "refresh-token-secret-key-12345")
    JWT_ACCESS_EXPIRES_IN_MINUTES = 15
    JWT_REFRESH_EXPIRES_IN_DAYS = 7

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mailtrap.io")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 2525))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@clerk-clone.local")

    # Sanity CMS configuration
    SANITY_PROJECT_ID = os.getenv("SANITY_PROJECT_ID", "")
    SANITY_DATASET = os.getenv("SANITY_DATASET", "production")
    SANITY_API_TOKEN = os.getenv("SANITY_API_TOKEN", "")
    SANITY_API_VERSION = os.getenv("SANITY_API_VERSION", "v2024-01-01")

    # Security configuration
    RATE_LIMIT_WINDOW_MINUTES = 15
    RATE_LIMIT_MAX = 100
    BRUTE_FORCE_MAX_ATTEMPTS = 5
