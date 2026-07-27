import re
import os
import uuid
import base64
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from sqlalchemy import or_
from werkzeug.utils import secure_filename
from models import db, User, FriendRequest, Friend, Conversation, ConversationMember, Message, MessageRead
from middleware import require_auth, rate_limit, build_success_response, build_error_response, log_audit_event
from package_limits import require_friend_limit, require_message_limit, get_user_limits
from services.sanity_service import SanityService

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mp3', 'pdf', 'doc', 'docx', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

social_bp = Blueprint('social', __name__)


# ============================================================
# USER SEARCH
# ============================================================
@social_bp.route('/users/search', methods=['GET'])
@require_auth
@rate_limit('default')
def search_users():
    """Search users by username or email (realtime, paginated).
    Excludes self and locked users.
    """
    current_user_id = g.user.get('userId')
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    print(f"[SEARCH DEBUG] User {current_user_id} searching for '{q}'")
    print(f"[SEARCH DEBUG] User ID type: {type(current_user_id)}, value: {current_user_id}")

    if not q or len(q) < 1:
        print("[SEARCH DEBUG] Empty query")
        return jsonify(build_success_response(message='Search results.', users=[], total=0, page=page, per_page=per_page)), 200

    per_page = min(per_page, 50)  # cap at 50

    # Count total users in DB excluding self
    total_users = User.query.count()
    print(f"[SEARCH DEBUG] Total users in DB: {total_users}")

    query = User.query.filter(
        User.id != current_user_id,
        or_(
            User.username.ilike(f'%{q}%'),
            User.email.ilike(f'%{q}%'),
            User.display_name.ilike(f'%{q}%'),
        )
    ).order_by(User.username.asc())

    total = query.count()
    users = query.offset((page - 1) * per_page).limit(per_page).all()
    
    print(f"[SEARCH DEBUG] Found {total} users matching '{q}'")
    print(f"[SEARCH DEBUG] Returning {len(users)} users")

    results = []
    for u in users:
        user_dict = u.to_dict()
        # Check friendship status
        friend_status = _get_friend_status(current_user_id, u.id)
        user_dict['friend_status'] = friend_status
        results.append(user_dict)
        print(f"[SEARCH DEBUG] User found: {u.username} ({u.email})")

    return jsonify(build_success_response(
        message='Search results.',
        users=results,
        total=total,
        page=page,
        per_page=per_page
    )), 200


def _get_friend_status(current_user_id, other_user_id):
    """Returns: 'friends', 'pending_sent', 'pending_received', 'none', 'self'"""
    if current_user_id == other_user_id:
        return 'self'

    # Check if friends
    friend = Friend.query.filter(
        ((Friend.user_id == current_user_id) & (Friend.friend_id == other_user_id)) |
        ((Friend.user_id == other_user_id) & (Friend.friend_id == current_user_id))
    ).first()
    if friend:
        return 'friends'

    # Check pending requests
    req = FriendRequest.query.filter(
        ((FriendRequest.sender_id == current_user_id) & (FriendRequest.receiver_id == other_user_id)) |
        ((FriendRequest.sender_id == other_user_id) & (FriendRequest.receiver_id == current_user_id))
    ).first()
    if req:
        if req.status == 'PENDING':
            if req.sender_id == current_user_id:
                return 'pending_sent'
            else:
                return 'pending_received'
        elif req.status == 'DECLINED':
            return 'declined'

    return 'none'


