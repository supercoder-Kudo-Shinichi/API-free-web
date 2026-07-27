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

class ApiKey(db.Model):
    __tablename__ = 'api_keys'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, default='API Key')
    prefix = db.Column(db.String(20), nullable=False, default='ak_live_')
    key_hash = db.Column(db.String(255), unique=True, nullable=False, index=True)
    revoked = db.Column(db.Boolean, default=False, nullable=False)
    last_used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, reveal=False):
        return {
            'id': self.id,
            'name': self.name,
            'prefix': self.prefix,
            'preview': f"{self.prefix}••••{self.key_hash[-6:]}" if reveal else f"{self.prefix}••••{self.key_hash[-6:]}",
            'revoked': self.revoked,
            'created_at': self.created_at.isoformat(),
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
        }

class Website(db.Model):
    __tablename__ = 'websites'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    domain = db.Column(db.String(255), nullable=False, index=True)
    redirect_url = db.Column(db.String(255), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'domain': self.domain,
            'redirect_url': self.redirect_url,
            'active': self.active,
            'created_at': self.created_at.isoformat(),
        }

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
    theme_preference = db.Column(db.String(20), nullable=True, default=None)

    sessions = db.relationship('Session', backref='user', cascade='all, delete-orphan', lazy=True)
    audit_logs = db.relationship('AuditLog', backref='user', cascade='all, delete-orphan', lazy=True)
    orders = db.relationship('Order', foreign_keys='Order.user_id', backref='user', cascade='all, delete-orphan', lazy=True)
    admin_orders = db.relationship('Order', foreign_keys='Order.admin_id', backref='admin', lazy=True)
    transactions = db.relationship('Transaction', backref='user', cascade='all, delete-orphan', lazy=True)
    api_keys = db.relationship('ApiKey', backref='user', cascade='all, delete-orphan', lazy=True)
    websites = db.relationship('Website', backref='user', cascade='all, delete-orphan', lazy=True)

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
            "package_activated_at": self.package_activated_at.isoformat() if self.package_activated_at else None,
            "theme_preference": self.theme_preference
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


# ============================================================
# SOCIAL FEATURES - Friend Request
# ============================================================
class FriendRequest(db.Model):
    __tablename__ = 'friend_requests'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    receiver_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='PENDING')  # PENDING, ACCEPTED, DECLINED, CANCELLED
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('sender_id', 'receiver_id', name='uq_friend_request'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


# ============================================================
# SOCIAL FEATURES - Friend
# ============================================================
class Friend(db.Model):
    __tablename__ = 'friends'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    friend_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'friend_id', name='uq_friend'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'friend_id': self.friend_id,
            'created_at': self.created_at.isoformat(),
        }


# ============================================================
# SOCIAL FEATURES - Conversation
# ============================================================
class Conversation(db.Model):
    __tablename__ = 'conversations'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = db.relationship('ConversationMember', backref='conversation', cascade='all, delete-orphan', lazy=True)
    messages = db.relationship('Message', backref='conversation', cascade='all, delete-orphan', lazy=True)

    def to_dict(self, current_user_id=None):
        data = {
            'id': self.id,
            'created_at': self.created_at.isoformat() + 'Z',
            'updated_at': self.updated_at.isoformat() + 'Z',
        }
        if current_user_id and self.members:
            other = [m for m in self.members if m.user_id != current_user_id]
            if other:
                data['other_user'] = other[0].user.to_dict() if other[0].user else None
        return data


class ConversationMember(db.Model):
    __tablename__ = 'conversation_members'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = db.Column(db.String(36), db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='conversation_memberships', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('conversation_id', 'user_id', name='uq_conversation_member'),
    )


# ============================================================
# SOCIAL FEATURES - Message
# ============================================================
class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = db.Column(db.String(36), db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False, index=True)
    sender_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), nullable=False, default='text')  # text, image, file
    file_size = db.Column(db.Integer, nullable=True, default=None)  # bytes, for image/file messages
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sender = db.relationship('User', backref='messages', lazy=True)
    reads = db.relationship('MessageRead', backref='message', cascade='all, delete-orphan', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender_id': self.sender_id,
            'content': self.content,
            'message_type': self.message_type,
            'file_size': self.file_size,
            'created_at': self.created_at.isoformat() + 'Z',
            'updated_at': self.updated_at.isoformat() + 'Z',
            'sender': self.sender.to_dict() if self.sender else None,
            'reads': [r.to_dict() for r in self.reads] if self.reads else [],
        }


class MessageRead(db.Model):
    __tablename__ = 'message_reads'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = db.Column(db.String(36), db.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'message_id': self.message_id,
            'user_id': self.user_id,
            'read_at': self.read_at.isoformat(),
        }
