from intents.intent import Intent


class Summary(Intent):

    def __init__(self):
        super().__init__()
        self._activity_log = {}  # don't log summary requests

    def _core(self):
        return {
            'accountSummary': self._env.get_account_values(self._env.config['account']),
            'portfolio': self._get_positions(),
            'openTrades': self._get_trades(),
            'fills': self._get_fills()
        }

    def _get_fills(self):
        fills = self._env.ibgw.fills()
        return {
            fill.contract.localSymbol: [{
                'side': fill.execution.side,
                'shares': int(fill.execution.shares),
                'price': fill.execution.price,
                'cumQuantity': int(fill.execution.cumQty),
                'avgPrice': fill.execution.avgPrice,
                'time': fill.execution.time.isoformat(),
                'commission': round(fill.commissionReport.commission, 2),
                'rPnL': round(fill.commissionReport.realizedPNL, 2)
            }] for fill in fills
        }

    def _get_positions(self):
        return {
            portfolio_item.contract.localSymbol: {
                'position': int(portfolio_item.position),
                'exposure': round(portfolio_item.marketValue, 2),
                'uPnL': round(portfolio_item.unrealizedPNL, 2)
            } for portfolio_item in self._env.ibgw.portfolio()
        }

    def _get_trades(self):
        trades = self._env.ibgw.openTrades()
        return {
            trade.contract.localSymbol: [{
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
            }] for trade in trades
        }


if __name__ == '__main__':
    from lib.environment import Environment

    env = Environment()
    env.ibgw.connect(port=4001)
    try:
        summary = Summary()
        print(summary._core())
        print(summary._activity_log)
    except Exception as e:
        raise e
    finally:
        env.ibgw.disconnect()
