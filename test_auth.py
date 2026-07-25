import os
# Force env to test
os.environ["FLASK_ENV"] = "test"

import unittest
import importlib
import json
from app import create_app
from models import db, User, Session, AuditLog
from services.user_service import UserService

class AuthIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        import tempfile
        import os
        # Use a file-based SQLite DB to avoid in-memory connection-sharing issues.
        # File-based SQLite correctly handles cross-request transaction visibility.
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.db_fd)
        
        self.app = create_app(test_config={
            'TESTING': True,
            'ENV': 'test',
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{self.db_path}',
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        import os
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    # Helpers
    def post_json(self, path, data, headers=None):
        return self.client.post(
            path,
            data=json.dumps(data),
            content_type='application/json',
            headers=headers
        )

    def get_json(self, path, headers=None):
        return self.client.get(
            path,
            content_type='application/json',
            headers=headers
        )

    def test_postgres_database_url_is_configured_for_railway(self):
        import config
        original_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgres://user:pass@host:5432/authdb"
        reloaded_config = importlib.reload(config)
        self.assertIn("sslmode=require", reloaded_config.Config.SQLALCHEMY_DATABASE_URI)
        self.assertIn("connect_timeout=5", reloaded_config.Config.SQLALCHEMY_DATABASE_URI)
        if original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_db_url
        importlib.reload(config)

    # 1. TEST REGISTRATION FLOW
    def test_registration_flow(self):
        print("\n--- Testing Registration Flow ---")

        # Test non-Gmail validation
        res1 = self.post_json('/api/auth/register', {
            "username": "coder_bob",
            "email": "bob@yahoo.com",
            "password": "securePassword123"
        })
        self.assertEqual(res1.status_code, 400)
        self.assertEqual(res1.get_json()['code'], "VALIDATION_ERROR")
        print("[OK] Correctly blocked non-Gmail addresses")

        # Test short password validation
        res2 = self.post_json('/api/auth/register', {
            "username": "coder_bob",
            "email": "bob@gmail.com",
            "password": "short"
        })
        self.assertEqual(res2.status_code, 400)
        self.assertEqual(res2.get_json()['code'], "VALIDATION_ERROR")
        print("[OK] Correctly blocked short passwords")

        # Successful Registration
        res3 = self.post_json('/api/auth/register', {
            "username": "CoderBob",
            "email": "bob@gmail.com",
            "password": "securePassword123"
        })
        self.assertEqual(res3.status_code, 201)
        data = res3.get_json()
        self.assertTrue(data['success'])
        self.assertIn('accessToken', data)
        self.assertIn('refreshToken', data)
        print("[OK] Registration successful")

    # 2. TEST LOGIN FLOW
    def test_login_flow(self):
        print("\n--- Testing Login Flow ---")
        
        # Register user first
        self.post_json('/api/auth/register', {
            "username": "CoderBob",
            "email": "bob@gmail.com",
            "password": "securePassword123"
        })

        # Incorrect Password
        res1 = self.post_json('/api/auth/login', {
            "usernameOrEmail": "coderbob",
            "password": "wrongPassword"
        })
        self.assertEqual(res1.status_code, 401)
        self.assertEqual(res1.get_json()['code'], "INVALID_CREDENTIALS")
        print("[OK] Blocked incorrect credentials")

        # Login with username (Case-insensitive)
        res2 = self.post_json('/api/auth/login', {
            "usernameOrEmail": "CODERBOB",
            "password": "securePassword123"
        })
        self.assertEqual(res2.status_code, 200)
        data = res2.get_json()
        self.assertIn('accessToken', data)
        print("[OK] Login with case-insensitive username successful")

        # Login with Email
        res3 = self.post_json('/api/auth/login', {
            "usernameOrEmail": "BOB@gmail.com",
            "password": "securePassword123"
        })
        self.assertEqual(res3.status_code, 200)
        self.assertIn('accessToken', res3.get_json())
        print("[OK] Login with email successful")

        # Me route with Token
        token = res3.get_json()['accessToken']
        res4 = self.get_json('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res4.status_code, 200)
        self.assertEqual(res4.get_json()['user']['email'], "bob@gmail.com")
        print("[OK] Protected me endpoint returns correct user information")

    # 3. TEST GOOGLE OAUTH
    def test_google_auth_flow(self):
        print("\n--- Testing Google OAuth Flow ---")

        # Register normal user Bob
        self.post_json('/api/auth/register', {
            "username": "CoderBob",
            "email": "bob@gmail.com",
            "password": "securePassword123"
        })

        # Login with Google (new user Alice)
        res1 = self.post_json('/api/auth/google', {
            "idToken": "mock_google_token_alice"
        })
        self.assertEqual(res1.status_code, 200)
        data = res1.get_json()
        self.assertEqual(data['user']['email'], "alice@gmail.com")
        print("[OK] Google login created and logged in new user successfully")

        # Login with Google using same email as normal user Bob (link logic check)
        res2 = self.post_json('/api/auth/google', {
            "idToken": "mock_google_token_bob"
        })
        self.assertEqual(res2.status_code, 200)
        with self.app.app_context():
            bob_db = UserService.find_by_email("bob@gmail.com")
            self.assertEqual(res2.get_json()['user']['id'], bob_db.id)
            self.assertIsNotNone(bob_db.google_sub)
        print("[OK] Google login correctly linked to existing user profile with same Gmail address")

    # 4. TEST TOKEN ROTATION & REPLAY ATTACK PROTECTION
    def test_token_rotation_and_replay_attack(self):
        print("\n--- Testing Token Rotation & Replay Attack Protection ---")

        # Register
        reg = self.post_json('/api/auth/register', {
            "username": "rotator",
            "email": "rotator@gmail.com",
            "password": "password123"
        })
        first_refresh = reg.get_json()['refreshToken']

        # Rotate once
        res1 = self.post_json('/api/auth/refresh', {"refreshToken": first_refresh})
        self.assertEqual(res1.status_code, 200)
        new_refresh = res1.get_json()['refreshToken']
        self.assertNotEqual(first_refresh, new_refresh)
        print("[OK] Successfully rotated Refresh Token and got new pair")

        # Replay Attack: attempt to use the first refresh token again.
        # We must delete the current cookie first because the Flask test client
        # automatically sends cookies. Without this, the route reads the new
        # valid cookie instead of the JSON body's old (revoked) token.
        # This simulates an attacker who has the OLD token string but not the
        # current browser cookie (e.g., captured via network sniffing).
        self.client.delete_cookie('refresh_token')
        res2 = self.post_json('/api/auth/refresh', {"refreshToken": first_refresh})
        self.assertEqual(res2.status_code, 401)
        print("[OK] Replay attempt correctly rejected")

        # Replay Protection Verification: All sessions of this user must have been revoked!
        with self.app.app_context():
            user = UserService.find_by_email("rotator@gmail.com")
            active_sessions = Session.query.filter_by(user_id=user.id, revoked=False).all()
            self.assertEqual(len(active_sessions), 0)
        print("[OK] Replay attack protection successfully revoked all user sessions")

    # 5. TEST DUPLICATE PREVENTION CONSTRAINTS
    def test_uniqueness_constraints(self):
        print("\n--- Testing Duplicate Prevention constraints ---")

        self.post_json('/api/auth/register', {
            "username": "CoderBob",
            "email": "bob@gmail.com",
            "password": "securePassword123"
        })

        # Duplicate Username (Case Insensitive)
        res1 = self.post_json('/api/auth/register', {
            "username": "coderbob",
            "email": "bob_new@gmail.com",
            "password": "securePassword123"
        })
        self.assertEqual(res1.status_code, 400)
        self.assertEqual(res1.get_json()['code'], "USERNAME_EXISTS")
        print("[OK] Duplicate username block (case-insensitive CoderBob vs coderbob) works perfectly")

        # Duplicate Email
        res2 = self.post_json('/api/auth/register', {
            "username": "coder_bob_new",
            "email": "bob@gmail.com",
            "password": "securePassword123"
        })
        self.assertEqual(res2.status_code, 400)
        self.assertEqual(res2.get_json()['code'], "EMAIL_EXISTS")
        print("[OK] Duplicate email block works perfectly")

    # 6. TEST RATE LIMITER
    def test_rate_limiter(self):
        print("\n--- Testing Rate Limiter & Brute-force Block ---")

        # Since authLimiter allows 5 attempts, we send 6 requests with 'x-test-rate-limit' header
        headers = {"x-test-rate-limit": "true"}
        last_status = 200

        for i in range(6):
            res = self.post_json('/api/auth/login', {
                "usernameOrEmail": "bob@gmail.com",
                "password": "wrong_password_attempt"
            }, headers=headers)
            last_status = res.status_code
            if last_status == 429:
                break

        self.assertEqual(last_status, 429)
        print("[OK] Brute force rate limiting block works perfectly (429 status)")

if __name__ == '__main__':
    unittest.main()
