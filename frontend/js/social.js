/**
 * Social Features - Search, Friends, Chat
 * Requires: config.js, utils.js, api.js, auth.js
 */

// ============================================================
// SOCKET.IO CONNECTION
// ============================================================
let socket = null;
let socialState = {
    onlineUsers: {},
    currentChat: null,
    typingTimeout: null,
};

function initSocket() {
    if (socket && socket.connected) return;

    const token = sessionStorage.getItem(CONFIG.TOKEN.ACCESS_TOKEN_KEY);
    if (!token) return;

    const url = CONFIG.SOCKET.URL || CONFIG.API_BASE_URL;
    socket = io(url, {
        path: CONFIG.SOCKET.PATH,
        query: { token },
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
    });

    socket.on('connect', function() {
        console.log('[Socket] Connected');
    });

    socket.on('disconnect', function() {
        console.log('[Socket] Disconnected');
    });

    socket.on('connect_error', function(err) {
        console.error('[Socket] Connection error:', err.message);
    });

    // Online/Offline events
    socket.on('online_users', function(data) {
        if (data.online_user_ids) {
            data.online_user_ids.forEach(function(uid) {
                socialState.onlineUsers[uid] = true;
            });
            updateOnlineStatusUI();
        }
    });

    socket.on('user_online', function(data) {
        if (data.user_id) {
            socialState.onlineUsers[data.user_id] = true;
            updateOnlineStatusUI();
        }
    });

    socket.on('user_offline', function(data) {
        if (data.user_id) {
            delete socialState.onlineUsers[data.user_id];
            updateOnlineStatusUI();
        }
    });

    // Friend request notifications
    socket.on('notification', function(data) {
        if (data.type === 'friend_request') {
            showFriendRequestNotification(data);
            loadPendingRequests();
        } else if (data.type === 'friend_accepted') {
            Utils.showToast(data.accepter.username + ' accepted your friend request!', 'success');
            loadFriends();
            loadConversations();
        } else if (data.type === 'new_message') {
            // Update conversation list
            loadConversations();
            // If currently chatting with this person, add message
            if (socialState.currentChat && socialState.currentChat.conversation_id === data.conversation_id) {
                // Message will be added via new_message event
            } else {
                // Show notification badge
                showMessageNotification(data);
            }
        }
    });

    // New message event
    socket.on('new_message', function(msg) {
        if (socialState.currentChat && socialState.currentChat.conversation_id === msg.conversation_id) {
            appendMessage(msg);
            // Mark as read
            socket.emit('mark_read', { message_id: msg.id });
        }
        loadConversations();
    });

    // Message sent confirmation - append to chat for sender
    socket.on('message_sent', function(msg) {
        if (socialState.currentChat && socialState.currentChat.conversation_id === msg.conversation_id) {
            appendMessage(msg);
        }
        loadConversations();
    });

    // Typing indicator
    socket.on('typing_indicator', function(data) {
        if (socialState.currentChat && socialState.currentChat.conversation_id === data.conversation_id) {
            showTypingIndicator(data.user_id, data.is_typing);
        }
    });

    // Message read
    socket.on('message_read', function(data) {
        updateMessageReadStatus(data.message_id, data.user_id);
    });
}

function disconnectSocket() {
    if (socket) {
        socket.disconnect();
        socket = null;
    }
}

// ============================================================
// USER SEARCH
// ============================================================
let searchTimeout = null;

function initUserSearch() {
    console.log('[Search] initUserSearch called');
    // Support both old (user-search-input) and new (msg-search-input) IDs
    var input = document.getElementById('user-search-input') || document.getElementById('msg-search-input');
    if (!input) {
        console.log('[Search] No input found');
        return;
    }
    console.log('[Search] Input found, id=' + input.id);

    input.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        var q = this.value.trim();
        if (q.length < 1) {
            var oldResults = document.getElementById('search-results');
            var newResults = document.getElementById('msg-search-results');
            if (oldResults) oldResults.innerHTML = '';
            if (newResults) { newResults.innerHTML = ''; newResults.classList.remove('show'); }
            return;
        }
        searchTimeout = setTimeout(function() {
            searchUsers(q);
        }, 200); // faster response
    });
}

