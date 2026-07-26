# Fix SyntaxError for Railway Deployment

## Problem
Bài toán Python 3.13 hiểu nhầm cú pháp list comprehension bên trong function call ở routes_payment.py line 167.
Lỗi: `closing parenthesis '}' does not match opening parenthesis '(' on line 152`

## Solution
Thay thế inline list comprehension bằng vòng lặp for thông thường trong các hàm sau:

### Phase 1: Fix routes_payment.py
- [ ] Fix `get_my_requests()` - list comprehension trong return value
- [ ] Fix `list_api_keys()` - inline list comprehension
- [ ] Fix `list_websites()` - inline list comprehension
- [ ] Fix `admin_get_users()` - inline list comprehension
- [ ] Verify syntax với Python

### Phase 2: Verify tests pass
- [ ] Run test_auth.py
- [ ] Run test_api.py
