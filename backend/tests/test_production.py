"""Account isolation, pagination, retry safety and live-service failure behavior."""
import contextlib
import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import adapters, auth, db, engine, gcal, main


class ProductionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(patch.multiple(db, DATABASE_URL='', DB_PATH=str(Path(tmp.name) / 'app.db'),
                                         CLOUD=False, _ready=False, _sqlite=None))
        self.addCleanup(lambda: db._sqlite.close() if db._sqlite else None)
        self.enterContext(patch.object(main, 'CLOUD', True))
        self.enterContext(patch.object(main, 'RUN_WORKER_IN_API', False))
        self.client = self.enterContext(TestClient(main.app, follow_redirects=False))
        for token in ('alice', 'bob', 'expert'):
            db.ex('INSERT INTO auth_sessions(token_hash,provider,subject,email,name,expires_at) VALUES(?,?,?,?,?,?)',
                  (auth._hash(token), 'linkedin' if token == 'expert' else 'google', token,
                   None if token == 'expert' else f'{token}@example.com', token, time.time() + 60))
        self.alice = {'Authorization': 'Bearer alice'}
        self.bob = {'Authorization': 'Bearer bob'}

    def test_history_is_owned_paginated_and_independent_of_browser_storage(self):
        ids = []
        for i in range(3):
            rid = engine.create_request(f'alice request {i}', 'alice@example.com')
            db.update_request(rid, created_at=f'2026-11-26T10:0{i}:00+05:30')
            ids.append(rid)
        foreign = engine.create_request('private bob request', 'bob@example.com')
        first = self.client.get('/requests?limit=2', headers=self.alice)
        self.assertEqual(first.status_code, 200)
        self.assertEqual([i['saved']['id'] for i in first.json()['items']], ids[:0:-1])
        self.assertNotIn('private bob', first.text)
        second = self.client.get('/requests', params={'limit': 2, 'cursor': first.json()['next_cursor']}, headers=self.alice)
        self.assertEqual([i['saved']['id'] for i in second.json()['items']], ids[:1])
        self.assertIsNone(second.json()['next_cursor'])
        self.assertEqual(self.client.get('/requests', params={'cursor': foreign}, headers=self.alice).status_code, 400)
        self.assertEqual(self.client.get('/requests').status_code, 401)
        self.assertEqual(self.client.get('/requests', headers={'Authorization': 'Bearer expert'}).status_code, 403)
        self.assertEqual(self.client.get('/requests?limit=10000', headers=self.alice).status_code, 400)

    def test_archive_hides_only_from_owner_list_without_deleting_request(self):
        rid = engine.create_request('my request', 'alice@example.com')
        self.assertEqual(self.client.post(f'/requests/{rid}/archive', headers=self.bob).status_code, 404)
        self.assertEqual(self.client.post(f'/requests/{rid}/archive', headers=self.alice).status_code, 200)
        self.assertEqual(self.client.get('/requests', headers=self.alice).json()['items'], [])
        self.assertEqual(self.client.get(f'/requests/{rid}', headers=self.alice).status_code, 200)
        self.assertEqual(db.get_request_row(rid)['status'], 'INTAKE')

    def test_duplicate_submission_is_one_request_and_key_cannot_change_payload(self):
        with patch.object(main, 'booking_availability', return_value={'available': True}):
            headers = {**self.alice, 'Idempotency-Key': 'same-retry-key'}
            one = self.client.post('/requests', json={'text': 'warehouse tomorrow'}, headers=headers)
            two = self.client.post('/requests', json={'text': 'warehouse tomorrow'}, headers=headers)
            self.assertEqual(one.status_code, 200)
            self.assertEqual(one.json(), two.json())
            self.assertEqual(db.q1('SELECT COUNT(*) AS n FROM requests')['n'], 1)
            self.assertEqual(db.q1('SELECT COUNT(*) AS n FROM timeline')['n'], 1)
            conflict = self.client.post('/requests', json={'text': 'different request'}, headers=headers)
            self.assertEqual(conflict.status_code, 409)
            separate = self.client.post('/requests', json={'text': 'warehouse tomorrow'},
                                        headers={**self.bob, 'Idempotency-Key': 'same-retry-key'})
            self.assertNotEqual(one.json()['request_id'], separate.json()['request_id'])

    def test_limits_are_per_account_and_return_retry_after(self):
        with patch.object(main, 'booking_availability', return_value={'available': True}):
            for _ in range(10):
                self.assertEqual(self.client.post('/requests', json={'text': 'a request'}, headers=self.alice).status_code, 200)
            blocked = self.client.post('/requests', json={'text': 'one too many'}, headers=self.alice)
            self.assertEqual(blocked.status_code, 429)
            self.assertGreater(int(blocked.headers['Retry-After']), 0)
            self.assertEqual(self.client.post('/requests', json={'text': 'bob request'}, headers=self.bob).status_code, 200)
            self.assertEqual(self.client.post('/requests', json={'text': 'x' * 4001}, headers=self.bob).status_code, 400)

    def test_booking_readiness_checks_worker_and_expert_pool(self):
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': '', 'GOOGLE_CALENDAR_TOKEN_JSON': ''}):
            self.assertFalse(main.booking_availability()['available'])
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test-only', 'GOOGLE_CALENDAR_TOKEN_JSON': 'test-only'}), \
                patch.object(adapters, 'load_experts', return_value=[{'expert_id': 'example'}]):
            self.assertFalse(main.booking_availability()['available'])
            db.kv_set('worker_heartbeat', str(time.time()))
            self.assertTrue(main.booking_availability()['available'])

    def test_worker_backs_off_and_eventually_stops_repeated_failures(self):
        rid = engine.create_request('test request', 'alice@example.com')
        with patch.object(adapters, 'poll_replies', return_value=[]), \
                patch.dict(engine.STEPS, {'INTAKE': lambda _: (_ for _ in ()).throw(RuntimeError('test failure'))}), \
                contextlib.redirect_stderr(io.StringIO()):
            engine.tick()
            after = db.get_request_row(rid)
            self.assertEqual(after['retry_count'], 1)
            self.assertGreater(after['next_attempt'], time.time())
            engine.tick()
            self.assertEqual(db.get_request_row(rid)['retry_count'], 1)
            for _ in range(7):
                db.update_request(rid, next_attempt=0)
                engine.tick()
            self.assertEqual(db.get_request_row(rid)['status'], 'FAILED')

    def test_cloud_never_reports_simulated_delivery_as_real(self):
        with patch.object(gcal, 'CLOUD', True), patch.object(gcal, '_credentials', return_value=None):
            with self.assertRaises(RuntimeError):
                gcal._service()
        with patch.object(adapters, 'CLOUD', True), patch.object(adapters, '_tg', None), \
                patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': ''}):
            self.assertFalse(adapters.send_once('test-cloud', 'test-chat', 'test message'))
            self.assertEqual(db.q1('SELECT status FROM outbox WHERE key=?', ('test-cloud',))['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
