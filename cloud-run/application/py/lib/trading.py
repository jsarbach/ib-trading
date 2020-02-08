from datetime import datetime, timezone
from google.cloud import firestore_v1 as firestore
from ib_insync import Contract as IBContract, Forex, MarketOrder, OrderStatus
import logging


# instantiate Firestore Client
db = firestore.Client()


class Contract:

    _contract = None
    _details = None
    _local_symbol = None
    _tickers = None

    def __init__(self, contract_id, ib_gw):
        self.id = contract_id
        self._ib_gw = ib_gw

        self.get_contract_details()
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

    def get_contract_details(self):
        """
        Requests contract details from IB.
        """

        contract_details = self._ib_gw.reqContractDetails(IBContract(conId=self.id))[0].nonDefaults()
        self._contract = contract_details.pop('contract')
        self._local_symbol = self._contract.localSymbol
        self._details: contract_details

    def get_tickers(self):
        """
        Requests price data for contract from IB.
        """

        logging.info('Requesting tick data for {}...'.format(self._local_symbol))
        self._tickers = self._ib_gw.reqTickers(self._contract)[0]


class Strategy:

    _contracts = []
    _fx = {}
    _holdings = {}
    _scaled_signals = {}
    _signals = {}
    _target_positions = {}
    _trades = {}

    def __init__(self, name, module=None, **kwargs):
        self._name = name
        self._module = module
        self._ib_gw = kwargs['ib_gw']
        self._trading_mode = kwargs['trading_mode']
        self._base_currency = kwargs.get('base_currency', None)
        self._exposure = kwargs.get('exposure', None)
        self._net_liquidation = kwargs.get('net_liquidation', None)
        self._scaling_factor = kwargs.get('scaling_factor', 1)

        if module is not None:
            self._get_signals()

        self._get_holdings()

        # complete holdings and signals w/ missing contracts from union
        contract_ids = set(list(self._signals.keys()) + list(self._holdings.keys()))
        self._holdings = {
            **{cid: 0 for cid in contract_ids},
            **self._holdings
        }
        self._signals = {
            **{cid: 0 for cid in contract_ids},
            **self._signals
        }
        self._contracts = {cid: Contract(cid, self._ib_gw) for cid in contract_ids}

        self._scale_signals()

        self._calculate_target_positions()

        self._calculate_trades()

    @property
    def contracts(self):
        return self._contracts

    @property
    def fx(self):
        return self._fx

    @property
    def holdings(self):
        return self._holdings

    @property
    def name(self):
        return self._name

    @property
    def scaled_signals(self):
        return self._scaled_signals

    @property
    def signals(self):
        return self._signals

    @property
    def target_positions(self):
        return self._target_positions

    @property
    def trades(self):
        return self._trades

    def _calculate_target_positions(self):
        """
        Converts signals into target positions (number of contracts).
        """

        if self._base_currency is not None and self._exposure is not None and self._net_liquidation is not None:
            self._get_currencies(self._base_currency)
            self._target_positions = {
                k: round(self._exposure * v * self._net_liquidation
                         / (self._contracts[k].tickers.close
                            * int(self._contracts[k].contract.multiplier)
                            * self._fx[self._contracts[k].contract.currency])) if v else 0
                for k, v in self._scaled_signals.items()
            }
        else:
            # TODO: review
            self._target_positions = {k: 0 for k in self._scaled_signals.keys()}

    def _calculate_trades(self):
        """
        Converts target positions into trades (subract current holdings)
        """

        self._trades = {
            k: v - self._holdings[k]
            for k, v in self._target_positions.items()
            if v - self._holdings[k]
        }

    def _get_currencies(self, base_currency):
        """
        Gets the FX rates for all involved contracts.

        :param base_currency: base currency of IB account in ISO format (str)
        """

        currencies = [c.contract.currency for c in self._contracts.values()]
        tickers = [self._ib_gw.reqTickers(Forex(c + base_currency))[0] for c in currencies]
        fx_rates = [t.midpoint() if t.midpoint() == t.midpoint() else t.close for t in tickers]
        self._fx = {
            currency: 1 if currency == base_currency else fx_rate
            for currency, fx_rate in zip(currencies, fx_rates)
        }

    def _get_holdings(self):
        """
        Gets current portfolio holdings from Firestore.
        """

        try:
            self._holdings = {
                int(k): v
                for k, v in db.collection('positions').document(self._trading_mode).collection('holdings').document(self._name).get().to_dict().items()
            }
        except AttributeError:
            # document doesn't exist
            self._holdings = {}

    def _get_signals(self):
        """
        Gets investment strategy signals from strategy module.
        """

        self._signals = self._module(self._ib_gw)

    def _scale_signals(self):
        """
        Scales strategy signals by constant factor.
        """

        self._scaled_signals = {
            k: v * self._scaling_factor
            for k, v in self._signals.items()
        }


