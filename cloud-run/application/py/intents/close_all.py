from datetime import datetime, timezone
from google.cloud import firestore_v1 as firestore
from ib_insync import MarketOrder
import json
import logging
from os import environ

from lib.trading import Strategy, Trade


# get environment variables
LMT_PRICE_DISTANCE = environ.get('LMT_PRICE_DISTANCE', default=0.1)
K_REVISION = environ.get('K_REVISION', default='localhost')
ORDER_PROPERTIES = environ.get('ORDER_PROPERTIES', default='{}')

# instantiate Firestore Client
db = firestore.Client()


def main(ib_gw, trading_mode, **kwargs):
    # query config
    config = db.collection('config').document(trading_mode).get().to_dict()

    # parse dry run flag from request body
    dry_run = kwargs['dryRun'] if kwargs is not None and 'dryRun' in kwargs else False

    # activity log for Firestore
    activity_log = {
        'agent': K_REVISION,
        'config': config,
        'dryRun': dry_run,
        'environment': {
            'LMT_PRICE_DISTANCE': LMT_PRICE_DISTANCE,
            'ORDER_PROPERTIES': ORDER_PROPERTIES
        },
        'exception': None,
        'tradingMode': trading_mode
    }

    main_e = None
    try:
        order_properties = json.loads(ORDER_PROPERTIES)

        logging.info('Cancelling open orders...')
        if not dry_run:
            for o in ib_gw.orders():
                ib_gw.cancelOrder(o)
                db.collection('positions').document(trading_mode).collection('openOrders').document(str(o.permId)).delete()
                # TODO: log

        logging.info('Closing all positions...')
        allocation_params = {
            'ib_gw': ib_gw,
            'trading_mode': trading_mode
        }
        strategies = [doc.id
                      for doc in db.collection('positions').document(trading_mode).collection('holdings').stream()]
        strategies = [Strategy(s, **allocation_params) for s in strategies]
        activity_log['holdings'] = {s.name: {s.contracts[k].local_symbol: v for k, v in s.holdings.items()} for s in strategies}
        activity_log['contractIds'] = {v.contract.localSymbol: k for s in strategies for k, v in s.contracts.items()}
        activity_log['trades'] = {s.name: {s.contracts[k].local_symbol: v for k, v in s.trades.items()} for s in strategies}
        logging.info('Trades: {}'.format(activity_log['trades']))

        trades = Trade(strategies, **allocation_params)
        trades.consolidate_trades()
        activity_log['consolidatedTrades'] = {v['contract'].local_symbol: v['quantity'] for v in trades.trades.values()}
        logging.info('Consolidated trades: {}'.format(activity_log['consolidatedTrades']))
        # double-check w/ ib_gw.potfolio()
        portfolio = {item.contract.conId: item.position for item in ib_gw.portfolio()}
        if {k: -v for k, v in portfolio.items()} != {k: v['quantity'] for k, v in trades.trades.items()}:
            logging.warning('Consolidated trade and IB portfolio don\'t match - portfolio: {}'.format(portfolio))

        if not dry_run:
            activity_log['orders'] = trades.place_orders(MarketOrder,
                                                         order_properties=order_properties)
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
