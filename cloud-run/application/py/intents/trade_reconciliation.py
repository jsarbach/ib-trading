from datetime import datetime, timezone
from google.cloud import firestore_v1 as firestore
from ib_insync import Contract, OrderStatus
import logging
from os import environ


# get environment variables
K_REVISION = environ.get('K_REVISION', default='localhost')

# instantiate Firestore Client
db = firestore.Client()


def main(ib_gw, trading_mode):
    # query config
    config = db.collection('config').document(trading_mode).get().to_dict()

    # activity log for Firestore
    activity_log = {
        'agent': K_REVISION,
        'config': config,
        'exception': None,
        'tradingMode': trading_mode
    }

    main_e = None
    try:
        # reconcile trades
        open_orders = []
        for t in ib_gw.trades():
            open_orders.append(t.orderStatus.nonDefaults())
            order_doc = db.collection('positions').document(trading_mode).collection('openOrders').document(str(t.order.permId))
            strategy = order_doc.get().to_dict()['strategy']
            holding_doc = db.collection('positions').document(trading_mode).collection('holdings').document(strategy).get().to_dict()
            position = holding_doc.get(str(t.contract.conId), 0) if holding_doc is not None else 0
            if t.orderStatus.status in OrderStatus.DoneStates:
                with db.transaction() as tx:
                    tx.update(holding_doc,
                              {str(t.contract.conId): position + t.orderStatus.filled or firestore.DELETE_FIELD})
                    tx.delete(order_doc)
        activity_log['openOrders'] = open_orders

        # double-check with IB portfolio
        ib_portfolio = ib_gw.portfolio()
        portfolio = {item.contract.conId: item.position for item in ib_portfolio}
        activity_log['portfolio'] = {item.contract.localSymbol: item.position for item in ib_portfolio}
        holdings = [doc.to_dict()
                    for doc in db.collection('positions').document(trading_mode).collection('holdings').stream()]
        holdings_consolidated = {}
        for h in holdings:
            for k, v in h.items():
                k = int(k)
                if k in holdings_consolidated:
                    holdings_consolidated[k] += v
                else:
                    holdings_consolidated[k] = v
        activity_log['consolidatedHoldings'] = {
            ib_gw.reqContractDetails(Contract(conId=k))[0].contract.localSymbol: v
            for k, v in holdings_consolidated.items()
        }

        assert portfolio == holdings_consolidated, 'Holdings in Firestore do not match the ones in IB portfolio!'

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
        print(main(ib, 'paper'))
    finally:
        ib.disconnect()
