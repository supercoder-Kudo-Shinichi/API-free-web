# HỆ THỐNG XÁC THỰC AuthGuard - PHÂN TÍCH CHI TIẾT

> Phiên bản: 1.0
> Kiến trúc: Authentication Platform độc lập (giống Clerk)
> Mục tiêu: Cung cấp nền tảng xác thực tập trung cho mọi backend (Flask, Node.js, React, Django, ...)

---

## MỤC LỤC

1. [Tổng quan Kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Cấu trúc Source Code](#2-cấu-trúc-source-code)
3. [Database Schema & Constraints](#3-database-schema--constraints)
4. [Token System & Session Lifecycle](#4-token-system--session-lifecycle)
5. [Authentication Flows Chi Tiết](#5-authentication-flows-chi-tiết)
6. [Authorization Middleware](#6-authorization-middleware)
7. [Security Mechanisms](#7-security-mechanisms)
8. [API Endpoints Reference](#8-api-endpoints-reference)
9. [Frontend Auth Flow](#9-frontend-auth-flow)
10. [Cách Tích Hợp Cho Backend Khác](#10-cách-tích-hợp-cho-backend-khác)
11. [Error Codes & Response Format](#11-error-codes--response-format)
12. [Testing & Verification](#12-testing--verification)

---

## 1. TỔNG QUAN KIẾN TRÚC

### 1.1. Mô hình Authentication Platform

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           INTERNET                                       │
└─────────────────────────────────────────────────────────────────────────┘
         │                          │                          │
         ▼                          ▼                          ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────────────┐
│  User Browser    │   │  Mobile App      │   │  Third-party Client      │
│  (SPA Frontend)  │   │  (iOS/Android)   │   │  (Postman, curl, ...)    │
└────────┬─────────┘   └────────┬─────────┘   └──────────┬───────────────┘
         │                      │                         │
         └──────────────────────┼─────────────────────────┘
                                │
                                ▼
              ┌───────────────────────────────────────────────────┐
              │              AUTHGUARD PLATFORM                    │
              │              (Authentication Server)               │
              │                                                    │
              │  ┌──────────────┐  ┌──────────────────────────┐   │
              │  │  JWT Issuer  │  │  Session/Token Manager   │   │
              │  │  (HS256)     │  │  (Rotation + Replay)     │   │
              │  └──────────────┘  └──────────────────────────┘   │
              │  ┌──────────────┐  ┌──────────────────────────┐   │
              │  │  OAuth 2.0   │  │  User Profile Service    │   │
              │  │  (Google)    │  │  (CRUD + Link/Unlink)    │   │
              │  └──────────────┘  └──────────────────────────┘   │
              │  ┌──────────────┐  ┌──────────────────────────┐   │
              │  │  Rate Limiter│  │  Audit Logger            │   │
              │  │  (In-memory) │  │  (Event Tracking)        │   │
              │  └──────────────┘  └──────────────────────────┘   │
              └──────────────────────┬────────────────────────────┘
                                     │
                                     ▼
              ┌───────────────────────────────────────────────────┐
              │              RESOURCE SERVERS                      │
              │  (Your Backend: Flask, Node.js, Django, React...)  │
              │                                                    │
              │  Cách 1: Dùng chung JWT_SECRET để verify token     │
              │  Cách 2: Gọi API /api/auth/verify để xác thực      │
              │  Cách 3: Dùng middleware/thư viện verify JWT       │
              └───────────────────────────────────────────────────┘
```

### 1.2. Nguyên lý hoạt động

1. **AuthGuard Platform** là một service xác thực độc lập, chạy riêng biệt
2. **Client** (browser, mobile app) đăng nhập vào AuthGuard qua các phương thức:
   - Username + Password
   - Gmail + Password
   - Google OAuth
3. **AuthGuard** cấp:
   - **Access Token** (JWT, 15 phút) - dùng để gọi API đến Resource Server
   - **Refresh Token** (HttpOnly Cookie, 7 ngày) - dùng để lấy Access Token mới
4. **Resource Server** (backend của bạn) nhận JWT từ client, verify và cho phép truy cập
5. **Resource Server KHÔNG cần** lưu user/password - chỉ cần verify JWT

### 1.3. So sánh với Clerk

| Tính năng                  | Clerk                          | AuthGuard                       |
|----------------------------|--------------------------------|---------------------------------|
| Đăng nhập Username         | Có                             | Có                              |
| Đăng nhập Gmail            | Có                             | Có                              |
| Google OAuth               | Có                             | Có                              |
| JWT Access Token           | HS256/RS256                    | HS256                           |
| Refresh Token              | HttpOnly Cookie + Rotation     | HttpOnly Cookie + Rotation      |
| Replay Attack Protection   | Có                             | Có (revoke all sessions)        |
| Session Management         | Dashboard quản lý              | Revoke từng cái hoặc tất cả     |
| Rate Limiting              | Có                             | Có (in-memory, 5 lần/15 phút)   |
| Brute Force Protection     | Có                             | Có                              |
| Audit Logging              | Có                             | Có (11 loại sự kiện)            |
| Welcome Email              | Có                             | Có (HTML responsive)            |
| API Key Management         | Có                             | Có (frontend)                   |
| Multi-session              | Có                             | Có                              |
| Middleware Verify          | @clerk/backend                 | require_auth decorator          |
| Password Hashing           | bcrypt/argon2                  | bcrypt (salt rounds=12)         |
| Account Linking (Google)   | Có                             | Có                              |

---

## 2. CẤU TRÚC SOURCE CODE

```
d:\auth like clerk\
│
├── app.py                    # Flask application factory
│   ├── create_app()          # Tạo Flask app với config, DB, blueprint, CORS
│   ├── serve_frontend()      # Static file serving cho SPA
│   └── health()              # Health check endpoint
│
├── config.py                 # Cấu hình toàn hệ thống
│   ├── PORT, ENV, SECRET_KEY
│   ├── SQLALCHEMY_DATABASE_URI (SQLite/PostgreSQL)
│   ├── JWT_ACCESS_SECRET, JWT_REFRESH_SECRET
│   ├── JWT_ACCESS_EXPIRES_IN_MINUTES (15)
│   ├── JWT_REFRESH_EXPIRES_IN_DAYS (7)
│   ├── GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
│   ├── SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
│   ├── RATE_LIMIT_WINDOW_MINUTES (15)
│   ├── RATE_LIMIT_MAX (100)
│   └── BRUTE_FORCE_MAX_ATTEMPTS (5)
│
├── models.py                 # SQLAlchemy models
│   ├── User (id, username, email, password_hash, google_sub, ...)
│   ├── Session (id, user_id, token, expires_at, revoked, ...)
│   └── AuditLog (id, user_id, event, status, details, ...)
│
├── routes.py                 # API Blueprint: /api/auth/*
│   ├── register()            # POST /api/auth/register
│   ├── login()               # POST /api/auth/login
│   ├── login_google()        # POST /api/auth/google
│   ├── logout()              # POST /api/auth/logout
│   ├── logout_all()          # POST /api/auth/logout-all
│   ├── refresh()             # POST /api/auth/refresh
│   ├── me()                  # GET /api/auth/me
│   ├── verify_session()      # POST /api/auth/verify
│   ├── link_google()         # POST /api/auth/link-google
│   ├── unlink_google()       # POST /api/auth/unlink-google
│   ├── check_username()      # POST /api/auth/check-username
│   ├── check_email()         # POST /api/auth/check-email
│   ├── update_profile()      # PUT /api/auth/me
│   └── change_password()     # POST /api/auth/change-password
│
├── middleware.py              # Decorators & middleware
│   ├── rate_limit(limit_type) # Rate limiter (in-memory)
│   ├── require_auth(f)       # JWT verification decorator
│   ├── add_cors_headers()    # CORS headers
│   └── log_audit_event()     # Audit logging function
│
├── services\                 # Business logic layer
│   ├── user_service.py       # User CRUD operations
│   │   ├── normalize_username(), normalize_email()
│   │   ├── find_by_id(), find_by_username(), find_by_email()
│   │   ├── find_by_google_sub()
│   │   ├── check_username_exists(), check_email_exists()
│   │   ├── create_user()
│   │   ├── update_user_profile()
│   │   ├── link_google_account()
│   │   └── unlink_google_account()
│   │
│   ├── token_service.py      # Token & Session management
│   │   ├── generate_access_token()   # JWT encode
│   │   ├── verify_access_token()     # JWT decode
│   │   ├── create_session()          # Tạo session mới
│   │   ├── rotate_session()          # Refresh + rotation
│   │   ├── revoke_session()          # Thu hồi 1 session
│   │   ├── revoke_all_sessions()     # Thu hồi tất cả
│   │   └── validate_session()        # Kiểm tra session
│   │
│   ├── google_service.py     # Google OAuth verification
│   │   ├── verify_id_token()         # Xác thực Google ID Token
│   │   └── GoogleUserInfo class
│   │
│   └── email_service.py      # Email sending
│       └── send_welcome_email()      # Gửi email HTML chào mừng
│
├── frontend\                 # Static frontend (served by Flask)
│   ├── index.html            # Landing page (unauthenticated)
│   ├── login.html            # Login form + Google Sign-In
│   ├── register.html         # Registration form + Google Sign-Up
│   ├── dashboard.html        # User dashboard (authenticated)
│   ├── docs.html             # API documentation
│   ├── purchase.html         # Pricing/checkout page
│   ├── css\                  # Stylesheets
│   └── js\
│       ├── config.js         # Frontend config (API URL, endpoints, Google Client ID)
│       ├── api.js            # HTTP client (auto-inject token, auto-refresh 401)
│       ├── auth.js           # Auth state manager (login, logout, user, listeners)
│       ├── utils.js          # Utility functions (format, validate, toast, debounce)
│       ├── nav.js            # Navigation bar auth-aware rendering
│       └── landing.js        # Landing page animations (scroll, counter, parallax)
│
├── test_auth.py              # Unit tests (6 test cases)
├── test_api.py               # Manual integration test script
├── AUTH_REQUIREMENTS.md      # Chi tiết yêu cầu hệ thống
└── Prompt.md                 # Hướng dẫn phát triển (Vietnamese)
```

---

## 3. DATABASE SCHEMA & CONSTRAINTS

### 3.1. Bảng `users` - Tài khoản người dùng

```sql
CREATE TABLE users (
    -- Primary Key
    id              VARCHAR(36) PRIMARY KEY,       -- UUID tự sinh

    -- Định danh (UNIQUE + INDEX)
    username        VARCHAR(80) NOT NULL UNIQUE,    -- Tên đăng nhập
    email           VARCHAR(120) NOT NULL UNIQUE,   -- Gmail (lowercase, trim)
    
    -- Xác thực
    password_hash   VARCHAR(255) DEFAULT NULL,      -- bcrypt hash (NULL nếu chỉ dùng Google)
    google_sub      VARCHAR(255) UNIQUE DEFAULT NULL, -- Google Subject ID (NULL nếu chưa link)
    
    -- Hồ sơ
    avatar_url      VARCHAR(255) DEFAULT NULL,      -- Ảnh đại diện
    display_name    VARCHAR(100) DEFAULT NULL,      -- Tên hiển thị
    
    -- Timestamps
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_users_username (username),
    INDEX idx_users_email (email)
);
```

**Constraints & Logic:**
- `username`: UNIQUE, case-insensitive khi kiểm tra (dùng `LOWER(username)` trong query)
- `email`: UNIQUE, lowercase, trim, chỉ chấp nhận @gmail.com
- `google_sub`: UNIQUE, nullable (mỗi Google account chỉ link được 1 user)
- `password_hash`: nullable (cho phép user chỉ dùng Google OAuth, không có password)
- Khi user có cả password_hash và google_sub → có thể login bằng cả 2 cách

### 3.2. Bảng `sessions` - Phiên đăng nhập

```sql
CREATE TABLE sessions (
    id              VARCHAR(36) PRIMARY KEY,        -- UUID tự sinh
    user_id         VARCHAR(36) NOT NULL,            -- FK → users.id
    token           VARCHAR(255) NOT NULL UNIQUE,    -- Refresh token (80 hex chars)
    expires_at      DATETIME NOT NULL,               -- Hết hạn sau 7 ngày
    user_agent      VARCHAR(255) DEFAULT NULL,       -- Thông tin trình duyệt
    ip_address      VARCHAR(45) DEFAULT NULL,        -- Địa chỉ IP
    revoked         BOOLEAN NOT NULL DEFAULT FALSE,  -- Đã thu hồi?
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_sessions_user_id (user_id),
    INDEX idx_sessions_token (token)
);
```

**Cơ chế quản lý session:**
- Mỗi lần đăng nhập thành công = 1 session mới được tạo
- Token là `secrets.token_hex(40)` = 80 ký tự hex ngẫu nhiên (đủ mạnh, không cần JWT)
- `expires_at` = thời điểm tạo + 7 ngày
- Khi refresh: session cũ `revoked = 1`, tạo session mới
- Khi logout: `revoked = 1` cho session hiện tại
- Khi logout-all: `revoked = 1` cho tất cả sessions của user
- Khi phát hiện replay attack: `revoked = 1` cho **tất cả** sessions của user

### 3.3. Bảng `audit_logs` - Nhật ký bảo mật

```sql
CREATE TABLE audit_logs (
    id              VARCHAR(36) PRIMARY KEY,        -- UUID tự sinh
    user_id         VARCHAR(36) DEFAULT NULL,        -- FK → users.id (NULL nếu chưa auth)
    event           VARCHAR(100) NOT NULL,           -- Tên sự kiện
    status          VARCHAR(20) NOT NULL,            -- SUCCESS / FAILED
    user_agent      VARCHAR(255) DEFAULT NULL,       -- User-Agent header
    ip_address      VARCHAR(45) DEFAULT NULL,        -- Địa chỉ IP
    details         TEXT DEFAULT NULL,               -- JSON string (đã sanitize)
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_audit_logs_user_id (user_id)
);
```

**Các sự kiện được ghi lại (11 loại):**

| Event                | Khi nào?                                   | Ghi chú                     |
|----------------------|--------------------------------------------|-----------------------------|
| REGISTER             | Đăng ký tài khoản mới                      | Ghi cả SUCCESS và FAILED    |
| LOGIN                | Đăng nhập username/password                | Ghi cả SUCCESS và FAILED    |
| GOOGLE_REGISTER      | Đăng ký bằng Google (user mới)             | Chỉ SUCCESS                 |
| GOOGLE_LOGIN         | Đăng nhập bằng Google (user đã tồn tại)    | Chỉ SUCCESS                 |
| GOOGLE_AUTH          | Xác thực Google thất bại                   | Chỉ FAILED                  |
| LOGOUT               | Đăng xuất                                  | Chỉ SUCCESS                 |
| LOGOUT_ALL_DEVICES   | Đăng xuất tất cả thiết bị                  | Chỉ SUCCESS                 |
| LINK_GOOGLE          | Liên kết Google account                    | Ghi cả SUCCESS và FAILED    |
| UNLINK_GOOGLE        | Hủy liên kết Google account                | Ghi cả SUCCESS và FAILED    |
| UPDATE_PROFILE       | Cập nhật hồ sơ                             | Ghi cả SUCCESS và FAILED    |
| CHANGE_PASSWORD      | Đổi mật khẩu                               | Ghi cả SUCCESS và FAILED    |

**Chi tiết bị sanitize (không bao giờ ghi vào log):**
- `password` - xóa khỏi details
- `token` - xóa khỏi details
- `idToken` (Google credential) - xóa khỏi details

---

## 4. TOKEN SYSTEM & SESSION LIFECYCLE

### 4.1. Access Token (JWT)

**Cấu trúc JWT:**
```
Header:     { "alg": "HS256", "typ": "JWT" }
Payload:    {
                "userId": "uuid",
                "username": "john_doe",
                "email": "john@gmail.com",
                "exp": 1700000000          // Unix timestamp, 15 phút từ lúc tạo
            }
Signature:  HMAC-SHA256(base64(header) + "." + base64(payload), JWT_ACCESS_SECRET)
```

**Thông số kỹ thuật:**
- Thuật toán: HS256 (HMAC-SHA256)
- Secret key: `Config.JWT_ACCESS_SECRET` (có thể cấu hình qua biến môi trường)
- Thời gian sống: 15 phút (`Config.JWT_ACCESS_EXPIRES_IN_MINUTES`)
- Chứa: userId, username, email (không chứa password, không chứa thông tin nhạy cảm)

**Code tạo JWT:**
```python
def generate_access_token(user: User) -> str:
    payload = {
        "userId": user.id,
        "username": user.username,
        "email": user.email,
        "exp": datetime.utcnow() + timedelta(minutes=Config.JWT_ACCESS_EXPIRES_IN_MINUTES)
    }
    return jwt.encode(payload, Config.JWT_ACCESS_SECRET, algorithm="HS256")
```

**Code verify JWT:**
```python
def verify_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, Config.JWT_ACCESS_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ValueError("Access token is expired.")
    except jwt.InvalidTokenError:
        raise ValueError("Access token is invalid.")
```

### 4.2. Refresh Token (Session Token)

**Cấu trúc:**
- Format: `secrets.token_hex(40)` → 80 ký tự hex ngẫu nhiên
- Không phải JWT, không decode được, không chứa thông tin user
- Lưu trong database (sessions table) và HttpOnly Cookie
- **Không bao giờ gửi qua URL**, chỉ trong HttpOnly Cookie hoặc request body POST

**Cookie configuration:**
```python
response.set_cookie(
    'refresh_token',
    token,
    httponly=True,              # JavaScript không thể đọc
    secure=request.is_secure,   # Chỉ gửi qua HTTPS
    samesite='Strict',          # Chống CSRF
    max_age=7 * 24 * 60 * 60   # 7 ngày
)
```

### 4.3. Token Rotation Flow (Chi tiết từng bước)

```
TRẠNG THÁI BAN ĐẦU:
┌──────────────────────────────────────────────────────────────────────┐
│  User vừa đăng nhập thành công:                                      │
│                                                                      │
│  Client (Browser) lưu:                                               │
│  ├── sessionStorage: access_token = "AT1"                            │
│  └── HttpOnly Cookie: refresh_token = "RT1"                          │
│                                                                      │
│  Database:                                                           │
│  └── sessions table:                                                 │
│      ┌────┬─────────┬───────┬───────────┬─────────┐                  │
│      │ id │ user_id │ token │ expires_at│ revoked │                  │
│      ├────┼─────────┼───────┼───────────┼─────────┤                  │
│      │ S1 │   U1    │  RT1  │ +7 ngày   │ FALSE   │                  │
│      └────┴─────────┴───────┴───────────┴─────────┘                  │
└──────────────────────────────────────────────────────────────────────┘

KHI ACCESS TOKEN HẾT HẠN (HTTP 401):
┌──────────────────────────────────────────────────────────────────────┐
│  Bước 1: Client nhận 401 từ API call                                │
│                                                                      │
│  Bước 2: Client tự động gọi POST /api/auth/refresh                  │
│          (Cookie refresh_token=RT1 được gửi tự động)                 │
│                                                                      │
│  Bước 3: Backend xử lý refresh:                                      │
│                                                                      │
│  3a. Đọc refresh_token từ cookie (ưu tiên) hoặc request body         │
│                                                                      │
│  3b. Query session từ DB (dùng db.engine.connect() - fresh connection│
│      để tránh đọc dữ liệu cũ từ transaction cache):                  │
│      SELECT id, user_id, revoked, expires_at                         │
│      FROM sessions WHERE token = 'RT1'                               │
│                                                                      │
│  3c. CASE 1 - Không tìm thấy token:                                  │
│      → Token không tồn tại (có thể đã bị xóa hoặc sai)              │
│      → Trả về 401 "Session expired, revoked, or reuse detected."     │
│                                                                      │
│  3d. CASE 2 - Tìm thấy, revoked = TRUE:                              │
│      → REPLAY ATTACK DETECTED!                                       │
│      → Token này đã được dùng để refresh trước đó                    │
│      → Attacker đang cố gắng dùng lại token cũ                       │
│      → Hủy TẤT CẢ sessions của user (revoke_all_sessions)           │
│      → Trả về 401 "Session expired, revoked, or reuse detected."     │
│                                                                      │
│  3e. CASE 3 - Tìm thấy, expires_at < now:                            │
│      → Session đã hết hạn tự nhiên (quá 7 ngày)                     │
│      → Hủy tất cả sessions (phòng ngừa)                              │
│      → Trả về 401 "Session expired"                                  │
│                                                                      │
│  3f. CASE 4 - Tìm thấy, revoked = FALSE, chưa hết hạn:               │
│      → Token hợp lệ                                                  │
│      → Đánh dấu session cũ: UPDATE sessions SET revoked=1 WHERE id=S1│
│      → Tạo session mới S2:                                           │
│        INSERT INTO sessions (id, user_id, token, expires_at, ...)    │
│        VALUES (S2, U1, RT2, now+7days, ...)                          │
│      → Tạo access token mới AT2                                      │
│      → Trả về 200 { accessToken: AT2, refreshToken: RT2 }           │
│      → Set cookie mới: refresh_token=RT2                             │
│                                                                      │
│  Bước 4: Client nhận token mới                                       │
│          → Cập nhật access_token trong sessionStorage                │
│          → Cookie tự động cập nhật (do backend set)                  │
│          → Retry lại API call ban đầu với AT2                        │
└──────────────────────────────────────────────────────────────────────┘

KẾT QUẢ SAU REFRESH:
┌──────────────────────────────────────────────────────────────────────┐
│  Client (Browser) lưu:                                               │
│  ├── sessionStorage: access_token = "AT2" (mới)                      │
│  └── HttpOnly Cookie: refresh_token = "RT2" (mới)                    │
│                                                                      │
│  Database:                                                           │
│  └── sessions table:                                                 │
│      ┌────┬─────────┬───────┬───────────┬─────────┐                  │
│      │ id │ user_id │ token │ expires_at│ revoked │                  │
│      ├────┼─────────┼───────┼───────────┼─────────┤                  │
│      │ S1 │   U1    │  RT1  │ +7 ngày   │ TRUE    │ ← revoked       │
│      │ S2 │   U1    │  RT2  │ +7 ngày   │ FALSE   │ ← active        │
│      └────┴─────────┴───────┴───────────┴─────────┘                  │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.4. Replay Attack Protection (Chi tiết)

```
KỊCH BẢN TẤN CÔNG REPLAY:
┌──────────────────────────────────────────────────────────────────────┐
│  Giả sử attacker đánh cắp được RT1 (qua MITM, XSS, log, ...)        │
│                                                                      │
│  THỜI GIAN:                                                          │
│                                                                      │
│  T1: User đăng nhập → nhận AT1, RT1                                  │
│      Attacker có RT1                                                 │
│                                                                      │
│  T2: User refresh token hợp lệ → RT1 revoked, nhận AT2, RT2          │
│      Attacker vẫn giữ RT1 (cũ)                                       │
│                                                                      │
│  T3: Attacker gọi /refresh với RT1 (cũ)                              │
│      → Backend query: RT1 tồn tại, revoked = TRUE                    │
│      → REPLAY ATTACK DETECTED!                                       │
│      → Backend gọi revoke_all_sessions(user_id)                      │
│      → RT2 cũng bị revoked!                                          │
│      → Attacker không thể dùng RT2                                   │
│      → User bị đăng xuất (phải login lại)                            │
│                                                                      │
│  KẾT LUẬN:                                                          │
│  - Attacker không thể chiếm session                                  │
│  - User bị logout là cái giá phải trả cho bảo mật                    │
│  - User có thể login lại ngay                                        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. AUTHENTICATION FLOWS CHI TIẾT

### 5.1. Đăng ký (Register) - Luồng xử lý đầy đủ

```
┌──────────────────────────────────────────────────────────────────────┐
│                    REGISTRATION FLOW                                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  CLIENT (Browser)                    BACKEND (AuthGuard)             │
│  ────────────────                    ─────────────────               │
│                                                                      │
│  POST /api/auth/register                                             │
│  { username, email, password }                                       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B1: VALIDATE INPUT                                      │       │
│    │                                                          │       │
│    │  validate_username(username):                            │       │
│    │  ├── null/empty check                                    │       │
│    │  ├── length: 3-20 characters                             │       │
│    │  └── regex: ^[a-zA-Z0-9_]+$                              │       │
│    │                                                          │       │
│    │  validate_email(email):                                  │       │
│    │  ├── null/empty check                                    │       │
│    │  ├── strip().lower()                                     │       │
│    │  ├── chỉ @gmail.com                                      │       │
│    │  └── regex: ^[a-z0-9._%+-]+@gmail\.com$                 │       │
│    │                                                          │       │
│    │  validate_password(password):                            │       │
│    │  ├── null/empty check                                    │       │
│    │  └── length >= 8                                         │       │
│    │                                                          │       │
│    │  Nếu lỗi → 400 VALIDATION_ERROR                          │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B2: CHECK UNIQUENESS                                    │       │
│    │                                                          │       │
│    │  check_username_exists(username):                        │       │
│    │  ├── trim().lower()                                      │       │
│    │  └── SELECT * FROM users WHERE LOWER(username)=?         │       │
│    │                                                          │       │
│    │  check_email_exists(email):                              │       │
│    │  ├── normalize_email() (lowercase, trim)                 │       │
│    │  └── SELECT * FROM users WHERE email=?                   │       │
│    │                                                          │       │
│    │  Nếu username tồn tại → 400 USERNAME_EXISTS              │       │
│    │  Nếu email tồn tại → 400 EMAIL_EXISTS                    │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B3: HASH PASSWORD                                       │       │
│    │                                                          │       │
│    │  salt = bcrypt.gensalt(12)  ← 2^12 rounds (mạnh)        │       │
│    │  password_hash = bcrypt.hashpw(password, salt)           │       │
│    │                                                          │       │
│    │  Kết quả: $2b$12$... (60 ký tự)                         │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B4: CREATE USER                                         │       │
│    │                                                          │       │
│    │  user = User(                                            │       │
│    │      id = uuid4(),                                       │       │
│    │      username = normalized_username,                     │       │
│    │      email = normalized_email,                           │       │
│    │      password_hash = hashed_password,                    │       │
│    │      google_sub = None,                                  │       │
│    │      avatar_url = None,                                  │       │
│    │      display_name = None                                 │       │
│    │  )                                                       │       │
│    │  db.session.add(user)                                    │       │
│    │  db.session.commit()                                     │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B5: CREATE SESSION & TOKENS                             │       │
│    │                                                          │       │
│    │  Session:                                                │       │
│    │  ├── token = secrets.token_hex(40)  ← 80 hex chars      │       │
│    │  ├── expires_at = now + 7 days                           │       │
│    │  ├── user_agent = từ request header                     │       │
│    │  ├── ip_address = request.remote_addr                   │       │
│    │  └── INSERT INTO sessions (...)                          │       │
│    │                                                          │       │
│    │  Access Token:                                           │       │
│    │  └── jwt.encode({ userId, username, email, exp }, secret)│       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B6: RESPONSE                                            │       │
│    │                                                          │       │
│    │  Status: 201 Created                                     │       │
│    │  Body: {                                                 │       │
│    │      success: true,                                      │       │
│    │      accessToken: "eyJ...",                              │       │
│    │      refreshToken: "a1b2c3...",                          │       │
│    │      user: { id, username, email, ... }                  │       │
│    │  }                                                       │       │
│    │  Set-Cookie: refresh_token=...; HttpOnly; SameSite=Strict│       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B7: AUDIT LOG + EMAIL (async)                          │       │
│    │                                                          │       │
│    │  AuditLog: REGISTER/SUCCESS                              │       │
│    │                                                          │       │
│    │  EmailService.send_welcome_email():                      │       │
│    │  ├── HTML template responsive                            │       │
│    │  ├── username, email, created_at, IP, device             │       │
│    │  ├── security notice                                     │       │
│    │  └── Nếu SMTP không config → mock log ra console         │       │
│    └─────────────────────────────────────────────────────────┘       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2. Đăng nhập (Login) - Luồng xử lý đầy đủ

```
┌──────────────────────────────────────────────────────────────────────┐
│                       LOGIN FLOW                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  CLIENT (Browser)                    BACKEND (AuthGuard)             │
│  ────────────────                    ─────────────────               │
│                                                                      │
│  POST /api/auth/login                                                │
│  { usernameOrEmail, password }                                       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B1: XÁC ĐỊNH LOẠI ĐĂNG NHẬP                             │       │
│    │                                                          │       │
│    │  if "@" in usernameOrEmail:                              │       │
│    │  ├── user = find_by_email(usernameOrEmail)               │       │
│    │  │   → normalize_email() (lowercase, trim)               │       │
│    │  │   → SELECT * FROM users WHERE email=?                 │       │
│    │  │                                                       │       │
│    │  else:                                                   │       │
│    │  └── user = find_by_username(usernameOrEmail)            │       │
│    │      → trim().lower()                                    │       │
│    │      → SELECT * FROM users WHERE LOWER(username)=?       │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B2: KIỂM TRA THÔNG TIN                                  │       │
│    │                                                          │       │
│    │  if not user or not user.password_hash:                  │       │
│    │  ├── AuditLog: LOGIN/FAILED (INVALID_CREDENTIALS)        │       │
│    │  └── 401 INVALID_CREDENTIALS                             │       │
│    │                                                          │       │
│    │  if not bcrypt.checkpw(password, user.password_hash):    │       │
│    │  ├── AuditLog: LOGIN/FAILED (INVALID_CREDENTIALS)        │       │
│    │  └── 401 INVALID_CREDENTIALS                             │       │
│    │                                                          │       │
│    │  LƯU Ý: Cả 2 trường hợp đều trả về cùng lỗi              │       │
│    │  "INVALID_CREDENTIALS" để tránh account enumeration      │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B3: TẠO SESSION & TOKENS                                │       │
│    │  (Giống hệt bước B5 của Register)                        │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B4: RESPONSE                                            │       │
│    │                                                          │       │
│    │  Status: 200 OK                                          │       │
│    │  Body: { success, accessToken, refreshToken, user }      │       │
│    │  Set-Cookie: refresh_token=...                           │       │
│    │  AuditLog: LOGIN/SUCCESS                                 │       │
│    └─────────────────────────────────────────────────────────┘       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.3. Google OAuth - Luồng xử lý đầy đủ

```
┌──────────────────────────────────────────────────────────────────────┐
│                    GOOGLE OAUTH FLOW                                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  CLIENT (Browser)                    BACKEND (AuthGuard)             │
│  ────────────────                    ─────────────────               │
│                                                                      │
│  Bước 1: Google Sign-In (phía client)                                │
│  ┌─────────────────────────────────────────────────────────┐         │
│  │  Google Identity Services (GSI) script load              │         │
│  │  google.accounts.id.initialize({ client_id, callback })  │         │
│  │  User click "Sign in with Google"                        │         │
│  │  Google popup → user chọn tài khoản                      │         │
│  │  Google trả về credential (idToken)                      │         │
│  └─────────────────────────────────────────────────────────┘         │
│         │                                                            │
│         ▼                                                            │
│  POST /api/auth/google                                               │
│  { idToken: "eyJhbGciOiJSUzI1NiIs..." }                             │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B2: VERIFY ID TOKEN                                    │       │
│    │                                                          │       │
│    │  GoogleService.verify_id_token(idToken):                 │       │
│    │                                                          │       │
│    │  Nếu là MOCK TOKEN (development/test):                   │       │
│    │  ├── Token bắt đầu bằng "mock_google_token_"             │       │
│    │  ├── Parse sub từ token: "mock_google_token_alice"       │       │
│    │  │   → sub = "google_sub_alice"                         │       │
│    │  │   → email = "alice@gmail.com"                        │       │
│    │  │   → display_name = "Mock User alice"                 │       │
│    │  │   → avatar_url = "https://avatar.vercel.sh/alice"    │       │
│    │  └── Trả về thông tin mock                              │       │
│    │                                                          │       │
│    │  Nếu là TOKEN THẬT (production):                         │       │
│    │  ├── Kiểm tra GOOGLE_CLIENT_ID đã cấu hình               │       │
│    │  ├── id_token.verify_oauth2_token(token, request, id)    │       │
│    │  │   → Xác thực chữ ký số (RSA)                         │       │
│    │  │   → Xác thực audience (client_id)                    │       │
│    │  │   → Xác thực issuer (accounts.google.com)            │       │
│    │  │   → Xác thực expiration                              │       │
│    │  ├── Kiểm tra email tồn tại trong token                  │       │
│    │  └── Trả về { sub, email, name, picture }               │       │
│    │                                                          │       │
│    │  Nếu lỗi → 400 GOOGLE_AUTH_FAILED                        │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B3: TÌM HOẶC TẠO USER                                   │       │
│    │                                                          │       │
│    │  google_info = { sub, email, display_name, avatar_url }  │       │
│    │                                                          │       │
│    │  user = find_by_google_sub(google_info['sub'])           │       │
│    │                                                          │       │
│    │  if user:                                                │       │
│    │  ├── Đã có Google link → login                           │       │
│    │  └── is_new_user = false                                 │       │
│    │                                                          │       │
│    │  if not user:                                            │       │
│    │  ├── Kiểm tra email đã tồn tại chưa:                     │       │
│    │  │   existing = find_by_email(google_info['email'])      │       │
│    │  │                                                       │       │
│    │  │   if existing:                                        │       │
│    │  │   ├── LINK GOOGLE: link_google_account(existing.id,   │       │
│    │  │   │                    google_info['sub'])            │       │
│    │  │   ├── Sync avatar/display_name nếu thiếu              │       │
│    │  │   └── user = existing                                 │       │
│    │  │                                                       │       │
│    │  │   if not existing:                                    │       │
│    │  │   ├── Tạo username từ email prefix:                   │       │
│    │  │   │   email_prefix = re.sub(r'[^a-zA-Z0-9_]', '',     │       │
│    │  │   │                   email.split('@')[0])            │       │
│    │  │   │   Nếu trùng username → thêm _1, _2, ...           │       │
│    │  │   ├── CREATE USER với google_sub                     │       │
│    │  │   ├── is_new_user = true                              │       │
│    │  │   └── user = user mới                                 │       │
│    │  └──                                                     │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B4: TẠO SESSION & TOKENS                                │       │
│    │  (Giống hệt bước B5 của Register)                        │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B5: RESPONSE                                            │       │
│    │                                                          │       │
│    │  Status: 200 OK                                          │       │
│    │  Body: { success, accessToken, refreshToken, user }      │       │
│    │  Set-Cookie: refresh_token=...                           │       │
│    │                                                          │       │
│    │  AuditLog:                                               │       │
│    │  ├── Nếu user mới: GOOGLE_REGISTER/SUCCESS               │       │
│    │  └── Nếu user cũ: GOOGLE_LOGIN/SUCCESS                   │       │
│    │                                                          │       │
│    │  Nếu user mới: Gửi welcome email (async)                 │       │
│    └─────────────────────────────────────────────────────────┘       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.4. Đổi mật khẩu (Change Password) - Luồng xử lý

```
┌──────────────────────────────────────────────────────────────────────┐
│                    CHANGE PASSWORD FLOW                               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  CLIENT (Browser)                    BACKEND (AuthGuard)             │
│  ────────────────                    ─────────────────               │
│                                                                      │
│  POST /api/auth/change-password                                      │
│  Authorization: Bearer AT1                                           │
│  { currentPassword, newPassword }                                    │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B1: VERIFY ACCESS TOKEN (require_auth middleware)       │       │
│    │  → jwt.decode(AT1, JWT_ACCESS_SECRET)                   │       │
│    │  → g.user = { userId, username, email }                  │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B2: VALIDATE INPUT                                      │       │
│    │  ├── currentPassword: required                           │       │
│    │  ├── newPassword: required, >= 8 chars                   │       │
│    │  └── Nếu lỗi → 400 VALIDATION_ERROR                     │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B3: XÁC THỰC MẬT KHẨU HIỆN TẠI                         │       │
│    │                                                          │       │
│    │  user = find_by_id(g.user.userId)                        │       │
│    │                                                          │       │
│    │  if not user or not user.password_hash:                  │       │
│    │  └── 400 "Password change not available"                 │       │
│    │      (user chỉ dùng Google, không có password)           │       │
│    │                                                          │       │
│    │  if not bcrypt.checkpw(currentPassword,                  │       │
│    │                        user.password_hash):              │       │
│    │  ├── AuditLog: CHANGE_PASSWORD/FAILED (WRONG_PASSWORD)   │       │
│    │  └── 401 WRONG_PASSWORD                                  │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B4: CẬP NHẬT MẬT KHẨU                                  │       │
│    │                                                          │       │
│    │  salt = bcrypt.gensalt(12)                               │       │
│    │  new_hash = bcrypt.hashpw(newPassword, salt)             │       │
│    │  user.password_hash = new_hash                           │       │
│    │  db.session.commit()                                     │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B5: REVOKE ALL SESSIONS + TẠO SESSION MỚI              │       │
│    │                                                          │       │
│    │  revoke_all_sessions(user_id)  ← đăng xuất khỏi tất cả  │       │
│    │  create_session(user_id, ...)  ← tạo session mới        │       │
│    │  generate_access_token(user)   ← tạo token mới          │       │
│    └─────────────────────────────────────────────────────────┘       │
│         │                                                            │
│         ▼                                                            │
│    ┌─────────────────────────────────────────────────────────┐       │
│    │  B6: RESPONSE                                            │       │
│    │                                                          │       │
│    │  Status: 200 OK                                          │       │
│    │  Body: { success, message, accessToken, refreshToken }   │       │
│    │  Set-Cookie: refresh_token=... (mới)                     │       │
│    │  AuditLog: CHANGE_PASSWORD/SUCCESS                       │       │
│    └─────────────────────────────────────────────────────────┘       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.5. Liên kết/Hủy liên kết Google Account

```
LINK GOOGLE (POST /api/auth/link-google):
┌──────────────────────────────────────────────────────────────────────┐
│  Yêu cầu: Authorization: Bearer AT (phải đăng nhập)                  │
│  Body: { idToken: "google_id_token" }                                │
│                                                                      │
│  1. Verify Google ID Token                                           │
│  2. Kiểm tra email đã được link với user khác chưa                   │
│     → Nếu email đã link với user khác → 400 EMAIL_ALREADY_LINKED    │
│  3. Link: user.google_sub = google_info['sub']                       │
│  4. AuditLog: LINK_GOOGLE/SUCCESS                                    │
└──────────────────────────────────────────────────────────────────────┘

UNLINK GOOGLE (POST /api/auth/unlink-google):
┌──────────────────────────────────────────────────────────────────────┐
│  Yêu cầu: Authorization: Bearer AT (phải đăng nhập)                  │
│                                                                      │
│  1. Kiểm tra user có password_hash không                             │
│     → Nếu không có password → 400 "Cannot unlink without password"   │
│  2. Unlink: user.google_sub = None                                   │
│  3. AuditLog: UNLINK_GOOGLE/SUCCESS                                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 6. AUTHORIZATION MIDDLEWARE

### 6.1. `require_auth` Decorator

```python
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # B1: Lấy Authorization header
        auth_header = request.headers.get("Authorization")
        
        # B2: Kiểm tra format "Bearer <token>"
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({
                "success": False,
                "code": "UNAUTHORIZED",
                "message": "Authorization token is required."
            }), 401

        # B3: Tách token
        token = auth_header.split(" ")[1]

        # B4: Verify JWT
        try:
            payload = TokenService.verify_access_token(token)
            g.user = payload  # Lưu vào Flask global
        except Exception as e:
            return jsonify({
                "success": False,
                "code": "TOKEN_EXPIRED_OR_INVALID",
                "message": str(e)
            }), 401

        # B5: Cho phép request đi tiếp
        return f(*args, **kwargs)
    return decorated_function
```

**Các endpoint sử dụng `@require_auth`:**
- `GET /api/auth/me` - Lấy thông tin user
- `PUT /api/auth/me` - Cập nhật profile
- `POST /api/auth/logout-all` - Đăng xuất tất cả
- `POST /api/auth/link-google` - Liên kết Google
- `POST /api/auth/unlink-google` - Hủy liên kết Google
- `POST /api/auth/change-password` - Đổi mật khẩu

### 6.2. `rate_limit` Decorator

```python
def rate_limit(limit_type="global"):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Bỏ qua rate limit trong development/test (trừ khi có header test)
            if Config.ENV in ("development", "test") and not request.headers.get("x-test-rate-limit"):
                return f(*args, **kwargs)

            ip = request.remote_addr or "unknown_ip"
            now = time.time()
            
            # Xác định threshold
            if limit_type == "auth":
                window = Config.RATE_LIMIT_WINDOW_MINUTES * 60  # 15 phút
                max_attempts = Config.BRUTE_FORCE_MAX_ATTEMPTS  # 5 lần
            else:
                window = Config.RATE_LIMIT_WINDOW_MINUTES * 60
                max_attempts = Config.RATE_LIMIT_MAX  # 100 lần

            # Lưu trữ in-memory
            key = f"{limit_type}:{ip}"
            if key not in _rate_limit_store:
                _rate_limit_store[key] = []

            # Xóa các timestamp cũ
            _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window]

            # Kiểm tra threshold
            if len(_rate_limit_store[key]) >= max_attempts:
                return jsonify({
                    "success": False,
                    "code": "TOO_MANY_REQUESTS",
                    "message": "Too many requests. Please try again later."
                }), 429

            # Ghi timestamp mới
            _rate_limit_store[key].append(now)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

**Các endpoint có rate limit:**
- `POST /api/auth/register` (auth type - 5 lần/15 phút)
- `POST /api/auth/login` (auth type - 5 lần/15 phút)
- `POST /api/auth/google` (auth type - 5 lần/15 phút)

### 6.3. CORS Middleware

```python
def add_cors_headers(response=None):
    origin = request.headers.get('Origin', 'http://localhost:5000')
    response.headers['Access-Control-Allow-Origin'] = origin  # Echo origin (không dùng *)
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, x-test-rate-limit'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'  # Cho phép gửi cookie
    if request.method == 'OPTIONS':
        response.status_code = 200
    return response
```

**Lưu ý quan trọng:** Khi dùng `credentials: 'include'` (để gửi HttpOnly cookie), `Access-Control-Allow-Origin` KHÔNG được dùng `*` mà phải echo đúng origin từ request.

---

## 7. SECURITY MECHANISMS

### 7.1. Password Security

| Tính năng              | Chi tiết                                    |
|------------------------|---------------------------------------------|
| Thuật toán hash        | bcrypt                                       |
| Salt rounds            | 12 (2^12 = 4096 iterations)                  |
| Độ dài hash            | 60 ký tự (format: $2b$12$...)                |
| So sánh                | bcrypt.checkpw() (constant-time)             |
| Lưu trữ                | Chỉ lưu hash, không bao giờ lưu plaintext    |
| Nullable               | Cho phép user không có password (chỉ Google) |

### 7.2. Rate Limiting & Brute Force Protection

| Endpoint type | Max attempts | Window    | Hành vi khi vượt quá          |
|---------------|:------------:|:---------:|-------------------------------|
| auth          | 5            | 15 phút   | 429 TOO_MANY_REQUESTS         |
| global        | 100          | 15 phút   | 429 TOO_MANY_REQUESTS         |

### 7.3. Cookie Security

| Thuộc tính    | Giá trị        | Mục đích                          |
|---------------|----------------|-----------------------------------|
| HttpOnly      | true           | Chống XSS (JS không đọc được)     |
| Secure        | true (HTTPS)   | Chỉ gửi qua kết nối an toàn       |
| SameSite      | Strict         | Chống CSRF                        |
| Max-Age       | 604800 (7 ngày)| Tự động hết hạn                    |

### 7.4. Account Enumeration Protection

Khi đăng nhập thất bại, backend luôn trả về cùng một lỗi:
```json
{
    "success": false,
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid username/email or password."
}
```
Dù là sai username, sai email, hay sai password - đều trả về lỗi giống hệt nhau.

### 7.5. Audit Logging Security

- Không ghi password, token, idToken vào log
- Tất cả sensitive fields đều được sanitize trước khi lưu
- Ghi cả SUCCESS và FAILED để phát hiện tấn công

### 7.6. Error Handling Security

- **500 Internal Server Error**: Không leak stack trace (trừ development/test mode)
- **Validation**: Kiểm tra input ở cả frontend và backend
- **XSS Prevention**: `escapeHtml()` utility ở frontend
- **SQL Injection**: SQLAlchemy ORM + parameterized queries

---

## 8. API ENDPOINTS REFERENCE

### 8.1. Danh sách đầy đủ

| # | Method | Endpoint              | Auth | Rate Limit | Mô tả                          |
|:-:|:------:|-----------------------|:----:|:----------:|--------------------------------|
| 1 | POST   | /api/auth/register    | No   | Yes (auth) | Đăng ký tài khoản mới          |
| 2 | POST   | /api/auth/login       | No   | Yes (auth) | Đăng nhập                      |
| 3 | POST   | /api/auth/google      | No   | Yes (auth) | Google OAuth                   |
| 4 | POST   | /api/auth/logout      | No   | No         | Đăng xuất 1 thiết bị           |
| 5 | POST   | /api/auth/logout-all  | Yes  | No         | Đăng xuất tất cả thiết bị      |
| 6 | POST   | /api/auth/refresh     | No   | No         | Refresh token rotation         |
| 7 | GET    | /api/auth/me          | Yes  | No         | Lấy thông tin user             |
| 8 | PUT    | /api/auth/me          | Yes  | No         | Cập nhật profile               |
| 9 | POST   | /api/auth/verify      | No   | No         | Xác thực session               |
|10 | POST   | /api/auth/link-google | Yes  | No         | Liên kết Google account        |
|11 | POST   | /api/auth/unlink-google| Yes | No         | Hủy liên kết Google account    |
|12 | POST   | /api/auth/check-username| No  | No         | Kiểm tra username tồn tại      |
|13 | POST   | /api/auth/check-email | No   | No         | Kiểm tra email tồn tại         |
|14 | POST   | /api/auth/change-password| Yes| No        | Đổi mật khẩu                   |
|15 | GET    | /health               | No   | No         | Kiểm tra health server         |

### 8.2. Chi tiết từng endpoint

#### 1. POST /api/auth/register
```
Request:
{
    "username": "john_doe",       // string, 3-20 chars, [a-zA-Z0-9_]
    "email": "john@gmail.com",    // string, chỉ @gmail.com
    "password": "securePass123"   // string, >= 8 chars
}

Response 201:
{
    "success": true,
    "accessToken": "eyJhbGciOiJIUzI1NiIs...",
    "refreshToken": "a1b2c3d4e5f6...",
    "user": {
        "id": "uuid-1234",
        "username": "john_doe",
        "email": "john@gmail.com",
        "display_name": null,
        "avatar_url": null,
        "created_at": "2025-01-01T00:00:00"
    }
}

Error 400: VALIDATION_ERROR, USERNAME_EXISTS, EMAIL_EXISTS
Error 500: REGISTRATION_FAILED
```

#### 2. POST /api/auth/login
```
Request:
{
    "usernameOrEmail": "john_doe",  // string, username hoặc email
    "password": "securePass123"     // string
}

Response 200:
{
    "success": true,
    "accessToken": "eyJhbGciOiJIUzI1NiIs...",
    "refreshToken": "a1b2c3d4e5f6...",
    "user": { ... }
}

Error 400: VALIDATION_ERROR
Error 401: INVALID_CREDENTIALS
Error 500: LOGIN_FAILED
```

#### 3. POST /api/auth/google
```
Request:
{
    "idToken": "eyJhbGciOiJSUzI1NiIs..."  // Google ID Token
}

Response 200:
{
    "success": true,
    "accessToken": "eyJ...",
    "refreshToken": "a1b2c3...",
    "user": { ... }
}

Error 400: VALIDATION_ERROR, GOOGLE_AUTH_FAILED
```

#### 4. POST /api/auth/logout
```
Request: (có thể gửi refreshToken trong body hoặc cookie)
{
    "refreshToken": "a1b2c3..."  // optional, có thể đọc từ cookie
}

Response 200:
{
    "success": true,
    "message": "Logged out successfully."
}

Error 400: MISSING_TOKEN
Error 500: LOGOUT_FAILED
```

#### 5. POST /api/auth/logout-all
```
Headers: Authorization: Bearer <access_token>

Response 200:
{
    "success": true,
    "message": "Logged out from all devices."
}

Error 401: UNAUTHORIZED, TOKEN_EXPIRED_OR_INVALID
Error 500: LOGOUT_FAILED
```

#### 6. POST /api/auth/refresh
```
Request: (refreshToken trong cookie hoặc body)
{
    "refreshToken": "a1b2c3..."  // optional
}

Response 200:
{
    "success": true,
    "accessToken": "eyJ...",
    "refreshToken": "d4e5f6..."
}

Error 400: MISSING_TOKEN
Error 401: SESSION_EXPIRED
```

#### 7. GET /api/auth/me
```
Headers: Authorization: Bearer <access_token>

Response 200:
{
    "success": true,
    "user": { id, username, email, display_name, avatar_url, created_at }
}

Error 401: UNAUTHORIZED, TOKEN_EXPIRED_OR_INVALID
Error 404: USER_NOT_FOUND
```

#### 8. PUT /api/auth/me
```
Headers: Authorization: Bearer <access_token>
Request:
{
    "username": "new_username",     // optional
    "display_name": "John Doe",     // optional
    "avatar_url": "https://..."     // optional
}

Response 200:
{
    "success": true,
    "message": "Profile updated successfully.",
    "user": { ... }
}

Error 400: VALIDATION_ERROR, UPDATE_FAILED
Error 401: UNAUTHORIZED
```

#### 9. POST /api/auth/verify
```
Request: (refreshToken trong cookie hoặc body)
{
    "refreshToken": "a1b2c3..."  // optional
}

Response 200:
{
    "success": true,
    "valid": true,
    "expiresAt": "2025-01-08T00:00:00",
    "user": { ... }
}

Error 401: SESSION_INVALID
```

#### 10. POST /api/auth/link-google
```
Headers: Authorization: Bearer <access_token>
Request:
{
    "idToken": "eyJhbGciOiJSUzI1NiIs..."  // Google ID Token
}

Response 200:
{
    "success": true,
    "message": "Google account linked successfully.",
    "user": { ... }
}

Error 400: VALIDATION_ERROR, EMAIL_ALREADY_LINKED, LINK_GOOGLE_FAILED
Error 401: UNAUTHORIZED
```

#### 11. POST /api/auth/unlink-google
```
Headers: Authorization: Bearer <access_token>

Response 200:
{
    "success": true,
    "message": "Google account unlinked successfully.",
    "user": { ... }
}

Error 400: UNLINK_GOOGLE_FAILED (nếu không có password)
Error 401: UNAUTHORIZED
```

#### 12. POST /api/auth/check-username
```
Request:
{
    "username": "john_doe"
}

Response 200:
{
    "success": true,
    "available": true  // hoặc false
}

Error 400: (nếu thiếu username)
```

#### 13. POST /api/auth/check-email
```
Request:
{
    "email": "john@gmail.com"
}

Response 200:
{
    "success": true,
    "available": true  // hoặc false
}

Error 400: INVALID_EMAIL
```

#### 14. POST /api/auth/change-password
```
Headers: Authorization: Bearer <access_token>
Request:
{
    "currentPassword": "oldPass123",
    "newPassword": "newPass456"
}

Response 200:
{
    "success": true,
    "message": "Password changed successfully. Please sign in again.",
    "accessToken": "eyJ...",
    "refreshToken": "a1b2c3..."
}

Error 400: VALIDATION_ERROR
Error 401: WRONG_PASSWORD, UNAUTHORIZED
Error 500: CHANGE_PASSWORD_FAILED
```

#### 15. GET /health
```
Response 200:
{
    "status": "ok",
    "database": "connected"
}

Response 500:
{
    "status": "error",
    "database": "disconnected",
    "error": "..."
}
```

---

## 9. FRONTEND AUTH FLOW

### 9.1. Kiến trúc Frontend JavaScript

```
┌──────────────────────────────────────────────────────────────────────┐
│                    FRONTEND JAVASCRIPT ARCHITECTURE                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  config.js ──── Cấu hình: API_BASE_URL, endpoints, Google Client ID  │
│       │                                                              │
│       ├── Được load đầu tiên                                         │
│       └── Có thể override bằng window.__API_BASE_URL                 │
│                                                                      │
│  utils.js ──── Hàm tiện ích                                          │
│       ├── formatDate(), maskApiKey(), copyToClipboard()              │
│       ├── showToast() (success/error/info)                           │
│       ├── debounce(), isValidGmail(), isValidUsername()              │
│       ├── isValidPassword(), getQueryParam(), escapeHtml()           │
│       └── Độc lập, không phụ thuộc module khác                      │
│                                                                      │
│  api.js ──── API Client (REST client)                                │
│       ├── ApiClient object                                           │
│       ├── _accessToken (in-memory)                                   │
│       ├── _refreshPromise (tránh refresh đồng thời)                  │
│       ├── _request() - core method                                   │
│       │   ├── Tự động inject Authorization header                    │
│       │   ├── Tự động refresh token khi 401                          │
│       │   └── credentials: 'include' (gửi cookie)                    │
│       ├── _tryRefresh() - refresh logic                              │
│       │   ├── Chỉ 1 refresh duy nhất tại 1 thời điểm                 │
│       │   └── Retry request ban đầu sau refresh                      │
│       └── Convenience methods: get(), post(), put(), delete()        │
│                                                                      │
│  auth.js ──── Auth State Manager                                     │
│       ├── Auth object                                                │
│       ├── _user (current user data)                                  │
│       ├── _listeners (subscribe pattern)                             │
│       ├── init() - khôi phục session từ sessionStorage               │
│       ├── login(), register(), googleLogin()                         │
│       │   ├── Gọi API → lưu token → set user → notify               │
│       │   └── Lưu accessToken vào sessionStorage                     │
│       ├── logout(), logoutAll()                                      │
│       │   ├── Gọi API → clear token → clear user → redirect login   │
│       │   └── Xóa sessionStorage                                     │
│       ├── refreshUser() - đồng bộ user data                          │
│       ├── subscribe() - observer pattern                             │
│       ├── requireAuth() - redirect nếu chưa login                    │
│       └── updateProfile(), changePassword()                          │
│                                                                      │
│  nav.js ──── Navigation Bar (tự động cập nhật theo auth state)       │
│       ├── IIFE (tự thực thi)                                         │
│       ├── renderNavActions() - render nút Sign In / Dashboard        │
│       ├── Kiểm tra sessionStorage trước (instant feedback)           │
│       ├── Sau đó gọi Auth.init() để verify token thật                │
│       └── Subscribe để cập nhật khi login/logout                     │
│                                                                      │
│  landing.js ──── Landing page animations                             │
│       ├── Intersection Observer cho reveal animations                │
│       ├── Counter animation (số liệu thống kê)                      │
│       ├── Smooth scroll, mobile nav, parallax                       │
│       └── FAQ accordion, floating cards                              │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 9.2. Luồng khởi tạo Auth (Auth.init())

```
┌──────────────────────────────────────────────────────────────────────┐
│                    AUTH.INIT() FLOW                                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  B1: Kiểm tra sessionStorage có access_token không                   │
│      ├── Có → Gán vào ApiClient._accessToken                         │
│      └── Không → return false (chưa đăng nhập)                       │
│                                                                      │
│  B2: Gọi GET /api/auth/me (có Authorization header)                  │
│      ├── Thành công (200) →                                          │
│      │   ├── Lưu user data vào Auth._user                            │
│      │   ├── Notify listeners                                        │
│      │   └── return true                                             │
│      │                                                               │
│      └── Thất bại (401) →                                            │
│          ├── Token hết hạn hoặc không hợp lệ                         │
│          └── ApiClient._tryRefresh() được gọi tự động                │
│              ├── Refresh thành công → retry /me                      │
│              └── Refresh thất bại → return false                     │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 9.3. Luồng Login (từ giao diện)

```
┌──────────────────────────────────────────────────────────────────────┐
│                    LOGIN UI FLOW                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  User nhập usernameOrEmail + password                                │
│         │                                                            │
│         ▼                                                            │
│  Validate phía client:                                               │
│  ├── usernameOrEmail: required                                       │
│  └── password: required                                              │
│         │                                                            │
│         ▼                                                            │
│  Gọi Auth.login(usernameOrEmail, password)                           │
│         │                                                            │
│         ▼                                                            │
│  ApiClient.post('/api/auth/login', { usernameOrEmail, password })    │
│         │                                                            │
│         ▼                                                            │
│  Backend trả về: { accessToken, refreshToken, user }                 │
│         │                                                            │
│         ▼                                                            │
│  Auth.login() xử lý:                                                 │
│  ├── ApiClient.setAccessToken(data.accessToken)                      │
│  ├── sessionStorage.setItem('authguard_access_token', data.accessToken)│
│  ├── Auth._user = data.user                                          │
│  ├── Auth._notify() → nav.js cập nhật UI                             │
│  └── return data                                                     │
│         │                                                            │
│         ▼                                                            │
│  Login page nhận kết quả:                                            │
│  ├── Thành công → showToast + redirect dashboard.html                │
│  └── Thất bại → show error message                                   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 9.4. Luồng Auto-Refresh Token (phía client)

```
┌──────────────────────────────────────────────────────────────────────┐
│                    AUTO-REFRESH TOKEN FLOW                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Client gọi API (vd: GET /api/auth/me)                              │
│         │                                                            │
│         ▼                                                            │
│  ApiClient._request() gửi request với Authorization: Bearer AT       │
│         │                                                            │
│         ▼                                                            │
│  Backend trả về 401 (token hết hạn)                                  │
│         │                                                            │
│         ▼                                                            │
│  ApiClient kiểm tra: response.status === 401 && !options._isRetry    │
│         │                                                            │
│         ▼                                                            │
│  Gọi ApiClient._tryRefresh():                                        │
│  ├── Kiểm tra _refreshPromise (đang refresh? → chờ)                  │
│  ├── POST /api/auth/refresh (cookie refresh_token tự động gửi)       │
│  │                                                                   │
│  │  ├── Thành công:                                                  │
│  │  │   ├── ApiClient._accessToken = data.accessToken (mới)          │
│  │  │   └── return true                                              │
│  │  │                                                               │
│  │  └── Thất bại:                                                    │
│  │      ├── ApiClient._accessToken = null                            │
│  │      └── return false                                             │
│  │                                                                   │
│  └── _refreshPromise = null (kết thúc)                               │
│         │                                                            │
│         ▼                                                            │
│  Nếu refresh thành công:                                             │
│  └── Retry request ban đầu với token mới (_isRetry: true)            │
│                                                                      │
│  Nếu refresh thất bại:                                               │
│  └── Trả về lỗi 401 cho caller                                      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 10. CÁCH TÍCH HỢP CHO BACKEND KHÁC

### 10.1. Nguyên lý tích hợp

AuthGuard là một **Authentication Platform độc lập**. Backend của bạn (Flask, Node.js, Django, React, ...) chỉ cần:

1. **Verify JWT Access Token** do AuthGuard cấp
2. **Trust userId** trong JWT payload
3. **Không cần lưu** user/password/session

### 10.2. Tích hợp với Flask

```python
import jwt
from functools import wraps
from flask import request, jsonify, g

# Cấu hình (phải giống với AuthGuard)
JWT_ACCESS_SECRET = "access-token-secret-key-12345"  # Copy từ AuthGuard config

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_ACCESS_SECRET, algorithms=["HS256"])
            g.current_user = payload  # { userId, username, email }
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        
        return f(*args, **kwargs)
    return decorated

@app.route('/api/protected-resource')
@require_auth
def protected_resource():
    user_id = g.current_user['userId']
    # Xử lý business logic với user_id
    return jsonify({"message": "Access granted", "user_id": user_id})
```

### 10.3. Tích hợp với Node.js (Express)

```javascript
const jwt = require('jsonwebtoken');

const JWT_ACCESS_SECRET = 'access-token-secret-key-12345'; // Copy từ AuthGuard

function requireAuth(req, res, next) {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'Unauthorized' });
    }

    const token = authHeader.split(' ')[1];
    try {
        const payload = jwt.verify(token, JWT_ACCESS_SECRET);
        req.user = payload; // { userId, username, email }
        next();
    } catch (err) {
        if (err.name === 'TokenExpiredError') {
            return res.status(401).json({ error: 'Token expired' });
        }
        return res.status(401).json({ error: 'Invalid token' });
    }
}

app.get('/api/protected', requireAuth, (req, res) => {
    res.json({ message: 'Access granted', userId: req.user.userId });
});
```

### 10.4. Tích hợp với React (Frontend)

```javascript
// api.js - API client cho React app
const API_BASE_URL = 'http://localhost:5000'; // AuthGuard URL
const JWT_SECRET = 'access-token-secret-key-12345'; // Dùng để verify (nếu cần)

class AuthGuardClient {
    constructor() {
        this.accessToken = null;
    }

    // Gọi API đăng nhập qua AuthGuard
    async login(usernameOrEmail, password) {
        const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include', // Quan trọng: gửi cookie
            body: JSON.stringify({ usernameOrEmail, password })
        });
        const data = await res.json();
        if (data.success) {
            this.accessToken = data.accessToken;
            localStorage.setItem('authguard_token', data.accessToken);
        }
        return data;
    }

    // Gọi API đến Resource Server (backend của bạn)
    async callResourceServer(url, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${this.accessToken}`,
            ...options.headers
        };
        
        const res = await fetch(url, { ...options, headers });
        
        // Nếu 401, thử refresh token
        if (res.status === 401) {
            const refreshed = await this.refreshToken();
            if (refreshed) {
                headers['Authorization'] = `Bearer ${this.accessToken}`;
                const retryRes = await fetch(url, { ...options, headers });
                return retryRes.json();
            }
        }
        
        return res.json();
    }

    async refreshToken() {
        const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
            method: 'POST',
            credentials: 'include' // Gửi cookie refresh_token
        });
        const data = await res.json();
        if (data.success) {
            this.accessToken = data.accessToken;
            localStorage.setItem('authguard_token', data.accessToken);
            return true;
        }
        return false;
    }
}

export default new AuthGuardClient();
```

### 10.5. Tích hợp với Django (Python)

```python
import jwt
from django.http import JsonResponse
from functools import wraps

JWT_ACCESS_SECRET = 'access-token-secret-key-12345'

def jwt_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, JWT_ACCESS_SECRET, algorithms=['HS256'])
            request.user_id = payload['userId']
            request.username = payload['username']
        except jwt.ExpiredSignatureError:
            return JsonResponse({'error': 'Token expired'}, status=401)
        except jwt.InvalidTokenError:
            return JsonResponse({'error': 'Invalid token'}, status=401)
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

@jwt_required
def my_protected_view(request):
    return JsonResponse({'user_id': request.user_id})
```

### 10.6. Tích hợp với Next.js (API Routes)

```javascript
// pages/api/protected.js
import jwt from 'jsonwebtoken';

const JWT_ACCESS_SECRET = 'access-token-secret-key-12345';

export default function handler(req, res) {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'Unauthorized' });
    }

    try {
        const payload = jwt.verify(authHeader.split(' ')[1], JWT_ACCESS_SECRET);
        // payload = { userId, username, email }
        res.status(200).json({ 
            message: 'Protected data',
            user: payload 
        });
    } catch (err) {
        res.status(401).json({ error: 'Invalid or expired token' });
    }
}
```

### 10.7. Sử dụng API Verify (không cần share secret)

Nếu bạn không muốn share JWT secret, Resource Server có thể gọi API verify:

```python
import requests

def verify_token(access_token):
    """Gọi AuthGuard API để verify token"""
    response = requests.post(
        'http://authguard-server:5000/api/auth/verify',
        headers={'Authorization': f'Bearer {access_token}'}
    )
    if response.status_code == 200:
        data = response.json()
        return data['user']  # { id, username, email, ... }
    return None
```

### 10.8. Luồng tích hợp tổng quát

```
┌──────────────────────────────────────────────────────────────────────┐
│                    INTEGRATION FLOW                                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  User Browser                    AuthGuard            Resource Server│
│  ────────────                    ────────            ───────────────│
│       │                             │                      │         │
│       │── POST /login ──────────────>│                      │         │
│       │   { username, password }     │                      │         │
│       │                              │                      │         │
│       │<── { accessToken, user } ────│                      │         │
│       │                              │                      │         │
│       │  (Lưu accessToken)           │                      │         │
│       │                              │                      │         │
│       │── GET /api/data ────────────────────────────────────>│         │
│       │   Authorization: Bearer AT   │                      │         │
│       │                              │                      │         │
│       │                              │                      │         │
│       │              ┌──────────────────────────────────────┘         │
│       │              │  Resource Server verify JWT:                   │
│       │              │  jwt.decode(AT, JWT_ACCESS_SECRET)             │
│       │              │  → { userId, username, email }                 │
│       │              └──────────────────────────────────────┐         │
│       │                              │                      │         │
│       │<── { data, userId } ─────────────────────────────────│         │
│       │                              │                      │         │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 11. ERROR CODES & RESPONSE FORMAT

### 11.1. Response Format Chuẩn

**Thành công:**
```json
{
    "success": true,
    // ... data tùy theo endpoint
}
```

**Thất bại:**
```json
{
    "success": false,
    "code": "ERROR_CODE",
    "message": "Human-readable error message"
}
```

### 11.2. Danh sách Error Codes

| HTTP Status | Code                      | Mô tả                                    |
|:-----------:|---------------------------|------------------------------------------|
| 400         | VALIDATION_ERROR          | Dữ liệu đầu vào không hợp lệ             |
| 400         | USERNAME_EXISTS           | Username đã tồn tại                      |
| 400         | EMAIL_EXISTS              | Email đã tồn tại                         |
| 400         | EMAIL_ALREADY_LINKED      | Google đã liên kết với user khác         |
| 400         | GOOGLE_AUTH_FAILED        | Xác thực Google thất bại                 |
| 400         | LINK_GOOGLE_FAILED        | Liên kết Google thất bại                 |
| 400         | UNLINK_GOOGLE_FAILED      | Hủy liên kết Google thất bại             |
| 400         | UPDATE_FAILED             | Cập nhật profile thất bại                |
| 400         | REGISTRATION_FAILED       | Đăng ký thất bại                         |
| 401         | INVALID_CREDENTIALS       | Sai username/email/password              |
| 401         | UNAUTHORIZED              | Thiếu Authorization header               |
| 401         | TOKEN_EXPIRED_OR_INVALID  | Access token hết hạn hoặc không hợp lệ   |
| 401         | SESSION_EXPIRED           | Refresh token hết hạn hoặc đã revoke     |
| 401         | WRONG_PASSWORD            | Mật khẩu hiện tại sai                    |
| 404         | USER_NOT_FOUND            | Không tìm thấy user                      |
| 429         | TOO_MANY_REQUESTS         | Vượt quá rate limit                      |
| 500         | INTERNAL_SERVER_ERROR     | Lỗi server nội bộ                        |
| 500         | LOGIN_FAILED              | Đăng nhập thất bại (server error)        |
| 500         | LOGOUT_FAILED             | Đăng xuất thất bại                       |
| 500         | CHANGE_PASSWORD_FAILED    | Đổi mật khẩu thất bại                    |

---

## 12. TESTING & VERIFICATION

### 12.1. Unit Tests (test_auth.py)

6 test cases bao phủ toàn bộ luồng xác thực:

| # | Test Case                          | Mô tả                                      |
|:-:|------------------------------------|--------------------------------------------|
| 1 | test_registration_flow             | Kiểm tra validation, đăng ký thành công    |
| 2 | test_login_flow                    | Login bằng username, email, sai password   |
| 3 | test_google_auth_flow              | Google login, link account                 |
| 4 | test_token_rotation_and_replay     | Refresh token, replay attack protection    |
| 5 | test_uniqueness_constraints        | Username/email trùng lặp                   |
| 6 | test_rate_limiter                  | Brute force protection                     |

### 12.2. Chạy tests

```bash
# Chạy tất cả tests
python -m pytest test_auth.py -v

# Chạy 1 test cụ thể
python -m pytest test_auth.py::AuthIntegrationTestCase::test_login_flow -v
```

### 12.3. Kiểm tra thủ công (test_api.py)

```bash
# Chạy server
python app.py

# Mở terminal khác, chạy test script
python test_api.py
```

### 12.4. Kiểm tra bằng curl

```bash
# Đăng ký
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@gmail.com","password":"password123"}'

# Đăng nhập
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"usernameOrEmail":"testuser","password":"password123"}'

# Lấy thông tin user (cần thay token)
curl -X GET http://localhost:5000/api/auth/me \
  -H "Authorization: Bearer <access_token>"

# Refresh token
curl -X POST http://localhost:5000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refreshToken":"<refresh_token>"}'

# Kiểm tra health
curl http://localhost:5000/health
```

---

## KẾT LUẬN

AuthGuard là một **Authentication Platform hoàn chỉnh** với kiến trúc tương tự Clerk, cung cấp:

1. **Đa dạng phương thức đăng nhập**: Username, Gmail, Google OAuth
2. **Bảo mật nhiều lớp**: JWT, bcrypt, rate limiting, replay protection, audit log
3. **Session Management**: Rotation, revocation, multi-device
4. **Tích hợp dễ dàng**: Bất kỳ backend nào cũng có thể verify JWT
5. **Frontend SPA**: Giao diện đăng nhập, dashboard, docs đầy đủ
6. **Production-ready**: Error handling, CORS, security headers, health check