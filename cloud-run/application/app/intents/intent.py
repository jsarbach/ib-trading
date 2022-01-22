import json
from datetime import datetime
from hashlib import md5

from lib.environment import Environment


class Intent:

    _activity_log = {}

    def __init__(self, **kwargs):
        self._env = Environment()

        # create signature hash
        hashstr = self._env.env['K_REVISION'] + self.__class__.__name__ + json.dumps(kwargs, sort_keys=True)
        self._signature = md5(hashstr.encode()).hexdigest()

        # activity log for Firestore
        self._activity_log = {
            'agent': self._env.env['K_REVISION'],
            'config': self._env.config,
            'exception': None,
            'intent': self.__class__.__name__,
            'signature': self._signature,
            'tradingMode': self._env.trading_mode
        }

    def _core(self):
        return {'currentTime': self._env.ibgw.reqCurrentTime().isoformat()}

    def _log_activity(self):
        if len(self._activity_log):
            try:
                self._activity_log.update(timestamp=datetime.utcnow())
                self._env.db.collection('activity').document().set(self._activity_log)
            except Exception as e:
                self._env.logging.error(e)
                self._env.logging.info(self._activity_log)

    def run(self):
        retval = {}
        exc = None
        try:
            self._env.ibgw.start_and_connect()
            # https://interactivebrokers.github.io/tws-api/market_data_type.html
            self._env.ibgw.reqMarketDataType(self._env.config['marketDataType'])
            retval = self._core()
        except Exception as e:
            error_str = f'{e.__class__.__name__}: {e}'
            self._env.logging.error(error_str)
            self._activity_log.update(exception=error_str)
            exc = e
        finally:
            self._env.ibgw.stop_and_terminate()
            if self._env.env['K_REVISION'] != 'localhost':
                self._log_activity()
            if exc is not None:
                # raise main exception so that main.py returns 500 response
                raise exc
            self._env.logging.info('Done.')
            return retval or {**self._activity_log, 'timestamp': self._activity_log['timestamp'].isoformat()}