# ============================================================
# FRIEND REQUEST
# ============================================================
@social_bp.route('/friends/request', methods=['POST'])
@require_auth
@require_friend_limit
@rate_limit('default')
def send_friend_request():
    """Send a friend request to another user."""
    current_user_id = g.user.get('userId')
    data = request.get_json() or {}
    receiver_id = data.get('receiver_id')

    if not receiver_id:
        return jsonify(build_error_response('VALIDATION_ERROR', 'receiver_id is required.')), 400

    if receiver_id == current_user_id:
        return jsonify(build_error_response('VALIDATION_ERROR', 'Cannot send friend request to yourself.')), 400

    # Check receiver exists
    receiver = User.query.get(receiver_id)
    if not receiver:
        return jsonify(build_error_response('USER_NOT_FOUND', 'User not found.')), 404

    # Check if already friends
    existing_friend = Friend.query.filter(
        ((Friend.user_id == current_user_id) & (Friend.friend_id == receiver_id)) |
        ((Friend.user_id == receiver_id) & (Friend.friend_id == current_user_id))
    ).first()
    if existing_friend:
        return jsonify(build_error_response('ALREADY_FRIENDS', 'You are already friends with this user.')), 400

    # Check for existing request
    existing_req = FriendRequest.query.filter(
        ((FriendRequest.sender_id == current_user_id) & (FriendRequest.receiver_id == receiver_id)) |
        ((FriendRequest.sender_id == receiver_id) & (FriendRequest.receiver_id == current_user_id))
    ).first()

    if existing_req:
        if existing_req.status == 'PENDING':
            return jsonify(build_error_response('REQUEST_EXISTS', 'A friend request already exists.')), 400
        elif existing_req.status == 'DECLINED':
            # Re-send: update the existing declined request
            existing_req.status = 'PENDING'
            existing_req.sender_id = current_user_id
            existing_req.updated_at = datetime.utcnow()
            db.session.commit()
            log_audit_event('FRIEND_REQUEST', 'SUCCESS', current_user_id, details={'receiver_id': receiver_id})
            return jsonify(build_success_response(message='Friend request sent.', friend_request=existing_req.to_dict())), 201
        else:
            return jsonify(build_error_response('REQUEST_EXISTS', f'Request status is {existing_req.status}.'), 400)

    # Create new request
    friend_req = FriendRequest(
        sender_id=current_user_id,
        receiver_id=receiver_id,
        status='PENDING'
    )
    db.session.add(friend_req)
    db.session.commit()

    log_audit_event('FRIEND_REQUEST', 'SUCCESS', current_user_id, details={'receiver_id': receiver_id})

    return jsonify(build_success_response(
        message='Friend request sent.',
        friend_request=friend_req.to_dict()
    )), 201


@social_bp.route('/friends/accept/<request_id>', methods=['POST'])
@require_auth
def accept_friend_request(request_id):
    """Accept a friend request."""
    current_user_id = g.user.get('userId')

    friend_req = FriendRequest.query.get(request_id)
    if not friend_req:
        return jsonify(build_error_response('NOT_FOUND', 'Friend request not found.')), 404

    if friend_req.receiver_id != current_user_id:
        return jsonify(build_error_response('FORBIDDEN', 'This request is not addressed to you.')), 403

    if friend_req.status != 'PENDING':
        return jsonify(build_error_response('INVALID_STATUS', f'Cannot accept request with status: {friend_req.status}.'), 400)

    # Update request status
    friend_req.status = 'ACCEPTED'
    friend_req.updated_at = datetime.utcnow()

    # Create bidirectional friend entries
    friend1 = Friend(user_id=friend_req.sender_id, friend_id=friend_req.receiver_id)
    friend2 = Friend(user_id=friend_req.receiver_id, friend_id=friend_req.sender_id)
    db.session.add(friend1)
    db.session.add(friend2)

    # Create conversation
    conversation = Conversation()
    db.session.add(conversation)
    db.session.flush()

    member1 = ConversationMember(conversation_id=conversation.id, user_id=friend_req.sender_id)
    member2 = ConversationMember(conversation_id=conversation.id, user_id=friend_req.receiver_id)
    db.session.add(member1)
    db.session.add(member2)

    db.session.commit()

    log_audit_event('FRIEND_ACCEPT', 'SUCCESS', current_user_id, details={'sender_id': friend_req.sender_id})

    return jsonify(build_success_response(
        message='Friend request accepted.',
        friend_request=friend_req.to_dict(),
        conversation=conversation.to_dict(current_user_id)
    )), 200


@social_bp.route('/friends/decline/<request_id>', methods=['POST'])
@require_auth
def decline_friend_request(request_id):
    """Decline a friend request."""
    current_user_id = g.user.get('userId')

    friend_req = FriendRequest.query.get(request_id)
    if not friend_req:
        return jsonify(build_error_response('NOT_FOUND', 'Friend request not found.')), 404

    if friend_req.receiver_id != current_user_id:
        return jsonify(build_error_response('FORBIDDEN', 'This request is not addressed to you.')), 403

    if friend_req.status != 'PENDING':
        return jsonify(build_error_response('INVALID_STATUS', f'Cannot decline request with status: {friend_req.status}.'), 400)

    friend_req.status = 'DECLINED'
    friend_req.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit_event('FRIEND_DECLINE', 'SUCCESS', current_user_id, details={'sender_id': friend_req.sender_id})

    return jsonify(build_success_response(message='Friend request declined.', friend_request=friend_req.to_dict())), 200