async function searchUsers(q) {
    try {
        var data = await ApiClient.get(CONFIG.SOCIAL.SEARCH + '?q=' + encodeURIComponent(q) + '&page=1&per_page=20');
        if (!data.success) throw data;
        renderSearchResults(data.users || []);
    } catch (err) {
        console.error('Search error:', err);
    }
}

function renderSearchResults(users) {
    // Check if we're using new HTML (msg-search-results) or old HTML (search-results)
    var container = document.getElementById('msg-search-results');
    var isNewHtml = !!container;
    
    if (!container) {
        container = document.getElementById('search-results');
    }
    if (!container) return;
    
    if (isNewHtml) {
        container.classList.add('show');
    }

    if (users.length === 0) {
        if (isNewHtml) {
            container.innerHTML = '<div class="msg-search-item" style="justify-content:center;color:var(--color-text-tertiary);font-size:13px;cursor:default;">Không tìm thấy người dùng</div>';
        } else {
            container.innerHTML = '<div class="empty-state" style="padding:var(--space-4)"><div class="empty-state-title">No users found</div></div>';
        }
        return;
    }

    if (isNewHtml) {
        // Zalo-style results
        container.innerHTML = users.map(function(u) {
            var avatarLetter = (u.display_name || u.username || '?')[0].toUpperCase();
            var actionBtn = '';
            if (u.friend_status === 'none' || u.friend_status === 'declined') {
                actionBtn = '<button class="s-add-btn" onclick="sendFriendRequest(\'' + u.id + '\', this)">Kết bạn</button>';
            } else if (u.friend_status === 'pending_sent') {
                actionBtn = '<button class="s-add-btn" style="opacity:0.5;cursor:default;" disabled>Đã gửi</button>';
            } else if (u.friend_status === 'pending_received') {
                actionBtn = '<button class="s-add-btn" style="opacity:0.5;cursor:default;" disabled>Đã nhận</button>';
            } else if (u.friend_status === 'friends') {
                actionBtn = '<button class="s-add-btn" style="background:var(--color-success);" onclick="openChat(\'' + u.id + '\')">Chat</button>';
            }

            return '<div class="msg-search-item">' +
                '<div class="s-avatar">' + avatarLetter + '</div>' +
                '<div class="s-info">' +
                    '<div class="s-name">' + Utils.escapeHtml(u.display_name || u.username) + '</div>' +
                    '<div class="s-email">@' + Utils.escapeHtml(u.username) + '</div>' +
                '</div>' +
                actionBtn +
            '</div>';
        }).join('');
    } else {
        // Old style results
        container.innerHTML = users.map(function(u) {
            var avatarHtml = u.avatar_url
                ? '<img src="' + Utils.escapeHtml(u.avatar_url) + '" alt="" class="social-avatar-img">'
                : '<div class="social-avatar-text">' + (u.username || '?')[0].toUpperCase() + '</div>';

            var statusClass = socialState.onlineUsers[u.id] ? 'online' : 'offline';
            var statusText = socialState.onlineUsers[u.id] ? 'Online' : 'Offline';

            var actionBtn = '';
            if (u.friend_status === 'none' || u.friend_status === 'declined') {
                actionBtn = '<button class="btn btn-primary btn-sm" onclick="sendFriendRequest(\'' + u.id + '\')">+ Kết bạn</button>';
            } else if (u.friend_status === 'pending_sent') {
                actionBtn = '<button class="btn btn-ghost btn-sm" onclick="cancelFriendRequest(\'' + u.id + '\')" style="color:var(--color-warning)">Đã gửi</button>';
            } else if (u.friend_status === 'pending_received') {
                actionBtn = '<button class="btn btn-ghost btn-sm" disabled style="color:var(--color-info)">Đã gửi cho bạn</button>';
            } else if (u.friend_status === 'friends') {
                actionBtn = '<button class="btn btn-ghost btn-sm" onclick="openChat(\'' + u.id + '\')" style="color:var(--color-success)">Chat</button>';
            }

            return '<div class="search-result-item">' +
                '<div class="social-avatar ' + statusClass + '">' + avatarHtml + '</div>' +
                '<div class="search-result-info">' +
                    '<div class="search-result-name">' + Utils.escapeHtml(u.display_name || u.username) + '</div>' +
                    '<div class="search-result-username">@' + Utils.escapeHtml(u.username) + '</div>' +
                '</div>' +
                '<div class="search-result-status ' + statusClass + '">' + statusText + '</div>' +
                '<div class="search-result-action">' + actionBtn + '</div>' +
            '</div>';
        }).join('');
    }
}

