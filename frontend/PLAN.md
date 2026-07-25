# Hoàn thiện Frontend + Backend Integration Plan

## 1. Vấn đề phát hiện

### Backend (Flask):
- [ ] `app.py`: Thiếu static file serving cho frontend HTML/CSS/JS
- [ ] `routes.py`: Thiếu route `PUT /api/auth/me` (update-profile) và `POST /api/auth/me` (change-password)

### Frontend:
- [ ] `config.js`: Thiếu TOKEN config — ĐÃ SỬA
- [ ] `login.html`: Đã tạo, cần test với backend thật
- [ ] `register.html`: Đã tạo, cần test với backend thật
- [ ] `dashboard.html`: Đã tạo, cần test
- [ ] `docs.html`: Đã tạo, cần test
- [ ] `index.html`: Đã tạo, cần test

## 2. Kế hoạch sửa

### Bước 1: Thêm static file serving vào app.py
- Serve frontend folder như static files
- Mặc định redirect `/` tới `frontend/index.html`

### Bước 2: Thêm backend routes còn thiếu
- `PUT /api/auth/me` - update profile (username, display_name, avatar_url)
- `POST /api/auth/me` (change-password) - đổi mật khẩu

### Bước 3: Kiểm tra kết nối frontend-backend
- Login/Register flow
- Token refresh
- Dashboard API keys & websites

## 3. File cần sửa
- `app.py`
- `routes.py`

## 4. Test
- `python app.py` -> mở browser localhost:5000