@social_bp.route('/friends/request/<request_id>', methods=['DELETE'])
@require_auth
def cancel_friend_request(request_id):
    """Cancel a friend request (sender only)."""
    current_user_id = g.user.get('userId')

    friend_req = FriendRequest.query.get(request_id)
    if not friend_req:
        return jsonify(build_error_response('NOT_FOUND', 'Friend request not found.')), 404

    if friend_req.sender_id != current_user_id:
        return jsonify(build_error_response('FORBIDDEN', 'You can only cancel your own requests.')), 403

    if friend_req.status != 'PENDING':
        return jsonify(build_error_response('INVALID_STATUS', f'Cannot cancel request with status: {friend_req.status}.'), 400)

    db.session.delete(friend_req)
    db.session.commit()

    log_audit_event('FRIEND_CANCEL', 'SUCCESS', current_user_id)

    return jsonify(build_success_response(message='Friend request cancelled.')), 200


@social_bp.route('/friends/remove/<friend_id>', methods=['DELETE'])
@require_auth
def remove_friend(friend_id):
    """Remove a friend (unfriend)."""
    current_user_id = g.user.get('userId')

    if friend_id == current_user_id:
        return jsonify(build_error_response('VALIDATION_ERROR', 'Cannot remove yourself.')), 400

    # Find the friendship entries
    friend_links = Friend.query.filter(
        ((Friend.user_id == current_user_id) & (Friend.friend_id == friend_id)) |
        ((Friend.user_id == friend_id) & (Friend.friend_id == current_user_id))
    ).all()

    if not friend_links:
        return jsonify(build_error_response('NOT_FRIENDS', 'You are not friends with this user.')), 400

    for f in friend_links:
        db.session.delete(f)

    # Delete the conversation between them
    # Find conversation with exactly these 2 members
    conversation_ids = db.session.query(ConversationMember.conversation_id).filter(
        ConversationMember.user_id.in_([current_user_id, friend_id])
    ).group_by(ConversationMember.conversation_id).having(
        db.func.count(ConversationMember.id) == 2
    ).all()

    for (conv_id,) in conversation_ids:
        conv = Conversation.query.get(conv_id)
        if conv:
            # Check it's a 2-person conversation
            members = ConversationMember.query.filter_by(conversation_id=conv_id).all()
            if len(members) == 2:
                member_ids = [m.user_id for m in members]
                if current_user_id in member_ids and friend_id in member_ids:
                    db.session.delete(conv)

    db.session.commit()

    log_audit_event('FRIEND_REMOVE', 'SUCCESS', current_user_id, details={'friend_id': friend_id})

    return jsonify(build_success_response(message='Friend removed.')), 200


# ============================================================
# FRIEND LIST
# ============================================================
@social_bp.route('/package/limits', methods=['GET'])
@require_auth
def get_package_limits():
    """Get the current user's package limits and usage."""
    from services.user_service import UserService
    from package_limits import get_user_limits, check_friend_limit, check_message_limit
    from datetime import datetime, timedelta
    import os
    
    current_user_id = g.user.get('userId')
    user = UserService.find_by_id(current_user_id)
    if not user:
        return jsonify(build_error_response("USER_NOT_FOUND", "User not found.")), 404
    
    limits = get_user_limits(user)
    
    # Count current usage
    friend_count = Friend.query.filter_by(user_id=current_user_id).count()
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    msg_count_today = Message.query.filter(
        Message.sender_id == current_user_id,
        Message.created_at >= today_start,
        Message.created_at < today_end
    ).count()
    
    conv_count = ConversationMember.query.filter_by(user_id=current_user_id).count()
    
    # Calculate storage usage from messages with file_size
    image_storage = db.session.query(db.func.coalesce(db.func.sum(Message.file_size), 0)).filter(
        Message.sender_id == current_user_id,
        Message.message_type == 'image',
        Message.file_size.isnot(None)
    ).scalar() or 0
    
    file_storage = db.session.query(db.func.coalesce(db.func.sum(Message.file_size), 0)).filter(
        Message.sender_id == current_user_id,
        Message.message_type == 'file',
        Message.file_size.isnot(None)
    ).scalar() or 0
    
    return jsonify(build_success_response(
        message='Package limits loaded.',
        package=user.package,
        limits={
            'max_friends': limits['max_friends'],
            'max_conversations': limits['max_conversations'],
            'max_messages_per_day': limits['max_messages_per_day'],
            'max_image_size_mb': limits['max_image_size_mb'],
            'max_file_size_mb': limits['max_file_size_mb'],
            'can_file_share': limits['can_file_share'],
            'can_message_history': limits['can_message_history'],
            'can_custom_emoji': limits['can_custom_emoji'],
        },
        usage={
            'friends': friend_count,
            'conversations': conv_count,
            'messages_today': msg_count_today,
            'image_storage': image_storage,
            'file_storage': file_storage,
        }
    )), 200