// ============================================================
// FRIEND REQUESTS
// ============================================================
// Support both: sendFriendRequest(userId) and sendFriendRequest(userId, btn)
async function sendFriendRequest(receiverId, btn) {
    try {
        var data = await ApiClient.post(CONFIG.SOCIAL.FRIEND_REQUEST, { receiver_id: receiverId });
        if (!data.success) throw data;
        Utils.showToast('Friend request sent!', 'success');
        // Update button state if provided
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Đã gửi';
            btn.style.opacity = '0.5';
        }
        // Notify via socket
        if (socket && socket.connected) {
            socket.emit('friend_request_sent', {
                receiver_id: receiverId,
                request_id: data.friend_request ? data.friend_request.id : null
            });
        }
        // Refresh search
        var input = document.getElementById('user-search-input') || document.getElementById('msg-search-input');
        if (input && input.value.trim()) {
            searchUsers(input.value.trim());
        }
    } catch (err) {
        Utils.showToast(err.message || 'Failed to send request.', 'error');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Kết bạn';
        }
    }
}

async function cancelFriendRequest(receiverId) {
    // Find the request ID first
    try {
        var data = await ApiClient.get(CONFIG.SOCIAL.PENDING_REQUESTS);
        if (!data.success) throw data;
        var requests = data.requests || [];
        var req = requests.find(function(r) { return r.sender_id === receiverId; });
        if (req) {
            var delData = await ApiClient.delete(CONFIG.SOCIAL.FRIEND_CANCEL + '/' + req.id);
            if (!delData.success) throw delData;
            Utils.showToast('Request cancelled.', 'info');
            var input = document.getElementById('user-search-input');
            if (input && input.value.trim()) {
                searchUsers(input.value.trim());
            }
        }
    } catch (err) {
        Utils.showToast(err.message || 'Failed to cancel.', 'error');
    }
}

async function acceptFriendRequest(requestId) {
    try {
        var data = await ApiClient.post(CONFIG.SOCIAL.FRIEND_ACCEPT + '/' + requestId, {});
        if (!data.success) throw data;
        Utils.showToast('Friend request accepted!', 'success');
        // Notify sender via socket
        if (socket && socket.connected) {
            socket.emit('friend_request_accepted', {
                sender_id: data.friend_request ? data.friend_request.sender_id : null,
                conversation_id: data.conversation ? data.conversation.id : null
            });
        }
        loadPendingRequests();
        loadFriends();
        loadConversations();
    } catch (err) {
        Utils.showToast(err.message || 'Failed to accept.', 'error');
    }
}

async function declineFriendRequest(requestId) {
    try {
        var data = await ApiClient.post(CONFIG.SOCIAL.FRIEND_DECLINE + '/' + requestId, {});
        if (!data.success) throw data;
        Utils.showToast('Request declined.', 'info');
        loadPendingRequests();
    } catch (err) {
        Utils.showToast(err.message || 'Failed to decline.', 'error');
    }
}

async function removeFriend(friendId) {
    if (!confirm('Remove this friend?')) return;
    try {
        var data = await ApiClient.delete(CONFIG.SOCIAL.FRIEND_REMOVE + '/' + friendId);
        if (!data.success) throw data;
        Utils.showToast('Friend removed.', 'info');
        loadFriends();
        loadConversations();
    } catch (err) {
        Utils.showToast(err.message || 'Failed to remove.', 'error');
    }
}

