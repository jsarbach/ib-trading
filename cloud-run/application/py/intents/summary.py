from google.cloud import firestore_v1 as firestore
import logging
from os import environ

from lib.account import get_account_values


local = environ.get('K_REVISION') is None


# instantiate Firestore Client
db = firestore.Client()


def main(ib_gw, trading_mode):
    # query config
    config = db.collection('config').document(trading_mode).get().to_dict()

    try:
        if local:
            print(ib_gw.orders())
            print(ib_gw.openOrders())
            print(ib_gw.trades())
            print(ib_gw.openTrades())
            print(ib_gw.fills())
            print(ib_gw.executions())

        trades = ib_gw.openTrades()
        trades_grouped = {trade.contract.localSymbol: [] for trade in trades}
        for trade in trades:
            trades_grouped[trade.contract.localSymbol].append({
                'isActive': trade.isActive(),
                'isDone': trade.isDone(),
                'orderStatus': trade.orderStatus.status,
                'whyHeld': trade.orderStatus.whyHeld,
                'action': trade.order.action,
                'totalQuantity': int(trade.order.totalQuantity),
                'orderType': trade.order.orderType,
                'limitPrice': trade.order.lmtPrice,
                'timeInForce': trade.order.tif,
                'goodAfterTime': trade.order.goodAfterTime,
                'goodTillDate': trade.order.goodTillDate
            })
        fills = ib_gw.fills()
        fills_grouped = {fill.contract.localSymbol: [] for fill in fills}
        for fill in fills:
            fills_grouped[fill.contract.localSymbol].append({
                'side': fill.execution.side,
                'shares': int(fill.execution.shares),
                'price': fill.execution.price,
                'cumQuantity': int(fill.execution.cumQty),
                'avgPrice': fill.execution.avgPrice,
                'time': fill.execution.time.isoformat(),
                'commission': round(fill.commissionReport.commission, 2),
                'rPnL': round(fill.commissionReport.realizedPNL, 2)
            })

        response = {
            'accountSummary': get_account_values(ib_gw, config['account']),
            'portfolio': {
                portfolio_item.contract.localSymbol: {
                    'position': int(portfolio_item.position),
                    'exposure': round(portfolio_item.marketValue, 2),
                    'uPnL': round(portfolio_item.unrealizedPNL, 2)
                } for portfolio_item in ib_gw.portfolio()
            },
            'openTrades': trades_grouped,
            'fills': fills_grouped
        }
    except Exception as e:
        logging.error(e)
        raise e

    logging.debug(response)
    return response


if __name__ == '__main__':
    from ib_insync import IB
    ib = IB()
    ib.connect('localhost', 4001, 1)
    try:
        print(main(ib, 'paper'))
    finally:
        ib.disconnect()
