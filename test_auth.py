import os
# Force env to test
os.environ["FLASK_ENV"] = "test"

import unittest
import importlib
import json
from datetime import datetime
from unittest.mock import patch
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

    def test_auth_success_responses_use_consistent_envelope(self):
        print("\n--- Testing standardized auth response envelope ---")

        res = self.post_json('/api/auth/register', {
            "username": "EnvelopeUser",
            "email": "envelope@gmail.com",
            "password": "securePassword123"
        })

        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('message', data)
        self.assertIn('accessToken', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['email'], 'envelope@gmail.com')
        print("[OK] Auth success responses expose a consistent envelope")

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

    # 6. TEST PACKAGE LIMITS
    def test_package_user_limit_is_enforced(self):
        print("\n--- Testing Package User Limit ---")
        with self.app.app_context():
            for i in range(100):
                UserService.create_user(
                    username=f"freeuser{i}",
                    email=f"freeuser{i}@gmail.com",
                    password_hash="hashed",
                    package='free'
                )

            with self.assertRaises(ValueError):
                UserService.create_user(
                    username="freeuser101",
                    email="freeuser101@gmail.com",
                    password_hash="hashed",
                    package='free'
                )
        print("[OK] Free package user limit enforced")

    def test_google_client_id_has_default_value(self):
        import config
        self.assertTrue(config.Config.GOOGLE_CLIENT_ID)
        print("[OK] Google client ID is configured by default")

    def test_account_backup_and_restore(self):
        print("\n--- Testing Account Backup & Restore ---")
        with self.app.app_context():
            user = UserService.create_user(
                username="backupuser",
                email="backupuser@gmail.com",
                password_hash="hashed",
                package='free'
            )
            user.package = 'pro'
            user.package_activated_at = datetime.utcnow()
            db.session.commit()

            stored = {}
            def fake_save(data):
                stored['data'] = data
                return 'backup-1'

            def fake_get_backups(user_id=None, email=None):
                return [stored['data']] if stored.get('data') else []

            with patch('services.user_service.SanityService.save_account_backup', side_effect=fake_save), patch('services.user_service.SanityService.get_account_backups', side_effect=fake_get_backups):
                # Save backup directly (synchronous) instead of using threaded sync_account_backup
                from services.sanity_service import SanityService
                from services.user_service import PACKAGE_FEATURES
                backup_data = {
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'package': 'pro',
                    'package_activated_at': user.package_activated_at.isoformat() if user.package_activated_at else None,
                    'role': user.role,
                    'display_name': user.display_name,
                    'avatar_url': user.avatar_url,
                    'created_at': user.created_at.isoformat(),
                    'updated_at': user.updated_at.isoformat() if user.updated_at else None,
                    'backup_source': 'app',
                    'package_used': 0,
                    'package_remaining': None,
                    'package_features': PACKAGE_FEATURES.get('pro', {}),
                    'apikeys': [],
                    'website_domains': [],
                    'payment_history': [],
                }
                SanityService.save_account_backup(backup_data)
                
                user.package = 'free'
                user.package_activated_at = None
                db.session.commit()
                restored = UserService.restore_account_backup(user.id)
                self.assertEqual(restored.package, 'pro')
        print("[OK] Account backup and restore work")

    # 7. TEST PACKAGE USAGE + API KEY FLOW
    def test_package_usage_and_api_key_flow(self):
        print("\n--- Testing Package Usage & API Key Flow ---")

        reg = self.post_json('/api/auth/register', {
            "username": "quotauser",
            "email": "quotauser@gmail.com",
            "password": "password123"
        })
        access_token = reg.get_json()['accessToken']

        keys_res = self.client.post('/api/keys', data=json.dumps({'name': 'Test Key'}), content_type='application/json', headers={'Authorization': f'Bearer {access_token}'})
        self.assertEqual(keys_res.status_code, 201)
        self.assertTrue(keys_res.get_json()['success'])

        usage_res = self.client.get('/api/package/usage', headers={'Authorization': f'Bearer {access_token}'})
        self.assertEqual(usage_res.status_code, 200)
        self.assertEqual(usage_res.get_json()['package']['package'], 'free')
        self.assertIn('used', usage_res.get_json()['package'])
        self.assertIn('remaining', usage_res.get_json()['package'])

        admin_reg = self.post_json('/api/auth/register', {
            "username": "adminquota",
            "email": "soladzpro@gmail.com",
            "password": "password123"
        })
        admin_token = admin_reg.get_json()['accessToken']
        admin_usage = self.client.get('/api/admin/package-usage', headers={'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(admin_usage.status_code, 200)
        self.assertTrue(admin_usage.get_json()['success'])
        self.assertIn('packages', admin_usage.get_json())
        print("[OK] Package usage and API key flow work")

    def test_external_verification_with_api_key(self):
        print("\n--- Testing External Verification With API Key ---")

        reg = self.post_json('/api/auth/register', {
            "username": "integrator",
            "email": "integrator@gmail.com",
            "password": "password123"
        })
        access_token = reg.get_json()['accessToken']

        keys_res = self.client.post('/api/keys', data=json.dumps({'name': 'External App'}), content_type='application/json', headers={'Authorization': f'Bearer {access_token}'})
        self.assertEqual(keys_res.status_code, 201)
        api_key = keys_res.get_json()['key']

        verify_res = self.client.post('/api/integrations/verify', data=json.dumps({'accessToken': access_token}), content_type='application/json', headers={'X-API-Key': api_key})
        self.assertEqual(verify_res.status_code, 200)
        body = verify_res.get_json()
        self.assertTrue(body['success'])
        self.assertTrue(body['valid'])
        self.assertEqual(body['tokenType'], 'access')
        self.assertIn('expiresAt', body)
        self.assertEqual(body['user']['email'], 'integrator@gmail.com')
        print("[OK] External verification accepted API-key-based requests")

    # 8. TEST RATE LIMITER
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
