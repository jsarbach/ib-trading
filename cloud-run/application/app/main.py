from datetime import datetime
import falcon
import json
import logging
from os import environ, listdir
import re

from intents.allocation import Allocation
from intents.cash_balancer import CashBalancer
from intents.close_all import CloseAll
from intents.collect_market_data import CollectMarketData
from intents.intent import Intent
from intents.summary import Summary
from intents.trade_reconciliation import TradeReconciliation
from lib.environment import Environment

# get environment variables
TRADING_MODE = environ.get('TRADING_MODE', 'paper')
TWS_INSTALL_LOG = environ.get('TWS_INSTALL_LOG')

if TRADING_MODE not in ['live', 'paper']:
    raise ValueError('Unknown trading mode')

# set constants
INTENTS = {
    'allocation': Allocation,
    'cash-balancer': CashBalancer,
    'close-all': CloseAll,
    'collect-market-data': CollectMarketData,
    'summary': Summary,
    'trade-reconciliation': TradeReconciliation
}

# build IBC config from environment variables
env = {
    key: environ.get(key) for key in
    ['ibcIni', 'ibcPath', 'javaPath', 'twsPath', 'twsSettingsPath']
}
env['javaPath'] += f"/{listdir(env['javaPath'])[0]}/bin"
with open(TWS_INSTALL_LOG, 'r') as fp:
    install_log = fp.read()
ibc_config = {
    'gateway': True,
    'twsVersion': re.search('IB Gateway ([0-9]{3})', install_log).group(1),
    **env
}
Environment(TRADING_MODE, ibc_config)


class Main:
    """
    Main route.
    """

    def on_get(self, request, response, intent):
        self._on_request(request, response, intent)

    def on_post(self, request, response, intent):
        body = json.load(request.stream) if request.content_length else {}
        self._on_request(request, response, intent, **body)

    @staticmethod
    def _on_request(_, response, intent, **kwargs):
        """
        Handles HTTP request.

        :param _: Falcon request (not used)
        :param response: Falcon response
        :param intent: intent (str)
        :param kwargs: HTTP request body (dict)
        """

        try:
            if intent is None or intent not in INTENTS.keys():
                logging.warning('Unknown intent')
                intent_instance = Intent()
            else:
                intent_instance = INTENTS[intent](**kwargs)
            result = intent_instance.run()
            response.status = falcon.HTTP_200
        except Exception as e:
            error_str = f'{e.__class__.__name__}: {e}'
            result = {'error': error_str}
            response.status = falcon.HTTP_500

        result['utcTimestamp'] = datetime.utcnow().isoformat()
        response.content_type = falcon.MEDIA_JSON
        response.text = json.dumps(result) + '\n'


# instantiante Falcon App and define route for intent
app = falcon.App()
app.add_route('/{intent}', Main())
