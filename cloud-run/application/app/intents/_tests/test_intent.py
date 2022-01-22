import unittest
from unittest.mock import MagicMock, patch

from intents.intent import Intent
from intents.intent import datetime, md5


class TestIntent(unittest.TestCase):

    ACTIVITY_LOG = {
        'agent': 'k_revision',
        'exception': None
    }
    CONFIG = {'marketDataType': 12}
    ENV = {'K_REVISION': 'k_revision'}
    TRADING_MODE = 'trading_mode'

    @patch('intents.intent.Environment', return_value=MagicMock(db=MagicMock(),
                                                                env=ENV,
                                                                ibgw=MagicMock(),
                                                                logging=MagicMock(),
                                                                sm=MagicMock()))
    def setUp(self, *_):
        self.test_obj = Intent()
        self.test_obj._config = self.CONFIG

    @patch('intents.intent.Environment', return_value=MagicMock(config=CONFIG,
                                                                env=ENV,
                                                                trading_mode=TRADING_MODE))
    def test_init(self, env):
        intent = Intent(xyz='xyz', abc='abc')
        expected = {
            **self.ACTIVITY_LOG,
            'config': intent._env.config,
            'intent': 'Intent',
            'signature': md5(b'k_revisionIntent{"abc": "abc", "xyz": "xyz"}').hexdigest(),
            'tradingMode': self.TRADING_MODE
        }
        self.assertDictEqual(expected, intent._activity_log)

    def test_core(self):
        with patch.object(self.test_obj, '_env', ibgw=MagicMock(), logging=MagicMock()) as env:
            expected = {'currentTime': env.ibgw.reqCurrentTime.return_value.isoformat()}
            actual = self.test_obj._core()
            self.assertDictEqual(expected, actual)

    @patch('intents.intent.datetime', utcnow=MagicMock(return_value=datetime(1977, 9, 27, 19, 15)))
    def test_log_activity(self, dt):
        with patch.object(self.test_obj, '_env',
                          db=MagicMock(collection=MagicMock(return_value=MagicMock(document=MagicMock(return_value=MagicMock(set=MagicMock(side_effect=[None, Exception])))))),
                          logging=MagicMock()) as env:
            with patch.object(self.test_obj, '_activity_log', {}):
                self.test_obj._log_activity()
                try:
                    env.db.collection.assert_not_called()
                except AssertionError:
                    self.fail()

        activity_log = {'abc': 123, 'def': 'ghi'}

        with patch.object(self.test_obj, '_env',
                          db=MagicMock(collection=MagicMock(return_value=MagicMock(document=MagicMock(return_value=MagicMock(set=MagicMock(side_effect=[None, Exception])))))),
                          logging=MagicMock()) as env:
            with patch.object(self.test_obj, '_activity_log', activity_log):
                self.test_obj._log_activity()
                self.assertDictEqual({**activity_log, 'timestamp': dt.utcnow.return_value}, self.test_obj._activity_log)
                try:
                    env.db.collection.return_value.document.return_value.set.assert_called_once_with(self.test_obj._activity_log)
                except AssertionError:
                    self.fail()

            self.test_obj._log_activity()
            try:
                env.logging.error.assert_called_once()
                env.logging.info.assert_called_once_with(self.test_obj._activity_log)
            except AssertionError:
                self.fail()

    @patch.object(Intent, '_log_activity')
    @patch.object(Intent, '_core', side_effect=[{'abc': 123}, {}, Exception('error')])
    def test_run(self, core, log_activity):
        activity_log = {'abc': 'xyz', 'timestamp': datetime(1977, 9, 27, 19, 15)}
        self.test_obj._activity_log = activity_log

        with patch.object(self.test_obj, '_core'):
            with patch.object(self.test_obj, '_env', ibgw=MagicMock(), logging=MagicMock(), env={'K_REVISION': 'localhost'}):
                self.test_obj.run()
                log_activity.assert_not_called()

        with patch.object(self.test_obj, '_env', config=self.CONFIG, ibgw=MagicMock(), logging=MagicMock()) as env:
            actual = self.test_obj.run()
            self.assertDictEqual({'abc': 123}, actual)
            try:
                env.ibgw.start_and_connect.assert_called_once()
                env.ibgw.reqMarketDataType.assert_called_once_with(self.CONFIG['marketDataType'])
                core.assert_called_once()
                log_activity.assert_called_once()
                env.ibgw.stop_and_terminate.assert_called_once()
            except AssertionError:
                self.fail()

            actual = self.test_obj.run()
            self.assertDictEqual({**activity_log, 'timestamp': activity_log['timestamp'].isoformat()}, actual)

            self.assertRaises(Exception, self.test_obj.run)
            self.assertDictEqual({**activity_log, 'exception': 'Exception: error'}, self.test_obj._activity_log)
            try:
                env.logging.error.assert_called_once()
            except AssertionError:
                self.fail()

            self.assertEqual(3, log_activity.call_count)
            self.assertEqual(3, env.ibgw.stop_and_terminate.call_count)


if __name__ == '__main__':
    unittest.main()
