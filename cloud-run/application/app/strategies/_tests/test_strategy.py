import unittest
from unittest.mock import call, MagicMock, patch, PropertyMock

from strategies.strategy import Instrument, Strategy


class TestStrategy(unittest.TestCase):

    @patch.object(Strategy, '_calculate_trades')
    @patch.object(Strategy, '_calculate_target_positions')
    @patch.object(Strategy, '_get_holdings')
    @patch.object(Strategy, '_get_signals')
    @patch.object(Strategy, '_setup')
    @patch('strategies.strategy.Environment')
    def setUp(self, *_):
        self.test_obj = Strategy()

    @patch.object(Strategy, '_calculate_trades')
    @patch.object(Strategy, '_calculate_target_positions')
    @patch.object(Strategy, '_get_holdings')
    @patch.object(Strategy, '_get_signals')
    @patch.object(Strategy, '_setup')
    @patch('strategies.strategy.Environment')
    def test_init(self, environment, _setup, _get_signals, _get_holdings, _calculate_target_positions, _calculate_trades, *_):
        kwargs = {'base_currency': 'ABC', 'exposure': 3}

        strategy = Strategy(**kwargs)
        self.assertEqual('strategy', strategy._id)
        self.assertEqual(kwargs['base_currency'], strategy._base_currency)
        self.assertEqual(kwargs['exposure'], strategy._exposure)
        try:
            environment.assert_called_once()
            _setup.assert_called_once()
            _get_signals.assert_called_once()
            _get_holdings.assert_called_once()
            _calculate_target_positions.assert_called_once()
            _calculate_trades.assert_called_once()
        except AssertionError:
            self.fail()

        with patch('strategies.strategy.Strategy._signals', {i: i * 10 for i in [1, 2, 3]}):
            with patch('strategies.strategy.Strategy._holdings', {i: i * 10 for i in [2, 3, 4, 5]}):
                strategy = Strategy(**kwargs)
                self.assertEqual({1: 10, 2: 20, 3: 30, 4: 0, 5: 0}, strategy._signals)
                self.assertEqual({1: 0, 2: 20, 3: 30, 4: 40, 5: 50}, strategy._holdings)

    @patch.object(Strategy, '_get_currencies')
    def test_calculate_target_positions(self, _get_currencies):
        contracts = {
            'abc': MagicMock(contract=MagicMock(currency='USD', multiplier=2, get_tickers=MagicMock()), tickers=MagicMock(close=10)),
            'def': MagicMock(contract=MagicMock(currency='EUR', multiplier=5, get_tickers=MagicMock()), tickers=MagicMock(close=20)),
            'ghi': MagicMock(contract=MagicMock(currency='CHF', multiplier=10, get_tickers=MagicMock()), tickers=MagicMock(close=5)),
        }

        with patch.object(self.test_obj, '_signals', {'abc': 1.2, 'def': -2.3, 'ghi': 3.4}):
            with patch.object(self.test_obj, '_fx', {'CHF': 1, 'EUR': 1.1, 'USD': 0.9}):
                with patch.object(self.test_obj, '_exposure', 50000):
                    with patch.object(self.test_obj, '_base_currency', 'CHF'):
                        with patch.object(self.test_obj, '_contracts', contracts):
                            self.test_obj._calculate_target_positions()
                            self.assertDictEqual({'abc': 3333, 'def': -1045, 'ghi': 3400}, self.test_obj._target_positions)
                            try:
                                for v in contracts.values():
                                    v.contract.get_tickers.assert_not_called()
                                _get_currencies.assert_called_once_with('CHF')
                            except AssertionError:
                                self.fail()

                        type(contracts['ghi']).tickers = PropertyMock(side_effect=[None, MagicMock(close=5)])
                        with patch.object(self.test_obj, '_contracts', contracts):
                            self.test_obj._calculate_target_positions()
                            self.assertDictEqual({'abc': 3333, 'def': -1045, 'ghi': 3400}, self.test_obj._target_positions)
                            try:
                                contracts['ghi'].get_tickers.assert_called_once()
                            except AssertionError:
                                self.fail()

                        with patch.object(self.test_obj, '_base_currency', None):
                            self.test_obj._calculate_target_positions()
                            self.assertDictEqual({'abc': 0, 'def': 0, 'ghi': 0}, self.test_obj._target_positions)
                    with patch.object(self.test_obj, '_exposure', 0):
                        self.test_obj._calculate_target_positions()
                        self.assertDictEqual({'abc': 0, 'def': 0, 'ghi': 0}, self.test_obj._target_positions)

    def test_calculate_trades(self):
        with patch.object(self.test_obj, '_target_positions', {'abc': 1, 'def': 2, 'ghi': 3}):
            with patch.object(self.test_obj, '_holdings', {'abc': 2, 'def': 1, 'ghi': 3}):
                with patch.object(self.test_obj, '_contracts', {k: MagicMock(local_symbol=k) for k in ['abc', 'def', 'ghi']}):
                    self.test_obj._calculate_trades()
                    self.assertDictEqual({'abc': -1, 'def': 1}, self.test_obj._trades)

    def test_get_currencies(self):
        base_currency = 'CHF'
        currencies = ['CHF', 'USD', 'EUR', 'USD']

        with patch('strategies.strategy.InstrumentSet', MagicMock(get_tickers=MagicMock())) as instrumentset:
            instrumentset.return_value.__iter__.return_value = [MagicMock(get_ticker=MagicMock(), tickers=MagicMock(close=1, midpoint=MagicMock(return_value=1))),
                                                                 MagicMock(get_ticker=MagicMock(), tickers=MagicMock(close=1, midpoint=MagicMock(return_value=float('nan')))),
                                                                 MagicMock(get_ticker=MagicMock(), tickers=MagicMock(close=1, midpoint=MagicMock(return_value=1)))]
            with patch('strategies.strategy.Forex') as forex:
                with patch.object(self.test_obj, '_contracts', {c: MagicMock(contract=MagicMock(currency=c)) for c in currencies}):
                    self.test_obj._get_currencies(base_currency)
                    self.assertDictEqual({'CHF': 1, 'EUR': 1, 'USD': 1}, self.test_obj._fx)
                    try:
                        forex.assert_has_calls([call(pair=c + base_currency) for c in set(currencies)])
                        instrumentset.assert_called_once_with(*[forex.return_value] * 3)
                        instrumentset.return_value.get_tickers.assert_called_once()
                    except AssertionError:
                        self.fail()

    @patch.object(Strategy, '_register_contracts')
    def test_get_holdings(self, _register_contracts):
        with patch.object(self.test_obj, '_env',
                          db=MagicMock(document=MagicMock(return_value=MagicMock(get=MagicMock(return_value=MagicMock(to_dict=MagicMock(return_value={f'{i}': i for i in range(3)}),
                                                                                                                      exists=True))))),
                          trading_mode='trading_mode') as env:
            self.test_obj._get_holdings()
            self.assertDictEqual({i: i for i in range(3)}, self.test_obj._holdings)
            try:
                env.db.document.assert_called_once_with('positions/trading_mode/holdings/strategy')
                _register_contracts.assert_called_once_with(*[i for i in range(3)])
            except AssertionError:
                self.fail()

            with patch.object(self.test_obj, '_env',
                              db=MagicMock(document=MagicMock(return_value=MagicMock(get=MagicMock(return_value=MagicMock(to_dict=MagicMock(return_value={f'{i}': i for i in range(3)}),
                                                                                     exists=False))))),
                              trading_mode='trading_mode'):
                self.test_obj._get_holdings()
                self.assertDictEqual({}, self.test_obj._holdings)

    def test_get_signals(self):
        with patch.object(self.test_obj, '_holdings', {'a': 1, 'b': 2, 'c': 3}):
            self.test_obj._get_signals()
            self.assertDictEqual({'a': 0, 'b': 0, 'c': 0}, self.test_obj._signals)

    def test_register_contracts(self):
        self.assertRaises(TypeError, self.test_obj._register_contracts, 1, 'a', MagicMock(spec=Instrument))

        with patch.object(self.test_obj, '_contracts', {1: '1', 2: '2'}):
            with patch('strategies.strategy.Contract') as contract:
                self.test_obj._register_contracts(2, 3)
                self.assertDictEqual({1: '1', 2: '2', 3: contract.return_value}, self.test_obj._contracts)
                try:
                    contract.assert_has_calls([call(conId=2), call(conId=3)])
                except AssertionError:
                    self.fail()

        with patch.object(self.test_obj, '_contracts', {1: '1', 2: '2'}):
            contracts = [MagicMock(spec=Instrument, contract=MagicMock(conId=2)),
                         MagicMock(spec=Instrument, contract=MagicMock(conId=3))]
            self.test_obj._register_contracts(*contracts)
            self.assertDictEqual({1: '1', 2: '2', 3: contracts[1]}, self.test_obj._contracts)


if __name__ == '__main__':
    unittest.main()
