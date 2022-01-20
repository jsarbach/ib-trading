from ib_insync import MarketOrder, OrderStatus
import unittest
from unittest.mock import call, MagicMock, patch, PropertyMock

from lib.trading import Instrument, InstrumentSet, Future, Trade
from lib.trading import datetime, DELETE_FIELD


class TestInstrument(unittest.TestCase):

    @patch('lib.trading.Environment')
    @patch.object(Instrument, 'IB_CLS')
    def setUp(self, *_):
        self.test_obj = Instrument()

    @patch('lib.trading.Environment')
    @patch.object(Instrument, 'get_tickers')
    @patch.object(Instrument, 'get_contract_details')
    @patch.object(Instrument, 'IB_CLS')
    def test_init(self, ib_cls, get_contract_details, get_tickers, *_):
        Instrument(a=1, b=2)
        try:
            ib_cls.assert_called_once_with(a=1, b=2)
            get_contract_details.assert_called_once()
            get_tickers.assert_not_called()
        except AssertionError:
            self.fail()

        ib_cls.reset_mock()
        Instrument(get_tickers=True, a=3, b=4)
        try:
            ib_cls.assert_called_once_with(a=3, b=4)
            get_tickers.assert_called_once()
        except AssertionError:
            self.fail()

    @patch('lib.trading.InstrumentSet', spec=InstrumentSet)
    def test_as_instrumentset(self, instrumentset):
        actual = self.test_obj.as_instrumentset()
        self.assertEqual(instrumentset.return_value, actual)
        try:
            instrumentset.assert_called_once_with(self.test_obj)
        except AssertionError:
            self.fail()

    def test_get_contract_details(self):
        contract = {'contract': MagicMock(localSymbol='ABC')}
        key_value = {'key': 'value'}

        with patch.object(self.test_obj, '_env', ibgw=MagicMock(reqContractDetails=MagicMock(return_value=[]))):
            self.test_obj.get_contract_details()
            self.assertEqual(None, self.test_obj._details)

        with patch.object(self.test_obj, '_ib_contract') as ib_contract:
            with patch.object(self.test_obj, '_env', ibgw=MagicMock(reqContractDetails=MagicMock(return_value=[MagicMock(nonDefaults=MagicMock(return_value={**contract, **key_value}))]))) as env:
                self.test_obj.get_contract_details()
                self.assertEqual(contract['contract'], self.test_obj._contract)
                self.assertEqual(contract['contract'].localSymbol, self.test_obj._local_symbol)
                self.assertDictEqual(key_value, self.test_obj._details)
                try:
                    env.ibgw.reqContractDetails.assert_called_once_with(ib_contract)
                except AssertionError:
                    self.fail()

    def test_get_tickers(self):
        with patch.object(self.test_obj, '_env', ibgw=MagicMock(reqTickers=MagicMock(return_value=[]))):
            self.test_obj.get_tickers()
            self.assertEqual(None, self.test_obj._details)

        with patch.object(self.test_obj, '_contract') as contract:
            with patch.object(self.test_obj, '_env', ibgw=MagicMock(reqTickers=MagicMock(return_value=['ABC']))) as env:
                self.test_obj.get_tickers()
                self.assertEqual('ABC', self.test_obj._tickers)
                try:
                    env.ibgw.reqTickers.assert_called_once_with(contract)
                except AssertionError:
                    self.fail()


