from datetime import datetime
import unittest
from unittest.mock import MagicMock, patch

from intents.summary import Summary


class TestSummary(unittest.TestCase):

    ENV = {
        'K_REVISION': 'k_revision',
    }

    @patch('intents.intent.Environment', return_value=MagicMock(env=ENV))
    def setUp(self, *_):
        self.test_obj = Summary()

    @patch('intents.summary.Summary._get_fills', return_value='jkl')
    @patch('intents.summary.Summary._get_trades', return_value='ghi')
    @patch('intents.summary.Summary._get_positions', return_value='def')
    def test_core(self, get_positions, get_trades, get_fills):
        with patch.object(self.test_obj, '_env', config={'account': 'account'}, get_account_values=MagicMock(return_value='abc')) as env:
            expected = {
                'accountSummary': 'abc',
                'portfolio': 'def',
                'openTrades': 'ghi',
                'fills': 'jkl'
            }
            actual = self.test_obj._core()
            self.assertDictEqual(expected, actual)
            try:
                env.get_account_values.assert_called_once_with('account')
                get_positions.assert_called_once()
                get_trades.assert_called_once()
                get_fills.assert_called_once()
            except AssertionError:
                self.fail()

    def test_get_fills(self):
        expected = {
            's0': [{'side': 'side0', 'shares': 10, 'price': 2.73, 'cumQuantity': 100, 'avgPrice': 3.14, 'time': '2021-09-01T12:34:56', 'commission': 0.12, 'rPnL': 1.23}],
            's1': [{'side': 'side1', 'shares': 20, 'price': 5.46, 'cumQuantity': 200, 'avgPrice': 6.28, 'time': '2021-09-02T12:34:56', 'commission': 0.25, 'rPnL': 2.47}]
        }
        with patch.object(self.test_obj, '_env',
                          ibgw=MagicMock(fills=MagicMock(return_value=[MagicMock(contract=MagicMock(localSymbol=f's{i}'),
                                         execution=MagicMock(shares=(i + 1) * 10, price=(i + 1) * 2.73, side=f'side{i}', cumQty=(i + 1) * 100, avgPrice=(i + 1) * 3.14, time=datetime(2021, 9, i + 1, 12, 34, 56)),
                                         commissionReport=MagicMock(commission=(i + 1) * 0.1234, realizedPNL=(i + 1) * 1.2345)) for i in range(2)]))) as p:
            actual = self.test_obj._get_fills()
            self.assertDictEqual(expected, actual)
            try:
                p.ibgw.fills.assert_called_once()
            except AssertionError:
                self.fail()

    def test_get_positions(self):
        expected = {
            's0': {'position': 1, 'exposure': 12.35, 'uPnL': 1.23},
            's1': {'position': 2, 'exposure': 24.69, 'uPnL': 2.47}
        }
        with patch.object(self.test_obj, '_env',
                          ibgw=MagicMock(portfolio=MagicMock(return_value=[MagicMock(contract=MagicMock(localSymbol=f's{i}'),
                                         position=float(i + 1),
                                         marketValue=(i + 1) * 12.345,
                                         unrealizedPNL=(i + 1) * 1.2345) for i in range(2)]))) as p:
            actual = self.test_obj._get_positions()
            self.assertDictEqual(expected, actual)
            try:
                p.ibgw.portfolio.assert_called_once()
            except AssertionError:
                self.fail()

    def test_get_trades(self):
        expected = {
            's0': [{'isActive': False, 'isDone': False, 'orderStatus': 's0', 'whyHeld': 'wh0', 'action': 'a0', 'totalQuantity': 1, 'orderType': 't0', 'limitPrice': 123, 'timeInForce': 'tif{i}', 'goodAfterTime': 'gat0', 'goodTillDate': 'gtd0'}],
            's1': [{'isActive': True, 'isDone': True, 'orderStatus': 's1', 'whyHeld': 'wh1', 'action': 'a1', 'totalQuantity': 2, 'orderType': 't1', 'limitPrice': 246, 'timeInForce': 'tif{i}', 'goodAfterTime': 'gat1', 'goodTillDate': 'gtd1'}]
        }
        with patch.object(self.test_obj, '_env',
                          ibgw=MagicMock(openTrades=MagicMock(return_value=[MagicMock(contract=MagicMock(localSymbol=f's{i}'),
                                         isActive=MagicMock(return_value=bool(i)),
                                         isDone=MagicMock(return_value=bool(i)),
                                         order=MagicMock(action=f'a{i}', totalQuantity=float(i + 1), orderType=f't{i}', lmtPrice=(i + 1) * 123, tif='tif{i}', goodAfterTime=f'gat{i}', goodTillDate=f'gtd{i}'),
                                         orderStatus=MagicMock(status=f's{i}', whyHeld=f'wh{i}')) for i in range(2)]))) as p:
            actual = self.test_obj._get_trades()
            self.assertDictEqual(expected, actual)
            try:
                p.ibgw.openTrades.assert_called_once()
            except AssertionError:
                self.fail()


if __name__ == '__main__':
    unittest.main()
