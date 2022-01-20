from abc import ABC
from datetime import datetime, timedelta, timezone
import ib_insync
from google.cloud.firestore_v1 import DELETE_FIELD

from lib.environment import Environment
from lib.gcp import GcpModule


class Instrument(ABC):

    IB_CLS = None
    _contract = None
    _details = None
    _local_symbol = None
    _tickers = None

    def __init__(self, get_tickers=False, **kwargs):
        self._ib_contract = self.IB_CLS(**kwargs)
        self._env = Environment()
        self.get_contract_details()
        if get_tickers:
            self.get_tickers()

    @property
    def contract(self):
        return self._contract

    @property
    def details(self):
        return self._details

    @property
    def local_symbol(self):
        return self._local_symbol

    @property
    def tickers(self):
        return self._tickers

    def as_instrumentset(self):
        return InstrumentSet(self)

    def get_contract_details(self):
        """
        Requests contract details from IB.
        """
        if len(contract_details := self._env.ibgw.reqContractDetails(self._ib_contract)):
            contract_details = contract_details[0].nonDefaults()
            self._contract = contract_details.pop('contract')
            self._local_symbol = self._contract.localSymbol
            self._details = contract_details

    def get_tickers(self):
        """
        Requests price data for contract from IB.
        """
        self._env.logging.info(f'Requesting tick data for {self._local_symbol}...')
        if len(tickers := self._env.ibgw.reqTickers(self._contract)):
            self._tickers = tickers[0]


class Contract(Instrument):

    IB_CLS = ib_insync.Contract


class Forex(Instrument):

    IB_CLS = ib_insync.Forex


class Future(Instrument):

    CONTRACT_SPECS = {
        'MNQ': {
            'currency': 'USD',
            'exchange': 'GLOBEX',
            'expiry_scheme': 'q'
        }
    }
    IB_CLS = ib_insync.Future
    EXPIRY_SCHEMES = {
        'm': ['F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z'],
        'q': ['H', 'M', 'U', 'Z']
    }

    @classmethod
    def get_contract_series(cls, n, ticker, rollover_days_before_expiry=1):
        logging = GcpModule.get_logger()

        contract_years = [str(datetime.now().year + i)[-1] for i in range(2)]
        contract_symbols = [ticker + m + y for y in contract_years for m in cls.EXPIRY_SCHEMES[cls.CONTRACT_SPECS[ticker]['expiry_scheme']]]

        logging.info(f"Requesting contract for {', '.join(contract_symbols)}...")
        contracts = InstrumentSet(*[f for f in [cls(localSymbol=s,
                                                    exchange=cls.CONTRACT_SPECS[ticker]['exchange'],
                                                    currency=cls.CONTRACT_SPECS[ticker]['currency'])
                                                for s in contract_symbols]
                                    if f.contract is not None and f.contract.lastTradeDateOrContractMonth > (datetime.now() + timedelta(days=rollover_days_before_expiry)).strftime('%Y%m%d')])
        return contracts[:n]


class Index(Instrument):

    IB_CLS = ib_insync.Index


class InstrumentSet:

    def __init__(self, *args):
        # check for iterability and type
        iter(args)
        if not all(isinstance(a, Instrument) for a in args):
            raise TypeError('Not all arguments are of type Instrument')

        self._constituents = args
        self._env = Environment()

    def __add__(self, other):
        return InstrumentSet(*[*self] + [*other])

    def __getitem__(self, item):
        return self._constituents[item]

    def __iter__(self):
        return iter(self._constituents)

    @property
    def constituents(self):
        return self._constituents

    @property
    def contracts(self):
        return [c.contract for c in self._constituents]

    @property
    def tickers(self):
        return [c.tickers for c in self._constituents]

    def get_tickers(self):
        """
        Requests price data for contract from IB.
        """
        self._env.logging.info(f"Requesting tick data for {', '.join(c.local_symbol for c in self._constituents)}...")
        tickers = self._env.ibgw.reqTickers(*self.contracts)
        for c, t in zip(self._constituents, tickers):
            c._tickers = t