class TestFuture(unittest.TestCase):

    CONTRACT_SPECS = {
        'TICKER': {
            'currency': 'CCY',
            'exchange': 'EXC',
            'expiry_scheme': 'x'
        }
    }
    EXPIRY_SCHEMES = {
        'x': ['A', 'B', 'C']
    }

    @patch('lib.trading.Environment')
    def setUp(self, *_):
        self.test_obj = Future()
        self.test_obj.CONTRACT_SPECS = self.CONTRACT_SPECS
        self.test_obj.EXPIRY_SCHEMES = self.EXPIRY_SCHEMES

    @patch.object(Future, 'CONTRACT_SPECS', CONTRACT_SPECS)
    @patch.object(Future, 'EXPIRY_SCHEMES', EXPIRY_SCHEMES)
    @patch.object(Future, '__new__')
    @patch('lib.trading.InstrumentSet', return_value=range(6))
    @patch('lib.trading.GcpModule', get_logger=MagicMock())
    def test_get_contract_series(self, gcp_module, instrumentset, future, *_):
        side_effect = [MagicMock(contract=None),
                       MagicMock(contract=MagicMock(lastTradeDateOrContractMonth='20211118')),
                       MagicMock(contract=MagicMock(lastTradeDateOrContractMonth='20211218')),
                       MagicMock(contract=MagicMock(lastTradeDateOrContractMonth='20220118')),
                       MagicMock(contract=MagicMock(lastTradeDateOrContractMonth='20220218')),
                       MagicMock(contract=MagicMock(lastTradeDateOrContractMonth='20220318'))]

        future.side_effect = side_effect
        with patch('lib.trading.datetime', now=MagicMock(return_value=datetime(2021, 12, 12))):
            actual = Future.get_contract_series(3, 'TICKER', 6)
            self.assertCountEqual(instrumentset.return_value[:3], actual)
            try:
                gcp_module.get_logger.assert_called_once()
                future.assert_has_calls([call(Future, localSymbol=s, exchange='EXC', currency='CCY')
                                         for s in [f'TICKER{m}{y}' for y in [1, 2] for m in self.EXPIRY_SCHEMES['x']]])
                instrumentset.assert_called_once_with(*side_effect[3:])
            except AssertionError:
                self.fail()

        future.side_effect = side_effect
        instrumentset.reset_mock()
        with patch('lib.trading.datetime', now=MagicMock(return_value=datetime(2021, 12, 11))):
            Future.get_contract_series(3, 'TICKER', 6)
            try:
                instrumentset.assert_called_once_with(*side_effect[2:])
            except AssertionError:
                self.fail()


class TestInstrumentSet(unittest.TestCase):

    @patch('lib.trading.Environment')
    @patch.object(Instrument, 'IB_CLS')
    def setUp(self, *_):
        instruments = tuple([MagicMock(spec=Instrument, local_symbol=str(i)) for i in range(3)])
        self.test_obj = InstrumentSet(*instruments)

    @patch('lib.trading.Environment')
    @patch.object(Instrument, 'IB_CLS')
    def test_init(self, *_):
        instruments = tuple([Instrument() for _ in range(3)])
        instrumentset = InstrumentSet(*instruments)
        self.assertTupleEqual(instruments, instrumentset._constituents)

        self.assertRaises(TypeError, InstrumentSet, 'a')
        self.assertRaises(TypeError, InstrumentSet, 1, 2, '3')

    @patch('lib.trading.Environment')
    @patch.object(Instrument, 'IB_CLS')
    def test_add(self, *_):
        instruments = tuple([Instrument() for _ in range(3)])
        actual = self.test_obj + InstrumentSet(*instruments)
        self.assertTupleEqual(tuple(list(self.test_obj._constituents) + list(instruments)), actual._constituents)

    @patch('lib.trading.Environment')
    @patch.object(Instrument, 'IB_CLS')
    def test_get_item(self, *_):
        instruments = tuple([Instrument() for _ in range(3)])
        instrumentset = InstrumentSet(*instruments)
        for i in range(3):
            self.assertEqual(instruments[i], instrumentset[i])
        self.assertEqual(instruments[1:], instrumentset[1:])

    @patch('lib.trading.Environment')
    @patch.object(Instrument, 'IB_CLS')
    def test_iter(self, *_):
        instruments = tuple([Instrument() for _ in range(3)])
        instrumentset = InstrumentSet(*instruments)
        for i, j in zip(instruments, instrumentset):
            self.assertEqual(i, j)

    def test_get_tickers(self):
        with patch.object(self.test_obj, '_env', ibgw=MagicMock(reqTickers=MagicMock(return_value=[i for i in range(3)]))) as env:
            self.test_obj.get_tickers()
            self.assertEqual([i for i in range(3)], [c._tickers for c in self.test_obj._constituents])
            try:
                env.ibgw.reqTickers.assert_called_once_with(*self.test_obj.contracts)
            except AssertionError:
                self.fail()