// ============================================================
// LOAD DATA
// ============================================================
async function loadPendingRequests() {
    try {
        var data = await ApiClient.get(CONFIG.SOCIAL.PENDING_REQUESTS);
        if (!data.success) throw data;
        renderPendingRequests(data.requests || []);
    } catch (err) {
        console.error('Load pending requests error:', err);
    }
}

function renderPendingRequests(requests) {
    var container = document.getElementById('msg-requests-list') || document.getElementById('pending-requests-list');
    if (!container) return;

    var badge = document.getElementById('msg-notif-badge');
    if (badge) {
        badge.textContent = requests.length;
        badge.style.display = requests.length > 0 ? 'inline' : 'none';
    }

    if (requests.length === 0) {
        container.innerHTML = '<div class="msg-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg><div class="e-title">Không có thông báo</div></div>';
        return;
    }

    container.innerHTML = requests.map(function(req) {
        var sender = req.sender || {};
        var displayName = sender.display_name || sender.username || 'User';
        var avatarLetter = displayName.charAt(0).toUpperCase();

        return '<div class="friend-req-item">' +
            '<div class="msg-item-avatar">' +
                '<div class="avatar-text" style="background:var(--msg-blue);">' + avatarLetter + '</div>' +
            '</div>' +
            '<div class="req-info">' +
                '<div class="req-name">' + Utils.escapeHtml(displayName) + '</div>' +
                '<div class="req-text">Đã gửi lời mời kết bạn</div>' +
            '</div>' +
            '<div class="req-actions">' +
                '<button class="req-accept" onclick="acceptFriendRequest(\'' + req.id + '\')">Chấp nhận</button>' +
                '<button class="req-decline" onclick="declineFriendRequest(\'' + req.id + '\')">Từ chối</button>' +
            '</div>' +
        '</div>';
    }).join('');
}

async function loadFriends() {
    try {
        var data = await ApiClient.get(CONFIG.SOCIAL.FRIENDS);
        if (!data.success) throw data;
        renderFriends(data.friends || []);
    } catch (err) {
        console.error('Load friends error:', err);
    }
}

function renderFriends(friends) {
    var container = document.getElementById('msg-friends-list') || document.getElementById('friends-list');
    if (!container) return;

    if (friends.length === 0) {
        container.innerHTML = '<div class="msg-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg><div class="e-title">Chưa có bạn bè</div><div class="e-desc">Tìm kiếm và gửi lời mời kết bạn</div></div>';
        return;
    }

    container.innerHTML = friends.map(function(f) {
        var displayName = f.display_name || f.username || 'User';
        var avatarLetter = displayName.charAt(0).toUpperCase();
        var isOnline = socialState.onlineUsers[f.id];
        var avatarHtml = f.avatar_url
            ? '<img src="' + Utils.escapeHtml(f.avatar_url) + '" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">'
            : '<div class="avatar-text">' + avatarLetter + '</div>';

        return '<div class="msg-item">' +
            '<div class="msg-item-avatar" onclick="openChat(\'' + f.id + '\')">' +
                avatarHtml +
                (isOnline ? '<div class="online-dot"></div>' : '') +
            '</div>' +
            '<div class="msg-item-info" onclick="openChat(\'' + f.id + '\')">' +
                '<div class="msg-item-name">' + Utils.escapeHtml(displayName) + '</div>' +
                '<div class="msg-item-preview" style="color:var(--color-success);">' + (isOnline ? 'Đang hoạt động' : 'Ngoại tuyến') + '</div>' +
            '</div>' +
            '<button class="friend-action-btn" onclick="removeFriend(\'' + f.id + '\')" title="Remove">Xóa bạn</button>' +
        '</div>';
    }).join('');
}

// ============================================================
// CONVERSATIONS
// ============================================================
async function loadConversations() {
    try {
        var data = await ApiClient.get(CONFIG.SOCIAL.CONVERSATIONS);
        if (!data.success) throw data;
        renderConversations(data.conversations || []);
    } catch (err) {
        console.error('Load conversations error:', err);
    }
}

