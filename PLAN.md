# Social Features Implementation Plan

## Backend Changes

### 1. Install new dependencies
- flask-socketio
- eventlet (async server for SocketIO)

### 2. Database Models (models.py - APPEND only)
- FriendRequest: id, sender_id, receiver_id, status, created_at, updated_at
- Friend: id, user_id, friend_id, created_at  
- Conversation: id, created_at
- ConversationMember: id, conversation_id, user_id, joined_at
- Message: id, conversation_id, sender_id, content, message_type, created_at, updated_at
- MessageRead: id, message_id, user_id, read_at
- add `is_locked` column to User model (for disabled users)

### 3. New API Routes (routes_social.py)
- GET /api/users/search?q=&page=&per_page=
- POST /api/friends/request
- POST /api/friends/accept/<request_id>
- POST /api/friends/decline/<request_id>
- DELETE /api/friends/remove/<friend_id>
- GET /api/friends
- GET /api/friends/pending
- DELETE /api/friends/request/<request_id> (cancel)
- GET /api/conversations
- POST /api/messages
- GET /api/messages/<conversation_id>
- POST /api/messages/read/<message_id>

### 4. WebSocket (socketio_events.py)
- connect (authenticate)
- disconnect
- send_message
- typing
- seen

### 5. Update app.py
- Initialize SocketIO
- Register new blueprint

### 6. Frontend
- New: js/social.js (search, friends, chat logic)
- New: css/social.css (styles for social features)
- Update: dashboard.html (add sidebar sections + UI components)
- Update: config.js (add new API endpoints)
- Update: dashboard.css (add social styles)