@social_bp.route('/friends', methods=['GET'])
@require_auth
def get_friends():
    """Get the current user's friend list."""
    current_user_id = g.user.get('userId')

    friend_links = Friend.query.filter_by(user_id=current_user_id).all()
    friend_ids = [f.friend_id for f in friend_links]

    # Get online status from the user_sessions map (handled by socketio)
    # For now, return basic info
    friends_data = []
    for fid in friend_ids:
        friend = User.query.get(fid)
        if friend:
            fd = friend.to_dict()
            fd['is_online'] = False  # Will be updated via WebSocket
            friends_data.append(fd)

    return jsonify(build_success_response(message='Friends list loaded.', friends=friends_data)), 200


@social_bp.route('/friends/pending', methods=['GET'])
@require_auth
def get_pending_requests():
    """Get all pending friend requests for the current user (received)."""
    current_user_id = g.user.get('userId')

    requests = FriendRequest.query.filter_by(
        receiver_id=current_user_id,
        status='PENDING'
    ).order_by(FriendRequest.created_at.desc()).all()

    results = []
    for req in requests:
        d = req.to_dict()
        sender = User.query.get(req.sender_id)
        if sender:
            d['sender'] = sender.to_dict()
        results.append(d)

    return jsonify(build_success_response(message='Pending requests loaded.', requests=results)), 200


# ============================================================
# CONVERSATIONS
# ============================================================
@social_bp.route('/conversations', methods=['GET'])
@require_auth
def get_conversations():
    """Get all conversations for the current user."""
    current_user_id = g.user.get('userId')

    memberships = ConversationMember.query.filter_by(user_id=current_user_id).order_by(
        ConversationMember.joined_at.desc()
    ).all()

    conversations = []
    for m in memberships:
        conv = Conversation.query.get(m.conversation_id)
        if conv:
            conv_data = conv.to_dict(current_user_id)
            # Get last message
            last_msg = Message.query.filter_by(conversation_id=conv.id).order_by(Message.created_at.desc()).first()
            if last_msg:
                conv_data['last_message'] = last_msg.to_dict()
            else:
                conv_data['last_message'] = None
            conversations.append(conv_data)

    return jsonify(build_success_response(message='Conversations loaded.', conversations=conversations)), 200


# ============================================================
# MESSAGES
# ============================================================
@social_bp.route('/messages/<conversation_id>', methods=['GET'])
@require_auth
def get_messages(conversation_id):
    """Get messages for a conversation (paginated, latest first)."""
    current_user_id = g.user.get('userId')

    # Verify user is member of this conversation
    member = ConversationMember.query.filter_by(
        conversation_id=conversation_id,
        user_id=current_user_id
    ).first()
    if not member:
        return jsonify(build_error_response('FORBIDDEN', 'You are not a member of this conversation.')), 403

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 100)

    messages = Message.query.filter_by(conversation_id=conversation_id).order_by(
        Message.created_at.desc()
    ).offset((page - 1) * per_page).limit(per_page).all()

    # Return in chronological order
    messages.reverse()

    return jsonify(build_success_response(
        message='Messages loaded.',
        messages=[m.to_dict() for m in messages]
    )), 200


@social_bp.route('/messages', methods=['POST'])
@require_auth
@require_message_limit
@rate_limit('default')
def send_message():
    """Send a message to a conversation."""
    current_user_id = g.user.get('userId')
    data = request.get_json() or {}
    conversation_id = data.get('conversation_id')
    content = data.get('content', '').strip()
    message_type = data.get('message_type', 'text')

    if not conversation_id:
        return jsonify(build_error_response('VALIDATION_ERROR', 'conversation_id is required.')), 400

    if not content:
        return jsonify(build_error_response('VALIDATION_ERROR', 'Message content is required.')), 400

    # Verify user is member
    member = ConversationMember.query.filter_by(
        conversation_id=conversation_id,
        user_id=current_user_id
    ).first()
    if not member:
        return jsonify(build_error_response('FORBIDDEN', 'You are not a member of this conversation.')), 403

    msg = Message(
        conversation_id=conversation_id,
        sender_id=current_user_id,
        content=content,
        message_type=message_type,
        file_size=data.get('file_size', None)
    )
    db.session.add(msg)

    # Update conversation updated_at
    conv = Conversation.query.get(conversation_id)
    if conv:
        conv.updated_at = datetime.utcnow()

    db.session.commit()

    log_audit_event('MESSAGE_SEND', 'SUCCESS', current_user_id, details={'conversation_id': conversation_id})

    return jsonify(build_success_response(message='Message sent.', **msg.to_dict())), 201


