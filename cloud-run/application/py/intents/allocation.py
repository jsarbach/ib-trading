from datetime import datetime, timezone
from google.cloud import firestore_v1 as firestore
from ib_insync import MarketOrder
from importlib import import_module
import json
import logging
from os import environ

from lib.account import get_account_values
from lib.trading import Strategy, Trade


# get environment variables
K_REVISION = environ.get('K_REVISION', default='localhost')
ORDER_PROPERTIES = environ.get('ORDER_PROPERTIES', default='{}')
STRATEGIES = environ.get('STRATEGIES')

assert STRATEGIES is not None, 'STRATEGIES not set'
strategy_modules = {s: import_module('strategies.' + s) for s in STRATEGIES.split(',')}

# instantiate Firestore Client
db = firestore.Client()


def main(ib_gw, trading_mode, **kwargs):
    # query config
    config = db.collection('config').document(trading_mode).get().to_dict()

    # parse dry run flag from request body
    dry_run = kwargs.get('dryRun', False) if kwargs is not None else False

    # activity log for Firestore
    activity_log = {
        'agent': K_REVISION,
        'config': config,
        'dryRun': dry_run,
        'environment': {
            'ORDER_PROPERTIES': ORDER_PROPERTIES,
            'STRATEGIES': STRATEGIES
        },
        'exception': None,
        'tradingMode': trading_mode
    }

    main_e = None
    try:
        order_properties = json.loads(ORDER_PROPERTIES)

        logging.info('Running allocator for {}...'.format(list(strategy_modules.keys())))

        # get base currency and net liquidation value
        account_values = get_account_values(ib_gw, config['account'])
        base_currency, net_liquidation = list(account_values['NetLiquidation'].items())[0]
        activity_log['netLiquidation'] = net_liquidation

        allocation_params = {
            'base_currency': base_currency,
            'exposure': config['exposure']['overall'],
            'ib_gw': ib_gw,
            'net_liquidation': net_liquidation,
            'trading_mode': trading_mode
        }
        # get signals for all strategies
        strategies = [Strategy(k, v.main, **{**allocation_params, 'scaling_factor': config['exposure']['strategies'][k]})
                      for k, v in strategy_modules.items()]
        # log activity
        activity_log['signals'] = {s.name: {s.contracts[k].local_symbol: v for k, v in s.signals.items()} for s in strategies}
        activity_log['scaledSignals'] = {s.name: {s.contracts[k].local_symbol: v for k, v in s.scaled_signals.items()} for s in strategies}
        activity_log['holdings'] = {s.name: {s.contracts[k].local_symbol: v for k, v in s.holdings.items()} for s in strategies}
        activity_log['targetPositions'] = {s.name: {s.contracts[k].local_symbol: v for k, v in s.target_positions.items()} for s in strategies}
        activity_log['fx'] = {k: v for s in strategies for k, v in s.fx.items()}
        activity_log['contractIds'] = {v.contract.localSymbol: k for s in strategies for k, v in s.contracts.items()}

        # consolidate trades over strategies, remembering to which strategies a trade belongs
        trades = Trade(strategies, **allocation_params)
        trades.consolidate_trades()
        activity_log['consolidatedTrades'] = {v['contract'].local_symbol: v['quantity'] for v in trades.trades.values()}
        logging.info('Consolidated trades: {}'.format(activity_log['consolidatedTrades']))

        if not dry_run:
            # place orders
            activity_log['orders'] = trades.place_orders(MarketOrder, order_properties=order_properties)
            logging.info('Orders placed: {}'.format(activity_log['orders']))

    except Exception as e:
        logging.error(e)
        activity_log['exception'] = str(e)
        main_e = e

    finally:
        try:
            activity_log['timestamp'] = datetime.now(timezone.utc)
            db.collection('activity').document().set(activity_log)
        except Exception as e:
            logging.error(e)
            logging.info(activity_log)

    if main_e is not None:
        # raise main exception so that main.py returns 500 response
        raise main_e

    logging.info('Done.')
    return {**activity_log, 'timestamp': activity_log['timestamp'].isoformat()}


if __name__ == '__main__':
    from ib_insync import IB
    ib = IB()
    ib.connect('localhost', 4001, 1)
    try:
        print(main(ib, 'paper', dryRun=True))
    finally:
        ib.disconnect()