class TestTrade(unittest.TestCase):

    CONFIG = {'account': 'account'}

    @patch('lib.trading.Environment')
    def setUp(self, *_):
        self.test_obj = Trade()

    @patch('lib.trading.Environment')
    def test_init(self, *_):
        strategies = ['a', 'b', 'c']
        trade = Trade(strategies)
        self.assertEqual(strategies, trade._strategies)

    def test_consolidate_trades(self):
        with patch.object(self.test_obj, '_strategies', [MagicMock(trades={'abc': 10, 'def': -20}, contracts={'abc': 'c1', 'def': 'c2'}),
                                                         MagicMock(trades={'def': 20, 'ghi': 30}, contracts={'def': 'c2', 'ghi': 'c3'}),
                                                         MagicMock(trades={'ghi': -10}, contracts={'ghi': 'c3'})]) as strategies:
            for i, s in enumerate(strategies):
                type(s).id = PropertyMock(return_value=f's{i}')

            expected = {
                'abc': {
                    'contract': 'c1',
                    'quantity': 10,
                    'source': {'s0': 10}
                },
                'ghi': {
                    'contract': 'c3',
                    'quantity': 20,
                    'source': {'s1': 30, 's2': -10}
                },
            }
            self.test_obj.consolidate_trades()
            self.assertDictEqual(expected, self.test_obj._trades)

    @patch('lib.trading.datetime', now=MagicMock(return_value=datetime(2022, 1, 1)))
    def test_log_trades(self, *_):
        active_trades = [MagicMock(contract=MagicMock(conId=i, localSymbol=f's{i}'),
                                   orderStatus=MagicMock(status=o, nonDefaults=MagicMock(return_value={i: f'{i}'})),
                                   order=MagicMock(orderId=f'o{i}', permId=f'p{i}', nonDefaults=MagicMock(return_value={i: f'{i}'})),
                                   isActive=MagicMock(return_value=i))
                         for i, o in enumerate(OrderStatus.ActiveStates)]
        done_trades = [MagicMock(contract=MagicMock(conId=i + len(active_trades), localSymbol=f's{i + len(active_trades)}'),
                                 orderStatus=MagicMock(status=o, nonDefaults=MagicMock(return_value={i + len(active_trades): f'{i + len(active_trades)}'})),
                                 order=MagicMock(orderId=f'o{i + len(active_trades)}', permId=f'p{i + len(active_trades)}', nonDefaults=MagicMock(return_value={i + len(active_trades): f'{i + len(active_trades)}'})),
                                 isActive=MagicMock(return_value=i + len(active_trades)))
                       for i, o in enumerate(OrderStatus.DoneStates)]
        _active_trades = {i: {'source': {f's{i}': (i + 1) * 100}} for i in range(len(active_trades))}
        _done_trades = {i + len(active_trades): {'source': {f's{i + len(active_trades)}': (i + len(active_trades) + 1) * 100}} for i in range(len(done_trades))}

        with patch.object(self.test_obj, '_trades', {**_active_trades, **_done_trades}):
            with patch.object(self.test_obj, '_env',
                              config=self.CONFIG,
                              db=MagicMock(collection=MagicMock(return_value=MagicMock(
                                  document=MagicMock(return_value=MagicMock(
                                      id='id',
                                      set=MagicMock(),
                                      get=MagicMock(return_value=MagicMock(exists=True, to_dict=MagicMock(return_value={f'{k}': (i + 1) * 10 for i, k in enumerate(_done_trades.keys())}))),
                                      update=MagicMock()))))),
                              trading_mode='trading_mode') as env:
                expected = {
                    f's{i}': {
                        'order': {i: f'{i}'},
                        'orderStatus': {i: f'{i}'},
                        'isActive': i
                    } for i in range(len(active_trades + done_trades))
                }
                actual = self.test_obj._log_trades(active_trades + done_trades)
                self.assertDictEqual(expected, actual)
                try:
                    env.db.collection.assert_has_calls([call('positions/trading_mode/openOrders') for _ in range(len(active_trades))] + [call('positions/trading_mode/holdings') for _ in range(len(done_trades))])
                    env.db.collection.return_value.document.assert_has_calls([call() for _ in range(len(active_trades))] + [call(k) for v in _done_trades.values() for k in v['source'].keys()])
                    env.db.collection.return_value.document.return_value.set.assert_has_calls([call({
                        'acctNumber': self.CONFIG['account'],
                        'contractId': i,
                        'orderId': f'o{i}',
                        'permId': f'p{i}',
                        'source': {f's{i}': (i + 1) * 100},
                        'timestamp': datetime(2022, 1, 1)
                    }) for i in range(len(active_trades))])
                    env.db.collection.return_value.document.return_value.update.assert_has_calls([call({'4': 510}), call({'5': 620}), call({'6': 730})])
                except AssertionError:
                    self.fail()

                env.db = MagicMock(collection=MagicMock(return_value=MagicMock(
                    document=MagicMock(return_value=MagicMock(
                        set=MagicMock(),
                        get=MagicMock(return_value=MagicMock(exists=False, to_dict=MagicMock(return_value={f'{k}': (k + 1) * -100 for k in _done_trades.keys()}))))))))
                self.test_obj._log_trades(done_trades)
                try:
                    env.db.collection.return_value.document.return_value.set.assert_has_calls([call({'4': DELETE_FIELD}), call({'5': DELETE_FIELD}), call({'6': DELETE_FIELD})])
                except AssertionError:
                    self.fail()

    @patch.object(MarketOrder, 'update', return_value=MagicMock(update=MagicMock()))
    def test_place_orders(self, market_order):
        trades = {i: {'contract': MagicMock(contract=f'c{i}'), 'quantity': (2 * int(i % 2) - 1) * (i + 1) * 100} for i in range(3)}
        order_prarams = {'key': 'param_value'}
        order_properties = {'key': 'property_value'}

        with patch.object(self.test_obj, '_trades', trades):
            with patch.object(self.test_obj, '_log_trades', return_value={i: str(i) for i in range(3)}) as log_trades:
                with patch.object(self.test_obj, '_env',
                                  ibgw=MagicMock(placeOrder=MagicMock(side_effect=[MagicMock(order=MagicMock(permId=i)) for i in range(3)]),
                                                 trades=MagicMock(return_value=[MagicMock(order=MagicMock(permId=i)) for i in range(4)]),
                                                 sleep=MagicMock())) as env:
                    actual = self.test_obj.place_orders(market_order, order_prarams, order_properties)
                    self.assertDictEqual(log_trades.return_value, actual)
                    try:
                        market_order.assert_has_calls([call(action='SELL', totalQuantity=100, key='param_value'),
                                                       call(action='BUY', totalQuantity=200, key='param_value'),
                                                       call(action='SELL', totalQuantity=300, key='param_value')])
                        market_order.return_value.update.assert_called_with(**{'tif': 'GTC', 'key': 'property_value'})
                        env.ibgw.sleep.assert_called_with(2)
                        log_trades.assert_called_once_with(env.ibgw.trades.return_value[:3])
                    except AssertionError:
                        self.fail()


if __name__ == '__main__':
    unittest.main()
