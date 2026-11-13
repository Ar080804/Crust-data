"""Exercise both sign-in flows with a temporary DB and offline provider responses."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.app import auth, db, main


class SignInTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(patch.multiple(db, DATABASE_URL="", DB_PATH=str(Path(tmp.name) / "auth.db"),
                                         CLOUD=False, _ready=False, _sqlite=None))
        self.addCleanup(lambda: db._sqlite.close() if db._sqlite is not None else None)
        self.enterContext(patch.multiple(auth, CLOUD=False, API_BASE="http://testserver", DEFAULT_ORIGIN="http://testserver",
                                         ALLOWED_ORIGINS={"http://testserver"}, CREDS=Path(tmp.name) / "none.json"))
        self.enterContext(patch.object(main, "CLOUD", True))
        self.enterContext(patch.object(main, "RUN_WORKER_IN_API", False))
        self.enterContext(patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "example-google", "GOOGLE_CLIENT_SECRET": "test-only",
                                                  "LINKEDIN_CLIENT_ID": "1234", "LINKEDIN_CLIENT_SECRET": "test-only"}))
        self.client = self.enterContext(TestClient(main.app, follow_redirects=False))

    def begin(self, provider):
        response = self.client.get(f"/auth/{provider}/login", params={"redirect": "http://testserver/"})
        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlsplit(response.headers["location"]).query)
        if provider == 'google':
            self.assertEqual(params['code_challenge_method'], ['S256'])
        else:
            self.assertEqual(urlsplit(response.headers['location']).netloc, 'www.linkedin.com')
            self.assertEqual(params['scope'], ['openid profile'])
            self.assertEqual(params['redirect_uri'], ['http://testserver/auth/linkedin/callback'])
        return params["state"][0]

    def test_missing_setup_keeps_both_choices_visible(self):
        with patch.object(auth, "CLOUD", True), patch.object(auth, "DATABASE_URL", ""):
            self.assertEqual(self.client.get('/auth/providers').json(), {"google": False, "linkedin": False})
            for provider in ("google", "linkedin"):
                self.assertEqual(self.client.get(f'/auth/{provider}/login').status_code, 503)

    def test_linkedin_round_trip_and_client_permissions(self):
        self.assertEqual(self.client.get('/auth/providers').json(), {"google": True, "linkedin": True})
        state = self.begin('linkedin')
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {"iss": "https://www.linkedin.com/oauth", "aud": "1234", "sub": "sample-expert", "name": "Test Expert",
                  "iat": int(time.time()), "exp": int(time.time()) + 120}
        token = jwt.encode(claims, key, algorithm='RS256', headers={"kid": "test"})
        keys = Mock()
        keys.get_signing_key_from_jwt.return_value = SimpleNamespace(key=key.public_key())
        payload = Mock()
        payload.json.return_value = {"id_token": token}
        cb = {"code": "local-test", "state": state}
        with patch.object(auth, '_linkedin_keys', return_value=keys), patch.object(auth.httpx, 'post', return_value=payload) as exchange:
            response = self.client.get('/auth/linkedin/callback', params=cb)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(exchange.call_args.args[0], 'https://www.linkedin.com/oauth/v2/accessToken')
            self.assertEqual(exchange.call_args.kwargs['data']['client_secret'], 'test-only')
            self.assertEqual(exchange.call_args.kwargs['data']['client_id'], '1234')
            session = parse_qs(urlsplit(response.headers['location']).fragment)['session'][0]
            headers = {"Authorization": "Bearer " + session}
            me = self.client.get('/auth/me', headers=headers).json()
            self.assertEqual((me['provider'], me['subject'], me['email']), ('linkedin', 'sample-expert', None))
            self.assertEqual(self.client.post('/requests', json={'text':'sample'}, headers=headers).status_code, 403)
            self.assertEqual(self.client.get('/auth/linkedin/callback', params=cb).status_code, 400)
            self.assertEqual(self.client.post('/auth/logout', headers=headers).status_code, 200)
            self.assertEqual(self.client.get('/auth/me', headers=headers).status_code, 401)

    def test_google_round_trip_and_cancel(self):
        state = self.begin('google')
        claims = {'email': 'Client@Example.com', 'email_verified': True, 'sub': 'sample-user', 'name': 'Test Client'}
        payload = Mock()
        payload.json.return_value = {'id_token':'example-provider-response'}
        with patch.object(auth.httpx, 'post', return_value=payload), patch.object(auth.google_id_token, 'verify_oauth2_token', return_value=claims):
            response = self.client.get('/auth/google/callback', params={'state':state, 'code':'local-test'})
            self.assertEqual(response.status_code, 302)
            session = parse_qs(urlsplit(response.headers['location']).fragment)['session'][0]
            user = self.client.get('/auth/me', headers={'Authorization': 'Bearer ' + session}).json()
            self.assertEqual((user['provider'], user['email']), ('google','client@example.com'))
        state = self.begin('linkedin')
        cancelled = self.client.get('/auth/linkedin/callback', params={'state':state,'error':'access_denied'})
        self.assertEqual(cancelled.headers['location'], 'http://testserver/login?role=expert&result=cancelled')

    def test_retired_expert_session_is_not_a_linkedin_identity(self):
        db.ex('INSERT INTO auth_sessions(token_hash,provider,subject,expires_at) VALUES(?,?,?,?)',
              (auth._hash('retired-local'), 'telegram', 'former-expert', time.time() + 120))
        self.assertEqual(self.client.get('/auth/me', headers={'Authorization': 'Bearer retired-local'}).status_code, 401)

    def test_old_google_sessions_survive_upgrade(self):
        import sqlite3
        with sqlite3.connect(db.DB_PATH) as con:
            con.execute('CREATE TABLE auth_sessions (token_hash TEXT PRIMARY KEY,email TEXT,name TEXT,picture TEXT,created_at TEXT,expires_at REAL)')
            con.execute('INSERT INTO auth_sessions VALUES(?,?,?,?,?,?)', (auth._hash('legacy-local'), 'demo@example.com', 'Demo', '', '', time.time()+120))
        result = self.client.get('/auth/me', headers={'Authorization':'Bearer legacy-local'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['provider'], 'google')


if __name__ == '__main__':
    unittest.main()
