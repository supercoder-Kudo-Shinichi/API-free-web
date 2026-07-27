from datetime import datetime
from flask import request
from flask_socketio import join_room, leave_room, emit
from services.token_service import TokenService
from models import db, User, Message, MessageRead, FriendRequest, Conversation, ConversationMember

# Online users map: {user_id: set(sid)}
online_users = {}
# Reverse map: {sid: user_id}
sid_to_user = {}


def register_socketio_events(socketio):

    @socketio.on('connect')
    def handle_connect():
        """Authenticate and register user as online."""
        token = request.args.get('token')
        if not token:
            print("[WS] Connection rejected: no token")
            return

        try:
            payload = TokenService.verify_access_token(token)
            user_id = payload.get('userId')
        except Exception as e:
            print(f"[WS] Connection rejected: invalid token - {str(e)}")
            return

        # Store connection
        sid = request.sid
        if user_id not in online_users:
            online_users[user_id] = set()
        online_users[user_id].add(sid)
        sid_to_user[sid] = user_id

        # Join user's personal room for notifications
        join_room(f'user_{user_id}')

        # Emit online status to all connected users
        emit('user_online', {'user_id': user_id}, broadcast=True)

        # Send current online users list to the newly connected user
        emit('online_users', {'online_user_ids': list(online_users.keys())})

        print(f"[WS] User {user_id} connected (sessions: {len(online_users[user_id])})")

    @socketio.on('disconnect')
    def handle_disconnect():
        """Remove user from online map."""
        sid = request.sid
        user_id = sid_to_user.pop(sid, None)

        if user_id and user_id in online_users:
            online_users[user_id].discard(sid)
            if not online_users[user_id]:
                del online_users[user_id]
                # Only broadcast offline if no more sessions
                emit('user_offline', {'user_id': user_id}, broadcast=True)
                print(f"[WS] User {user_id} disconnected (fully offline)")
            else:
                print(f"[WS] User {user_id} disconnected one session ({len(online_users[user_id])} remaining)")

    @socketio.on('send_message')
    def handle_send_message(data):
        """Handle real-time message sending."""
        sid = request.sid
        user_id = sid_to_user.get(sid)
        if not user_id:
            emit('error', {'message': 'Not authenticated'})
            return

        conversation_id = data.get('conversation_id')
        content = data.get('content', '').strip()
        message_type = data.get('message_type', 'text')

        if not conversation_id or not content:
            emit('error', {'message': 'Missing required fields'})
            return

        # Verify user is member
        member = ConversationMember.query.filter_by(
            conversation_id=conversation_id,
            user_id=user_id
        ).first()
        if not member:
            emit('error', {'message': 'Not a member of this conversation'})
            return

        # Create message
        msg = Message(
            conversation_id=conversation_id,
            sender_id=user_id,
            content=content,
            message_type=message_type
        )
        db.session.add(msg)

        # Update conversation timestamp
        conv = Conversation.query.get(conversation_id)
        if conv:
            conv.updated_at = datetime.utcnow()
        db.session.commit()

        msg_data = msg.to_dict()

        # Emit to all members of the conversation
        members = ConversationMember.query.filter_by(conversation_id=conversation_id).all()
        for m in members:
            if m.user_id != user_id:
                emit('new_message', msg_data, room=f'user_{m.user_id}')
                # Emit notification
                sender = User.query.get(user_id)
                if sender:
                    emit('notification', {
                        'type': 'new_message',
                        'title': sender.username,
                        'body': content[:50],
                        'conversation_id': conversation_id,
                        'sender': sender.to_dict()
                    }, room=f'user_{m.user_id}')

        # Also emit back to sender for confirmation
        emit('message_sent', msg_data, room=sid)

    @socketio.on('typing')
    def handle_typing(data):
        """Handle typing indicator."""
        sid = request.sid
        user_id = sid_to_user.get(sid)
        if not user_id:
            return

        conversation_id = data.get('conversation_id')
        is_typing = data.get('is_typing', True)

        if not conversation_id:
            return

        # Emit to other members
        members = ConversationMember.query.filter_by(conversation_id=conversation_id).all()
        for m in members:
            if m.user_id != user_id:
                emit('typing_indicator', {
                    'conversation_id': conversation_id,
                    'user_id': user_id,
                    'is_typing': is_typing
                }, room=f'user_{m.user_id}')

    @socketio.on('mark_read')
    def handle_mark_read(data):
        """Mark message as read."""
        sid = request.sid
        user_id = sid_to_user.get(sid)
        if not user_id:
            return

        message_id = data.get('message_id')
        if not message_id:
            return

        msg = Message.query.get(message_id)
        if not msg:
            return

        # Verify user is member
        member = ConversationMember.query.filter_by(
            conversation_id=msg.conversation_id,
            user_id=user_id
        ).first()
        if not member:
            return

        # Don't mark own messages
        if msg.sender_id == user_id:
            return

        # Create read receipt
        existing = MessageRead.query.filter_by(message_id=message_id, user_id=user_id).first()
        if not existing:
            read = MessageRead(message_id=message_id, user_id=user_id)
            db.session.add(read)
            db.session.commit()

            # Notify the sender
            emit('message_read', {
                'message_id': message_id,
                'user_id': user_id,
                'read_at': read.read_at.isoformat()
            }, room=f'user_{msg.sender_id}')

    @socketio.on('friend_request_sent')
    def handle_friend_request_sent(data):
        """Notify receiver about a new friend request."""
        sid = request.sid
        user_id = sid_to_user.get(sid)
        if not user_id:
            return

        receiver_id = data.get('receiver_id')
        request_id = data.get('request_id')

        if not receiver_id:
            return

        sender = User.query.get(user_id)
        if not sender:
            return

        emit('notification', {
            'type': 'friend_request',
            'request_id': request_id,
            'sender': sender.to_dict()
        }, room=f'user_{receiver_id}')

    @socketio.on('friend_request_accepted')
    def handle_friend_request_accepted(data):
        """Notify sender that their request was accepted."""
        sid = request.sid
        user_id = sid_to_user.get(sid)
        if not user_id:
            return

        sender_id = data.get('sender_id')
        if not sender_id:
            return

        accepter = User.query.get(user_id)
        if not accepter:
            return

        emit('notification', {
            'type': 'friend_accepted',
            'accepter': accepter.to_dict(),
            'conversation_id': data.get('conversation_id')
        }, room=f'user_{sender_id}')

    def get_online_users():
        """Return the current online users map (for API)."""
        return list(online_users.keys())