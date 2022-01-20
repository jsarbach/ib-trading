from random import randint

from lib.trading import Future
from strategies.strategy import Strategy


class Dummy(Strategy):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _get_signals(self):
        allocation = {
            self._instruments['mnq'][0].contract.conId: randint(-1, 1)
        }
        self._env.logging.debug(f'Allocation: {allocation}')
        self._signals = allocation
        # register allocation contracts so that they don't have to be created again
        self._register_contracts(self._instruments['mnq'][0])

    def _setup(self):
        self._instruments = {
            'mnq': Future.get_contract_series(1, 'MNQ', rollover_days_before_expiry=2)
        }


if __name__ == '__main__':
    from lib.environment import Environment

    env = Environment()
    env.ibgw.connect(port=4001)
    env.ibgw.reqMarketDataType(2)
    try:
        Dummy(base_currency='CHF', exposure=1, net_liquidation=100000)
    except Exception as e:
        raise e
    finally:
        env.ibgw.disconnect()