class Trade:

    _trades = {}
    _trade_log = {}

    def __init__(self, strategies=()):
        self._env = Environment()
        self._strategies = strategies

    @property
    def trades(self):
        return self._trades

    def consolidate_trades(self):
        """
        Consolidates the trades of all strategies (sum of quantities, grouped by
        contract), remembering which strategy ('source') wants to trade what so
        that we have proper accounting.
        """
        self._trades = {}
        for strategy in self._strategies:
            for k, v in strategy.trades.items():
                if k not in self._trades:
                    self._trades[k] = {}
                self._trades[k]['contract'] = strategy.contracts[k]
                if 'quantity' in self._trades[k]:
                    self._trades[k]['quantity'] += v
                else:
                    self._trades[k]['quantity'] = v
                if 'source' in self._trades[k]:
                    self._trades[k]['source'][strategy.id] = v
                else:
                    self._trades[k]['source'] = {strategy.id: v}

        self._trades = {k: v for k, v in self._trades.items() if v['quantity'] != 0}

    def _log_trades(self, trades=None):
        """
        Logs orders in Firestore under holdings if already filled or openOrders if not.

        :param trades: orders that were placed (list of ib_insync Trade objects)
        :return: activity log entry (dict)
        """
        if trades is None:
            trades = self._env.ibgw.trades()

        for t in trades:
            # self._env.logging.debug(ib_insync.util.tree(t.nonDefaults()))
            contract_id = t.contract.conId
            if t.orderStatus.status in ib_insync.OrderStatus.ActiveStates:
                # add to openOrders collection if not done yet
                doc_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/openOrders').document()
                doc_ref.set({
                    'acctNumber': self._env.config['account'],
                    'contractId': contract_id,
                    'orderId': t.order.orderId,
                    'permId': t.order.permId if t.order.permId else None,
                    'source': self._trades[contract_id]['source'],
                    'timestamp': datetime.now(timezone.utc)
                })
                self._env.logging.info(f'Added {contract_id} to /positions/{self._env.trading_mode}/openOrders/{doc_ref.id}')
            elif t.orderStatus.status in ib_insync.OrderStatus.DoneStates:
                for strategy, quantity in self._trades[contract_id]['source'].items():
                    # update holdings collection if filled
                    doc_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings').document(strategy)
                    portfolio = doc_ref.get().to_dict() or {}
                    # firestore.transforms.Increment(increment)
                    action = doc_ref.update if doc_ref.get().exists else doc_ref.set
                    action({
                        str(contract_id): portfolio.get(str(contract_id), 0) + quantity or DELETE_FIELD
                    })
                    self._env.logging.info(f'Updated {contract_id} in /positions/{self._env.trading_mode}/holdings/{strategy}')
                    # TODO: use Fill/Execution instead?

        # return activity log entry
        return {
            t.contract.localSymbol: {
                'order': {
                    k: v
                    for k, v in t.order.nonDefaults().items()
                    if isinstance(v, (int, float, str))
                },
                'orderStatus': {
                    k: v
                    for k, v in t.orderStatus.nonDefaults().items()
                    if isinstance(v, (int, float, str))
                },
                'isActive': t.isActive()
            } for t in trades
        }

    def place_orders(self, order_type=ib_insync.MarketOrder, order_params=None, order_properties=None):
        """
        Places orders in the market.

        :param order_type: IB order type (ib_insync Order object)
        :param order_params: arguments for IB order (dict)
        :param order_properties: additional order parameters (dict)
        :return: activity log entry (dict)
        """
        order_properties = order_properties or {}
        order_params = order_params or {}

        # place orders
        perm_ids = []
        for v in self._trades.values():
            order = self._env.ibgw.placeOrder(v['contract'].contract,
                                              order_type(action='BUY' if v['quantity'] > 0 else 'SELL',
                                                         totalQuantity=abs(v['quantity']),
                                                         **order_params).update(**{'tif': 'GTC', **order_properties}))
            # give the IB Gateway a couple of seconds to digest orders and to raise possible errors
            self._env.ibgw.sleep(2)
            perm_ids.append(order.order.permId)
        self._env.logging.debug(f'Order permanent IDs: {perm_ids}')

        self._trade_log = self._log_trades([t for t in self._env.ibgw.trades() if t.order.permId in perm_ids])

        return self._trade_log
