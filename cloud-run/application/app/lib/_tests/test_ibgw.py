import unittest
from unittest.mock import MagicMock, mock_open, patch

from lib.ibgw import IBGW


class TestIbgw(unittest.TestCase):

    CONNECTION_TIMEOUT = 60
    IB_CONFIG = {'abc': 123, 'def': 'ghi'}
    IBC_CONFIG = {'abc': 123, 'twsPath': 'tws/path'}
    TIMEOUT_SLEEP = 5

    @patch('lib.ibgw.IB')
    @patch('lib.ibgw.IBC')
    def setUp(self, *_):
        self.test_obj = IBGW(self.IBC_CONFIG, self.IB_CONFIG, self.CONNECTION_TIMEOUT, self.TIMEOUT_SLEEP)

    @patch('lib.ibgw.IB')
    @patch('lib.ibgw.IBC')
    def test_init(self, ibc, *_):
        ibgw = IBGW(self.IBC_CONFIG, self.IB_CONFIG, self.CONNECTION_TIMEOUT, self.TIMEOUT_SLEEP)
        self.assertDictEqual(self.IBC_CONFIG, ibgw.ibc_config)
        self.assertDictEqual({**self.test_obj.IB_CONFIG, **self.IB_CONFIG}, ibgw.ib_config)
        self.assertEqual(self.CONNECTION_TIMEOUT, ibgw.connection_timeout)
        self.assertEqual(self.TIMEOUT_SLEEP, ibgw.timeout_sleep)
        try:
            ibc.assert_called_once_with(**self.IBC_CONFIG)
        except AssertionError:
            self.fail()

        ibgw = IBGW(self.IBC_CONFIG)
        self.assertDictEqual(self.IBC_CONFIG, ibgw.ibc_config)
        self.assertDictEqual(self.test_obj.IB_CONFIG, ibgw.ib_config)
        self.assertEqual(self.CONNECTION_TIMEOUT, ibgw.connection_timeout)
        self.assertEqual(self.TIMEOUT_SLEEP, ibgw.timeout_sleep)

    @patch('lib.ibgw.logging')
    def test_start_and_connect(self, logging):
        self.test_obj.ibc = MagicMock(start=MagicMock())
        self.test_obj.isConnected = MagicMock(side_effect=[False, False, True])
        self.test_obj.sleep = MagicMock()
        self.test_obj.connect = MagicMock()

        self.test_obj.start_and_connect()
        try:
            self.test_obj.ibc.start.assert_called_once()
            self.test_obj.sleep.assert_called_with(self.test_obj.timeout_sleep)
            self.test_obj.connect.assert_called_with(**self.test_obj.ib_config)
        except AssertionError:
            self.fail()

        self.test_obj.isConnected = MagicMock(side_effect=[False, False, True])
        self.test_obj.connect = MagicMock(side_effect=ConnectionRefusedError())
        self.test_obj.connection_timeout = 5
        with patch('builtins.open', mock_open(read_data='data')) as p:
            self.assertRaises(TimeoutError, self.test_obj.start_and_connect)
        try:
            p.assert_called_once_with(f"{self.test_obj.ibc_config['twsPath']}/launcher.log", 'r')
            logging.info.assert_called_with('data')
        except AssertionError:
            self.fail()

        self.test_obj.isConnected = MagicMock(side_effect=[False, False, True])
        self.test_obj.connect = MagicMock(side_effect=ConnectionRefusedError())
        self.test_obj.connection_timeout = 5
        self.assertRaises(TimeoutError, self.test_obj.start_and_connect)
        try:
            logging.warning.assert_called_with(f"{self.test_obj.ibc_config['twsPath']}/launcher.log not found")
        except AssertionError:
            self.fail()

    def test_stop_and_terminate(self):
        self.test_obj.disconnect = MagicMock()
        self.test_obj.ibc.terminate = MagicMock()
        self.test_obj.sleep = MagicMock()

        self.test_obj.stop_and_terminate()
        try:
            self.test_obj.disconnect.assert_called_once()
            self.test_obj.ibc.terminate.assert_called_once()
            self.test_obj.sleep.assert_called_once_with(0)
        except AssertionError:
            self.fail()

        self.test_obj.stop_and_terminate(5)
        try:
            self.test_obj.sleep.assert_called_with(5)
        except AssertionError:
            self.fail()


if __name__ == '__main__':
    unittest.main()
