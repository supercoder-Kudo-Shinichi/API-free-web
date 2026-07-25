import uuid
import secrets
import string
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def generate_payment_code():
    """Generate a unique 12-character alphanumeric payment code."""
    alphabet = string.ascii_uppercase + string.digits
    return 'AG' + ''.join(secrets.choice(alphabet) for _ in range(10))

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    google_sub = db.Column(db.String(255), unique=True, nullable=True)
    avatar_url = db.Column(db.String(255), nullable=True)
    display_name = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='user')  # 'user' or 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    package = db.Column(db.String(50), nullable=False, default='free')
    package_activated_at = db.Column(db.DateTime, nullable=True)

    sessions = db.relationship('Session', backref='user', cascade='all, delete-orphan', lazy=True)
    audit_logs = db.relationship('AuditLog', backref='user', cascade='all, delete-orphan', lazy=True)
    orders = db.relationship('Order', foreign_keys='Order.user_id', backref='user', cascade='all, delete-orphan', lazy=True)
    admin_orders = db.relationship('Order', foreign_keys='Order.admin_id', backref='admin', lazy=True)
    transactions = db.relationship('Transaction', backref='user', cascade='all, delete-orphan', lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
            "package": self.package,
            "package_activated_at": self.package_activated_at.isoformat() if self.package_activated_at else None
        }

class Session(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    user_agent = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    revoked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    event = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False) # SUCCESS, FAILED
    user_agent = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    details = db.Column(db.Text, nullable=True) # JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    package = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='VND')
    payment_code = db.Column(db.String(20), unique=True, nullable=False, index=True, default=generate_payment_code)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, approved, rejected
    payment_proof_url = db.Column(db.Text, nullable=True)  # Sanity image URL
    sanity_transaction_id = db.Column(db.String(100), nullable=True)  # Sanity document ID
    admin_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id', ondelete='SET NULL'), nullable=True, index=True)
    package = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='VND')
    status = db.Column(db.String(20), nullable=False, default='completed')
    payment_method = db.Column(db.String(20), nullable=False, default='manual')
    approved_by = db.Column(db.String(36), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)