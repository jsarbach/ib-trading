from google.cloud.firestore_v1 import DELETE_FIELD
from ib_insync import Contract, util

from intents.intent import Intent


class TradeReconciliation(Intent):

    def __init__(self):
        super().__init__()

    def _core(self):
        self._env.logging.info('Running trade reconciliation...')

        # log open orders/trades
        self._activity_log.update(openOrders=[
            {
                'contract': t.contract.nonDefaults(),
                'orderStatus': t.orderStatus.nonDefaults(),
                'log': util.tree(t.log)
            } for t in self._env.ibgw.trades()
        ])

        # reconcile trades
        fills = []
        for fill in self._env.ibgw.fills():
            # logging.debug(util.tree(fill.nonDefaults()))
            contract_id = fill.contract.conId
            query = self._env.db.collection(f'positions/{self._env.trading_mode}/openOrders')\
                .where('permId', '==', fill.execution.permId)
            res = list(query.get())
            if len(res):
                order_doc = res[0].reference
                order = res[0].to_dict()
            else:
                # retry with orderId and contractId
                query = self._env.db.collection(f'positions/{self._env.trading_mode}/openOrders')\
                    .where('orderId', '==', fill.execution.orderId)\
                    .where('contractId', '==', contract_id)
                res = list(query.get())
                if len(res):
                    order_doc = res[0].reference
                    order = res[0].to_dict()
                else:
                    continue

            # update holdings if fully executed
            side = 1 if fill.execution.side == 'BOT' else -1
            if len(order) and side * fill.execution.cumQty == sum(order['source'].values()):
                fills.append({
                    'contract': fill.contract.nonDefaults(),
                    'execution': util.tree(fill.execution.nonDefaults())
                })

                for strategy, quantity in order['source'].items():
                    holdings_doc = self._env.db.document(f'positions/{self._env.trading_mode}/holdings/{strategy}')
                    holdings = holdings_doc.get().to_dict() or {}
                    position = holdings.get(str(contract_id), 0)

                    with self._env.db.transaction() as tx:
                        action = tx.update if holdings_doc.get().exists else tx.set
                        action(holdings_doc, {str(contract_id): position + quantity or DELETE_FIELD})
                        tx.delete(order_doc)
        self._activity_log.update(fills=fills)
        self._env.logging.info(f'Fills: {fills}')

        # double-check with IB portfolio
        self._env.logging.info('Comparing Firestore holdings with IB portfolio...')
        ib_portfolio = self._env.ibgw.portfolio()
        portfolio = {item.contract.conId: item.position for item in ib_portfolio}
        self._activity_log.update(portfolio={item.contract.localSymbol: item.position for item in ib_portfolio})
        holdings = [doc.get().to_dict()
                    for doc in self._env.db.collection(f'positions/{self._env.trading_mode}/holdings').list_documents()]
        holdings_consolidated = {}
        for h in holdings:
            for k, v in h.items():
                k = int(k)
                if k in holdings_consolidated:
                    holdings_consolidated[k] += v
                else:
                    holdings_consolidated[k] = v
        self._activity_log.update(consolidatedHoldings={
            self._env.ibgw.reqContractDetails(Contract(conId=k))[0].contract.localSymbol: v
            for k, v in holdings_consolidated.items()
        })
        if portfolio != holdings_consolidated:
            self._env.logging.warning(f'Holdings do not match -- Firestore: {holdings_consolidated}; IB: {portfolio}')
            raise AssertionError('Holdings in Firestore do not match the ones in IB portfolio.')


if __name__ == '__main__':
    from lib.environment import Environment

    env = Environment()
    env.ibgw.connect(port=4001)
    try:
        trade_reconciliation = TradeReconciliation()
        trade_reconciliation._core()
    except Exception as e:
        raise e
    finally:
        env.ibgw.disconnect()