function renderConversations(conversations) {
    var container = document.getElementById('msg-conversations-list') || document.getElementById('conversations-list');
    if (!container) return;

    if (conversations.length === 0) {
        container.innerHTML = '<div class="msg-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg><div class="e-title">Chưa có cuộc trò chuyện</div><div class="e-desc">Kết bạn để bắt đầu nhắn tin</div></div>';
        return;
    }

    container.innerHTML = conversations.map(function(c) {
        var other = c.other_user || {};
        var displayName = other.display_name || other.username || 'User';
        var avatarLetter = displayName.charAt(0).toUpperCase();
        var lastMsg = c.last_message || {};
        var lastMsgText = lastMsg.content ? (lastMsg.content.length > 30 ? lastMsg.content.substring(0, 30) + '...' : lastMsg.content) : 'Chưa có tin nhắn';
        var timeText = lastMsg.created_at ? Utils.formatDate(lastMsg.created_at) : '';
        var isOnline = socialState.onlineUsers[other.id];
        var avatarHtml = other.avatar_url
            ? '<img src="' + Utils.escapeHtml(other.avatar_url) + '" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">'
            : '<div class="avatar-text">' + avatarLetter + '</div>';

        return '<div class="msg-item" onclick="openConversation(\'' + c.id + '\')">' +
            '<div class="msg-item-avatar">' +
                avatarHtml +
                (isOnline ? '<div class="online-dot"></div>' : '') +
            '</div>' +
            '<div class="msg-item-info">' +
                '<div class="msg-item-name">' + Utils.escapeHtml(displayName) + '</div>' +
                '<div class="msg-item-preview">' + Utils.escapeHtml(lastMsgText) + '</div>' +
            '</div>' +
            '<div class="msg-item-meta">' +
                '<span class="msg-item-time">' + timeText + '</span>' +
            '</div>' +
        '</div>';
    }).join('');
}

// ============================================================
// CHAT
// ============================================================
async function openChat(friendId) {
    // Find or create conversation with this friend
    try {
        var data = await ApiClient.get(CONFIG.SOCIAL.CONVERSATIONS);
        if (!data.success) throw data;
        var conversations = data.conversations || [];
        var conv = conversations.find(function(c) {
            return c.other_user && c.other_user.id === friendId;
        });
        if (conv) {
            openConversation(conv.id);
        } else {
            Utils.showToast('No conversation found. Please add friend first.', 'info');
        }
    } catch (err) {
        console.error('Open chat error:', err);
    }
}

async function openConversation(conversationId) {
    socialState.currentChat = { conversation_id: conversationId };

    // Sync with inline script variable
    if (typeof currentConversationId !== 'undefined') {
        window.currentConversationId = conversationId;
    }

    // Show chat header + input area
    var chatHeader = document.getElementById('msg-chat-header');
    var inputArea = document.getElementById('msg-input-area');
    if (chatHeader) chatHeader.style.display = 'flex';
    if (inputArea) inputArea.style.display = 'flex';

    // Try to update chat header with partner info from conversations data
    try {
        var convData = await ApiClient.get(CONFIG.SOCIAL.CONVERSATIONS);
        if (convData.success && convData.conversations) {
            var conv = convData.conversations.find(function(c) {
                return c.id === conversationId;
            });
            if (conv && conv.other_user) {
                var partner = conv.other_user;
                var displayName = partner.display_name || partner.username || 'User';
                var avatarEl = document.getElementById('msg-ch-avatar');
                var nameEl = document.getElementById('msg-ch-name');
                var statusEl = document.getElementById('msg-ch-status');
                
                if (avatarEl) {
                    if (partner.avatar_url) {
                        avatarEl.innerHTML = '<img src="' + Utils.escapeHtml(partner.avatar_url) + '" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">';
                    } else {
                        avatarEl.innerHTML = displayName.charAt(0).toUpperCase();
                        avatarEl.style.background = 'linear-gradient(135deg, var(--msg-blue), #0050c0)';
                        avatarEl.style.color = '#fff';
                    }
                }
                if (nameEl) nameEl.textContent = displayName;
                if (statusEl) {
                    var isOnline = socialState.onlineUsers[partner.id];
                    statusEl.textContent = isOnline ? 'Đang hoạt động' : 'Ngoại tuyến';
                    statusEl.className = 'ch-status' + (isOnline ? ' online' : '');
                }
            }
        }
    } catch (e) {
        // Silent fail, header shows defaults
    }

    // Load messages
    await loadMessages(conversationId);

    // Focus input
    var input = document.getElementById('msg-chat-input');
    if (input) input.focus();
}