@social_bp.route('/upload', methods=['POST'])
@require_auth
def upload_file():
    """Upload a file/image for chat messages via Sanity CDN."""
    from services.user_service import UserService
    from package_limits import get_user_limits
    
    current_user_id = g.user.get('userId')
    user = UserService.find_by_id(current_user_id)
    if not user:
        return jsonify(build_error_response("USER_NOT_FOUND", "User not found.")), 404
    
    limits = get_user_limits(user)
    if not limits.get('can_file_share', False) and user.package == 'free':
        return jsonify(build_error_response("LIMIT_REACHED", "Gói Free không hỗ trợ gửi file. Hãy nâng cấp gói Pro hoặc Enterprise.")), 403
    
    if 'file' not in request.files:
        return jsonify(build_error_response("NO_FILE", "No file provided.")), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify(build_error_response("NO_FILE", "No file selected.")), 400
    
    if not allowed_file(file.filename):
        return jsonify(build_error_response("INVALID_FILE", f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")), 400
    
    # Read file and get extension
    original_name = file.filename
    ext = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else 'bin'
    
    # Check file size based on type (image vs file)
    is_image = ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    max_size_mb = limits['max_image_size_mb'] if is_image else limits['max_file_size_mb']
    max_size = max_size_mb * 1024 * 1024
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > max_size:
        type_label = 'ảnh' if is_image else 'file'
        return jsonify(build_error_response(
            "FILE_TOO_LARGE", 
            f"{type_label.capitalize()} quá lớn. Giới hạn cho gói {user.package} là {max_size_mb}MB ({max_size_mb//1024}GB)."
        )), 413
    
    # Read file data
    file_data = file.read()
    base64_data = base64.b64encode(file_data).decode('utf-8')
    
    # Determine mime prefix
    mime_map = {
        'png': 'data:image/png;base64,',
        'jpg': 'data:image/jpeg;base64,',
        'jpeg': 'data:image/jpeg;base64,',
        'gif': 'data:image/gif;base64,',
        'webp': 'data:image/webp;base64,',
    }
    mime_prefix = mime_map.get(ext, '')
    
    try:
        # Upload to Sanity CDN
        sanity_url = SanityService.upload_image(
            f"{mime_prefix}{base64_data}",
            filename=original_name
        )
        file_url = sanity_url
        log_audit_event('FILE_UPLOAD_SANITY', 'SUCCESS', current_user_id, details={'filename': original_name, 'size': file_size})
    except Exception as e:
        # Fallback: save locally if Sanity fails
        print(f"[Upload] Sanity upload failed: {str(e)}, falling back to local storage")
        upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        unique_name = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join(upload_folder, unique_name)
        with open(file_path, 'wb') as f:
            f.write(file_data)
        file_url = f"/uploads/{unique_name}"
        log_audit_event('FILE_UPLOAD_LOCAL', 'SUCCESS', current_user_id, details={'filename': original_name, 'size': file_size})
    
    return jsonify(build_success_response(
        message='File uploaded successfully.',
        url=file_url,
        filename=original_name,
        size=file_size,
        message_type='image' if ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'} else 'file'
    )), 201


@social_bp.route('/messages/read/<message_id>', methods=['POST'])
@require_auth
def mark_message_read(message_id):
    """Mark a message as read."""
    current_user_id = g.user.get('userId')

    msg = Message.query.get(message_id)
    if not msg:
        return jsonify(build_error_response('NOT_FOUND', 'Message not found.')), 404

    # Check user is member of conversation
    member = ConversationMember.query.filter_by(
        conversation_id=msg.conversation_id,
        user_id=current_user_id
    ).first()
    if not member:
        return jsonify(build_error_response('FORBIDDEN', 'You are not a member of this conversation.')), 403

    # Don't mark own messages as read
    if msg.sender_id == current_user_id:
        return jsonify(build_success_response(message='Cannot mark own message as read.')), 200

    # Check if already read
    existing = MessageRead.query.filter_by(message_id=message_id, user_id=current_user_id).first()
    if existing:
        return jsonify(build_success_response(message='Already marked as read.', read=existing.to_dict())), 200

    read = MessageRead(message_id=message_id, user_id=current_user_id)
    db.session.add(read)
    db.session.commit()

    return jsonify(build_success_response(message='Message marked as read.', read=read.to_dict())), 200