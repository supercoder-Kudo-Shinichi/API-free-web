"""
Package-based feature limits for social features.
"""
from functools import wraps
from flask import jsonify, g
from middleware import build_error_response

# Package limit definitions
PACKAGE_LIMITS = {
    'free': {
        'max_friends': 1000,
        'max_conversations': 1000,
        'max_messages_per_day': 1000,
        'max_image_size_mb': 128,    # 128MB cho ảnh
        'max_file_size_mb': 512,     # 512MB cho file
        'can_file_share': True,
        'can_message_history': True,
        'can_custom_emoji': False,
    },
    'pro': {
        'max_friends': 10000,
        'max_conversations': 10000,
        'max_messages_per_day': 10000,
        'max_image_size_mb': 512,    # 512MB cho ảnh
        'max_file_size_mb': 1024,    # 1GB cho file
        'can_file_share': True,
        'can_message_history': True,
        'can_custom_emoji': True,
    },
    'enterprise': {
        'max_friends': 1000000000,
        'max_conversations': 1000000000,
        'max_messages_per_day': 1000000000,
        'max_image_size_mb': 2048,   # 2GB cho ảnh
        'max_file_size_mb': 2048,    # 2GB cho file
        'can_file_share': True,
        'can_message_history': True,
        'can_custom_emoji': True,
    }
}

def get_user_limits(user):
    """Get limits for a user based on their package."""
    package = user.package if user else 'free'
    return PACKAGE_LIMITS.get(package, PACKAGE_LIMITS['free'])

UNLIMITED_THRESHOLD = 999999999

def _is_unlimited(val):
    return val is None or val == float('inf') or val >= UNLIMITED_THRESHOLD

def check_friend_limit(user):
    """Check if user can add more friends based on package."""
    from models import Friend, db
    limits = get_user_limits(user)
    if _is_unlimited(limits['max_friends']):
        return True, None
    
    friend_count = Friend.query.filter_by(user_id=user.id).count()
    if friend_count >= limits['max_friends']:
        return False, f"Bạn đã đạt giới hạn {limits['max_friends']} bạn bè cho gói {user.package}. Hãy nâng cấp gói để mở rộng."
    return True, None

def check_conversation_limit(user):
    """Check if user can create more conversations."""
    from models import ConversationMember, db
    limits = get_user_limits(user)
    if _is_unlimited(limits['max_conversations']):
        return True, None
    
    conv_count = ConversationMember.query.filter_by(user_id=user.id).count()
    if conv_count >= limits['max_conversations']:
        return False, f"Bạn đã đạt giới hạn {limits['max_conversations']} cuộc trò chuyện cho gói {user.package}. Hãy nâng cấp gói để mở rộng."
    return True, None

def check_message_limit(user):
    """Check if user can send more messages today."""
    from datetime import datetime, timedelta
    from models import Message, db
    limits = get_user_limits(user)
    if _is_unlimited(limits['max_messages_per_day']):
        return True, None
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    msg_count = Message.query.filter(
        Message.sender_id == user.id,
        Message.created_at >= today_start,
        Message.created_at < today_end
    ).count()
    
    if msg_count >= limits['max_messages_per_day']:
        return False, f"Bạn đã đạt giới hạn {limits['max_messages_per_day']} tin nhắn/ngày cho gói {user.package}. Hãy nâng cấp gói để nhắn tin không giới hạn."
    return True, None

def require_friend_limit(f):
    """Decorator to check friend limit before adding friends."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from services.user_service import UserService
        user_id = g.user.get('userId')
        user = UserService.find_by_id(user_id)
        if not user:
            return jsonify(build_error_response("USER_NOT_FOUND", "User not found.")), 404
        
        ok, error = check_friend_limit(user)
        if not ok:
            return jsonify(build_error_response("LIMIT_REACHED", error)), 403
        return f(*args, **kwargs)
    return decorated_function

def require_message_limit(f):
    """Decorator to check message limit before sending."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from services.user_service import UserService
        user_id = g.user.get('userId')
        user = UserService.find_by_id(user_id)
        if not user:
            return jsonify(build_error_response("USER_NOT_FOUND", "User not found.")), 404
        
        ok, error = check_message_limit(user)
        if not ok:
            return jsonify(build_error_response("LIMIT_REACHED", error)), 403
        return f(*args, **kwargs)
    return decorated_function