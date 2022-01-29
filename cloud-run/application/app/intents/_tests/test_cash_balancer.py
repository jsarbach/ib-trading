import unittest
from unittest.mock import MagicMock, patch

from intents.cash_balancer import CashBalancer


class TestCashBalancer(unittest.TestCase):

    ENV = {
        'K_REVISION': 'k_revision'
    }
    TRADING_MODE = 'trading_mode'

    @patch('intents.intent.Environment', return_value=MagicMock(env=ENV))
    def setUp(self, *_):
        self.test_obj = CashBalancer()

    @patch('intents.intent.Environment', return_value=MagicMock(env=ENV))
    def test_init(self, *_):
        cash_balancer = CashBalancer()
        self.assertEqual(CashBalancer._dry_run, cash_balancer._dry_run)

        dry_run = True
        cash_balancer = CashBalancer(dryRun=dry_run)
        self.assertEqual(dry_run, cash_balancer._dry_run)

    @patch('intents.cash_balancer.MarketOrder')
    @patch('intents.cash_balancer.Forex')
    def test_core(self, forex, market_order):
        activity_log = self.test_obj._activity_log

        with patch.object(self.test_obj, '_env',
                          config={'account': 'account', 'cashBalanceThresholdInBaseCurrency': 2000},
                          get_account_values=MagicMock(return_value={'NetLiquidation': {'CHF': 12345},
                                                                     'CashBalance': {'CHF': 10000, 'EUR': -2345, 'USD': 3456},
                                                                     'ExchangeRate': {'CHF': 1.0, 'EUR': 0.5, 'USD': 2.0}}),
                          ibgw=MagicMock(placeOrder=MagicMock(return_value=MagicMock(order=MagicMock(permId='permId'))),
                                         trades=MagicMock(return_value=[MagicMock(contract=MagicMock(pair=MagicMock(return_value='pair')),
                                                                                  order=MagicMock(nonDefaults=MagicMock(return_value={'a': 'A'})),
                                                                                  orderStatus=MagicMock(permId='permId', nonDefaults=MagicMock(return_value={'b': 'B'})))]))) as env:
            expected_log = {
                **activity_log,
                'exposure': {'EUR': -1172.5, 'USD': 6912.0},
                'orders': {'pair': {'order': {'a': 'A'}, 'orderStatus': {'b': 'B'}}},
                'trades': {'USDCHF': -3000}
            }
            self.test_obj._core()
            self.assertDictEqual(expected_log, self.test_obj._activity_log)
            try:
                env.get_account_values.assert_called_once_with('account', rows=['NetLiquidation', 'CashBalance', 'ExchangeRate'])
                env.ibgw.placeOrder.assert_called_once_with(forex.return_value, market_order.return_value)
                forex.assert_called_once_with(pair='USDCHF', exchange='FXCONV')
                market_order.assert_called_once_with('SELL', 3000)
            except AssertionError:
                self.fail()

            env.ibgw.placeOrder.reset_mock()
            with patch.object(self.test_obj, '_dry_run', True):
                self.test_obj._core()
                try:
                    env.ibgw.placeOrder.assert_not_called()
                except AssertionError:
                    self.fail()

            env.ibgw.placeOrder.reset_mock()
            env.config = {'account': 'account', 'cashBalanceThresholdInBaseCurrency': 20000}
            expected_log = {
                **activity_log,
                'exposure': {'EUR': -1172.5, 'USD': 6912.0},
                'trades': {}
            }
            self.test_obj._core()
            self.assertDictEqual(expected_log, self.test_obj._activity_log)
            try:
                env.ibgw.placeOrder.assert_not_called()
            except AssertionError:
                self.fail()


if __name__ == '__main__':
    unittest.main()
