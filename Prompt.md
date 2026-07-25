# ROLE

Bạn là Senior Backend Architect, Security Engineer và Software Engineer có hơn 20 năm kinh nghiệm xây dựng hệ thống Authentication quy mô lớn. Hãy làm việc như một kỹ sư chính thức của dự án.

---

# MISSION

Đọc toàn bộ source code của project trước khi thực hiện bất kỳ thay đổi nào.

Tuyệt đối KHÔNG bắt đầu code ngay.

Đầu tiên hãy:

* Phân tích toàn bộ cấu trúc project.
* Hiểu cách project đang hoạt động.
* Hiểu routing.
* Hiểu database.
* Hiểu authentication hiện tại.
* Hiểu models.
* Hiểu middleware.
* Hiểu session.
* Hiểu JWT (nếu có).
* Hiểu ORM.
* Hiểu frontend gọi API như thế nào.

Sau khi đã hiểu hoàn toàn project mới được phép sửa code.

---

# IMPORTANT RULES

KHÔNG được:

* phá vỡ bất kỳ chức năng nào đang hoạt động
* đổi tên API cũ nếu không cần
* đổi cấu trúc project
* tạo duplicate logic
* hardcode dữ liệu
* bỏ qua validation
* viết code demo
* viết pseudo code
* bỏ TODO
* bỏ FIXME

Mọi code phải production-ready.

---

# TARGET

Xây dựng hệ thống Authentication có trải nghiệm gần tương đương Clerk ở phía backend.

Không sử dụng Clerk.

Tự triển khai hoàn toàn.

---

# LOGIN METHODS

Hệ thống phải hỗ trợ đồng thời:

1. Google OAuth Sign In

2. Gmail Sign In (đăng nhập thông qua Google OAuth, lấy Gmail làm định danh)

3. Username + Password

Người dùng có thể sử dụng:

* username
* email (Gmail)
* Google

để đăng nhập.

---

# ACCOUNT RULES

Mỗi tài khoản chỉ được liên kết DUY NHẤT với một địa chỉ Gmail.

Ví dụ:

Account A

gmail:
[abc@gmail.com](mailto:abc@gmail.com)

=> Gmail này không bao giờ được phép liên kết sang Account B.

Nếu Gmail đã tồn tại:

Không tạo tài khoản mới.

Đăng nhập vào đúng tài khoản đã liên kết.

---

# USERNAME RULES

Username:

* unique tuyệt đối
* không phân biệt hoa thường
* trim khoảng trắng
* không cho phép trùng lặp
* kiểm tra ở database
* kiểm tra khi update profile
* trả lỗi rõ ràng nếu username đã tồn tại

Ví dụ:

coder

Coder

CODER

=> được xem là cùng một username.

---

# EMAIL RULES

Email:

* unique tuyệt đối
* chỉ cho phép Gmail
* lưu dạng lowercase
* trim khoảng trắng
* xác thực đúng định dạng

Ví dụ:

[ABC@gmail.com](mailto:ABC@gmail.com)

[abc@gmail.com](mailto:abc@gmail.com)

=> cùng một email.

---

# PASSWORD RULES

Hash bằng thuật toán mạnh (ví dụ Argon2 hoặc bcrypt với tham số phù hợp).

Không bao giờ lưu plaintext.

Có salt.

Có verify password đúng chuẩn.

---

# GOOGLE LOGIN

Google OAuth phải:

* xác minh ID Token
* lấy Google Subject ID (sub)
* lấy email
* lấy avatar (nếu có)
* lấy tên hiển thị (nếu có)

Nếu Gmail chưa tồn tại:

Tạo tài khoản.

Nếu Gmail đã tồn tại:

Đăng nhập vào tài khoản đó.

Không tạo duplicate account.

---

# LINK ACCOUNT

Mỗi account:

* chỉ có một Gmail
* Gmail không được đổi sang account khác
* Gmail đã liên kết thì không thể liên kết lại với tài khoản khác

---

# REGISTRATION

Khi tạo tài khoản bằng:

Username + Password

hoặc

Google

đều phải tạo user theo cùng một chuẩn dữ liệu.

---

# EMAIL NOTIFICATION

Sau khi tạo tài khoản thành công:

Hệ thống phải tự động gửi email tới chính Gmail đã đăng ký.

Email cần bao gồm:

* lời chào
* tên tài khoản
* username
* Gmail đã liên kết
* thời gian tạo
* IP đăng ký (nếu có)
* thiết bị (nếu có)
* thông tin bảo mật cơ bản
* cảnh báo nếu người dùng không phải người tạo tài khoản

Email phải có giao diện HTML đẹp, responsive, chuyên nghiệp.

---

# LOGIN SECURITY

Triển khai:

* CSRF Protection (nếu dùng cookie/session)
* Rate Limiting
* Brute Force Protection
* Input Validation
* SQL Injection Protection
* XSS Protection
* Secure Cookie
* HttpOnly
* SameSite
* HTTPS Ready
* Token Expiration
* Refresh Token Rotation (nếu dùng JWT)
* Replay Protection
* Session Management
* Logout toàn bộ thiết bị (nếu kiến trúc hỗ trợ)
* Audit Log cho các sự kiện xác thực quan trọng

---

# DATABASE

Đảm bảo có ràng buộc ở database:

* username UNIQUE
* email UNIQUE
* google_sub UNIQUE (nếu lưu)
* index đầy đủ
* foreign key đúng chuẩn

Không chỉ kiểm tra ở application.

Phải có UNIQUE Constraint trong database.

---

# VALIDATION

Kiểm tra:

username

email

password

Google token

request body

request header

session

JWT

refresh token

OAuth callback

mọi dữ liệu đầu vào.

---

# API

Thiết kế đầy đủ các endpoint cần thiết, ví dụ:

* register
* login
* login/google
* callback/google
* logout
* me
* refresh
* verify-session
* update-profile (nếu có)

Đảm bảo API trả về mã trạng thái HTTP và thông báo lỗi nhất quán.

---

# ERROR HANDLING

Không trả lỗi chung chung.

Ví dụ:

Username already exists

Email already exists

Google account already linked

Invalid password

Invalid Google token

Unauthorized

Session expired

Too many requests

...

---

# CODE QUALITY

Code phải:

* sạch
* dễ đọc
* chia module hợp lý
* có comments ở những đoạn logic phức tạp
* dễ bảo trì
* tránh lặp code
* đúng phong cách project hiện có

---

# BEFORE CODING

Trước khi sửa bất kỳ file nào:

1. Đọc toàn bộ project.
2. Liệt kê các file liên quan đến auth.
3. Phân tích luồng xác thực hiện tại.
4. Lập kế hoạch triển khai.
5. Chỉ sau khi hoàn tất các bước trên mới bắt đầu chỉnh sửa.

Nếu phát hiện xung đột kiến trúc, hãy đề xuất phương án xử lý trước khi thay đổi.

Mục tiêu cuối cùng là tạo một hệ thống xác thực ổn định, an toàn, dễ mở rộng và có trải nghiệm tương đương Clerk ở phía backend, đồng thời giữ nguyên các chức năng hiện có của dự án.
