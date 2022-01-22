from datetime import datetime, timedelta

import dateparser
from ib_insync import MarketOrder, TagValue

from intents.intent import Intent
from lib.trading import Trade
from strategies import STRATEGIES


class Allocation(Intent):

    _dry_run = False
    _order_properties = {}
    _strategies = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._dry_run = kwargs.get('dryRun', self._dry_run) if kwargs is not None else self._dry_run
        self._order_properties = kwargs.get('orderProperties', self._order_properties) if kwargs is not None else self._order_properties
        strategies = kwargs.get('strategies', [])
        if any([s not in STRATEGIES.keys() for s in strategies]):
            raise KeyError(f"Unknown strategies: {','.join([s for s in strategies if s not in STRATEGIES.keys()])}")
        self._strategies = {s: STRATEGIES[s] for s in strategies}
        self._activity_log.update(dryRun=self._dry_run, orderProperties=self._order_properties, strategies=strategies)

    def _core(self):
        if (overall_exposure := self._env.config['exposure']['overall']) == 0:
            self._env.logging.info('Aborting allocator as overall exposure is 0')
            return

        if self._env.config['retryCheckMinutes']:
            # check if agent has created an order before (prevent trade repetition)
            query = self._env.db.collection('activity') \
                .where('tradingMode', '==', self._env.trading_mode) \
                .where('signature', '==', self._signature) \
                .where('timestamp', '>', datetime.utcnow() - timedelta(minutes=self._env.config['retryCheckMinutes'])) \
                .order_by('timestamp') \
                .order_by('orders')
            if len(list(query.get())):
                self._env.logging.warning('Agent has run before.')
                return

        self._env.logging.info(f"Running allocator for {', '.join(self._strategies.keys())}...")

        # get base currency and net liquidation value
        account_values = self._env.get_account_values(self._env.config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        self._activity_log.update(netLiquidation=net_liquidation)

        # get signals for all strategies
        strategies = []
        for k, v in self._strategies.items():
            if strategy_exposure := self._env.config['exposure']['strategies'].get(k, 0):
                self._env.logging.info(f'Getting signals for {k}...')
                try:
                    strategies.append(v(base_currency=base_currency, exposure=net_liquidation * overall_exposure * strategy_exposure))
                except Exception as exc:
                    self._env.logging.error(f'{exc.__class__.__name__} running strategy {k}: {exc}')
        # log activity
        self._activity_log.update(**{
            'signals': {s.id: {s.contracts[k].local_symbol: v for k, v in s.signals.items()} for s in strategies},
            'holdings': {s.id: {s.contracts[k].local_symbol: v for k, v in s.holdings.items()} for s in strategies},
            'targetPositions': {s.id: {s.contracts[k].local_symbol: v for k, v in s.target_positions.items()} for s in strategies},
            'fx': {k: v for s in strategies for k, v in s.fx.items()},
            'contractIds': {v.contract.localSymbol: k for s in strategies for k, v in s.contracts.items()}
        })

        # consolidate trades over strategies, remembering to which strategies a trade belongs
        trades = Trade(strategies)
        trades.consolidate_trades()
        self._activity_log.update(consolidatedTrades={v['contract'].local_symbol: v['quantity'] for v in trades.trades.values()})
        self._env.logging.info(f"Consolidated trades: {self._activity_log['consolidatedTrades']}")

        if not self._dry_run:
            # parse goodAfterTime
            if 'goodAfterTime' in self._order_properties:
                self._order_properties.update(goodAfterTime=dateparser.parse(self._order_properties['goodAfterTime']).strftime('%Y%m%d %H:%M:%S %Z'))

            # place orders
            orders = trades.place_orders(MarketOrder,
                                         order_params={
                                             'algoStrategy': 'Adaptive',
                                             'algoParams': [TagValue('adaptivePriority', self._env.config['adaptivePriority'])]
                                         },
                                         order_properties={**self._order_properties, 'tif': 'DAY'})
            self._activity_log.update(orders=orders)
            self._env.logging.info(f"Orders placed: {self._activity_log['orders']}")


if __name__ == '__main__':
    from lib.environment import Environment

    env = Environment()
    env.ibgw.connect(port=4001)
    env.ibgw.reqMarketDataType(2)
    try:
        allocation = Allocation(strategies=['vxcurve', 'vxarma'], dryRun=True)
        allocation._core()
        print(allocation._activity_log)
    except Exception as e:
        raise e
    finally:
        env.ibgw.disconnect()
