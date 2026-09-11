import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import requests
from cloud_health import start_health

class WebsiteTests(unittest.TestCase):
    def test_routes_remain_read_only_and_hide_provider_errors(self):
        class FailedProvider:
            def status(self):
                raise RuntimeError('secret-provider-key')
        garden = SimpleNamespace(status='waiting_for_backup', round=3)
        with patch.dict(os.environ, PORT='0'):
            server = start_health(garden, FailedProvider())
        url = 'http://127.0.0.1:' + str(server.server_port)
        try:
            page = requests.get(url, timeout=5)
            self.assertEqual(page.status_code, 200)
            self.assertIn('<title>Garden of Flies</title>', page.text)
            for asset in ('observatory.js', 'observatory.css'):
                self.assertEqual(requests.get(url + '/' + asset, timeout=5).status_code, 200)
            self.assertEqual(requests.get(url + '/healthz', timeout=5).json()['status'], 'waiting_for_backup')
            failure = requests.get(url + '/api/status', timeout=5)
            self.assertEqual(failure.status_code, 503)
            self.assertNotIn('secret-provider-key', failure.text)
            for path in ('/.garden/live-status.json', '/Garden-of-Flies-wallet-backup.json', '/pilot_config.json'):
                self.assertEqual(requests.get(url + path, timeout=5).status_code, 404)
            self.assertEqual(requests.post(url + '/api/status', timeout=5).status_code, 405)
        finally:
            server.shutdown()
            server.server_close()

if __name__ == '__main__':
    unittest.main()
