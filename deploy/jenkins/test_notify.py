"""Exercise CI report delivery without contacting Telegram."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import notify


class NotificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.reports = Path(temporary.name)
        (self.reports / 'deployment.json').write_text('{"status":"deployed"}')
        (self.reports / 'frontend.xml').write_text(
            '<testsuites tests="2"><testcase/><testcase><skipped/></testcase></testsuites>')
        (self.reports / 'pytest.xml').write_text(
            '<testsuites tests="2"><testsuite tests="2"><testcase/>'
            '<testcase><failure/></testcase></testsuite></testsuites>')
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.enterContext(patch.dict(notify.os.environ, {
            'TELEGRAM_BOT_TOKEN': 'secret-test-token',
            'TELEGRAM_CHAT_ID': '123', 'CI_RESULT': 'FAILURE',
        }, clear=True))
        self.sleep = self.enterContext(patch.object(notify.time, 'sleep'))
        self.urlopen = self.enterContext(patch.object(notify.urllib.request, 'urlopen'))

    def success(self):
        return io.BytesIO(b'{"ok":true}')

    def test_report_preserves_result_and_counts_cases_once(self):
        self.urlopen.return_value = self.success()
        notify.main(self.reports)
        request = self.urlopen.call_args.args[0]
        text = json.loads(request.data)['text']
        self.assertIn('FAILURE', text)
        self.assertIn('Тестов: 4; ошибок: 1; пропущено: 1', text)
        self.assertIn('Приложение обновлено, проверка запуска успешна.', text)
        self.sleep.assert_not_called()

    def test_transient_errors_retry_then_succeed(self):
        self.urlopen.side_effect = [TimeoutError(), urllib.error.URLError('private'), self.success()]
        notify.main(self.reports)
        self.assertEqual(self.urlopen.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)
        self.assertIn('delivered', self.output.getvalue())
        self.assertNotIn('private', self.output.getvalue())

    def test_http_error_has_safe_diagnostic_and_nonzero_exit(self):
        self.urlopen.side_effect = urllib.error.HTTPError(
            'https://example.test/secret-test-token', 401, 'secret-test-token', None, None)
        with self.assertRaises(SystemExit):
            notify.main(self.reports)
        self.assertEqual(self.urlopen.call_count, 3)
        self.assertIn('HTTP 401', self.output.getvalue())
        self.assertNotIn('secret-test-token', self.output.getvalue())

    def test_malformed_and_rejected_responses_retry_then_succeed(self):
        self.urlopen.side_effect = [io.BytesIO(b'not-json'), io.BytesIO(b'{"ok":false}'), self.success()]
        notify.main(self.reports)
        self.assertEqual(self.urlopen.call_count, 3)

    def test_network_exhaustion_does_not_change_deployment(self):
        self.urlopen.side_effect = urllib.error.URLError('secret-test-token')
        with self.assertRaises(SystemExit):
            notify.main(self.reports)
        self.assertEqual(self.urlopen.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)
        self.assertEqual(json.loads((self.reports / 'deployment.json').read_text())['status'], 'deployed')
        self.assertNotIn('secret-test-token', self.output.getvalue())


if __name__ == '__main__':
    unittest.main()
