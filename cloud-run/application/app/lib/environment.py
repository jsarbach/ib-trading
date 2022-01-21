from ib_insync import util
import logging
from os import environ

from lib.gcp import GcpModule
from lib.ibgw import IBGW


class Environment:
    """Singleton class"""

    class __Implementation(GcpModule):

        ACCOUNT_VALUE_TIMEOUT = 60
        ENV_VARS = ['K_REVISION', 'PROJECT_ID']
        SECRET_RESOURCE = 'projects/{}/secrets/{}/versions/latest'

        def __init__(self, trading_mode, ibc_config):
            self._env = {k: v for k, v in environ.items() if k in self.ENV_VARS}
            self._trading_mode = trading_mode
            # get secrets and update config
            config = {
                **ibc_config,
                'tradingMode': self._trading_mode,
                **self.get_secret(self.SECRET_RESOURCE.format(self._env['PROJECT_ID'], self._trading_mode))
            }
            self._logging.debug({**config, 'password': 'xxx'})

            # query config
            self._config = {
                **self._db.document('config/common').get().to_dict(),
                **self._db.document(f'config/{self._trading_mode}').get().to_dict()
            }

            # instantiate IB Gateway
            self._ibgw = IBGW(config)
            # set IB logging level
            util.logToConsole(level=logging.ERROR)

        @property
        def config(self):
            return self._config

        @property
        def env(self):
            return self._env

        @property
        def ibgw(self):
            return self._ibgw

        @property
        def logging(self):
            return self._logging

        @property
        def trading_mode(self):
            return self._trading_mode

        def get_account_values(self, account, rows=('NetLiquidation', 'CashBalance', 'MaintMarginReq')):
            """
            Requests account data from IB.

            :param account: account identifier (str)
            :param rows: rows to return (list)
            :return: account data (dict)
            """
            account_summary = {}
            account_value = []
            timeout = self.ACCOUNT_VALUE_TIMEOUT
            while not len(account_value) and timeout:
                # needs several attempts sometimes, so let's retry
                self._ibgw.sleep(1)
                account_value = self._ibgw.accountValues(account)
                timeout -= 1
            if len(account_value):
                # filter rows and build dict
                account_values = util.df(account_value).set_index(['tag', 'currency']).loc[list(rows), 'value']
                for (k, c), v in account_values.items():
                    if c != 'BASE':
                        if k in account_summary:
                            account_summary[k][c] = float(v)
                        else:
                            account_summary[k] = {c: float(v)}

            return account_summary

    __instance = None

    def __init__(self, trading_mode='paper', ibc_config=None):
        if Environment.__instance is None:
            Environment.__instance = self.__Implementation(trading_mode, ibc_config or {})
            # store instance reference as the only member in the handle
            self.__dict__['_Environment__instance'] = Environment.__instance

    def __getattr__(self, attr):
        """ Delegate access to implementation """
        return getattr(self.__instance, attr)

    def __setattr__(self, attr, value):
        """ Delegate access to implementation """
        return setattr(self.__instance, attr, value)

    def destroy(self):
        Environment.__instance = None
        self.__dict__.pop('_Environment__instance', None)