async function loadMessages(conversationId) {
    try {
        var data = await ApiClient.get(CONFIG.SOCIAL.MESSAGES + '/' + conversationId + '?page=1&per_page=50');
        if (!data.success) throw data;
        renderMessages(data.messages || []);
    } catch (err) {
        console.error('Load messages error:', err);
    }
}

// Shared helper: render message content (text/image/file)
function renderMessageContent(message) {
    if (message.message_type === 'image') {
        return '<img src="' + Utils.escapeHtml(message.content) + '" alt="Image" class="chat-image" onclick="window.open(this.src)" style="max-width:280px;border-radius:8px;cursor:pointer;display:block;">';
    } else if (message.message_type === 'file') {
        var fileName = message.content.split('/').pop();
        return '<a href="' + Utils.escapeHtml(message.content) + '" target="_blank" class="chat-file-link" style="display:flex;align-items:center;gap:8px;color:inherit;text-decoration:none;">' +
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>' +
            '<span style="text-decoration:underline;">' + Utils.escapeHtml(fileName) + '</span></a>';
    }
    return Utils.escapeHtml(message.content);
}

// Shared helper: render a single message bubble (Zalo/Messenger style)
function renderMessageBubble(msg, currentUserId) {
    var isMine = msg.sender_id === currentUserId;
    var rowClass = isMine ? 'm-row mine' : 'm-row other';
    var timeStr = Utils.formatDate(msg.created_at);
    var contentHtml = renderMessageContent(msg);

    return '<div class="' + rowClass + '" data-msg-id="' + msg.id + '">' +
        '<div class="m-bubble">' +
            contentHtml +
            '<span class="m-time">' + timeStr + '</span>' +
        '</div>' +
    '</div>';
}

function renderMessages(messages) {
    var container = document.getElementById('msg-messages') || document.getElementById('chat-messages');
    if (!container) return;

    var currentUserId = Auth._user ? Auth._user.id : null;

    if (messages.length === 0) {
        container.innerHTML = '<div class="msg-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg><div class="e-title">Chưa có tin nhắn</div><div class="e-desc">Hãy gửi tin nhắn đầu tiên</div></div>';
        return;
    }

    container.innerHTML = messages.map(function(m) {
        return renderMessageBubble(m, currentUserId);
    }).join('');

    // Auto scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function appendMessage(msg) {
    var container = document.getElementById('msg-messages') || document.getElementById('chat-messages');
    if (!container) return;

    var currentUserId = Auth._user ? Auth._user.id : null;

    // Remove empty state if present
    var emptyState = container.querySelector('.msg-empty');
    if (emptyState) container.innerHTML = '';

    var html = renderMessageBubble(msg, currentUserId);

    container.insertAdjacentHTML('beforeend', html);
    container.scrollTop = container.scrollHeight;
}

function sendChatMessage() {
    var input = document.getElementById('msg-chat-input') || document.getElementById('chat-input');
    if (!input) return;

    var content = input.value.trim();
    if (!content || !socialState.currentChat) return;

    // Send via socket for realtime
    if (socket && socket.connected) {
        socket.emit('send_message', {
            conversation_id: socialState.currentChat.conversation_id,
            content: content,
            message_type: 'text'
        });
    } else {
        // Fallback to REST API
        ApiClient.post(CONFIG.SOCIAL.MESSAGES, {
            conversation_id: socialState.currentChat.conversation_id,
            content: content,
            message_type: 'text'
        }).then(function(data) {
            if (data.success) {
                // Build message object from response (API spreads msg.to_dict() into response)
                var msg = {
                    id: data.id,
                    conversation_id: data.conversation_id,
                    sender_id: data.sender_id,
                    content: data.content,
                    message_type: data.message_type || 'text',
                    created_at: data.created_at,
                    sender: data.sender,
                    reads: data.reads || []
                };
                appendMessage(msg);
                loadConversations();
            }
        }).catch(function(err) {
            Utils.showToast(err.message || 'Failed to send.', 'error');
        });
    }

    input.value = '';
    input.focus();
}

function handleChatKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
    }
}

// ============================================================
// FILE UPLOAD
// ============================================================
async function uploadChatFile(input) {
    if (!input.files || !input.files[0] || !socialState.currentChat) return;
    
    var file = input.files[0];
    var formData = new FormData();
    formData.append('file', file);
    
    try {
        var data = await ApiClient.post(CONFIG.SOCIAL.UPLOAD, formData);
        if (!data.success) throw data;
        
        // Send the uploaded file URL as a message
        var msgType = data.message_type || 'file';
        var content = data.url;
        
        if (socket && socket.connected) {
            socket.emit('send_message', {
                conversation_id: socialState.currentChat.conversation_id,
                content: content,
                message_type: msgType
            });
        } else {
            await ApiClient.post(CONFIG.SOCIAL.MESSAGES, {
                conversation_id: socialState.currentChat.conversation_id,
                content: content,
                message_type: msgType
            });
        }
        
        Utils.showToast('File sent!', 'success');
    } catch (err) {
        Utils.showToast(err.message || 'Failed to upload file.', 'error');
    }
    
    input.value = '';
}

// ============================================================
// TYPING INDICATOR
// ============================================================
function handleChatInput() {
    if (!socket || !socket.connected || !socialState.currentChat) return;

    socket.emit('typing', {
        conversation_id: socialState.currentChat.conversation_id,
        is_typing: true
    });

    clearTimeout(socialState.typingTimeout);
    socialState.typingTimeout = setTimeout(function() {
        if (socket && socket.connected && socialState.currentChat) {
            socket.emit('typing', {
                conversation_id: socialState.currentChat.conversation_id,
                is_typing: false
            });
        }
    }, 2000);
}

function showTypingIndicator(userId, isTyping) {
    var container = document.getElementById('typing-indicator');
    if (!container) return;

    if (isTyping) {
        container.textContent = 'Someone is typing...';
        container.style.display = 'block';
    } else {
        container.style.display = 'none';
    }
}

function updateMessageReadStatus(messageId, userId) {
    var indicators = document.querySelectorAll('.chat-read-indicator');
    indicators.forEach(function(el) {
        el.textContent = '✓✓';
    });
}

function updateOnlineStatusUI() {
    // Update all online/offline indicators in the DOM
    document.querySelectorAll('.social-avatar').forEach(function(el) {
        var parent = el.closest('[data-user-id]');
        if (parent) {
            var uid = parent.getAttribute('data-user-id');
            if (socialState.onlineUsers[uid]) {
                el.classList.remove('offline');
                el.classList.add('online');
            } else {
                el.classList.remove('online');
                el.classList.add('offline');
            }
        }
    });

    // Update status text
    document.querySelectorAll('.friend-status, .search-result-status').forEach(function(el) {
        var parent = el.closest('[data-user-id]');
        if (parent) {
            var uid = parent.getAttribute('data-user-id');
            if (socialState.onlineUsers[uid]) {
                el.textContent = 'Online';
                el.className = el.className.replace(/offline/g, '') + ' online';
            } else {
                el.textContent = 'Offline';
                el.className = el.className.replace(/online/g, '') + ' offline';
            }
        }
    });
}

// ============================================================
// NOTIFICATIONS
// ============================================================
function showFriendRequestNotification(data) {
    var sender = data.sender || {};
    var name = sender.display_name || sender.username || 'Someone';
    Utils.showToast(name + ' đã gửi lời mời kết bạn!', 'info');
}

function showMessageNotification(data) {
    var title = data.title || 'New message';
    var body = data.body || '';
    Utils.showToast(title + ': ' + body, 'info');
}

// ============================================================
// INIT
// ============================================================
function initSocialFeatures() {
    initSocket();
    initUserSearch();
    loadPendingRequests();
    loadFriends();
    loadConversations();
}