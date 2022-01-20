import unittest
from unittest.mock import call, MagicMock, patch, PropertyMock

from intents.close_all import CloseAll


class TestCloseAll(unittest.TestCase):

    ENV = {
        'K_REVISION': 'k_revision',
        'ORDER_PROPERTIES': '{"goodAfterTime":"today"}'
    }
    ORDER_PROPERTIES = {'goodAfterTime': 'today'}
    TRADING_MODE = 'trading_mode'

    @patch('intents.intent.Environment', return_value=MagicMock(env=ENV))
    def setUp(self, *_):
        self.test_obj = CloseAll()

    @patch('intents.intent.Environment', return_value=MagicMock(env=ENV))
    def test_init(self, *_):
        close_all = CloseAll()
        self.assertEqual(CloseAll._dry_run, close_all._dry_run)
        self.assertDictEqual(CloseAll._order_properties, close_all._order_properties)

        dry_run = True
        order_properties = {'order': 'properties'}
        close_all = CloseAll(dryRun=dry_run, orderProperties=order_properties)
        self.assertEqual(dry_run, close_all._dry_run)
        self.assertDictEqual(order_properties, close_all._order_properties)

    @patch('intents.close_all.MarketOrder')
    @patch('intents.close_all.Trade', return_value=MagicMock(consolidate_trades=MagicMock(),
                                                             place_orders=MagicMock(return_value='orders'),
                                                             trades={'abc': {'contract': MagicMock(local_symbol='ABC'), 'quantity': 100},
                                                                     'def': {'contract': MagicMock(local_symbol='DEF'), 'quantity': -10}}))
    def test_core(self, trade, market_order):
        strategy_side_effect = [MagicMock(contracts={'abc': MagicMock(contract=MagicMock(localSymbol='ABC'), local_symbol='ABC'), 'def': MagicMock(contract=MagicMock(localSymbol='DEF'), local_symbol='DEF')},
                                          holdings={'abc': 0.1, 'def': 0.2},
                                          trades={'abc': -0.1, 'def': -0.2}),
                                MagicMock(contracts={'def': MagicMock(contract=MagicMock(localSymbol='DEF'), local_symbol='DEF'), 'ghi': MagicMock(contract=MagicMock(localSymbol='GHI'), local_symbol='GHI')},
                                          holdings={'def': -0.3, 'ghi': 0.4},
                                          trades={'def': 0.3, 'ghi': -0.4})]
        type(strategy_side_effect[0]).id = PropertyMock(return_value='s1')
        type(strategy_side_effect[1]).id = PropertyMock(return_value='s2')

        with patch.object(self.test_obj, '_env',
                          db=MagicMock(document=MagicMock(return_value=MagicMock(delete=MagicMock())),
                                       collection=MagicMock(return_value=MagicMock(get=MagicMock(return_value=[MagicMock(id=f's{i + 1}') for i in range(2)])))),
                          ibgw=MagicMock(orders=MagicMock(return_value=[MagicMock(permId=f'o{i}') for i in range(3)]),
                                         cancelOrder=MagicMock(),
                                         portfolio=MagicMock(return_value=[MagicMock(contract=MagicMock(conId='abc'), position=-100),
                                                                           MagicMock(contract=MagicMock(conId='def'), position=10)])),
                          logging=MagicMock(warning=MagicMock())) as env:
            with patch('intents.close_all.Strategy', side_effect=strategy_side_effect) as strategy:
                expected_log = {
                    **self.test_obj._activity_log,
                    'contractIds': {'ABC': 'abc', 'DEF': 'def', 'GHI': 'ghi'},
                    'consolidatedTrades': {'ABC': 100, 'DEF': -10},
                    'holdings': {'s1': {'ABC': 0.1, 'DEF': 0.2}, 's2': {'DEF': -0.3, 'GHI': 0.4}},
                    'orders': 'orders',
                    'trades': {'s1': {'ABC': -0.1, 'DEF': -0.2}, 's2': {'DEF': 0.3, 'GHI': -0.4}}
                }
                self.test_obj._core()
                self.assertDictEqual(expected_log, self.test_obj._activity_log)
                try:
                    env.ibgw.cancelOrder.assert_has_calls([call(m) for m in env.ibgw.orders.return_value])
                    env.db.document.assert_has_calls([call(f'positions/{self.test_obj._env.trading_mode}/openOrders/o{i}') for i in range(3)])
                    self.assertEqual(3, env.db.document.return_value.delete.call_count)
                    env.db.collection.assert_called_once_with(f'positions/{self.test_obj._env.trading_mode}/holdings')
                    strategy.assert_has_calls([call(k.id) for k in env.db.collection.return_value.get.return_value])
                    trade.return_value.consolidate_trades.assert_called_once()
                    trade.return_value.place_orders.assert_called_once_with(market_order, order_properties=self.test_obj._order_properties)
                except AssertionError:
                    self.fail()

            with patch('intents.close_all.Strategy', side_effect=strategy_side_effect):
                with patch('intents.close_all.Trade', return_value=MagicMock(trades={'abc': {'contract': MagicMock(local_symbol='ABC'), 'quantity': -100},
                                                                                     'def': {'contract': MagicMock(local_symbol='DEF'), 'quantity': 10}})):
                    self.test_obj._core()
                    try:
                        portfolio = {item.contract.conId: item.position for item in env.ibgw.portfolio()}
                        env.logging.warning.assert_called_once_with(f"Consolidated trade and IB portfolio don't match - portfolio: {portfolio}")
                    except AssertionError:
                        self.fail()

            with patch('intents.close_all.Strategy', side_effect=strategy_side_effect):
                with patch.object(self.test_obj, '_dry_run', True):
                    env.db.reset_mock()
                    env.ibgw.reset_mock()
                    trade.reset_mock()
                    self.test_obj._core()
                    try:
                        env.ibgw.cancelOrder.assert_not_called()
                        env.db.document.return_value.delete.assert_not_called()
                        trade.return_value.place_orders.assert_not_called()
                    except AssertionError:
                        self.fail()


if __name__ == '__main__':
    unittest.main()
