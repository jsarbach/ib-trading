import unittest
from unittest.mock import call, MagicMock, patch

from intents.trade_reconciliation import DELETE_FIELD
from intents.trade_reconciliation import TradeReconciliation


class TestTradeReconciliation(unittest.TestCase):

    ENV = {
        'K_REVISION': 'k_revision',
    }

    @patch('intents.intent.Environment', return_value=MagicMock(env=ENV))
    def setUp(self, *_):
        self.test_obj = TradeReconciliation()

    def test_core(self):
        with patch.object(self.test_obj, '_env',
                          db=MagicMock(document=MagicMock(),
                                       collection=MagicMock(),
                                       transaction=MagicMock(return_value=MagicMock(set=MagicMock(),
                                                                                    update=MagicMock(),
                                                                                    delete=MagicMock()))),
                          ibgw=MagicMock(trades=MagicMock(return_value=[MagicMock(contract=MagicMock(nonDefaults=MagicMock(return_value=f'c{i}')),
                                                                                  orderStatus=MagicMock(
                                                                                      nonDefaults=MagicMock(return_value=f'os{i}')), log=f'log{i}')
                                                                        for i in range(2)]),
                                         fills=MagicMock(return_value=[MagicMock(contract=MagicMock(conId=f'c{i}',
                                                                                                    nonDefaults=MagicMock(return_value=f'c{i}')),
                                                                                 execution=MagicMock(permId=f'p{i}',
                                                                                                     orderId=f'o{i}',
                                                                                                     side='SLD',
                                                                                                     cumQty=(i + 1) * 100,
                                                                                                     nonDefaults=MagicMock(return_value=f'e{i}')))
                                                                       for i in range(2)]),
                                         portfolio=MagicMock(return_value=[MagicMock(contract=MagicMock(conId=i), position=(i + 1) * 200) for i in range(2)]),
                                         reqContractDetails=MagicMock(return_value=MagicMock(contract=MagicMock(localSymbol='abc'))))) as env:
            document_side_effect = [MagicMock(get=MagicMock(return_value=MagicMock(to_dict=MagicMock(return_value={'c0': 100, 'c1': -200}), exists=True))),
                                    MagicMock(get=MagicMock(return_value=MagicMock(to_dict=MagicMock(return_value={'c0': 100, 'c1': -200}), exists=False)))]
            env.db.document.side_effect = document_side_effect
            collection_side_effect = [MagicMock(where=MagicMock(return_value=MagicMock(get=MagicMock(return_value=(MagicMock(reference='order_doc', to_dict=MagicMock(return_value={'source': {'s0': 100, 's1': -200}})), ))))) for _ in range(2)] +\
                                     [MagicMock(list_documents=MagicMock(return_value=[MagicMock(get=MagicMock(return_value=MagicMock(to_dict=MagicMock(return_value={i: (i + 1) * 100 for i in range(2)})))) for _ in range(2)]))]
            env.db.collection.side_effect = collection_side_effect

            self.test_obj._core()
            try:
                env.db.collection.assert_has_calls([call(f'positions/{self.test_obj._env.trading_mode}/openOrders'),
                                                    call(f'positions/{self.test_obj._env.trading_mode}/openOrders'),
                                                    call(f'positions/{self.test_obj._env.trading_mode}/holdings')])
                for i, c in enumerate(collection_side_effect[:2]):
                    c.where.assert_called_with('permId', '==', env.ibgw.fills.return_value[i].execution.permId)
                env.db.document.assert_has_calls([call(f'positions/{self.test_obj._env.trading_mode}/holdings/s{i}') for i in range(2)])
                env.db.transaction.return_value.__enter__.return_value.update.assert_called_once_with(document_side_effect[0], {'c0': 200 or DELETE_FIELD})
                env.db.transaction.return_value.__enter__.return_value.set.assert_called_once_with(document_side_effect[1], {'c0': -100 or DELETE_FIELD})
                env.db.transaction.return_value.__enter__.return_value.delete.assert_has_calls([call('order_doc') for _ in range(2)])
            except AssertionError:
                self.fail()


if __name__ == '__main__':
    unittest.main()
