from ib_insync.objects import AccountValue
import unittest
from unittest.mock import call, MagicMock, patch

from lib.environment import Environment


class TestEnvironment(unittest.TestCase):

    ACCOUNT_VALUE_TIMEOUT = 2
    ENV_VARS = ['ABC', 'DEF', 'GHI', 'PROJECT_ID']
    IBC_CONFIG = {'a': 1, 'b': 2, 'c': 3}
    PROJECT_ID = 'project-id'
    TRADING_MODE = 'trading_mode'

    @patch('lib.environment.environ', {'PROJECT_ID': 'project-id'})
    @patch('lib.environment.IBGW')
    @patch('lib.environment.GcpModule.get_secret')
    def setUp(self, *_):
        self.test_obj = Environment(self.TRADING_MODE, self.IBC_CONFIG)
        self.test_obj.ACCOUNT_VALUE_TIMEOUT = self.ACCOUNT_VALUE_TIMEOUT
        self.test_obj.ENV_VARS = self.ENV_VARS

    @patch.object(Environment._Environment__Implementation, 'ENV_VARS', ENV_VARS)
    @patch('lib.environment.environ', {'ABC': 'abc', 'DEF': 'def', 'GHI': 'ghi', 'JKL': 'jkl', 'PROJECT_ID': 'project-id'})
    @patch('lib.environment.GcpModule._db', document=MagicMock(side_effect=[MagicMock(get=MagicMock(return_value=MagicMock(to_dict=MagicMock(return_value={'a': 1, 'b': 2, 'c': 3})))),
                                                                            MagicMock(get=MagicMock(return_value=MagicMock(to_dict=MagicMock(return_value={'d': 4, 'e': 5, 'c': 6}))))]))
    @patch('lib.environment.IBGW')
    @patch('lib.environment.GcpModule.get_secret', return_value={'userid': 'userid', 'password': 'password'})
    def test_init(self, get_secret, ibgw, db, *_):
        self.test_obj.destroy()

        environment = Environment(self.TRADING_MODE, self.IBC_CONFIG)
        self.assertDictEqual({'ABC': 'abc', 'DEF': 'def', 'GHI': 'ghi', 'PROJECT_ID': 'project-id'}, environment.env)
        self.assertEqual(self.TRADING_MODE, environment.trading_mode)
        self.assertEqual(ibgw.return_value, environment.ibgw)
        try:
            ibgw.assert_called_once_with({
                **self.IBC_CONFIG,
                'tradingMode': self.TRADING_MODE,
                'userid': 'userid',
                'password': 'password'
            })
            db.document.assert_has_calls([call('config/common'), call(f'config/{self.TRADING_MODE}')])
            get_secret.assert_called_once_with(environment.SECRET_RESOURCE.format(self.PROJECT_ID, self.TRADING_MODE))
        except AssertionError:
            self.fail()

        environment.destroy()

    def test_get_account_values(self):
        account = 'ABC'

        with patch.object(self.test_obj._Environment__instance, '_ibgw',
                          accountValues=MagicMock(side_effect=[[],
                                                               [],
                                                               [AccountValue(account='ABC', tag='NetLiquidation', value='123456', currency='CHF', modelCode=''),
                                                                AccountValue(account='ABC', tag='CashBalance', value='123.45', currency='BASE',modelCode=''),
                                                                AccountValue(account='ABC', tag='CashBalance', value='234.56', currency='CHF', modelCode=''),
                                                                AccountValue(account='ABC', tag='CashBalance', value='345.67', currency='USD', modelCode=''),
                                                                AccountValue(account='ABC', tag='MaintMarginReq', value='321', currency='CHF', modelCode='')]])) as p:
            actual = self.test_obj.get_account_values(account)
            self.assertDictEqual({}, actual)

            with patch.object(self.test_obj._Environment__instance, 'ACCOUNT_VALUE_TIMEOUT', 5):
                expected = {
                    'CashBalance': {'CHF': 234.56, 'USD': 345.67},
                    'MaintMarginReq': {'CHF': 321.0},
                    'NetLiquidation': {'CHF': 123456.0}
                }
                actual = self.test_obj.get_account_values(account)
                self.assertDictEqual(expected, actual)
                try:
                    p.accountValues.assert_called_with(account)
                except AssertionError:
                    self.fail()


if __name__ == '__main__':
    unittest.main()