class Trade:

    _trades = {}
    trade_log = {}

    def __init__(self, strategies=(), **kwargs):
        self._strategies = strategies
        self._ib_gw = kwargs['ib_gw']
        self._trading_mode = kwargs['trading_mode']

    @property
    def trades(self):
        return self._trades

    def consolidate_trades(self):
        """
        Consolidates the trades of all strategies (sum of quantities, grouped by
        contract), remembering which strategy ('source') wants to trade what so
        that we have proper accounting.
        """

        assert len(self._strategies), 'No strategies to consolidate'

        self._trades = {}
        for strategy in self._strategies:
            for k, v in strategy.trades.items():
                if k not in self._trades:
                    self._trades[k] = {}
                self._trades[k]['source'] = {strategy.name: v}
                self._trades[k]['contract'] = strategy.contracts[k]
                if 'quantity' in self._trades[k]:
                    self._trades[k]['quantity'] += v
                else:
                    self._trades[k]['quantity'] = v

        self._trades = {k: v for k, v in self._trades.items() if v['quantity'] != 0}

    def _log_trades(self, orders):
        """
        Logs orders in Firestore under holdings if already filled or openOrders if not.

        :param orders: orders that were placed (list of ib_insync Trade objects)
        :return: activity log entry (dict)
        """

        # query config
        config = db.collection('config').document(self._trading_mode).get().to_dict()

        for o in orders:
            contract_id = o.contract.conId
            for strategy in self._trades[contract_id]['source'].keys():
                if o.orderStatus.status in OrderStatus.ActiveStates:
                    # add to openOrders collection if not done yet
                    db.collection('positions').document(self._trading_mode).collection('openOrders').document(str(o.order.permId)).create({
                        'acctNumber': config['account'],
                        'contractId': contract_id,
                        'quantity': self._trades[contract_id]['source'][strategy],
                        'strategy': strategy,
                        'timestamp': datetime.now(timezone.utc)
                    })
                    logging.info('Added {} to /positions/{}/openOrders/{}'.format(contract_id, self._trading_mode, o.order.permId))
                elif o.orderStatus.status in OrderStatus.DoneStates:
                    # update holdings collection if filled
                    doc_ref = db.collection('positions').document(self._trading_mode).collection('holdings').document(strategy)
                    portfolio = doc_ref.get().to_dict()
                    increment = (1 if o.order.action == 'BUY' else -1) * int(o.orderStatus.filled)
                    # firestore.transforms.Increment(increment)
                    doc_ref.update({
                        str(contract_id): portfolio[str(contract_id)] + increment or firestore.DELETE_FIELD
                    })
                    logging.info('Updated {} in /positions/{}/holdings/{}'.format(contract_id, self._trading_mode, strategy))

        # return activity log entry
        return {
            o.contract.localSymbol: {
                'order': {
                    k: v
                    for k, v in o.order.nonDefaults().items()
                    if isinstance(v, (int, float, str))
                },
                'orderStatus': {
                    k: v
                    for k, v in o.orderStatus.nonDefaults().items()
                    if isinstance(v, (int, float, str))
                },
                'isActive': o.isActive()
            } for o in orders
        }

    def place_orders(self, order_type=MarketOrder, order_params={}, order_properties={}):
        """
        Places orders in the market.

        :param order_type: IB order type (ib_insync Order object)
        :param order_params: arguments for IB order (dict)
        :param order_properties: additional order parameters (dict)
        :return: activity log entry (dict)
        """

        # place orders
        perm_ids = []
        for k, v in self._trades.items():
            order = self._ib_gw.placeOrder(v['contract'].contract,
                                           order_type(action='BUY' if v['quantity'] > 0 else 'SELL',
                                                      totalQuantity=abs(v['quantity']),
                                                      **order_params).update(**{'tif': 'GTC', **order_properties}))
            # give the IB Gateway a couple of seconds to digest orders and to raise possible errors
            self._ib_gw.sleep(2)
            perm_ids.append(order.order.permId)
        logging.debug(perm_ids)

        self.trade_log = self._log_trades([t for t in self._ib_gw.trades() if t.order.permId in perm_ids])

        return self.trade_log
