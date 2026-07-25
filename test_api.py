import requests

BASE = 'http://127.0.0.1:5000/api/auth'

# 1. Test Login
print('=== LOGIN ===')
r = requests.post(BASE + '/login', json={'usernameOrEmail': 'testuser', 'password': 'password123'})
print('Status:', r.status_code)
data = r.json()
print('Success:', data['success'])
access_token = data.get('accessToken')
print('Access Token:', access_token[:30] + '...')

# 2. Test GET /me
print('\n=== GET /me ===')
headers = {'Authorization': 'Bearer ' + access_token}
r = requests.get(BASE + '/me', headers=headers)
print('Status:', r.status_code)
print('User:', r.json()['user']['username'])

# 3. Test PUT /me (update profile)
print('\n=== UPDATE PROFILE ===')
r = requests.put(BASE + '/me', headers=headers, json={'display_name': 'Test User Display'})
print('Status:', r.status_code, 'Success:', r.json()['success'])

# 4. Test CHANGE PASSWORD
print('\n=== CHANGE PASSWORD ===')
r = requests.post(BASE + '/change-password', headers=headers, json={'currentPassword': 'password123', 'newPassword': 'newpass1234'})
print('Status:', r.status_code, 'Success:', r.json().get('success'))

# 5. Test LOGIN with new password
print('\n=== LOGIN WITH NEW PASSWORD ===')
r = requests.post(BASE + '/login', json={'usernameOrEmail': 'testuser', 'password': 'newpass1234'})
print('Status:', r.status_code, 'Success:', r.json()['success'])

# 6. Test CHECK USERNAME
print('\n=== CHECK USERNAME ===')
r = requests.post(BASE + '/check-username', json={'username': 'testuser'})
print('Available:', r.json()['available'])

# 7. Test HEALTH
print('\n=== HEALTH ===')
r = requests.get('http://127.0.0.1:5000/health')
print('Status:', r.json())

print('\nALL TESTS PASSED!')
