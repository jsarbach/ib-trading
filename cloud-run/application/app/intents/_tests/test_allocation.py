import unittest
from unittest.mock import MagicMock, patch

from intents.allocation import Allocation


class TestAllocation(unittest.TestCase):

    ACTIVITY_LOG = {
        'agent': 'k_revision',
        'exception': None
    }
    CONFIG = {
        'account': 123,
        'adaptivePriority': 'adaptive_priority',
        'exposure': {
            'strategies': {
                's1': 0.5,
                's2': 0.25
            },
            'overall': 1
        },
        'retryCheckMinutes': 0
    }
    ENV = {'K_REVISION': 'k_revision'}
    STRATEGIES = {
        's1': MagicMock(return_value=MagicMock(
            id='s1',
            contracts={'abc': MagicMock(contract=MagicMock(localSymbol='ABC'), local_symbol='ABC'),
                       'def': MagicMock(contract=MagicMock(localSymbol='DEF'), local_symbol='DEF')},
            fx={'a': 123, 'b': 456},
            holdings={'abc': 0.1, 'def': 0.2},
            signals={'abc': 1, 'def': 2},
            target_positions={'abc': 100, 'def': 200})),
        's2': MagicMock(return_value=MagicMock(
            id='s2',
            contracts={'abc': MagicMock(contract=MagicMock(localSymbol='ABC'), local_symbol='ABC'),
                       'def': MagicMock(contract=MagicMock(localSymbol='DEF'), local_symbol='DEF')},
            fx={'a': 123, 'b': 456},
            holdings={'abc': 0.3, 'def': 0.4},
            signals={'abc': 3, 'def': 4},
            target_positions={'abc': 300, 'def': 400}))
    }
    TRADING_MODE = 'trading_mode'

    @patch('intents.intent.Environment', return_value=MagicMock(config=CONFIG, env=ENV))
    @patch('intents.allocation.STRATEGIES', STRATEGIES)
    def setUp(self, *_):
        self.test_obj = Allocation(strategies=[*self.STRATEGIES.keys()])

    @patch('intents.intent.Environment', return_value=MagicMock(
        config=CONFIG,
        db=MagicMock(document=MagicMock(return_value=MagicMock(get=MagicMock(return_value=MagicMock(to_dict=MagicMock(return_value=CONFIG)))))),
        env=ENV,
        trading_mode=TRADING_MODE))
    @patch('intents.allocation.STRATEGIES', STRATEGIES)
    def test_init(self, *_):
        dry_run = False
        order_properties = {}
        strategies = []
        expected = {
            **self.ACTIVITY_LOG,
            'config': self.CONFIG,
            'intent': 'Allocation',
            'signature': 'fa895ca25cae973bf2fe428fe863fac7',
            'tradingMode': self.TRADING_MODE,
            'dryRun': dry_run,
            'orderProperties': order_properties,
            'strategies': strategies
        }
        allocation = Allocation()
        self.assertEqual(Allocation._dry_run, allocation._dry_run)
        self.assertEqual(Allocation._order_properties, allocation._order_properties)
        self.assertEqual(Allocation._strategies, allocation._strategies)
        self.assertDictEqual(expected, allocation._activity_log)

        dry_run = True
        order_properties = {'order': 'properties'}
        allocation = Allocation(dryRun=dry_run, orderProperties=order_properties, strategies=[*self.STRATEGIES.keys()])
        self.assertEqual(dry_run, allocation._dry_run)
        self.assertDictEqual(order_properties, allocation._order_properties)
        self.assertDictEqual(self.STRATEGIES, allocation._strategies)

    @patch('intents.allocation.TagValue', return_value='tag_value')
    @patch('intents.allocation.MarketOrder')
    @patch('intents.allocation.Trade', return_value=MagicMock(consolidate_trades=MagicMock(),
                                                              place_orders=MagicMock(return_value='orders'),
                                                              trades={'abc': {'contract': MagicMock(local_symbol='ABC'),
                                                                              'quantity': 100},
                                                                      'def': {'contract': MagicMock(local_symbol='DEF'),
                                                                              'quantity': -10}}))
    def test_core(self, trade, market_order, tag_value):
        with patch.object(self.test_obj, '_env',
                          config=self.CONFIG,
                          db=MagicMock(collection=MagicMock(return_value=MagicMock(
                              where=MagicMock(return_value=MagicMock(
                                  where=MagicMock(return_value=MagicMock(
                                      where=MagicMock(return_value=MagicMock(
                                          order_by=MagicMock(return_value=MagicMock(
                                              order_by=MagicMock(return_value=MagicMock(
                                                  get=MagicMock(return_value=[123])))))))))))))),
                          env=self.ENV,
                          get_account_values=MagicMock(return_value={'NetLiquidation': {'CHF': 12345}})) as env:
            with patch.object(self.test_obj, '_strategies', self.STRATEGIES) as strategies:
                expected_log = {
                    **self.test_obj._activity_log,
                    'contractIds': {'ABC': 'abc', 'DEF': 'def'},
                    'consolidatedTrades': {'ABC': 100, 'DEF': -10},
                    'fx': {'a': 123, 'b': 456},
                    'holdings': {'s1': {'ABC': 0.1, 'DEF': 0.2}, 's2': {'ABC': 0.3, 'DEF': 0.4}},
                    'netLiquidation': 12345,
                    'orders': 'orders',
                    'signals': {'s1': {'ABC': 1, 'DEF': 2}, 's2': {'ABC': 3, 'DEF': 4}},
                    'targetPositions': {'s1': {'ABC': 100, 'DEF': 200}, 's2': {'ABC': 300, 'DEF': 400}}
                }
                self.test_obj._core()
                self.assertDictEqual(expected_log, self.test_obj._activity_log)
                try:
                    env.get_account_values.assert_called_once_with(self.CONFIG['account'])
                    for k, v in strategies.items():
                        v.assert_called_once_with(base_currency=[*env.get_account_values.return_value['NetLiquidation'].keys()][0],
                                                  exposure=[*env.get_account_values.return_value['NetLiquidation'].values()][0] * self.CONFIG['exposure']['overall'] * self.CONFIG['exposure']['strategies'][k])
                    trade.assert_called_with([v.return_value for v in self.test_obj._strategies.values()])
                    trade.return_value.consolidate_trades.assert_called_once()
                    trade.return_value.place_orders.assert_called_once_with(market_order,
                                                                            order_params={
                                                                                'algoStrategy': 'Adaptive',
                                                                                'algoParams': [tag_value.return_value]
                                                                            },
                                                                            order_properties={**self.test_obj._order_properties, 'tif': 'DAY'})
                    tag_value.assert_called_once_with('adaptivePriority', self.CONFIG['adaptivePriority'])
                except AssertionError:
                    self.fail()

                env.config = {**self.CONFIG, 'exposure': {'strategies': {'s1': 0, 's2': 0.25}, 'overall': 1}}
                strategies['s1'].reset_mock()
                self.test_obj._core()
                try:
                    strategies['s1'].assert_not_called()
                except AssertionError:
                    self.fail()

            env.config = {**self.CONFIG, 'retryCheckMinutes': 5}
            env.get_account_values.reset_mock()
            self.test_obj._core()
            try:
                env.db.collection.assert_called_once_with('activity')
                env.get_account_values.assert_not_called()
            except AssertionError:
                self.fail()

            with patch.object(self.test_obj, '_dry_run', True):
                trade.reset_mock()
                self.test_obj._core()
                try:
                    trade.return_value.place_orders.assert_not_called()
                except AssertionError:
                    self.fail()


if __name__ == '__main__':
    unittest.main()
